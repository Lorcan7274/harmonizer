"""Run drafted rules through real CANONICAL and score against the answer key.

Usage: score.py DRAFT_DIR ANSWER_KEY.csv [dev|held|all]
"""
import csv, json, os, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harmonizer.canon import run_canonical
from harmonizer.checks import COMPATIBLE
from harmonizer.edf import read_header
from harmonizer.inject import is_dev
from harmonizer.layout import luna_labels
from harmonizer.targets import TARGETS, REQUIRED_TYPES

draft, keyfile = sys.argv[1], sys.argv[2]
part = sys.argv[3] if len(sys.argv) > 3 else "all"
key = defaultdict(list)
for r in csv.DictReader(open(keyfile)):
    key[r["id"]].append(r)
conf = {(r["id"], r["target"]): r["confidence"] for r in csv.DictReader(open(os.path.join(draft, "confidence.csv")))}
rules = os.path.join(draft, "rules.sigs")
res, verdicts, conf_wrong = [], Counter(), []
for lst in sorted(os.listdir(os.path.join(draft, "lists"))):
    lid = lst[:-4]
    for line in open(os.path.join(draft, "lists", lst)):
        rid, path = line.rstrip("\n").split("\t")
        if part != "all" and is_dev(rid) != (part == "dev"):
            continue
        made = run_canonical(path, [rules], group=lid)["made"]
        idx = {l.upper(): i for i, l in enumerate(luna_labels(read_header(path)))}
        got = defaultdict(list)
        for target, (sig, _) in made.items():
            k = key[rid][idx[str(sig).upper()]]
            if k["status"] != "settled":
                v = k["status"]
            else:
                v = "right" if k["trace_type"] in COMPATIBLE[TARGETS[target]] else "wrong"
            verdicts[v] += 1
            got[TARGETS[target]].append(v)
            if v == "wrong" and conf.get((rid, target)) == "high":
                conf_wrong.append((rid, target, sig))
        need = [t for t in REQUIRED_TYPES
                if any(k["status"] == "settled" and k["label_type"] == t for k in key[rid])]
        ok = all("right" in got[t] for t in need) and not any("wrong" in got[t] for t in REQUIRED_TYPES)
        res.append(dict(id=rid, layout=lid, made=len(made), need=need, all_required_right=ok,
                        missing=[t for t in need if "right" not in got[t]]))
n = len(res)
print(f"[{part}] {n} recordings through CANONICAL")
print(f"all required signals right: {sum(r['all_required_right'] for r in res)}/{n} ({sum(r['all_required_right'] for r in res) / n:.1%})")
print("canonical signals made:", sum(r["made"] for r in res), "verdicts", dict(verdicts))
print("confident and wrong:", len(conf_wrong), conf_wrong[:10])
print("missing required types:", dict(Counter(t for r in res for t in r["missing"])))
json.dump(res, open(os.path.join(draft, f"score_{part}.json"), "w"), indent=0)
