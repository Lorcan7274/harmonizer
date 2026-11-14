"""Judge a drafted mapping against the answer key. A reader's ruling outranks the trace check."""
import re
from .checks import COMPATIBLE
from .targets import TARGETS, REQUIRED_TYPES

# what a reader can tell apart by eye: effort belts and airflow are both breathing
RULINGS = ("eeg", "eog", "emg", "emg_leg", "ecg", "resp", "other", "unusable")
_CLASS = {"effort": "resp", "flow": "resp"}


def ruling(k):
    return (k.get("reader_ruling") or "").strip().lower()


def verdict(k, target):
    """right, wrong, or the key row's unsettled status, for making canonical `target` from key row k."""
    kind = TARGETS[target]
    if ruling(k):
        return "right" if ruling(k) == _CLASS.get(kind, kind) else "wrong"
    if k["status"] != "settled":
        return k["status"]
    return "right" if k["trace_type"] in COMPATIBLE[kind] else "wrong"


def mappable(label, t):
    """Bipolar scalp chains (F4-C4, C3-P3) have no canonical target, so they cannot make EEG required."""
    return t != "eeg" or bool(re.search(r"[am][12]|^[a-z]+\d*$", label.lower().replace(" ", "")))


def needed(rows):
    """Required types this recording really holds, by ruling where there is one and by settled label otherwise."""
    def kind(k):
        return ruling(k) or (k["label_type"] if k["status"] == "settled" else None)
    return [t for t in REQUIRED_TYPES if any(kind(k) == t and mappable(k["label"], t) for k in rows)]
