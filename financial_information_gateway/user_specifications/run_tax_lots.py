import pickle
from pathlib import Path
from collections import defaultdict


# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
SNAPSHOT_PATH = Path(
    "C:/Users/hjmne/PycharmProjects/chest/funds/Portfolio1/Calendars/Monthly/Snapshots/2021-05-31T23-59-59.pkl"
)


# ------------------------------------------------------------
# FUNCTION 1 — BUILD POSITION + LOT STRUCTURE
# ------------------------------------------------------------
def build_position_with_lots(snapshot_path):

    with open(snapshot_path, "rb") as f:
        snapshot = pickle.load(f)

    state = snapshot["state"]
    repo = state["asset_liability_repository"]
    positions = repo.investment_positions

    result = {}

    for investment, subspace in positions.items():

        entries = getattr(subspace, "entries", {})

        lot_data = defaultdict(lambda: {
            "qty": 0.0,
            "local": 0.0,
            "book": 0.0
        })

        total_qty = 0.0
        total_local = 0.0
        total_book = 0.0

        for key, values in entries.items():

            if not isinstance(key, tuple) or len(key) < 7:
                continue

            lotid = key[2]
            tax_date = key[3]
            account = key[6]

            # ONLY COST DRIVES POSITION
            if account != "Cost":
                continue

            qty = values[0] if len(values) > 0 else 0.0
            local = values[1] if len(values) > 1 else 0.0
            book = values[2] if len(values) > 2 else 0.0

            lot_key = (lotid, tax_date)

            lot_data[lot_key]["qty"] += qty
            lot_data[lot_key]["local"] += local
            lot_data[lot_key]["book"] += book

            total_qty += qty
            total_local += local
            total_book += book

        if abs(total_qty) < 1e-9:
            continue

        result[investment] = {
            "total": {
                "qty": total_qty,
                "local": total_local,
                "book": total_book
            },
            "lots": lot_data
        }

    return result


# ------------------------------------------------------------
# FUNCTION 2 — FLATTEN (HIERARCHY)
# ------------------------------------------------------------
def flatten_position_with_lots(view):

    rows = []

    for investment, data in view.items():

        total = data["total"]

        # POSITION ROW
        rows.append({
            "level": 0,
            "investment": investment,
            "lotid": None,
            "tax_date": None,
            "qty": total["qty"],
            "local": total["local"],
            "book": total["book"],
            "row_type": "position"
        })

        # LOT ROWS
        for (lotid, tax_date), lot in data["lots"].items():

            # 🚫 REMOVE FAKE LOTS
            if lotid in (0, None):
                continue

            if abs(lot["qty"]) < 1e-9:
                continue

            rows.append({
                "level": 1,
                "investment": investment,
                "lotid": lotid,
                "tax_date": tax_date,
                "qty": lot["qty"],
                "local": lot["local"],
                "book": lot["book"],
                "row_type": "lot"
            })

    return rows


# ------------------------------------------------------------
# FUNCTION 3 — FORMAT FOR GWI
# ------------------------------------------------------------
def format_for_gwi(rows):

    formatted = []

    for r in rows:

        if r["level"] == 0:
            formatted.append({
                "Investment": r["investment"],
                "Lot": "",
                "Date": "",
                "Qty": r["qty"],
                "Local": r["local"],
                "Book": r["book"],
                "Indent": 0
            })

        else:
            formatted.append({
                "Investment": "",
                "Lot": r["lotid"],
                "Date": r["tax_date"],
                "Qty": r["qty"],
                "Local": r["local"],
                "Book": r["book"],
                "Indent": 1
            })

    return formatted


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def main():

    print("\n=== RUNNING POSITION + LOT VIEW ===")

    view = build_position_with_lots(SNAPSHOT_PATH)

    rows = flatten_position_with_lots(view)

    gwi_rows = format_for_gwi(rows)

    # ✅ FINAL OUTPUT ONLY (CLEAN)
    for r in gwi_rows[:50]:
        print(r)


if __name__ == "__main__":
    main()