import numpy as np

FIELDS = [("label", 16), ("trans", 80), ("unit", 8), ("pmin", 8), ("pmax", 8),
          ("dmin", 8), ("dmax", 8), ("prefilt", 80), ("nsamp", 8), ("res", 32)]


def _num(s, default=0.0):
    try:
        return float(s)
    except ValueError:
        return default


def parse_header(b):
    ns = int(b[252:256])
    if len(b) < 256 + ns * 256:
        raise ValueError("header truncated")
    h = dict(nsig=ns, hdr_bytes=256 + ns * 256, nrec=int(b[236:244]),
             rec_dur=float(b[244:252]), reserved=b[192:236].decode("latin1").strip(),
             start=b[168:184].decode("latin1"), ch=[])
    off = 256
    cols = {}
    for name, w in FIELDS:
        cols[name] = [b[off + i * w: off + (i + 1) * w].decode("latin1").strip() for i in range(ns)]
        off += ns * w
    for i in range(ns):
        c = {k: cols[k][i] for k in ("label", "trans", "unit", "prefilt")}
        c["nsamp"] = int(cols["nsamp"][i])
        c["sr"] = c["nsamp"] / h["rec_dur"]
        for k in ("pmin", "pmax", "dmin", "dmax"):
            c[k] = _num(cols[k][i])
        dd = c["dmax"] - c["dmin"]
        c["gain"] = (c["pmax"] - c["pmin"]) / dd if dd else 1.0
        c["offset"] = c["pmin"] - c["gain"] * c["dmin"]
        h["ch"].append(c)
    h["rec_bytes"] = 2 * sum(c["nsamp"] for c in h["ch"])
    return h


def read_header(path):
    with open(path, "rb") as f:
        b = f.read(256)
        b += f.read(int(b[252:256]) * 256)
    return parse_header(b)


def read_signals(path, physical=True):
    """Return (header, list of 1-D arrays), one per channel, whole file."""
    h = read_header(path)
    raw = np.fromfile(path, dtype="<i2", offset=h["hdr_bytes"])
    per = h["rec_bytes"] // 2
    raw = raw[: (len(raw) // per) * per].reshape(-1, per)
    out, o = [], 0
    for c in h["ch"]:
        x = raw[:, o:o + c["nsamp"]].reshape(-1)
        o += c["nsamp"]
        out.append(x * c["gain"] + c["offset"] if physical else x)
    return h, out


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
