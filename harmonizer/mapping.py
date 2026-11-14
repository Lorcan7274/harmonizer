"""Layout-level mapping from header labels to canonical targets.

A mapping is a list of {label, target, ref, reason}; label and ref are Luna-sanitised labels,
target is a key of TARGETS or None. baseline() is the no-model reader the model has to beat.
"""
import re
from .checks import label_type
from .targets import TARGETS

_EEG = [("C4_M1", r"^c4.{0,3}[am]1$", "C4", r"^[am]1$"), ("C3_M2", r"^c3.{0,3}[am]2$", "C3", r"^[am]2$"),
        ("F4_M1", r"^f4.{0,3}[am]1$", "F4", r"^[am]1$"), ("F3_M2", r"^f3.{0,3}[am]2$", "F3", r"^[am]2$"),
        ("O2_M1", r"^o2.{0,3}[am]1$", "O2", r"^[am]1$"), ("O1_M2", r"^o1.{0,3}[am]2$", "O1", r"^[am]2$")]
_SIMPLE = {"emg": "EMG", "ecg": "ECG", "spo2": "SpO2", "hr": "HR", "pleth": "pleth", "pos": "pos",
           "snore": "snore", "flow": "airflow"}
_PAIRED = ("emg", "ecg", "emg_leg")


def leg_side(s):
    """RAT or LAT when a lower-cased leg label names exactly one side, else None."""
    right = re.search(r"dx|right|(^|_)r(_|\d|$)|^r(leg|tib)", s)
    left = re.search(r"sx|sin|left|(^|_)l(_|\d|$)|^l(leg|tib)", s)
    return ("RAT" if right else "LAT") if bool(right) != bool(left) else None


def baseline(labels):
    low = {l: l.lower() for l in labels}
    out, used = [], set()

    def find(pat):
        return next((l for l in labels if re.search(pat, low[l])), None)

    def partner(s):
        """The other half of a numbered pair (EMG1 for EMG2 and back), if the layout has it."""
        m = re.search(r"[a-z]([12])$", s)
        return find("^" + re.escape(s[:-1]) + ("2" if m.group(1) == "1" else "1") + "$") if m else None

    def add(label, target, reason, ref=None):
        if target in used:
            target, reason = None, f"second candidate for an already mapped target ({reason})"
        elif target:
            used.add(target)
        out.append(dict(label=label, target=target, ref=ref, reason=reason))

    for l in labels:
        s, t = low[l], label_type(l)
        hit = next((e for e in _EEG if re.search(e[1], s)), None)
        bare = next((e for e in _EEG if s == e[2].lower()), None)
        pair = partner(s) if t in _PAIRED else None
        if hit:
            add(l, hit[0], "label names electrode and contralateral mastoid")
        elif bare and find(bare[3]):
            add(l, bare[0], "unreferenced electrode with the mastoid recorded separately", ref=find(bare[3]))
        elif t == "eog":
            if re.search(r"roc.*loc|loc.*roc", s):
                add(l, "EOG", "bipolar eye channel")
            elif re.search(r"roc|eog.?r|eog.?dx", s):
                add(l, "ROC", "right eye label")
            elif re.search(r"loc|eog.?l|eog.?sin", s):
                add(l, "LOC", "left eye label")
            else:
                add(l, None, "eye label without a side")
        elif pair and s.endswith("2"):
            add(l, None, "used as reference for its pair")
        elif pair and t in ("emg", "ecg"):
            add(l, _SIMPLE[t], "first of a numbered pair, referenced to the second", ref=pair)
        elif t == "effort":
            add(l, "thorax" if re.search(r"tor|thor", s) else "abdomen", "effort belt label")
        elif t == "emg_leg":
            side = leg_side(s)
            if side:
                add(l, side, "leg label; dx is right, sx/sin is left", ref=pair)
            else:
                add(l, None, "leg label without a side")
        elif t in _SIMPLE:
            add(l, _SIMPLE[t], f"label reads as {t}")
        else:
            add(l, None, "no canonical target for this label" if t != "unknown" else "label not understood")
    return out


def validate(mapping, labels):
    """Drop anything the emitter could not write safely. Returns (clean mapping, problems)."""
    known, probs, seen, clean = set(labels), [], set(), []
    missing = known - {x.get("label") for x in mapping}
    if missing:
        probs.append(f"no answer for {sorted(missing)}")
    for m in mapping:
        m = dict(label=m.get("label"), target=m.get("target") or None, ref=m.get("ref") or None, reason=m.get("reason", ""))
        if m["label"] not in known:
            probs.append(f"unknown label {m['label']!r}")
            continue
        if m["target"] and m["target"] not in TARGETS:
            probs.append(f"{m['label']}: unknown target {m['target']!r}")
            m["target"] = None
        if m["ref"] and m["ref"] not in known:
            probs.append(f"{m['label']}: unknown reference {m['ref']!r}")
            m["target"] = m["ref"] = None
        if m["target"] in seen:
            probs.append(f"{m['label']}: target {m['target']} already used")
            m["target"] = None
        if m["target"]:
            seen.add(m["target"])
        clean.append(m)
    return clean, probs
