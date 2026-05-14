# ==========================================
# FIG CONTROLLER (STATE-CORRECT VERSION)
# ==========================================

import pandas as pd
from pathlib import Path
import pickle
from datetime import datetime

# ==========================================
# CONSTANTS
# ==========================================
ENGINE_TOLERANCE = 1e-9
TOLERANCE = 1e-6

# ==========================================
# FILTER
# ==========================================
def passes_filter(obj, uber_filter):
    if not uber_filter:
        return True

    for field, expected in uber_filter.items():
        value = obj.get(field) if isinstance(obj, dict) else getattr(obj, field, None)
        if value != expected:
            return False

    return True

# ==========================================
# VALIDATION
# ==========================================
def validate_invariants(balances):
    failures = []

    for key, b in balances.items():
        if abs((b["opening_qty"] + b["movement_qty"]) - b["closing_qty"]) > TOLERANCE:
            failures.append(key)

    return failures

# ==========================================
# EXTRACT STRUCTURAL (FIXED)
# ==========================================
def extract_structural(state, uber_filter=None):
    rows = []

    if not state:
        return rows

    al_repo = state["asset_liability_repository"]
    re_repo = state["revenue_expense_repository"]

    def passes(inv):
        if not uber_filter:
            return True
        if "investment" in uber_filter:
            return inv == uber_filter["investment"]
        return True

    def decode(row):
        qty = row[0] if len(row) > 0 else 0.0
        local = row[1] if len(row) > 1 else 0.0
        book = row[2] if len(row) > 2 else 0.0
        return qty, local, book

    # -----------------------------
    # ASSET / LIABILITY
    # -----------------------------
    for subspace in al_repo.investment_positions.values():
        for key, row in subspace.entries.items():

            (_, inv, lotid, tax_date, ls, loc, fa) = key

            if not passes(inv):
                continue

            qty, local, book = decode(row)

            rows.append({
                "investment": inv,
                "lotid": lotid,
                "tax_date": tax_date,
                "location": loc,
                "ls": ls,
                "financial_account": fa,
                "quantity": qty,
                "local": local,
                "book": book,
            })

    # -----------------------------
    # REVENUE / EXPENSE
    # -----------------------------
    entries = re_repo.entries

    if isinstance(entries, dict):
        iterable = entries.items()
    else:
        iterable = entries

    for key, row in iterable:

        if not isinstance(key, tuple) or len(key) < 7:
            continue

        (_, inv, lotid, tax_date, ls, loc, fa) = key

        if not passes(inv):
            continue

        qty, local, book = decode(row)

        rows.append({
            "investment": inv,
            "lotid": lotid,
            "tax_date": tax_date,
            "location": loc,
            "ls": ls,
            "financial_account": fa,
            "quantity": qty,
            "local": local,
            "book": book,
        })

    return rows

# ==========================================
# MATERIALIZE (CORRECTED)
# ==========================================
def materialize_box_state(
        prior_state,
        current_state,
        journal_entries,
        prior_cutoff_datetime,
        current_cutoff_datetime,
        uber_filter=None
):
    print(">>> MATERIALIZE (STATE MODE)")

    # ---------------------------------------------
    # EXTRACT STATE
    # ---------------------------------------------
    prior_rows = extract_structural(prior_state, uber_filter)
    current_rows = extract_structural(current_state, uber_filter)

    opening_map = {}
    closing_map = {}

    # ---------------------------------------------
    # INDEX STATE (DICT ACCESS ONLY)
    # ---------------------------------------------
    for r in prior_rows:
        key = (
            r["investment"],
            r["lotid"],
            r["tax_date"],
            r["location"],
            r["ls"],
            r["financial_account"],
        )
        opening_map[key] = r

    for r in current_rows:
        key = (
            r["investment"],
            r["lotid"],
            r["tax_date"],
            r["location"],
            r["ls"],
            r["financial_account"],
        )
        closing_map[key] = r

    keys = set(opening_map) | set(closing_map)

    balances = {}

    # ---------------------------------------------
    # STATE → OPEN / Δ / CLOSE
    # ---------------------------------------------
    for k in keys:
        o = opening_map.get(k, {"quantity": 0.0, "local": 0.0, "book": 0.0})
        c = closing_map.get(k, {"quantity": 0.0, "local": 0.0, "book": 0.0})

        balances[k] = {
            "opening_qty": o.get("quantity", 0.0),
            "opening_local": o.get("local", 0.0),
            "opening_book": o.get("book", 0.0),

            "movement_qty": c.get("quantity", 0.0) - o.get("quantity", 0.0),
            "movement_local": c.get("local", 0.0) - o.get("local", 0.0),
            "movement_book": c.get("book", 0.0) - o.get("book", 0.0),

            "closing_qty": c.get("quantity", 0.0),
            "closing_local": c.get("local", 0.0),
            "closing_book": c.get("book", 0.0),

            "je_lines": []
        }

    # ---------------------------------------------
    # ATTACH JOURNALS (OBJECT ACCESS ONLY)
    # ---------------------------------------------
    for je in journal_entries:

        # ---------------------------------
        # FILTER BY INVESTMENT
        # ---------------------------------
        if uber_filter:
            if getattr(je, "investment", None) != uber_filter.get("investment"):
                continue

        # ---------------------------------
        # FILTER BY IBOR DATE (CRITICAL FIX)
        # ---------------------------------
        je_ibor = getattr(je, "ibor_date", None)

        if not je_ibor:
            continue

        if not (prior_cutoff_datetime < je_ibor <= current_cutoff_datetime):
            continue

        # ---------------------------------
        # BUILD EXACT KEY (NO FUZZY MATCH)
        # ---------------------------------
        je_key = (
            getattr(je, "investment", None),
            getattr(je, "lotid", None),
            getattr(je, "tax_date", None),
            getattr(je, "location", None),
            getattr(je, "ls", None),
            getattr(je, "financial_account", None),
        )

        # ---------------------------------
        # ONLY ATTACH IF KEY EXISTS
        # ---------------------------------
        if je_key not in balances:
            continue

        # ---------------------------------
        # APPEND JE LINE
        # ---------------------------------
        balances[je_key]["je_lines"].append({
            "ibor_date": getattr(je, "ibor_date", None),
            "trade_date": getattr(je, "tradedate", None),
            "settle_date": getattr(je, "settledate", None),
            "sequence": getattr(je, "sequence", 0),

            "qty": getattr(je, "quantity", 0.0),
            "local": getattr(je, "local", 0.0),
            "book": getattr(je, "book", 0.0),

            "transaction": getattr(je, "transaction", None),

            "lotid": getattr(je, "lotid", None),
            "tax_date": getattr(je, "tax_date", None),

            "is_ppa": getattr(je, "adjustment", False)
        })

    # ---------------------------------------------
    # SORT JE LINES (TIME ORDER)
    # ---------------------------------------------
    for b in balances.values():
        b["je_lines"].sort(
            key=lambda x: (
                x["ibor_date"],
                x["sequence"]
            )
        )

    return balances

# ==========================================
# PREP (UNCHANGED)
# ==========================================
def prep_state(portfolio, calendar, period_start, period_end):
    from pathlib import Path
    import pickle
    from datetime import datetime
    import calendar as cal

    base_dir = Path("C:/Users/hjmne/PycharmProjects/chest/funds") / portfolio / "Calendars" / calendar
    snapshots_dir = base_dir / "Snapshots"
    journals_dir = base_dir / "Journals"

    period_map = {}

    # ------------------------------------------------------------
    # HELPER: period name
    # ------------------------------------------------------------
    def pname(dt):
        return f"{dt.year}-{dt.month:02d}"

    # ------------------------------------------------------------
    # BUILD SNAPSHOT MAP
    # ------------------------------------------------------------
    for snap in snapshots_dir.glob("*.pkl"):
        try:
            dt = datetime.strptime(snap.stem.split("T")[0], "%Y-%m-%d")
            period_map[pname(dt)] = snap
        except:
            continue

    periods = sorted(period_map.keys())

    if period_start not in periods or period_end not in periods:
        raise ValueError("Period start/end not found in snapshots")

    si = periods.index(period_start)
    ei = periods.index(period_end)

    # ------------------------------------------------------------
    # LOAD PRIOR STATE
    # ------------------------------------------------------------
    prior_state = None
    prior_cutoff_datetime = None

    if si > 0:
        prior_period = periods[si - 1]

        with open(period_map[prior_period], "rb") as f:
            prior_state = pickle.load(f)["state"]

        # build cutoff timestamp (end of prior month)
        prior_dt = datetime.strptime(prior_period + "-01", "%Y-%m-%d")
        last_day = cal.monthrange(prior_dt.year, prior_dt.month)[1]

        prior_cutoff_datetime = prior_dt.replace(
            day=last_day,
            hour=23,
            minute=59,
            second=59
        )

    # ------------------------------------------------------------
    # LOAD CURRENT STATE
    # ------------------------------------------------------------
    with open(period_map[period_end], "rb") as f:
        current_state = pickle.load(f)["state"]

    # build cutoff timestamp (end of current month)
    current_dt = datetime.strptime(period_end + "-01", "%Y-%m-%d")
    last_day = cal.monthrange(current_dt.year, current_dt.month)[1]

    current_cutoff_datetime = current_dt.replace(
        day=last_day,
        hour=23,
        minute=59,
        second=59
    )

    # ------------------------------------------------------------
    # LOAD JOURNALS (range)
    # ------------------------------------------------------------
    journals = []

    for i in range(si, ei + 1):
        stub = period_map[periods[i]].stem

        for suffix in ["regular", "adjusting"]:
            fpath = journals_dir / f"{stub}.{suffix}.pkl"

            if fpath.exists():
                data = pickle.load(open(fpath, "rb"))

                if isinstance(data, dict) and "journals" in data:
                    journals.extend(data["journals"])

    print(">>> TOTAL JOURNALS:", len(journals))

    # ------------------------------------------------------------
    # RETURN PREP PACKAGE
    # ------------------------------------------------------------
    return {
        "prior_state": prior_state,
        "current_state": current_state,
        "journal_entries": journals,
        "prior_cutoff_datetime": prior_cutoff_datetime,
        "current_cutoff_datetime": current_cutoff_datetime,
    }

# ==========================================
# COMPUTE
# ==========================================
def compute_ledger(prep, uber_filter=None):
    balances = materialize_box_state(
        prep["prior_state"],
        prep["current_state"],
        prep["journal_entries"],
        prep["prior_cutoff_datetime"],
        prep["current_cutoff_datetime"],
        uber_filter
    )

    df = render_ledger(
        balances,
        prep["prior_cutoff_datetime"],
        prep["current_cutoff_datetime"],
        print_output=True
    )

    return df


def render_ledger(
        balances,
        prior_cutoff_datetime,
        current_cutoff_datetime,
        print_output=True
):
    import pandas as pd

    rows = []

    for (inv, lotid, tax_date, loc, ls, fa), b in balances.items():

        # OPENING (synthetic IBOR)
        rows.append({
            "IBOR_Date": prior_cutoff_datetime,
            "EventType": "OPENING",
            "Investment": inv,
            "LotID": lotid,
            "TaxDate": tax_date,
            "Location": loc,
            "LS": ls,
            "FinancialAccount": fa,
            "Qty": b.get("opening_qty", 0.0),
            "Local": b.get("opening_local", 0.0),
            "Book": b.get("opening_book", 0.0),
            "Transaction": None,
            "Sequence": -1,
        })

        # ACTIVITY
        for je in b["je_lines"]:
            rows.append({
                "IBOR_Date": je.get("ibor_date"),
                "EventType": "ACTIVITY",
                "Investment": inv,
                "LotID": je.get("lotid"),
                "TaxDate": je.get("tax_date"),
                "Location": loc,
                "LS": ls,
                "FinancialAccount": fa,
                "Qty": je.get("qty", 0.0),
                "Local": je.get("local", 0.0),
                "Book": je.get("book", 0.0),
                "Transaction": je.get("transaction"),
                "Sequence": je.get("sequence", 0),
            })

        # CLOSING (synthetic IBOR)
        rows.append({
            "IBOR_Date": current_cutoff_datetime,
            "EventType": "CLOSING",
            "Investment": inv,
            "LotID": lotid,
            "TaxDate": tax_date,
            "Location": loc,
            "LS": ls,
            "FinancialAccount": fa,
            "Qty": b.get("closing_qty", 0.0),
            "Local": b.get("closing_local", 0.0),
            "Book": b.get("closing_book", 0.0),
            "Transaction": None,
            "Sequence": 999999,
        })

    df = pd.DataFrame(rows)

    df["IBOR_Date"] = pd.to_datetime(df["IBOR_Date"], errors="coerce")

    df = df.sort_values(by=["Investment", "IBOR_Date", "Sequence"])

    df = df[
        [
            "IBOR_Date",
            "EventType",
            "Investment",
            "LotID",
            "TaxDate",
            "Location",
            "LS",
            "FinancialAccount",
            "Qty",
            "Local",
            "Book",
            "Transaction",
        ]
    ]

    if print_output:
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 100000)
        print(df.to_string(index=False))

    return df

# ==========================================
# MAIN
# ==========================================
def main():

    portfolio = "Portfolio1"
    calendar = "Monthly"
    period_start = "2025-12"
    period_end = "2025-12"

    uber_filter = {"investment": "ZTS"}

    prep = prep_state(portfolio, calendar, period_start, period_end)

    df = compute_ledger(prep, uber_filter)


if __name__ == "__main__":
    main()