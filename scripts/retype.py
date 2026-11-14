"""Re-run typing from cached features after a rule change. Usage: retype.py PREFIX"""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harmonizer.checks import classify

prefix = sys.argv[1]
old = list(csv.DictReader(open(prefix + "_channels.csv")))
feats = json.load(open(prefix + "_features.json"))
cols = list(old[0].keys())
by = {}
for r in old:
    by.setdefault(r["id"], []).append(r)
with open(prefix + "_channels.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, cols, extrasaction="ignore")
    w.writeheader()
    for rid, rs in by.items():
        chs = [dict(label=r["label"], unit=r["unit"], sr=float(r["sr"]), cal_inverted=r["cal_inverted"] == "True") for r in rs]
        fs = [{k: v for k, v in f.items() if k != "label"} for f in feats[rid]]
        for row in classify(chs, fs):
            w.writerow(dict(row, id=rid))
