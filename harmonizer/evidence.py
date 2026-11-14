"""Evidence-based confidence: compare what a mapping claims with what the trace showed. No model estimate involved."""
from collections import Counter
from .checks import COMPATIBLE
from .targets import TARGETS


def confidence(target, row):
    """row is one audit row for the source channel in one recording."""
    want = COMPATIBLE.get(TARGETS[target], set())
    st = row["signal_type"]
    if st == "flat" or not want:
        return "medium"
    return "high" if st in want else "flag"


def layout_evidence(labels_per_rec, audit_rows):
    """Per Luna label: how often each trace type was seen across the layout's recordings."""
    ev = {}
    for rid, labels in labels_per_rec.items():
        for lab, row in zip(labels, audit_rows[rid]):
            ev.setdefault(lab.upper(), Counter())[row["signal_type"]] += 1
    return ev
