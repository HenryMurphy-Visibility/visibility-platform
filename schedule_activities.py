# =======================================================================
#   schedule_activities.py
#   Marks + Coupons + Candidate Building
# =======================================================================

import os
from datetime import datetime, timedelta
import pandas as pd

from business_days import (
    generate_business_days,
    is_non_business_day
)

import utilities
import bond_domain
import bond_calc
from bookkeeping import SecurityInformationRepository

def parse_any_date(value):
    """
    Safely convert value to datetime whether value is:
    - pandas Timestamp
    - already a datetime
    - string in known formats
    """
    if isinstance(value, datetime):
        return value

    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()

    if isinstance(value, str):
        fmts = [
            "%m/%d/%Y:%H:%M:%S",
            "%Y-%m-%d:%H:%M:%S",
            "%Y-%m-%d",
            "%m/%d/%Y",
        ]
        for f in fmts:
            try:
                return datetime.strptime(value.strip(), f)
            except Exception:
                continue

    raise TypeError(f"Unsupported date format: {value}")

# =======================================================================
# 🔹 BUILD CANDIDATES (used by marks + coupons)
# =======================================================================

def build_candidates(retrieved_events_records, period_end):
    """
    Build mapping:
        (portfolio, investment) → first tradedate
    """
    candidates = {}
    details_list = []

    for er in retrieved_events_records:
        tradedate = parse_any_date(er["tradedate"])

        if tradedate > period_end:
            continue

        inv = er["investment"]
        port = er["portfolio"]
        key = (port, inv)

        if key not in candidates:
            candidates[key] = tradedate

    return candidates


# =======================================================================
# 🔹 BUILD BOND CANDIDATES
# =======================================================================

def build_bond_candidates(retrieved_events_records, period_end, space):
    """
    Same as build_candidates but filters to investment_type == BOND.
    """
    candidates = {}

    def parse_date(date_str):
        if isinstance(date_str, datetime):
            return date_str
        fmts = [
            "%Y-%m-%d:%H:%M:%S", "%m/%d/%Y:%H:%M:%S",
            "%Y-%m-%d", "%m/%d/%Y"
        ]
        for f in fmts:
            try:
                return datetime.strptime(date_str.strip(), f)
            except:
                continue
        raise ValueError(f"Unrecognized date: {date_str}")

    for er in retrieved_events_records:
        tradedate = parse_date(er["tradedate"])
        if tradedate > period_end:
            continue

        inv = er["investment"]
        port = er["portfolio"]
        itype = space.get_attribute_field(inv, "AIF", "Investment_Type")

        if itype == "BOND":
            key = (port, inv)
            if key not in candidates:
                candidates[key] = tradedate

    return candidates

def assert_aif_available(space, investment):
    sub = space.asset_liability_repository.get_position_space(investment)

    missing = []
    for field in ("Currency", "Investment_Type", "Pricing_Factor"):
        if sub.get_attribute_field("AIF", field) is None:
            missing.append(field)

    if missing:
        raise RuntimeError(
            f"AIF missing for {investment}: {missing}"
        )

import pandas as pd
import os

def initialize_marks_file(marks_path):
    df = pd.DataFrame(columns=EVENT_COLUMNS)
    df.to_csv(marks_path, index=False)

# =======================================================================
# 🔹 MARK GENERATION — FROM SCRATCH (ENGINE-ALIGNED, NEW OUTPUT FORMAT)
# =======================================================================

def marks_from_scratch(
    portfolio,
    candidates,
    period_start,
    period_end,
    space,
    price_data,
    fx_data,
    scheduler=None,
    stat_repo=None,
    smf=None,
):
    """
    CREATE mark EVENTS from scratch for a portfolio.

    Truth model:
      • Marks are EVENTS
      • Events carry valuation inputs only
      • Position resolution happens at rule execution time

    Output:
      • CSV for persistence / replay
      • (Optional) scheduled events if scheduler provided
    """

    import pandas as pd
    from business_days import generate_business_days
    from datetime import datetime

    marks_path = (
        f"C:/Users/hjmne/PycharmProjects/chest/funds/"
        f"{portfolio}/Events/{portfolio}_marks.csv"
    )

    rows = []
    business_days = generate_business_days(period_start, period_end)

    for (port, inv), first_trade_date in candidates.items():

        # --------------------------------------------------
        # Validate required AIF metadata (NO POSITION USE)
        # --------------------------------------------------
        currency = space.get_attribute_field(inv, "AIF", "currency")
        itype = space.get_attribute_field(inv, "AIF", "investment_type")
        pricing_factor = space.get_attribute_field(inv, "AIF", "pricing_factor")

        if None in (currency, itype, pricing_factor):
            continue

        for bd in business_days:
            if bd < first_trade_date:
                continue

            # --------------------------------------------------
            # Resolve valuation inputs
            # --------------------------------------------------
            price = utilities.get_price(inv, bd, price_data)
            if price is None:
                continue

            try:
                fx = utilities.get_fx_rate(currency, bd, fx_data)
            except Exception:
                continue

            # --------------------------------------------------
            # Canonical Visibility event dates
            # --------------------------------------------------
            ts = bd.strftime("%Y-%m-%d:00:00:00")

            trade_dt = bd.strftime("%Y-%m-%d:00:00:00")
            kd_end = "2099-12-31:23:59:59"

            rows.append({
                "portfolio": port,
                "method": "mark",
                "transaction": "Mark",
                "tranid": 0,

                "tradedate": trade_dt,
                "settledate": trade_dt,
                "kdbegin": trade_dt,
                "kdend": kd_end,
                "knowledge_date": trade_dt,

                "investment": inv,
                "payment_currency": currency,

                "quantity": 0,
                "price": "",
                "notional": 0,
                "original_face": 0,
                "total_amount": 0,
                "total_amount_base": 0,
                "local": 0,
                "book": 0,
                "accrued_local": 0,
                "accrued_book": 0,

                "new_shares": 0,
                "old_shares": 0,
                "per_share": 0,
                "buy_amt": 0,
                "sell_amt": 0,
                "buy_currency": "",
                "sell_currency": "",

                "legin": "",
                "legout": "",
                "allocation_entities": "",
                "allocation_percents": "",
                "financial_account": "",
                "location": "",
                "strategy": "",

                "last_updated": trade_dt,
                "source": "mark",

                # ---- MARK EXTENSIONS ----
                "mark_price": price,
                "mark_fx": fx,
                "mark_100FV_accrue": "",
                "mark_100FV_amort": "",
            })

            # --------------------------------------------------
            # OPTIONAL: schedule immediately
            # --------------------------------------------------
            if scheduler is not None:
                scheduler.schedule_event(
                    bd,
                    "mark_prices",
                    event,
                    space,
                    stat_repo,
                    smf,
                )

    # ----------------------------------------------------------
    # Persist marks as EVENTS
    # ----------------------------------------------------------
    df = pd.DataFrame(rows)
    df.to_csv(marks_path, index=False)

    print(f"✔ Marks generated from scratch: {marks_path}")
    print(f"✔ Total mark events written: {len(df):,}")

    return marks_path

def marks_append(portfolio, candidates, period_start, period_end,
                 space, price_data, fx_data):
    """
    APPEND new marks to existing file — system auto-detects last MarkDate.
    """

    marks_path = f"C:/Users/hjmne/PycharmProjects/chest/funds/{portfolio}/Events/{portfolio}_marks.csv"

    if not os.path.exists(marks_path):
        print("⚠ No existing marks file — switching to marks_from_scratch.")
        return marks_from_scratch(
            portfolio, candidates, period_start, period_end,
            space, price_data, fx_data
        )

    df_old = pd.read_csv(marks_path, parse_dates=["MarkDate"])
    last_date = df_old["MarkDate"].max()
    append_start = last_date + timedelta(days=1)

    print(f"Appending marks beginning {append_start.date()}…")

    business_days = generate_business_days(append_start, period_end)

    rows = []
    for (port, inv), tradedate in candidates.items():

        sub = space.asset_liability_repository.get_position_space(inv)
        currency = sub.get_attribute_field("AIF", "Currency")
        itype = sub.get_attribute_field("AIF", "Investment_Type")

        if currency is None:
            continue

        for bd in business_days:
            price = utilities.get_price(inv, bd, price_data)
            try:
                fx = utilities.get_fx_rate(currency, bd, fx_data)
            except:
                continue

            row = {
                "MarkDate": bd.strftime("%Y-%m-%d"),
                "Portfolio": port,
                "Investment": inv,
                "Price": price,
                "FXRate": fx,
                "Per100FV": "",
                "Per100FV_Amor": "",
            }
            rows.append(row)

    df_new = pd.DataFrame(rows)
    df_all = pd.concat([df_old, df_new], ignore_index=True)

    df_all.to_csv(marks_path, index=False)
    print(f"✔ Appended {len(df_new)} rows → {marks_path}")

    return marks_path


# =======================================================================
# 🔹 AUTO-GENERATED MARK EVENTS (uses marks file)
# =======================================================================

def load_mark_events_into_scheduler(scheduler, portfolio, space, stat_repo,
                                    smf, period_cutoff):
    """
    Reads the marks CSV and schedules mark_prices + bond accrual events.
    """

    path = f"C:/Users/hjmne/PycharmProjects/chest/funds/{portfolio}/Events/{portfolio}_marks.csv"
    if not os.path.exists(path):
        print(f"⚠ No marks file found for {portfolio}.")
        return

    df = pd.read_csv(path, parse_dates=["MarkDate"])
    df = df[df["MarkDate"] <= period_cutoff]

    from global_domain import mark_prices, mark_bond_accruals

    for _, row in df.iterrows():
        dt = row["MarkDate"]
        port = row["Portfolio"]
        inv = row["Investment"]
        price = row["Price"]
        fx = row["FXRate"]
        per100 = row.get("Per100FV", "")
        # amort unused but included
        per100_amor = row.get("Per100FV_Amor", "")

        scheduler.schedule_event(
            dt,
            mark_prices,
            port,
            inv,
            dt,
            stat_repo,
            space,
            price,
            fx,
            per100,
            smf,
            SecurityInformationRepository()
        )


# =======================================================================
# 🔹 COUPON SCHEDULING (UNCHANGED)
# =======================================================================

def schedule_bond_coupons(
    scheduler, bond_candidates, portfolio, investment,
     space, tranid, transaction,
    tradedate, settledate, period_start, period_end,
    payment_currency, per_share # smf
):

    if not bond_candidates:
        return

    business_days = generate_business_days(period_start, period_end)

    issue_date = space.get_attribute_field(investment, 'AIF', 'Issue_Date')
    maturity_date = space.get_attribute_field(investment, 'AIF', 'Maturity_Date')
    freq = space.get_attribute_field(investment, 'AIF', 'Payment_Frequency')
    coupon_rate = float(space.get_attribute_field(investment, 'AIF', 'Coupon_Rate'))

    issue_date = datetime.strptime(issue_date, "%m/%d/%Y")
    maturity_date = datetime.strptime(maturity_date, "%m/%d/%Y")

    # per-share payout depending on frequency
    if freq == 'annual':
        per_share = coupon_rate
    elif freq == 'semi-annual':
        per_share = coupon_rate / 2
    elif freq == 'quarterly':
        per_share = coupon_rate / 4
    elif freq == 'monthly':
        per_share = coupon_rate / 12
    else:
        raise ValueError(f"Unknown payment frequency: {freq}")

    coupon_dates = generate_coupon_dates(issue_date, maturity_date, freq, period_start, period_end)

    for cd in coupon_dates:
        scheduler.schedule_event(
            cd, bond_domain.bond_coupon, portfolio, investment,
             space, tranid, "BondCoupon",
            cd, settledate, period_start, period_end,
            payment_currency, per_share # smf
        )


def generate_coupon_dates(first_coupon_date, maturity_date, freq, period_start, period_end):
    cur = first_coupon_date
    cds = []

    while cur <= maturity_date and cur <= period_end:
        if cur >= period_start:
            cds.append(cur)

        if freq == "annual":
            cur += timedelta(days=365)
        elif freq == "semi-annual":
            cur += timedelta(days=182)
        elif freq == "quarterly":
            cur += timedelta(days=91)
        elif freq == "monthly":
            cur += timedelta(days=30)

    return cds
