"""Draft answer key from traces. Usage: answer_key.py PREFIX [RULINGS.csv]

Label/trace disagreements stay unsettled until a reader rules. Re-running keeps rulings already entered;
RULINGS.csv (id, idx, ruling, as copied from the review page) adds more.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harmonizer.pipeline import answer_key

if len(sys.argv) not in (2, 3):
    sys.exit(__doc__.strip())
n, kept, dropped = answer_key(*sys.argv[1:])
print(n)
if kept:
    print(f"{kept} reader rulings in the key")
if dropped:
    print(f"warning: {len(dropped)} reader rulings dropped because their channel is no longer in the audit: {dropped[:10]}")
