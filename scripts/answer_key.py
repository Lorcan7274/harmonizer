"""Draft answer key from traces. Usage: answer_key.py PREFIX. Label/trace disagreements stay unsettled until a reader rules.

Re-running keeps any reader_ruling already entered for the same recording and channel index.
"""
import csv, os, sys

if len(sys.argv) != 2:
    sys.exit(__doc__.strip())
prefix = sys.argv[1]
out = prefix + "_answer_key.csv"
status = {"agree": "settled", "flat": "flat", "conflict": "unsettled", "label_unread": "unsettled"}
rows = list(csv.DictReader(open(prefix + "_channels.csv")))
rulings = {}
if os.path.exists(out):
    rulings = {(r["id"], r["idx"]): r["reader_ruling"] for r in csv.DictReader(open(out)) if r.get("reader_ruling")}
with open(out, "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["id", "idx", "label", "unit", "sr", "trace_type", "label_type", "status", "evidence", "reader_ruling"])
    for r in rows:
        w.writerow([r["id"], r["idx"], r["label"], r["unit"], r["sr"], r["signal_type"], r["label_type"],
                    status[r["agree"]], r["reason"], rulings.pop((r["id"], r["idx"]), "")])
n = {s: sum(status[r["agree"]] == s for r in rows) for s in set(status.values())}
print(n)
if rulings:
    print(f"warning: {len(rulings)} reader rulings dropped because their channel is no longer in the audit: {sorted(rulings)[:10]}")
