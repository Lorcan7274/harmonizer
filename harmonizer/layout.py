"""Group recordings by header layout. CANONICAL rules are written per layout."""
import re
from collections import defaultdict
from .edf import read_header


_TO_UNDERSCORE = set("-+ /\\*<>=&^!@#$%(),")


def sanitize(label):
    """Luna's label sanitisation, as measured on lunapi 1.7: these characters become underscores and outer
    underscores are dropped. Periods, colons, quotes and brackets are kept; a non-ASCII character becomes ?."""
    return "".join("_" if ch in _TO_UNDERSCORE else "?" if ord(ch) > 127 else ch for ch in label).strip("_")


def luna_labels(h):
    """Channel labels as Luna will see them; repeats get .1, .2, ..."""
    seen, out = {}, []
    for c in h["ch"]:
        s = sanitize(c["label"])
        n = seen.get(s.upper(), 0)
        seen[s.upper()] = n + 1
        out.append(s if n == 0 else f"{s}.{n}")
    return out


def layout_key(h, with_units=False):
    labs = [s.upper() for s in luna_labels(h)]
    if with_units:
        return tuple(sorted(zip(labs, (c["unit"].lower() for c in h["ch"]), (c["sr"] for c in h["ch"]))))
    return tuple(sorted(labs))


def group(paths, with_units=False):
    out = defaultdict(list)
    for p in paths:
        out[layout_key(read_header(p), with_units)].append(p)
    return dict(out)


def numbered(groups):
    """Stable layout ids, largest layout first."""
    order = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return {f"L{i + 1:02d}": (k, sorted(v)) for i, (k, v) in enumerate(order)}
