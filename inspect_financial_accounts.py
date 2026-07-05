"""
check_fa.py — show all unique financial_account values in JEs
Run from chest root: python check_fa.py Portfolio3 Monthly
"""
import pickle, sys
from pathlib import Path
from collections import Counter

portfolio = sys.argv[1] if len(sys.argv) > 1 else "Portfolio3"
calendar  = sys.argv[2] if len(sys.argv) > 2 else "Monthly"

journals_dir = Path("funds") / portfolio / "Calendars" / calendar / "Journals"
fa_counter = Counter()
total = 0

for pkl_file in sorted(journals_dir.glob("*.pkl")):
    with open(pkl_file, "rb") as f:
        data = pickle.load(f)
    jes = data.get("journals", []) if isinstance(data, dict) else data
    for je in jes:
        fa = getattr(je, "financial_account", None) or (je.get("financial_account") if isinstance(je, dict) else None)
        fa_counter[str(fa)] += 1
        total += 1

print(f"\nTotal JEs: {total}")
print(f"\nFinancial Accounts found:")
for fa, count in sorted(fa_counter.items()):
    print(f"  {count:5d}  {fa}")