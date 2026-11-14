"""Label-swap fault injection. Only the 16-byte label fields move; calibration stays with the trace."""
import hashlib
from itertools import combinations
from .checks import COMPATIBLE
from .edf import read_header, rewrite_labels


def is_dev(rec_id):
    """Fixed half of a cohort used while fixing checks; the other half is scored once."""
    return int(hashlib.sha1(rec_id.encode()).hexdigest(), 16) % 2 == 0


def eligible_swaps(rows):
    """Pairs of readable, non-flat channels with the same sampling rate and different labels."""
    ok = [r for r in rows if r["label_type"] != "unknown" and r["signal_type"] != "flat"]
    return [(a, b) for a, b in combinations(ok, 2)
            if float(a["sr"]) == float(b["sr"]) and a["label"] != b["label"]]


def swap_detected(a, b):
    """A swap is caught when a channel that agreed with its own label conflicts with the other's."""
    def newly(r, other):
        return r["agree"] == "agree" and r["signal_type"] not in COMPATIBLE.get(other["label_type"], ())
    return newly(a, b) or newly(b, a)


def write_swap(src, dst, i, j):
    perm = list(range(read_header(src)["nsig"]))
    perm[i], perm[j] = j, i
    rewrite_labels(src, dst, perm)
