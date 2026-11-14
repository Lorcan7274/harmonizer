"""Summarise an audit: agreement, flags per recording, and analytic label-swap recall. Usage: summarise.py PREFIX [dev|held|all]"""
import csv, collections, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harmonizer.inject import is_dev, eligible_swaps, swap_detected

if len(sys.argv) < 2 or (len(sys.argv) > 2 and sys.argv[2] not in ("dev", "held", "all")):
    sys.exit(__doc__.strip())
prefix, part = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "all")
R = [r for r in csv.DictReader(open(prefix + "_channels.csv"))
     if part == "all" or is_dev(r["id"]) == (part == "dev")]
recs = collections.defaultdict(list)
for r in R:
    recs[r["id"]].append(r)
if not recs:
    sys.exit(f"[{part}] no recordings in {prefix}_channels.csv")
print(f"[{part}] {len(recs)} recordings, {len(R)} channels")
print("agreement", dict(collections.Counter(r["agree"] for r in R)))
c = collections.Counter((r["label_type"], r["signal_type"]) for r in R)
lts, sts = sorted({k[0] for k in c}), sorted({k[1] for k in c})
print(" " * 9 + "".join(f"{s[:9]:>10}" for s in sts))
for l in lts:
    print(f"{l:9}" + "".join(f"{c[(l, s)]:10d}" for s in sts))
flags = [sum(r["agree"] == "conflict" for r in v) for v in recs.values()]
print(f"type flags per recording: mean {sum(flags) / len(flags):.2f}, recordings with none {sum(f == 0 for f in flags)}")
print("unit", dict(collections.Counter(r["unit_status"] for r in R)))
for r in R:
    if r["unit_status"] == "conflict":
        print("   unit conflict", r["id"], r["label"], r["unit"], r["signal_type"], r["amp_uv"])
print("inverted calibration: channels", sum(r["cal_inverted"] == "True" for r in R),
      "recordings", len({r["id"] for r in R if r["cal_inverted"] == "True"}))
cross = within = hit = 0
miss = collections.Counter()
for v in recs.values():
    for a, b in eligible_swaps(v):
        if a["label_type"] == b["label_type"]:
            within += 1
            continue
        cross += 1
        if swap_detected(a, b):
            hit += 1
        else:
            miss[tuple(sorted((a["label_type"], b["label_type"])))] += 1
print(f"label swaps: {cross} cross-type, caught {hit} ({hit / max(cross, 1):.1%}); {within} within-type (expected misses)")
print("missed cross-type swaps by type pair", miss.most_common(12))
print("top conflicts", collections.Counter((r["label"], r["signal_type"]) for r in R if r["agree"] == "conflict").most_common(25))
