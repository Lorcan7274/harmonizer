"""Run the signal checks on every EDF in a directory. Usage: audit_cohort.py EDF_DIR OUT_PREFIX"""
import csv, glob, json, os, sys, time
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harmonizer.checks import audit, pairs
from harmonizer.edf import read_signals


def one(p):
    t = time.time()
    h, xs = read_signals(p)
    return os.path.basename(p)[:-4], audit(h, xs), pairs(h, xs), time.time() - t


if __name__ == "__main__":
    src, out = sys.argv[1], sys.argv[2]
    files = sorted(glob.glob(os.path.join(src, "*.edf")))
    t0 = time.time()
    cols = ["id", "idx", "label", "unit", "sr", "label_type", "signal_type", "agree", "unit_status",
            "amp_uv", "cal_inverted", "ecg_pol", "ecg_artefact", "reason"]
    feats, allpairs, secs = {}, {}, 0
    with ProcessPoolExecutor(4) as ex, open(out + "_channels.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, cols, extrasaction="ignore")
        w.writeheader()
        for rid, rows, pr, dt in ex.map(one, files):
            secs += dt
            for r in rows:
                w.writerow(dict(r, id=rid))
            feats[rid] = [dict(label=r["label"], **r["feat"]) for r in rows]
            allpairs[rid] = pr
    json.dump(feats, open(out + "_features.json", "w"))
    json.dump(allpairs, open(out + "_pairs.json", "w"), indent=0)
    print(f"{len(files)} files, wall {time.time() - t0:.0f}s, cpu {secs:.0f}s")
