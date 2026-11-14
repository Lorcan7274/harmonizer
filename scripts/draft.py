"""Draft CANONICAL rules for a cohort.

Usage: draft.py EDF_DIR AUDIT_PREFIX OUT_DIR [baseline|model-headers|model-signals]
Needs audit_cohort.py output at AUDIT_PREFIX. The model readers need ANTHROPIC_API_KEY.
"""
import csv, glob, json, os, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harmonizer.edf import read_header
from harmonizer.layout import group, numbered, luna_labels
from harmonizer.mapping import baseline, validate
from harmonizer.evidence import confidence, layout_evidence
from harmonizer.emit import write_outputs
from harmonizer.targets import TARGETS, VOLTAGE
from harmonizer.checks import unit_scale

READERS = ("baseline", "model-headers", "model-signals")
if len(sys.argv) < 4 or (len(sys.argv) > 4 and sys.argv[4] not in READERS):
    sys.exit(__doc__.strip())
edf_dir, prefix, out_dir = sys.argv[1:4]
reader = sys.argv[4] if len(sys.argv) > 4 else "baseline"
audit = defaultdict(list)
for r in csv.DictReader(open(prefix + "_channels.csv")):
    audit[r["id"]].append(r)
layouts = numbered(group(sorted(glob.glob(os.path.join(edf_dir, "*.edf")))))
rid = lambda p: os.path.basename(p)[:-4]

mappings, notes, units_ok, problems, conf_rows, pre = {}, {}, {}, [], [], []
for lid, (_, paths) in layouts.items():
    heads = {rid(p): read_header(p) for p in paths}
    labs = {r: luna_labels(h) for r, h in heads.items()}
    pos = {r: {x.upper(): i for i, x in enumerate(ls)} for r, ls in labs.items()}
    first = heads[rid(paths[0])]
    order = labs[rid(paths[0])]
    ev = layout_evidence(labs, audit)
    print(lid, flush=True)
    if reader == "baseline":
        raw = baseline(order)
    else:
        from harmonizer.model import ask, layout_prompt
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
            row = audit[r][pos[r][key]]
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
json.dump(dict(reader=reader, layouts={k: [rid(p) for p in v[1]] for k, v in layouts.items()},
               mappings=mappings, problems=problems), open(os.path.join(out_dir, "mapping.json"), "w"), indent=1)
n_rules = sum(bool(m["target"]) for ms in mappings.values() for m in ms)
print(f"{reader}: {len(layouts)} layouts, {n_rules} rules, confidence {dict(Counter(c['confidence'] for c in conf_rows))}, "
      f"{len(problems)} mapping problems, {len(pre)} pre-script suggestions")
