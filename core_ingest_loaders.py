from utilities import load_fx_data_as_rows, load_price_data_as_rows

print("IMPORTING core ingest loaders")

HARD_CODED_CURRENCIES = {
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "CHF",
}

import os
import csv
import utilities
from business_days import generate_business_days, get_previous_business_day, get_next_business_day
import datetime
import bond_domain

class GlobalRefData:
    def __init__(self):
        # investment -> {date: price}
        self.prices_by_investment = {}

        # investment -> {date: fx}
        self.fx_by_investment = {}


    # # 2) SOFT WARNING: non-business-day prices
    # bday_set = set(business_days)
    # warned = set()
    # for r in price_rows:
    #     if r["date"] not in bday_set:
    #         key = (r["ticker"], r["date"])
    #         if key not in warned:
    #             print(
    #                 f"[PRICE WARNING] Non-business-day price ignored for valuation: "
    #                 f"{r['ticker']} @ {r['date']}"
    #             )
    #             warned.add(key)

# ========================================================
# 1) BUILD PORTFOLIO INVESTMENT MASTER (MPDB)
# ========================================================


def build_portfolio_investment_master(portfolio: str, candidate_investments: set):
    base = "C:/Users/hjmne/PycharmProjects/chest"

    global_im_path = f"{base}/refdata/investment_master.csv"
    portfolio_dir = f"{base}/funds/{portfolio}/RefData"
    portfolio_im_path = f"{portfolio_dir}/investment_master.csv"

    os.makedirs(portfolio_dir, exist_ok=True)

    print(f"\n[IM] Global IM path     : {global_im_path}")
    print(f"[IM] Portfolio IM path  : {portfolio_im_path}")

    # ---- Global IM must exist or we stop (this is the ONLY hard stop)
    if not os.path.isfile(global_im_path):
        print("❌ Global investment_master.csv NOT FOUND")
        return

    # ---- Load existing portfolio IM (if it exists)
    existing = set()
    if os.path.isfile(portfolio_im_path):
        with open(portfolio_im_path, newline="") as f:
            rows = list(csv.DictReader(f))
            if rows:
                existing = {r["investment"] for r in rows if r.get("investment")}
            else:
                print("⚠️ Portfolio IM exists but is EMPTY")

    needed = candidate_investments - existing
    if not needed:
        print("✅ No new investments needed for portfolio IM")
        return

    # ---- Load from global IM
    with open(global_im_path, newline="") as f:
        global_rows = list(csv.DictReader(f))

    global_map = {r.get("investment"): r for r in global_rows if r.get("investment")}
    missing = needed - global_map.keys()

    if missing:
        print(f"❌ These investments are NOT in global IM: {sorted(missing)}")
        return   # DO NOT RAISE

    write_header = not os.path.isfile(portfolio_im_path)

    with open(portfolio_im_path, "a", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(next(iter(global_map.values())).keys())
        )
        if write_header:
            writer.writeheader()

        for inv in sorted(needed):
            writer.writerow(global_map[inv])

    print(f"✅ Appended {len(needed)} investments to portfolio IM")


import os
import csv

def build_portfolio_bond_info(portfolio: str):
    base = "C:/Users/hjmne/PycharmProjects/chest"

    global_bond_path = f"{base}/refdata/bond_info.csv"
    portfolio_dir = f"{base}/funds/{portfolio}/RefData"
    portfolio_im_path = f"{portfolio_dir}/investment_master.csv"
    portfolio_bond_path = f"{portfolio_dir}/bond_info.csv"

    print(f"\n[BOND] Portfolio IM path : {portfolio_im_path}")
    print(f"[BOND] Bond info path    : {portfolio_bond_path}")

    if not os.path.isfile(portfolio_im_path):
        print("⚠️ Portfolio IM not present — skipping bond ingestion")
        return

    if not os.path.isfile(global_bond_path):
        print("⚠️ Global bond_info.csv not present — skipping")
        return

    with open(portfolio_im_path, newline="") as f:
        im_rows = list(csv.DictReader(f))

    bonds = {
        r["investment"]
        for r in im_rows
        if (r.get("investment_type") or r.get("Investment_Type") or "").upper() == "BOND"
    }

    if not bonds:
        print("ℹ️ No bonds found in portfolio IM")
        return

    existing = set()
    if os.path.isfile(portfolio_bond_path):
        with open(portfolio_bond_path, newline="") as f:
            existing = {
                r["investment"] for r in csv.DictReader(f) if r.get("investment")
            }

    needed = bonds - existing
    if not needed:
        print("✅ Bond info already complete")
        return

    with open(global_bond_path, newline="") as f:
        global_bonds = list(csv.DictReader(f))

    bond_map = {r["investment"]: r for r in global_bonds if r.get("investment")}
    missing = needed - bond_map.keys()

    if missing:
        print(f"❌ Missing bond_info rows for: {sorted(missing)}")
        return

    write_header = not os.path.isfile(portfolio_bond_path)

    with open(portfolio_bond_path, "a", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(next(iter(bond_map.values())).keys())
        )
        if write_header:
            writer.writeheader()

        for inv in sorted(needed):
            writer.writerow(bond_map[inv])

    print(f"✅ Appended {len(needed)} bond rows")


# ========================================================
# 3) LOAD AIFS FROM PORTFOLIO IM
def load_aifs_from_portfolio_im(space, portfolio: str):
    """
    Load AIFs from portfolio investment_master.csv
    """

    print("AIF load repo id:", id(space))

    portfolio_im_path = (
        f"C:/Users/hjmne/PycharmProjects/chest/"
        f"funds/{portfolio}/RefData/investment_master.csv"
    )

    print(f"\n[AIF] Loading portfolio AIFs")
    print(f"[AIF] Source file: {portfolio_im_path}")

    if not os.path.exists(portfolio_im_path):
        print("[AIF] ⚠️ investment_master.csv not found — skipping")
        return

    repo = space.asset_liability_repository
    skipped_fields = set()

    investment_count = 0
    field_count = 0

    with open(portfolio_im_path, newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("[AIF] ⚠️ investment_master.csv is empty")
        return

    for r in rows:
        inv = r.get("investment")
        if not inv:
            continue

        investment_count += 1

        for field, value in r.items():
            if field == "investment":
                continue
            if value in ("", None):
                continue

            # 🔒 SCHEMA GUARD — SKIP NON-AIF COLUMNS
            if field not in repo.allowed_aifs:
                skipped_fields.add(field)
                continue

            space.set_investment_attribute(
                investment=inv,
                field_type="AIF",
                attribute=field,
                value=value
            )
            field_count += 1

    if skipped_fields:
        print(
            f"[AIF] ℹ️ Skipped non-AIF columns: {sorted(skipped_fields)}"
        )

    print(
        f"[AIF] ✅ Loaded AIFs for {investment_count} investments "
        f"({field_count} fields applied)"
    )

def load_bond_aifs(space, portfolio: str):
    """
    Load bond AIFs from portfolio bond_info.csv
    """

    portfolio_bond_path = (
        f"C:/Users/hjmne/PycharmProjects/chest/"
        f"funds/{portfolio}/RefData/bond_info.csv"
    )

    print(f"\n[AIF] Loading bond AIFs")
    print(f"[AIF] Source file: {portfolio_bond_path}")

    if not os.path.exists(portfolio_bond_path):
        print("[AIF] ℹ️ No bond_info.csv found — skipping")
        return

    repo = space.asset_liability_repository
    skipped_fields = set()

    investment_count = 0
    field_count = 0

    with open(portfolio_bond_path, newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("[AIF] ⚠️ bond_info.csv is empty")
        return

    for r in rows:
        inv = r.get("investment")
        if not inv:
            continue

        investment_count += 1

        for field, value in r.items():
            if field == "investment":
                continue
            if value in ("", None):
                continue

            if field not in repo.allowed_aifs:
                skipped_fields.add(field)
                continue

            space.set_investment_attribute(
                investment=inv,
                field_type="AIF",
                attribute=field,
                value=value
            )
            field_count += 1

    if skipped_fields:
        print(
            f"[AIF] ℹ️ Skipped non-AIF bond columns: {sorted(skipped_fields)}"
        )

    print(
        f"[AIF] ✅ Loaded bond AIFs for {investment_count} investments "
        f"({field_count} fields applied)"
    )

import os
import csv

def _csv_serialize_row(row: dict) -> dict:
    from datetime import datetime

    out = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.strftime("%Y-%m-%d:%H:%M:%S")
        else:
            out[k] = v
    return out
from datetime import datetime

def csv_safe(row: dict) -> dict:
    return {
        k: (v.strftime("%Y-%m-%d:%H:%M:%S") if isinstance(v, datetime) else v)
        for k, v in row.items()
    }

from collections import defaultdict
from datetime import date

def derive_position_windows(events, current_period_cutoff):
    """
    Returns:
        dict[str, tuple[start_date, end_date_or_None]]
    Position-level windows, portfolio scoped.
    """

    position_qty = defaultdict(float)
    first_open = {}
    last_close = {}

    # events are already portfolio-filtered
    # sort by tradedate ASC to get clean transitions
    events_sorted = sorted(events, key=lambda e: e["tradedate"])

    for e in events_sorted:
        inv = e["investment"]
        td = e["tradedate"]
        qty = e.get("quantity", 0)

        prev_qty = position_qty[inv]
        new_qty = prev_qty + qty
        position_qty[inv] = new_qty

        # open window
        if prev_qty == 0 and new_qty != 0:
            if inv not in first_open:
                first_open[inv] = td

        # close window
        if prev_qty != 0 and new_qty == 0:
            last_close[inv] = td

    windows = {}
    for inv, start in first_open.items():
        end = last_close.get(inv)  # None if still open
        windows[inv] = (start, end)

    return windows


def create_portfolio_marks(
        *,
        portfolio: str,
        candidates: dict,  # {(portfolio, investment): first_trade_date}
        history_start,
        history_end,
):
    """
    CREATE FULL PORTFOLIO MARKS

    - Pure historical fact generation
    - No period semantics
    - Append only — never rebuilds existing rows
    - Schema matches main events file exactly
    - Two separate event rows per business day for bond investments:
        1. mark_prices        — price and FX for all investments
        2. mark_bond_accruals — accrual per 100 FV for bonds only
    """

    import os
    import csv
    from datetime import datetime

    import utilities
    from business_days import generate_business_days
    from kernel_utilities import (
        fx_rows_to_app,
        price_rows_to_app,
        app_event_to_events_csv_row,
    )
    import bond_calc

    MARK_TRANID_START = 100_000_000
    tranid = MARK_TRANID_START

    # ==================================================
    # SCHEMA — must match ops_routes.py EVENT_COLUMNS exactly
    # ==================================================

    EVENT_COLUMNS = [
        "portfolio", "method", "source", "tradedate", "settledate",
        "kdbegin", "kdend", "investment", "payment_currency", "tdate_fx",
        "location", "strategy", "quantity", "price", "notional",
        "original_face", "total_amount", "total_amount_base", "tranid",
        "transaction", "accrued_local", "accrued_book", "new_shares",
        "old_shares", "per_share", "legin", "legout",
        "allocation_entities", "allocation_percents", "financial_account",
        "buy_currency", "sell_currency", "buy_amt", "sell_amt",
        "feeder", "put_call", "mark_price", "mark_fx",
        "per_100FV_accrue", "per_100FV_amort", "closing_method",
    ]

    base_path = "C:/Users/hjmne/PycharmProjects/chest"
    fx_path = f"{base_path}/refdata/fx_master.csv"
    price_path = f"{base_path}/refdata/price_master.csv"
    bond_info_path = f"{base_path}/funds/{portfolio}/RefData/bond_info.csv"

    if not os.path.exists(bond_info_path):
        bond_info_path = f"{base_path}/refdata/bond_info.csv"

    marks_dir = f"{base_path}/funds/{portfolio}/Events"
    marks_path = f"{marks_dir}/{portfolio}_marks.csv"

    os.makedirs(marks_dir, exist_ok=True)

    # ==================================================
    # REBUILD FILE — header only
    # ==================================================

    with open(marks_path, "w", newline="") as f:
        csv.DictWriter(f, fieldnames=EVENT_COLUMNS).writeheader()

    # ==================================================
    # LOAD REF DATA (ONCE)
    # ==================================================

    fx_rows_raw = utilities.load_fx_data_as_rows(fx_path)
    price_rows_raw = utilities.load_price_data_as_rows(price_path)

    fx_data = fx_rows_to_app(fx_rows_raw, context="create_portfolio_marks")
    price_data_raw = price_rows_to_app(price_rows_raw, context="create_portfolio_marks")

    price_lookup = {
        (r["ticker"], r["date"]): r
        for r in price_data_raw
    }

    fx_lookup = {
        (r["currency"], r["date"]): r["price"]
        for r in fx_data
    }

    # ==================================================
    # LOAD BOND INFO (ONCE)
    # ==================================================

    bond_info_lookup = {}

    if os.path.exists(bond_info_path):
        with open(bond_info_path, newline="") as f:
            for row in csv.DictReader(f):
                inv = row.get("investment", "").strip()
                if inv:
                    bond_info_lookup[inv] = row
        print(f"    Marks: loaded bond info for {len(bond_info_lookup)} bond(s)")

    # ==================================================
    # GENERATE MARKS (GLOBAL WINDOW)
    # ==================================================

    business_days = generate_business_days(history_start, history_end)
    rows = []

    for (_, investment), first_open in candidates.items():

        window_start = max(first_open, history_start)
        bond_info = bond_info_lookup.get(investment)
        is_bond = bond_info is not None

        for trade_dt in business_days:
            if trade_dt < window_start:
                continue

            price = price_lookup.get((investment, trade_dt))
            if price is None:
                continue

            fx = fx_lookup.get((price["currency"], trade_dt))
            if fx is None:
                continue

            # ── ROW 1 — PRICE MARK (all investments) ──────────────
            tranid += 1

            rows.append({
                "portfolio": portfolio,
                "method": "mark_prices",
                "source": "mark",
                "tradedate": trade_dt,
                "settledate": trade_dt,
                "kdbegin": trade_dt,
                "kdend": datetime(2099, 12, 31),
                "investment": investment,
                "payment_currency": price["currency"],
                "tdate_fx": 0,
                "location": "",
                "strategy": "",
                "quantity": 0,
                "price": "",
                "notional": 0,
                "original_face": 0,
                "total_amount": 0,
                "total_amount_base": 0,
                "tranid": tranid,
                "transaction": "Price Mark",
                "accrued_local": 0,
                "accrued_book": 0,
                "new_shares": 0,
                "old_shares": 0,
                "per_share": 0,
                "legin": "",
                "legout": "",
                "allocation_entities": "",
                "allocation_percents": "",
                "financial_account": "",
                "buy_currency": "",
                "sell_currency": "",
                "buy_amt": 0,
                "sell_amt": 0,
                "feeder": "",
                "put_call": "",
                "mark_price": price["price"],
                "mark_fx": fx,
                "per_100FV_accrue": "",
                "per_100FV_amort": "",
                "closing_method": "",
            })

            # ── ROW 2 — ACCRUAL MARK (bonds only) ─────────────────
            if is_bond:
                per_100FV_accrue = ""
                try:
                    settle_str = trade_dt.strftime("%m/%d/%Y")
                    result = bond_calc.calculate_accrued_interest(
                        issue_date=bond_info.get("issue_date", ""),
                        first_coupon_date=bond_info.get("first_coupon_date", ""),
                        maturity_date=bond_info.get("maturity_date", ""),
                        settlement_date=settle_str,
                        coupon_rate=float(bond_info.get("coupon_rate", 0)),
                        payment_frequency=bond_info.get("payment_frequency", "SEMI_ANNUAL"),
                        day_count_convention=bond_info.get("day_count_convention", "30E/360"),
                        face_value=float(bond_info.get("face_value", 100)),
                    )
                    per_100FV_accrue = result["daily_per_100"]
                except Exception as e:
                    print(f"    Marks: bond accrual calc failed for {investment} on {trade_dt}: {e}")

                if per_100FV_accrue != "":
                    tranid += 1
                    rows.append({
                        "portfolio": portfolio,
                        "method": "mark_bond_accruals",
                        "source": "mark",
                        "tradedate": trade_dt,
                        "settledate": trade_dt,
                        "kdbegin": trade_dt,
                        "kdend": datetime(2099, 12, 31),
                        "investment": investment,
                        "payment_currency": price["currency"],
                        "tdate_fx": 0,
                        "location": "",
                        "strategy": "",
                        "quantity": 0,
                        "price": "",
                        "notional": 0,
                        "original_face": 0,
                        "total_amount": 0,
                        "total_amount_base": 0,
                        "tranid": tranid,
                        "transaction": "Bond Accrual",
                        "accrued_local": 0,
                        "accrued_book": 0,
                        "new_shares": 0,
                        "old_shares": 0,
                        "per_share": 0,
                        "legin": "",
                        "legout": "",
                        "allocation_entities": "",
                        "allocation_percents": "",
                        "financial_account": "",
                        "buy_currency": "",
                        "sell_currency": "",
                        "buy_amt": 0,
                        "sell_amt": 0,
                        "feeder": "",
                        "put_call": "",
                        "mark_price": "",
                        "mark_fx": fx,
                        "per_100FV_accrue": per_100FV_accrue,
                        "per_100FV_amort": "",
                        "closing_method": "",
                    })

    # ==================================================
    # WRITE ONCE
    # ==================================================

    if rows:
        csv_rows = [app_event_to_events_csv_row(r) for r in rows]
        with open(marks_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=EVENT_COLUMNS)
            writer.writerows(csv_rows)

    return len(rows)
