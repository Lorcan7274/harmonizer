"""Group recordings by header layout. CANONICAL rules are written per layout."""
import re
from collections import defaultdict
from .edf import read_header


def sanitize(label):
    """Approximates Luna's label sanitisation: non-alphanumerics become underscores, case folded."""
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]", "_", label)).strip("_").upper()


def layout_key(h, with_units=False):
    if with_units:
        return tuple(sorted((sanitize(c["label"]), c["unit"].lower(), c["sr"]) for c in h["ch"]))
    return tuple(sorted(sanitize(c["label"]) for c in h["ch"]))


def group(paths, with_units=False):
    out = defaultdict(list)
    for p in paths:
        out[layout_key(read_header(p), with_units)].append(p)
    return dict(out)
