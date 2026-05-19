"""
inspect_jes.py
Run from chest root:
  python inspect_jes.py Portfolio3 Monthly
  python inspect_jes.py Portfolio3 Monthly 3       <- filter by tranid
"""
import pickle
import json
import sys
from pathlib import Path

portfolio = sys.argv[1] if len(sys.argv) > 1 else "Portfolio3"
calendar  = sys.argv[2] if len(sys.argv) > 2 else "Monthly"
tranid    = int(sys.argv[3]) if len(sys.argv) > 3 else None

journals_dir = Path("funds") / portfolio / "Calendars" / calendar / "Journals"

if not journals_dir.exists():
    print(f"ERROR: {journals_dir} not found")
    sys.exit(1)

pkl_files = sorted(journals_dir.glob("*.pkl"))
print(f"Found {len(pkl_files)} journal file(s)\n")

all_jes = []

for pkl_file in pkl_files:
    with open(pkl_file, "rb") as f:
        data = pickle.load(f)

    # Each PKL is a dict with a 'journals' key containing the JE list
    if isinstance(data, dict):
        jes = data.get("journals", [])
    elif isinstance(data, list):
        jes = data
    else:
        print(f"  {pkl_file.name}: unknown structure {type(data)}")
        continue

    print(f"  {pkl_file.name}: {len(jes)} JEs")

    for je in jes:
        if tranid is None or getattr(je, "tranid", None) == tranid:
            all_jes.append(je)

print(f"\nMatching JEs: {len(all_jes)}\n")

if not all_jes:
    print("No matching JEs found.")
    sys.exit(0)

# Show structure of first JE
first = all_jes[0]
print(f"JE type: {type(first)}")
if hasattr(first, "__dict__"):
    print(f"Attributes: {list(first.__dict__.keys())}\n")
elif isinstance(first, dict):
    print(f"Keys: {list(first.keys())}\n")

print(f"{'='*60}")
print(f"ALL MATCHING JEs:")
print(f"{'='*60}")

for i, je in enumerate(all_jes):
    if hasattr(je, "to_dict"):
        d = je.to_dict()
    elif hasattr(je, "__dict__"):
        d = {k: str(v) for k, v in je.__dict__.items()}
    elif isinstance(je, dict):
        d = {k: str(v) for k, v in je.items()}
    else:
        d = {"value": str(je)}

    print(f"\n--- JE {i+1} ---")
    for k, v in d.items():
        print(f"  {k:30s} {v}")