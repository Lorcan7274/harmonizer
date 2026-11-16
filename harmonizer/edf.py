"""EDF and EDF+ reader. EDF+ annotation channels are skipped: they hold text, not samples, and Luna and MNE do not list them."""
import glob, os
import numpy as np

FIELDS = [("label", 16), ("trans", 80), ("unit", 8), ("pmin", 8), ("pmax", 8),
          ("dmin", 8), ("dmax", 8), ("prefilt", 80), ("nsamp", 8), ("res", 32)]
ANNOTATIONS = "EDF Annotations"


def edf_paths(edf_dir):
    """Every .edf file in a directory, any letter case, sorted."""
    return sorted(p for p in glob.glob(os.path.join(edf_dir, "*")) if p.lower().endswith(".edf"))


def rec_id(path):
    return os.path.basename(path)[:-4]


def _num(s, default=0.0):
    try:
        return float(s)
    except ValueError:
        return default


def _count(b):
    """Number of signals from the fixed header, with a readable error for files that are not EDF."""
    if b[:1] == b"\xff":
        raise ValueError("BDF (24-bit) file; convert it to EDF first")
    try:
        return int(b[252:256])
    except ValueError:
        raise ValueError("not an EDF file: unreadable header") from None


def parse_header(b):
    ns = _count(b)
    if len(b) < 256 + ns * 256:
        raise ValueError("header truncated")
    try:
        h = dict(nsig=ns, hdr_bytes=256 + ns * 256, nrec=int(b[236:244]),
                 rec_dur=float(b[244:252]), reserved=b[192:236].decode("latin1").strip(),
                 start=b[168:184].decode("latin1"), ch=[])
    except ValueError:
        raise ValueError("not an EDF file: unreadable header") from None
    if h["rec_dur"] <= 0:
        raise ValueError("data records have no duration (an annotation-only EDF+ file?)")
    off = 256
    cols = {}
    for name, w in FIELDS:
        cols[name] = [b[off + i * w: off + (i + 1) * w].decode("latin1").strip() for i in range(ns)]
        off += ns * w
    start = 0
    for i in range(ns):
        c = {k: cols[k][i] for k in ("label", "trans", "unit", "prefilt")}
        c["nsamp"] = int(cols["nsamp"][i])
        c["index"], c["start"] = i, start
        start += c["nsamp"]
        if c["label"] == ANNOTATIONS:
            continue
        c["sr"] = c["nsamp"] / h["rec_dur"]
        for k in ("pmin", "pmax", "dmin", "dmax"):
            c[k] = _num(cols[k][i])
        dd = c["dmax"] - c["dmin"]
        c["gain"] = (c["pmax"] - c["pmin"]) / dd if dd else 1.0
        c["offset"] = c["pmin"] - c["gain"] * c["dmin"]
        h["ch"].append(c)
    h["rec_bytes"] = 2 * start
    return h


def read_header(path):
    with open(path, "rb") as f:
        b = f.read(256)
        b += f.read(_count(b) * 256)
    return parse_header(b)


def n_records(path, h):
    """Whole data records actually in the file; the header's count can be -1 or stale."""
    return (os.path.getsize(path) - h["hdr_bytes"]) // h["rec_bytes"] if h["rec_bytes"] else 0


def _split(h, raw, physical):
    per = h["rec_bytes"] // 2
    raw = raw[: (len(raw) // per) * per].reshape(-1, per)
    out = []
    for c in h["ch"]:
        x = raw[:, c["start"]:c["start"] + c["nsamp"]].reshape(-1)
        out.append(x * c["gain"] + c["offset"] if physical else x)
    return out


def read_signals(path, physical=True):
    """Return (header, list of 1-D arrays), one per channel, whole file."""
    h = read_header(path)
    return h, _split(h, np.fromfile(path, dtype="<i2", offset=h["hdr_bytes"]), physical)


def read_window(path, start_sec, dur_sec, physical=True):
    """Like read_signals, but only the data records covering dur_sec from start_sec."""
    h = read_header(path)
    first = int(start_sec // h["rec_dur"])
    n = max(1, int(np.ceil(dur_sec / h["rec_dur"])))
    raw = np.fromfile(path, dtype="<i2", offset=h["hdr_bytes"] + first * h["rec_bytes"], count=n * h["rec_bytes"] // 2)
    return h, _split(h, raw, physical)


def window_starts(nrec, wrec, nwin):
    """First record of each of nwin windows of wrec records, spread over the middle 84% of a recording."""
    return [min(int(nrec * (0.08 + 0.84 * (i + 0.5) / nwin)), max(0, nrec - wrec)) for i in range(nwin)]


def read_blocks(path, h, block_sec, max_blocks=0, physical=True):
    """Yield per-channel arrays for blocks of whole records of about block_sec, never holding more than one block.

    With max_blocks, a recording longer than that many blocks is sampled at window_starts instead of read through.
    """
    wrec = max(1, int(round(block_sec / h["rec_dur"])))
    nrec = n_records(path, h)
    if max_blocks and nrec // wrec > max_blocks:
        starts = window_starts(nrec, wrec, max_blocks)
    else:
        starts = range(0, nrec, wrec)
    for first in starts:
        raw = np.fromfile(path, dtype="<i2", offset=h["hdr_bytes"] + first * h["rec_bytes"],
                          count=min(wrec, nrec - first) * h["rec_bytes"] // 2)
        yield _split(h, raw, physical)


def rewrite_labels(src, dst, perm):
    """Copy src to dst with channel i given the label of channel perm[i]; nothing else moves."""
    with open(src, "rb") as f:
        b = bytearray(f.read())
    ns = int(b[252:256])
    labels = [bytes(b[256 + i * 16: 256 + (i + 1) * 16]) for i in range(ns)]
    for i, j in enumerate(perm):
        b[256 + i * 16: 256 + (i + 1) * 16] = labels[j]
    with open(dst, "wb") as f:
        f.write(b)
