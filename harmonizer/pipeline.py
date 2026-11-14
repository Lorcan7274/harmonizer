"""The cohort-level steps behind the scripts and the command line: audit a directory of EDFs, then draft rules for it."""
import csv, glob, json, os, time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from .checks import audit, pairs, unit_scale
from .edf import read_header, read_signals
from .emit import write_outputs
from .evidence import confidence, layout_evidence
from .layout import group, numbered, luna_labels
from .mapping import baseline, validate
from .scoring import RULINGS
from .targets import TARGETS, VOLTAGE

READERS = ("baseline", "model-headers", "model-signals")
AUDIT_COLS = ["id", "idx", "label", "unit", "sr", "label_type", "signal_type", "agree", "unit_status",
              "amp_uv", "cal_inverted", "ecg_pol", "ecg_artefact", "reason"]


def rec_id(path):
    return os.path.basename(path)[:-4]


def edf_paths(edf_dir):
    return sorted(glob.glob(os.path.join(edf_dir, "*.edf")))


def read_audit(prefix):
    """Audit rows per recording id, in channel order."""
    rows = defaultdict(list)
    with open(prefix + "_channels.csv") as fh:
        for r in csv.DictReader(fh):
            rows[r["id"]].append(r)
    return rows


def _audit_one(path):
    t = time.time()
    h, xs = read_signals(path)
    return rec_id(path), audit(h, xs), pairs(h, xs), time.time() - t


def audit_cohort(edf_dir, prefix, jobs=4):
    """Run the signal checks on every EDF in edf_dir; writes PREFIX_channels.csv, _features.json and _pairs.json."""
    files = edf_paths(edf_dir)
    os.makedirs(os.path.dirname(os.path.abspath(prefix)), exist_ok=True)
    t0 = time.time()
    feats, allpairs, secs = {}, {}, 0
    with ProcessPoolExecutor(jobs) as ex, open(prefix + "_channels.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, AUDIT_COLS, extrasaction="ignore")
        w.writeheader()
        for rid, rows, pr, dt in ex.map(_audit_one, files):
            secs += dt
            for r in rows:
                w.writerow(dict(r, id=rid))
            feats[rid] = [dict(label=r["label"], **r["feat"]) for r in rows]
            allpairs[rid] = pr
    with open(prefix + "_features.json", "w") as fh:
        json.dump(feats, fh)
    with open(prefix + "_pairs.json", "w") as fh:
        json.dump(allpairs, fh, indent=0)
    return dict(files=len(files), wall=time.time() - t0, cpu=secs)


KEY_STATUS = {"agree": "settled", "flat": "flat", "conflict": "unsettled", "label_unread": "unsettled", "unchecked": "unchecked"}
KEY_COLS = ["id", "idx", "label", "unit", "sr", "trace_type", "label_type", "status", "evidence", "reader_ruling"]


def answer_key(prefix, rulings_csv=None):
    """Write PREFIX_answer_key.csv from the audit, keeping rulings already there and adding any from rulings_csv.

    Returns (rows per status, number of rulings kept, rulings whose channel is not in the audit).
    """
    out = prefix + "_answer_key.csv"
    rulings = {}
    for path in (out, rulings_csv):
        if path and os.path.exists(path):
            with open(path) as fh:
                for r in csv.DictReader(fh):
                    v = (r.get("reader_ruling") or r.get("ruling") or "").strip().lower()
                    if v and v not in RULINGS:
                        raise ValueError(f"{path}: ruling {v!r} for {r['id']} channel {r['idx']} is not one of {RULINGS}")
                    if v:
                        rulings[(r["id"], str(r["idx"]))] = v
    n, kept = Counter(), 0
    with open(prefix + "_channels.csv") as src, open(out + ".part", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(KEY_COLS)
        for r in csv.DictReader(src):
            ruling = rulings.pop((r["id"], r["idx"]), "")
            kept += bool(ruling)
            n[KEY_STATUS[r["agree"]]] += 1
            w.writerow([r["id"], r["idx"], r["label"], r["unit"], r["sr"], r["signal_type"], r["label_type"],
                        KEY_STATUS[r["agree"]], r["reason"], ruling])
    os.replace(out + ".part", out)
    return dict(n), kept, sorted(rulings)


def draft(edf_dir, prefix, out_dir, reader="baseline", log=print):
    """Draft CANONICAL rules for a cohort from its audit; writes the rule file, lists, pre-script and mapping.json."""
    if reader not in READERS:
        raise ValueError(f"reader must be one of {READERS}")
    audit_rows = read_audit(prefix)
    layouts = numbered(group(edf_paths(edf_dir)))
    mappings, notes, units_ok, problems, conf_rows, pre = {}, {}, {}, [], [], []
    for lid, (_, paths) in layouts.items():
        heads = {rec_id(p): read_header(p) for p in paths}
        labs = {r: luna_labels(h) for r, h in heads.items()}
        pos = {r: {x.upper(): i for i, x in enumerate(ls)} for r, ls in labs.items()}
        first = heads[rec_id(paths[0])]
        order = labs[rec_id(paths[0])]
        ev = layout_evidence(labs, audit_rows)
        log(lid)
        if reader == "baseline":
            raw = baseline(order)
        else:
            from .model import ask, layout_prompt
            chans = []
            for i, lab in enumerate(order):
                idx = {r: pos[r][lab.upper()] for r in heads}
                chans.append(dict(label=lab, original=first["ch"][i]["label"],
                                  units=sorted({heads[r]["ch"][idx[r]]["unit"] for r in heads}),
                                  rates=sorted({heads[r]["ch"][idx[r]]["sr"] for r in heads}),
                                  trans=first["ch"][i]["trans"], prefilt=first["ch"][i]["prefilt"]))
            raw = ask(layout_prompt(lid, len(paths), chans, ev if reader == "model-signals" else None),
                      os.path.join(out_dir, "model_cache"), order)
            raw = [dict(c, target=None if c["target"] == "none" else c["target"]) for c in raw]
        mappings[lid], probs = validate(raw, order)
        problems += [f"{lid}: {p}" for p in probs]
        for m in mappings[lid]:
            if not m["target"]:
                continue
            key = m["label"].upper()
            tally = Counter()
            for r in heads:
                row = audit_rows[r][pos[r][key]]
                c = confidence(m["target"], row)
                tally[c] += 1
                conf_rows.append(dict(layout=lid, id=r, label=m["label"], target=m["target"], confidence=c,
                                      trace_type=row["signal_type"], evidence=row["reason"]))
                if m["target"] == "ECG" and row["ecg_pol"] and float(row["ecg_pol"]) < -0.5:
                    pre.append(f"% {r}: ECG beats point down in {m['label']} (unverified heuristic).   FLIP sig={m['label']}")
            units_ok[(lid, key)] = all(unit_scale(heads[r]["ch"][pos[r][key]]["unit"]) is not None for r in heads)
            if TARGETS[m["target"]] in VOLTAGE and not units_ok[(lid, key)]:
                pre.append(f"% {lid}: {m['label']} has a blank or non-voltage unit in some recordings; set it before rescaling.   SET-HEADERS sig={m['label']} unit=?")
            notes[(lid, key)] = "Evidence: " + ", ".join(f"{n} {k}" for k, n in sorted(tally.items()))

    write_outputs(out_dir, layouts, mappings, notes, units_ok, pre)
    with open(os.path.join(out_dir, "confidence.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, ["layout", "id", "label", "target", "confidence", "trace_type", "evidence"])
        w.writeheader()
        w.writerows(conf_rows)
    with open(os.path.join(out_dir, "mapping.json"), "w") as fh:
        json.dump(dict(reader=reader, layouts={k: [rec_id(p) for p in v[1]] for k, v in layouts.items()},
                       mappings=mappings, problems=problems), fh, indent=1)
    return dict(reader=reader, layouts=len(layouts), rules=sum(bool(m["target"]) for ms in mappings.values() for m in ms),
                confidence=dict(Counter(c["confidence"] for c in conf_rows)), problems=len(problems), suggestions=len(pre))
