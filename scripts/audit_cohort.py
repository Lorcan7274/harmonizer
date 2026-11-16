"""Run the signal checks on every EDF in a directory. Usage: audit_cohort.py EDF_DIR OUT_PREFIX"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harmonizer.pipeline import audit_cohort

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__.strip())
    s = audit_cohort(sys.argv[1], sys.argv[2])
    print(f"{s['files']} files, wall {s['wall']:.0f}s, cpu {s['cpu']:.0f}s")
    for rid, err in s["skipped"]:
        print(f"skipped {rid}: {err}")
