from collections import defaultdict


# ------------------------------------------------------------
# CORE BUILDER (FROM YOUR STANDALONE)
# ------------------------------------------------------------
def build_position_with_lots_from_state(state):

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
# FLATTEN
# ------------------------------------------------------------
def flatten_position_with_lots(view):

    rows = []

    for investment, data in view.items():

        total = data["total"]

        rows.append({
            "Investment": investment,
            "Lot": "",
            "Date": "",
            "Qty": total["qty"],
            "Local": total["local"],
            "Book": total["book"],
            "Indent": 0
        })

        for (lotid, tax_date), lot in data["lots"].items():

            if lotid in (0, None):
                continue

            if abs(lot["qty"]) < 1e-9:
                continue

            rows.append({
                "Investment": investment,
                "Lot": lotid,
                "Date": tax_date,
                "Qty": lot["qty"],
                "Local": lot["local"],
                "Book": lot["book"],
                "Indent": 1
            })

    return rows


# ------------------------------------------------------------
# PUBLIC FIG ENTRY POINT
# ------------------------------------------------------------
def run_position_with_lots_view(state):

    view = build_position_with_lots_from_state(state)

    rows = flatten_position_with_lots(view)

    return rows