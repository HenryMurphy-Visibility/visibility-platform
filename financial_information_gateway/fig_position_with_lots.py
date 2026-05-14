from collections import defaultdict


# ============================================================
# BUILD POSITION + LOT STRUCTURE FROM STATE
# ============================================================
def build_position_with_lots_from_state(state):
    from collections import defaultdict

    positions = {}

    for key, values in state.items():

        # ---------------------------------------------
        # VALIDATE KEY
        # ---------------------------------------------
        if not isinstance(key, tuple) or len(key) < 6:
            continue

        # ---------------------------------------------
        # CORRECT KEY MAPPING
        # ---------------------------------------------
        investment = key[0]
        lotid = key[1]
        tax_date = key[2]
        account = key[5]

        # ---------------------------------------------
        # ONLY COST DRIVES POSITION
        # ---------------------------------------------
        if investment == "USD":
            if account not in ("Cost", "Receivable", "Payable", "DividendsReceivable", "DividendsPayable", "AccruedInterestReceivable",
            "AccruedInterestPayable"):
                continue
        else:
            if account != "Cost":
                continue

        # ---------------------------------------------
        # CORRECT VALUE FIELDS
        # ---------------------------------------------
        qty = values.get("quantity", 0.0)
        local = values.get("local", 0.0)
        book = values.get("book", 0.0)

        # ---------------------------------------------
        # INIT POSITION
        # ---------------------------------------------
        if investment not in positions:
            positions[investment] = {
                "total": {"qty": 0.0, "local": 0.0, "book": 0.0},
                "lots": defaultdict(lambda: {
                    "qty": 0.0,
                    "local": 0.0,
                    "book": 0.0
                })
            }

        # ---------------------------------------------
        # TOTALS
        # ---------------------------------------------
        positions[investment]["total"]["qty"] += qty
        positions[investment]["total"]["local"] += local
        positions[investment]["total"]["book"] += book

        # ---------------------------------------------
        # LOTS
        # ---------------------------------------------
        # ---------------------------------------------
        # FIX: INCLUDE ACCOUNT IN KEY
        # ---------------------------------------------
        lot_key = (lotid, tax_date, account)

        positions[investment]["lots"][lot_key]["qty"] += qty
        positions[investment]["lots"][lot_key]["local"] += local
        positions[investment]["lots"][lot_key]["book"] += book

    return positions

# ============================================================
# FLATTEN TO GWI ROWS
# ============================================================
def flatten_position_with_lots(
        view,
        show_currency_breakdown_by_account=True
):
    rows = []

    # TEMP — replace later with is_currency()
    CURRENCY_LIST = {"USD", "EUR", "GBP"}

    for investment, data in view.items():

        total = data["total"]

        # ---------------------------------------------
        # TOTAL ROW
        # ---------------------------------------------
        rows.append({
            "Investment": investment,
            "FinancialAccount": "TOTAL",
            "Lot": "",
            "Date": "",
            "Qty": total["qty"],
            "Local": total["local"],
            "Book": total["book"],
            "Indent": 0
        })

        # ---------------------------------------------
        # CURRENCY HANDLING
        # ---------------------------------------------
        if investment in CURRENCY_LIST:

            if not show_currency_breakdown_by_account:
                continue

            account_totals = {}

            # 🔥 NOTE: 3-part key
            for (lotid, tax_date, account), lot in data["lots"].items():

                if account not in account_totals:
                    account_totals[account] = {
                        "qty": 0.0,
                        "local": 0.0,
                        "book": 0.0
                    }

                account_totals[account]["qty"] += lot["qty"]
                account_totals[account]["local"] += lot["local"]
                account_totals[account]["book"] += lot["book"]

            # OUTPUT ACCOUNT ROWS
            for account, vals in account_totals.items():

                if abs(vals["qty"]) < 1e-9:
                    continue

                rows.append({
                    "Investment": investment,
                    "FinancialAccount": account,
                    "Lot": "",
                    "Date": "",
                    "Qty": vals["qty"],
                    "Local": vals["local"],
                    "Book": vals["book"],
                    "Indent": 1
                })

            continue  # skip lot logic for currencies

        # ---------------------------------------------
        # SECURITIES (LOT LEVEL)
        # ---------------------------------------------
        for (lotid, tax_date, account), lot in data["lots"].items():

            if lotid in (0, None):
                continue

            if abs(lot["qty"]) < 1e-9:
                continue

            rows.append({
                "Investment": investment,
                "FinancialAccount": account,
                "Lot": lotid,
                "Date": tax_date,
                "Qty": lot["qty"],
                "Local": lot["local"],
                "Book": lot["book"],
                "Indent": 1
            })

    return rows

# ============================================================
# PUBLIC ENTRY POINT
# ============================================================
def run_position_with_lots_view(state):

    view = build_position_with_lots_from_state(state)

    rows = flatten_position_with_lots(view)

    return rows