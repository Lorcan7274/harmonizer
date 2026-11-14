"""Draft answer key from traces. Usage: answer_key.py PREFIX. Label/trace disagreements stay unsettled until a reader rules."""
import csv, sys

prefix = sys.argv[1]
status = {"agree": "settled", "flat": "flat", "conflict": "unsettled", "label_unread": "unsettled"}
rows = list(csv.DictReader(open(prefix + "_channels.csv")))
with open(prefix + "_answer_key.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["id", "idx", "label", "unit", "sr", "trace_type", "label_type", "status", "evidence", "reader_ruling"])
    for r in rows:
        w.writerow([r["id"], r["idx"], r["label"], r["unit"], r["sr"], r["signal_type"], r["label_type"],
                    status[r["agree"]], r["reason"], ""])
n = {s: sum(status[r["agree"]] == s for r in rows) for s in set(status.values())}
print(n)
