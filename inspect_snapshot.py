# ============================================================
# inspect_snapshot.py
# Reads raw state snapshot directly.
# Shows the actual balance data the CPH wrote to disk.
# No compute layer. No journals. Just the raw state.
# ============================================================

import pickle
from pathlib import Path
from v_config import FUNDS_PATH

# ── INPUTS ──────────────────────────────────────────────────
PORTFOLIO  = "Portfolio1"
CALENDAR   = "Monthly"
PERIOD     = "2025-11"    # the PRIOR period snapshot
                           # (this is December's opening balance)
INVESTMENT = "ZTS"

# ── LOCATE SNAPSHOTS DIRECTORY ──────────────────────────────
snapshots_dir = (
    Path(FUNDS_PATH)
    / PORTFOLIO
    / "Calendars"
    / CALENDAR
    / "Snapshots"
)

print(f"\nSnapshots directory: {snapshots_dir}")
print(f"Exists: {snapshots_dir.exists()}")

# ── LIST ALL SNAPSHOT FILES ──────────────────────────────────
print("\n--- ALL SNAPSHOT FILES ---")
for f in sorted(snapshots_dir.glob("*.pkl")):
    print(f"  {f.name}")

# ── FIND THE TARGET SNAPSHOT ─────────────────────────────────
matches = [
    f for f in snapshots_dir.glob("*.pkl")
    if PERIOD in f.stem
]

if not matches:
    print(f"\nNo snapshot found for period {PERIOD}")
    exit()

fpath = matches[0]
print(f"\nLoading snapshot: {fpath.name}")

# ── LOAD SNAPSHOT ────────────────────────────────────────────
with open(fpath, "rb") as f:
    payload = pickle.load(f)

print(f"Payload type: {type(payload)}")
print(f"Payload keys: {list(payload.keys()) if isinstance(payload, dict) else 'not a dict'}")

# ── GET STATE ────────────────────────────────────────────────
state = payload.get("state") if isinstance(payload, dict) else payload

if state is None:
    print("No 'state' key found in payload")
    exit()

print(f"\nState type: {type(state)}")
print(f"State keys: {list(state.keys()) if isinstance(state, dict) else 'not a dict'}")

# ── INSPECT ASSET/LIABILITY REPOSITORY ──────────────────────
al_repo = state.get("asset_liability_repository")

if al_repo is None:
    print("\nNo asset_liability_repository found")
else:
    print(f"\nasset_liability_repository type: {type(al_repo)}")

    # Look for ZTS positions
    print(f"\n--- ZTS POSITIONS IN ASSET/LIABILITY REPO ---")

    found = 0

    for subspace in al_repo.investment_positions.values():
        for key, row in subspace.entries.items():

            (_, inv, lotid, tax_date, ls, loc, fa) = key

            if inv != INVESTMENT:
                continue

            found += 1

            qty   = row[0] if len(row) > 0 else 0.0
            local = row[1] if len(row) > 1 else 0.0
            book  = row[2] if len(row) > 2 else 0.0

            print(f"\n  Key:      {key}")
            print(f"  LotID:    {lotid}")
            print(f"  TaxDate:  {tax_date}")
            print(f"  Location: {loc}")
            print(f"  FA:       {fa}")
            print(f"  Qty:      {qty:,.4f}")
            print(f"  Local:    {local:,.4f}")
            print(f"  Book:     {book:,.4f}")
            print(f"  Raw row:  {row}")

    if found == 0:
        print(f"  No {INVESTMENT} positions found in asset_liability_repository")

# ── INSPECT REVENUE/EXPENSE REPOSITORY ──────────────────────
re_repo = state.get("revenue_expense_repository")

if re_repo is None:
    print("\nNo revenue_expense_repository found")
else:
    print(f"\n--- ZTS POSITIONS IN REVENUE/EXPENSE REPO ---")

    found = 0

    entries = re_repo.entries
    iterable = entries.items() if isinstance(entries, dict) else entries

    for key, row in iterable:
        if not isinstance(key, tuple) or len(key) < 7:
            continue

        (_, inv, lotid, tax_date, ls, loc, fa) = key

        if inv != INVESTMENT:
            continue

        found += 1

        qty   = row[0] if len(row) > 0 else 0.0
        local = row[1] if len(row) > 1 else 0.0
        book  = row[2] if len(row) > 2 else 0.0

        print(f"\n  Key:      {key}")
        print(f"  LotID:    {lotid}")
        print(f"  FA:       {fa}")
        print(f"  Qty:      {qty:,.4f}")
        print(f"  Local:    {local:,.4f}")
        print(f"  Book:     {book:,.4f}")

    if found == 0:
        print(f"  No {INVESTMENT} positions found in revenue_expense_repository")