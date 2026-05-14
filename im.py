import pandas as pd
from datetime import datetime

# ============================================================
# CONFIG
# ============================================================
BASE_DIR = "C:/Users/hjmne/PycharmProjects/chest"
PORTFOLIO = "Portfolio1"

EVENTS_FILE = f"{BASE_DIR}/funds/{PORTFOLIO}/Events/events.csv"

DATE_COL = "tradedate"
METHOD_COL = "method"
TICKER_COL = "investment"
QTY_COL = "quantity"

BUY_METHOD = "buy_equity"
SELL_METHOD = "sell_equity"

# ============================================================
# LOAD EVENTS
# ============================================================
print("📂 Loading events...")
df = pd.read_csv(EVENTS_FILE)

# Parse dates
df[DATE_COL] = pd.to_datetime(df[DATE_COL], format="%m/%d/%Y:%H:%M:%S")

# Sort strictly by time, then tranid to preserve precedence
if "tranid" in df.columns:
    df = df.sort_values([DATE_COL, "tranid"])
else:
    df = df.sort_values(DATE_COL)

print(f"✅ Loaded {len(df)} events")

# ============================================================
# INVENTORY CHECK
# ============================================================
inventory = {}   # ticker -> current shares
violations = []

for idx, row in df.iterrows():
    ticker = row[TICKER_COL]
    qty = int(row[QTY_COL])
    method = row[METHOD_COL]
    d = row[DATE_COL]

    inventory.setdefault(ticker, 0)

    if method == BUY_METHOD:
        inventory[ticker] += qty

    elif method == SELL_METHOD:
        if qty > inventory[ticker]:
            violations.append({
                "ticker": ticker,
                "date": d,
                "sell_qty": qty,
                "inventory_before": inventory[ticker],
                "row_index": idx
            })
            # still apply the sell to continue checking
            inventory[ticker] -= qty
        else:
            inventory[ticker] -= qty

# ============================================================
# REPORT
# ============================================================
print("\n=================================================")
print("📊 INVENTORY CHECK RESULTS")
print("=================================================")

if not violations:
    print("✅ NO OVERSELL VIOLATIONS FOUND")
else:
    print(f"❌ FOUND {len(violations)} OVERSELL VIOLATIONS\n")

    # Show first few violations
    for v in violations[:10]:
        print(
            f"❌ {v['ticker']} | {v['date'].date()} | "
            f"Sell: {v['sell_qty']} | "
            f"Inventory before: {v['inventory_before']}"
        )

    if len(violations) > 10:
        print(f"\n... {len(violations) - 10} more omitted")

print("=================================================")

# ============================================================
# OPTIONAL: FAIL HARD IF ANY VIOLATIONS
# ============================================================
if violations:
    raise SystemExit("❌ Oversell violations detected")
else:
    print("🎉 Inventory integrity confirmed")
