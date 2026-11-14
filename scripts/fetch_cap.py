"""Fetch CAP headers and a fixed set of excerpt windows per recording via HTTP range requests.

Each excerpt is written as a valid EDF (original header, fewer records), so Luna and the
signal checks read the same bytes. Usage: fetch_cap.py OUTDIR [n_windows] [window_seconds]
"""
import json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harmonizer.edf import parse_header

BASE = "https://physionet-open.s3.amazonaws.com/capslpdb/1.0.0/"


def rng(url, a, b):
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={a}-{b}"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)


def size(url):
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as r:
                return int(r.headers["Content-Length"])
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)


def fetch(name, out, nwin, wsec):
    dst = os.path.join(out, name)
    if os.path.exists(dst):
        return name, "cached"
    url = BASE + name
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
    out = sys.argv[1]
    nwin = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    wsec = float(sys.argv[3]) if len(sys.argv) > 3 else 300
    os.makedirs(out, exist_ok=True)
    names = urllib.request.urlopen("https://physionet.org/files/capslpdb/1.0.0/RECORDS", timeout=60).read().decode().split()
    t = time.time()
    with ThreadPoolExecutor(4) as ex:
        for name, st in ex.map(lambda n: fetch(n, out, nwin, wsec), names):
            print(name, st, flush=True)
    print(f"done {len(names)} in {time.time() - t:.0f}s")
