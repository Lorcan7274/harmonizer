"""Fetch headers and a fixed set of excerpt windows per recording from an open PhysioNet sleep dataset.

Each excerpt is written as a valid EDF (original header, fewer records), so Luna and the
signal checks read the same bytes. Usage: fetch_physionet.py DATASET OUTDIR [n_windows] [window_seconds]
DATASET is one of: cap, hmc, sleep-edf.
"""
import json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harmonizer.edf import parse_header

HOST = "https://physionet-open.s3.amazonaws.com/"
DATASETS = {  # name: (path under HOST, keeps a RECORDS entry)
    "cap": ("capslpdb/1.0.0/", lambda n: n.endswith(".edf")),
    "hmc": ("hmc-sleep-staging/1.1/", lambda n: n.endswith(".edf") and "sleepscoring" not in n),
    "sleep-edf": ("sleep-edfx/1.0.0/", lambda n: n.endswith("-PSG.edf")),
}


def _fetch(req, timeout, tries=5):
    """urlopen with exponential backoff. Returns (headers, body)."""
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.headers, r.read()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)


def rng(url, a, b):
    return _fetch(urllib.request.Request(url, headers={"Range": f"bytes={a}-{b}"}), 120)[1]


def size(url):
    return int(_fetch(urllib.request.Request(url, method="HEAD"), 60)[0]["Content-Length"])


def fetch(base, name, out, nwin, wsec):
    dst = os.path.join(out, os.path.basename(name))
    if os.path.exists(dst):
        return name, "cached"
    url = base + name
    hb = rng(url, 0, 65535)
    h = parse_header(hb)
    hb = hb[: h["hdr_bytes"]]
    nrec_real = (size(url) - h["hdr_bytes"]) // h["rec_bytes"]
    wrec = max(1, int(round(wsec / h["rec_dur"])))
    starts = [int(nrec_real * (0.08 + 0.84 * (i + 0.5) / nwin)) for i in range(nwin)]
    starts = [min(s, max(0, nrec_real - wrec)) for s in starts]
    chunks = []
    for s in starts:
        a = h["hdr_bytes"] + s * h["rec_bytes"]
        chunks.append(rng(url, a, a + wrec * h["rec_bytes"] - 1))
    data = b"".join(chunks)
    n = len(data) // h["rec_bytes"]
    hdr = bytearray(hb)
    hdr[236:244] = f"{n:<8d}".encode()
    with open(dst + ".part", "wb") as f:
        f.write(hdr + data[: n * h["rec_bytes"]])
    os.rename(dst + ".part", dst)
    meta = dict(name=name, nrec_header=h["nrec"], nrec_from_size=nrec_real, rec_dur=h["rec_dur"],
                window_start_sec=[s * h["rec_dur"] for s in starts], window_sec=wrec * h["rec_dur"])
    json.dump(meta, open(dst + ".json", "w"))
    return name, "ok"


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in DATASETS:
        sys.exit(__doc__.strip())
    path, keep = DATASETS[sys.argv[1]]
    out = sys.argv[2]
    nwin = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    wsec = float(sys.argv[4]) if len(sys.argv) > 4 else 300
    os.makedirs(out, exist_ok=True)
    base = HOST + path
    names = [n for n in _fetch(urllib.request.Request(base + "RECORDS"), 60)[1].decode().split() if keep(n)]
    t = time.time()
    with ThreadPoolExecutor(4) as ex:
        for name, st in ex.map(lambda n: fetch(base, n, out, nwin, wsec), names):
            print(name, st, flush=True)
    print(f"done {len(names)} in {time.time() - t:.0f}s")
