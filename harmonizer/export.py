"""Turn an audit and a drafted mapping into files other sleep tools read.

BIDS channels.tsv, MNE channel types and channel picks for automatic stagers, per recording.
Nothing is corrected: a channel whose trace disagrees with its header keeps the header's kind and carries the flag.
"""
import csv, json, os, re
from collections import Counter
from .layout import luna_labels
from .targets import TARGETS

STATUS = {"agree": "ok", "flat": "flat", "conflict": "check", "label_unread": "unread", "unchecked": "unchecked"}
BIDS_TYPE = {"eeg": "EEG", "eog": "EOG", "emg": "EMG", "emg_leg": "EMG", "ecg": "ECG", "effort": "RESP",
             "flow": "RESP", "pleth": "PPG", "temp": "TEMP"}
MNE_TYPE = {"eeg": "eeg", "eog": "eog", "emg": "emg", "emg_leg": "emg", "ecg": "ecg", "effort": "resp",
            "flow": "resp", "temp": "temperature", "spo2": "bio", "hr": "bio", "pleth": "bio"}
COLUMNS = ["id", "idx", "name", "label", "luna", "unit", "sr", "kind", "status", "label_type", "signal_type",
           "evidence", "target", "ref", "reason", "note"]
_RANK = {"ok": 0, "unchecked": 1, "check": 2, "unread": 3}


def mne_names(labels):
    """Channel names as mne.io.read_raw_edf gives them: repeated labels get -0, -1, ..."""
    seen, repeated = Counter(), {l for l, n in Counter(labels).items() if n > 1}
    out = []
    for l in labels:
        out.append(f"{l}-{seen[l]}" if l in repeated else l)
        seen[l] += 1
    return out


def _note(r):
    if r["status"] == "check":
        return f"header says {r['label_type']}, trace looks like {r['signal_type']} ({r['evidence']})"
    if r["status"] == "flat":
        return "flat trace"
    if r["status"] == "unchecked":
        return f"{r['kind']} cannot be confirmed from the trace at {r['sr']:g} Hz"
    if r["status"] == "unread":
        return f"label not understood; trace looks like {r['signal_type']}"
    return ""


def resolve(audit_rows, mapping):
    """One row per channel per recording: what the header says, what the trace shows and what the draft maps it to."""
    layout_of = {rid: lid for lid, ids in mapping["layouts"].items() for rid in ids}
    out = {}
    for rid, rows in audit_rows.items():
        labs = luna_labels({"ch": [{"label": r["label"]} for r in rows]})
        names = mne_names([r["label"] for r in rows])
        name_of = {lab.upper(): n for lab, n in zip(labs, names)}
        by = {m["label"].upper(): m for m in mapping["mappings"].get(layout_of.get(rid), [])}
        res = []
        for r, lab, name in zip(rows, labs, names):
            m = by.get(lab.upper(), {})
            target = m.get("target") or ""
            row = dict(id=rid, idx=int(r["idx"]), name=name, label=r["label"], luna=lab, unit=r["unit"],
                       sr=float(r["sr"]), kind=TARGETS[target] if target else r["label_type"], status=STATUS[r["agree"]],
                       label_type=r["label_type"], signal_type=r["signal_type"], evidence=r["reason"], target=target,
                       ref=name_of.get((m.get("ref") or "").upper(), ""), reason=m.get("reason", ""))
            row["note"] = _note(row)
            res.append(row)
        out[rid] = res
    return out


def channels_tsv(rows):
    """BIDS *_channels.tsv text for one recording. Unsettled channels get status n/a, flat ones bad."""
    lines = ["name\ttype\tunits\tsampling_frequency\tstatus\tstatus_description"]
    for r in rows:
        unit = "µV" if r["unit"].strip().lower() == "uv" else (r["unit"].strip() or "n/a")
        status = {"ok": "good", "flat": "bad"}.get(r["status"], "n/a")
        lines.append("\t".join([r["name"], BIDS_TYPE.get(r["kind"], "MISC"), unit, f"{r['sr']:g}", status, r["note"] or "n/a"]))
    return "\n".join(lines) + "\n"


def mne_spec(rows):
    """Arguments for raw.set_channel_types and raw.info['bads'], plus canonical names for channels that need no re-reference."""
    return dict(types={r["name"]: MNE_TYPE.get(r["kind"], "misc") for r in rows},
                bads=[r["name"] for r in rows if r["status"] == "flat"],
                rename={r["name"]: r["target"] for r in rows if r["target"] and not r["ref"]},
                reference={r["name"]: r["ref"] for r in rows if r["ref"]},
                check={r["name"]: r["note"] for r in rows if r["status"] in ("check", "unread")})


def _eeg_pref(r):
    """Stagers want a central lead referenced to a mastoid; then any canonical lead; then any lead over the central scalp."""
    if r["target"] in ("C4_M1", "C3_M2"):
        return 0
    if r["target"]:
        return 1
    return 2 if re.search(r"c[34z]", r["label"].lower()) else 3


def staging_pick(rows):
    """Best EEG, EOG and chin EMG channel for an automatic stager: trace-confirmed first, then the stager's preferred site."""
    refs = {r["ref"] for r in rows if r["ref"]}
    usable = [r for r in rows if r["status"] != "flat" and r["name"] not in refs
              and not re.fullmatch(r"(eeg[ _-]*)?[am][12]", r["label"].lower())]
    prefs = dict(eeg=_eeg_pref, eog=lambda r: ("LOC", "ROC", "EOG").index(r["target"]) if r["target"] in ("LOC", "ROC", "EOG") else 3,
                 emg=lambda r: 0 if r["target"] == "EMG" else 1)
    out = {"id": rows[0]["id"] if rows else ""}
    for kind, pref in prefs.items():
        best = min((r for r in usable if r["kind"] == kind), key=lambda r: (_RANK[r["status"]], pref(r), r["idx"]), default=None)
        out[kind], out[kind + "_ref"], out[kind + "_status"] = (best["name"], best["ref"], best["status"]) if best else ("", "", "missing")
    return out


def write_exports(audit_rows, mapping, out_dir):
    """Write channels.csv, staging_channels.csv, bids/ID_channels.tsv and mne/ID.json under out_dir."""
    resolved = resolve(audit_rows, mapping)
    for sub in ("bids", "mne"):
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)
    picks = []
    with open(os.path.join(out_dir, "channels.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS)
        w.writeheader()
        for rid, rows in resolved.items():
            w.writerows(rows)
            with open(os.path.join(out_dir, "bids", f"{rid}_channels.tsv"), "w", encoding="utf-8") as f:
                f.write(channels_tsv(rows))
            with open(os.path.join(out_dir, "mne", f"{rid}.json"), "w") as f:
                json.dump(mne_spec(rows), f, indent=1)
            picks.append(staging_pick(rows))
    with open(os.path.join(out_dir, "staging_channels.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, list(picks[0]) if picks else ["id"])
        w.writeheader()
        w.writerows(picks)
    return resolved
