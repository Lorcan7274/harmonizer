"""Draft CANONICAL rules for a cohort.

Usage: draft.py EDF_DIR AUDIT_PREFIX OUT_DIR [baseline|model-headers|model-signals]
Needs audit_cohort.py output at AUDIT_PREFIX. The model readers need ANTHROPIC_API_KEY.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harmonizer.pipeline import READERS, draft

if len(sys.argv) < 4 or (len(sys.argv) > 4 and sys.argv[4] not in READERS):
    sys.exit(__doc__.strip())
s = draft(*sys.argv[1:4], reader=sys.argv[4] if len(sys.argv) > 4 else "baseline", log=lambda lid: print(lid, flush=True))
print(f"{s['reader']}: {s['layouts']} layouts, {s['rules']} rules, confidence {s['confidence']}, "
      f"{s['problems']} mapping problems, {s['suggestions']} pre-script suggestions")
