# ============================================================
# Visibility — Compute Cash Trade Date Ledger
# compute_cash_trade_date.py
#
# Operational cash ledger, TRADE-DATE basis.
# "How much do I have to trade with, how much will I have."
#
# Scope: currency investments only (is_currency=1 in the investment
# master). Includes all JE lines that are NOT transaction=Settlement
# restricted to TRADE_DATE_CASH_ACCOUNTS (defined in
# compute_classifications.py -- single authoritative source shared
# with valuation reports and any other consumer that needs this
# account set).
#
# RUNNING BALANCE:
#   Computed in LOCAL (currency-native) terms as the primary
#   operational figure -- "how much actual currency do I have,"
#   not "what's it worth in dollars today." Book is carried
#   alongside for the base-currency view.
#
# Thin filter over compute_accounting_ledger -- same foundation
# every other report derives from. No new materialization path.
# ============================================================

import pandas as pd
from datetime import datetime, date as date_type, timedelta

from financial_information_gateway.fig_code.fig_core import prep_state_cached as prep_state
from financial_information_gateway.fig_code.compute_result import ComputeResult
from financial_information_gateway.fig_code.compute_accounting_ledger import (
    compute_accounting_ledger,
)
from financial_information_gateway.fig_code.compute_position_ledger import (
    _extract_al_positions_keep_zeros,
)
from financial_information_gateway.fig_code.compute_classifications import (
    TRADE_DATE_CASH_ACCOUNTS,
)


# ============================================================
# BUSINESS-DAY CALENDAR
# Ported from proof_engine.py's US_HOLIDAYS / _is_holiday_or_weekend.
# Single confirmed source for this calendar at the time this file
# was written -- if Visibility grows a shared business-day utility
# module later, repoint both this file and proof_engine.py to it
# rather than maintaining two copies.
# ============================================================

US_HOLIDAYS = {
    date_type(2019,1,1),date_type(2019,1,21),date_type(2019,2,18),date_type(2019,4,19),
    date_type(2019,5,27),date_type(2019,7,4),date_type(2019,9,2),date_type(2019,11,28),date_type(2019,12,25),
    date_type(2020,1,1),date_type(2020,1,20),date_type(2020,2,17),date_type(2020,4,10),
    date_type(2020,5,25),date_type(2020,7,3),date_type(2020,9,7),date_type(2020,11,26),date_type(2020,12,25),
    date_type(2021,1,1),date_type(2021,1,18),date_type(2021,2,15),date_type(2021,4,2),
    date_type(2021,5,31),date_type(2021,7,5),date_type(2021,9,6),date_type(2021,11,25),date_type(2021,12,24),
    date_type(2022,1,17),date_type(2022,2,21),date_type(2022,4,15),date_type(2022,5,30),
    date_type(2022,6,20),date_type(2022,7,4),date_type(2022,9,5),date_type(2022,11,24),date_type(2022,12,26),
    date_type(2023,1,2),date_type(2023,1,16),date_type(2023,2,20),date_type(2023,4,7),
    date_type(2023,5,29),date_type(2023,6,19),date_type(2023,7,4),date_type(2023,9,4),date_type(2023,11,23),date_type(2023,12,25),
    date_type(2024,1,1),date_type(2024,1,15),date_type(2024,2,19),date_type(2024,3,29),
    date_type(2024,5,27),date_type(2024,6,19),date_type(2024,7,4),date_type(2024,9,2),date_type(2024,11,28),date_type(2024,12,25),
    date_type(2025,1,1),date_type(2025,1,20),date_type(2025,2,17),date_type(2025,4,18),
    date_type(2025,5,26),date_type(2025,6,19),date_type(2025,7,4),date_type(2025,9,1),date_type(2025,11,27),date_type(2025,12,25),
    date_type(2026,1,1),date_type(2026,1,19),date_type(2026,2,16),date_type(2026,4,3),
    date_type(2026,5,25),date_type(2026,6,19),date_type(2026,7,3),date_type(2026,9,7),date_type(2026,11,26),date_type(2026,12,25),
    date_type(2027,1,1),date_type(2027,1,18),date_type(2027,2,15),date_type(2027,3,26),
    date_type(2027,5,31),date_type(2027,6,18),date_type(2027,7,5),date_type(2027,9,6),date_type(2027,11,25),date_type(2027,12,24),
}


def _is_holiday_or_weekend(d: date_type) -> bool:
    return d.weekday() >= 5 or d in US_HOLIDAYS


def _to_date(val) -> date_type:
    """
    Normalize a datetime/date/string to a date object. Returns None on
    failure OR on any null-like input (None, pd.NaT, NaN).

    pd.NaT must be checked explicitly: it is not None, not a datetime
    instance, not a date instance -- and pd.to_datetime(pd.NaT).date()
    returns NaT again rather than raising, so without this check NaT
    silently survives this function and breaks any downstream comparison
    (e.g. `sd <= ao` against a real date raises TypeError). Found via
    testing: any JE whose settle_date didn't resolve through the
    tranid-keyed lookup would have crashed the whole computation.
    """
    if val is None or pd.isna(val):
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date_type):
        return val
    try:
        parsed = pd.to_datetime(val)
        if pd.isna(parsed):
            return None
        return parsed.date()
    except Exception:
        return None


def business_days_between(start: date_type, end: date_type) -> int:
    """
    Count business days strictly between start and end (exclusive of
    start, inclusive of end), skipping weekends and US_HOLIDAYS.
    Returns a negative count if end < start.
    """
    if start is None or end is None:
        return None
    if end == start:
        return 0
    sign = 1 if end > start else -1
    lo, hi = (start, end) if end > start else (end, start)
    count = 0
    d = lo + timedelta(days=1)
    while d <= hi:
        if not _is_holiday_or_weekend(d):
            count += 1
        d += timedelta(days=1)
    return sign * count


def within_near_cash_horizon(settle_date, as_of_date, horizon_days: int) -> bool:
    """
    True if settle_date falls within horizon_days BUSINESS DAYS of
    as_of_date (inclusive). Already-settled (settle_date <= as_of_date)
    counts as within horizon -- it's not a future commitment anymore,
    it's effectively realized; excluding it would wrongly drop near-term
    cash that's about to (or already did) convert.
    """
    sd = _to_date(settle_date)
    ao = _to_date(as_of_date)
    if sd is None or ao is None:
        return False
    if sd <= ao:
        return True
    bd = business_days_between(ao, sd)
    return bd is not None and bd <= horizon_days


# ============================================================
# COMPUTE CASH TRADE DATE — PUBLIC INTERFACE
# ============================================================

def _rollup_trade_date_cash(lot_rows, currency_invs):
    """
    Roll AL-repo lot-level rows up to a SINGLE trade-date-cash number
    per currency investment: sum of local/book across every account in
    TRADE_DATE_CASH_ACCOUNTS, currency investments only. This is the
    real point-in-time balance operations people actually want --
    "what do I have," not an internal activity-only cumsum starting
    from zero.

    Returns {investment: {"local": x, "book": y}}.
    """
    acc = {}
    for r in lot_rows:
        inv = r.get("investment")
        if inv not in currency_invs:
            continue
        if r.get("financial_account") not in TRADE_DATE_CASH_ACCOUNTS:
            continue
        if inv not in acc:
            acc[inv] = {"local": 0.0, "book": 0.0}
        acc[inv]["local"] += r.get("local_cost", 0.0) or 0.0
        acc[inv]["book"]  += r.get("book_cost", 0.0) or 0.0
    return acc


def compute_cash_trade_date(
        portfolio,
        calendar,
        period_start,
        period_end,
        uber_filter=None,
        prep=None,
        ppa_ibor_date=None,
        near_cash_horizon_days=5,
):
    """
    Operational trade-date cash ledger for currency investments.

    OPENING / CLOSING are real point-in-time balances -- the AL-repo
    snapshot rolled up across TRADE_DATE_CASH_ACCOUNTS (Payable,
    Receivable, SpotFx*, ForwardFx*) for currency investments, at
    prior_cutoff and current_cutoff. This is the "what do I actually
    have" number operations people think in terms of -- not an
    internal activity-only cumsum starting from zero. Built the same
    way compute_position_ledger.py extracts AL positions, just pointed
    at this account set instead of Cost.

    ACTIVITY rows (between OPENING and CLOSING) are ALL Receivable/
    Payable postings within the period -- nothing excluded by settle
    date. Running balance starts from the real OPENING figure, not
    zero.

    TRADE_DATE_CASH_ACCOUNTS is fixed and named, same posture as every
    other account rollup in this codebase (see compute_classifications.py
    header: "Adding a new account is one line"). The exact set used on
    THIS call is always in metadata['accounts_included'] -- so if the
    set ever changes, that change is visible in the output itself, not
    just in a code diff. This is what keeps period-over-period
    comparisons honest without needing separate drift-detection
    machinery: the set is named, stable, and self-reporting.

    Does NOT include settlement-side Cost postings -- see
    compute_cash_settle_date for that ledger. The two are deliberately
    non-overlapping.

    Parameters
    ----------
    near_cash_horizon_days : int, default 5
        NOT currently used to exclude any activity -- see CORRECTION
        note below. Kept as a parameter for now in case a future
        forward-looking view (commitments extending past period end)
        wants it; has no effect on this function's output today.

    CORRECTION (read before relying on old behavior): an earlier
    version of this function used near_cash_horizon_days to EXCLUDE
    Payable/Receivable rows whose settle date fell outside a business-
    day window of the period's as-of date. That was wrong -- it dropped
    real, already-settled, mid-period activity (e.g. a trade settling
    cleanly on the 6th of the month) while keeping only rows settling
    near the period boundary. Trade-date cash now shows ALL Payable/
    Receivable activity within the period, full stop. The near-cash-
    horizon idea was never meant to gate what already happened inside
    the period -- if it's reintroduced later, it should only ever
    apply to a forward-looking view of commitments extending PAST
    period end, never as an exclusion on in-period activity.

    Returns
    -------
    ComputeResult with shape='cash_trade_date'
    """
    start_time = datetime.now()

    if prep is None:
        prep = prep_state(portfolio, calendar, period_start, period_end)

    ledger = compute_accounting_ledger(
        portfolio=portfolio, calendar=calendar,
        period_start=period_start, period_end=period_end,
        uber_filter=uber_filter, prep=prep,
        ppa_ibor_date=ppa_ibor_date,
    )

    df = ledger.data
    as_of_date = _to_date(prep.get("current_cutoff_datetime"))
    prior_cutoff = prep.get("prior_cutoff_datetime")
    current_cutoff = prep.get("current_cutoff_datetime")

    # -- OPENING boundary, display-only --
    # prior_cutoff_datetime is correctly None at inception (no prior
    # period exists) -- fig_core.py's prep_state is NOT touched, that
    # None is a real, relied-upon signal elsewhere. But a None/NaT
    # OPENING row date is a confusing thing to show a user. When there
    # IS a prior period, prior_cutoff is already correct and calendar-
    # aware (Monthly/Quarterly/Yearly/Daily all handled by prep_state
    # itself) -- only the inception case needs a real DISPLAY date,
    # which start_period_boundary in portfolio.json exists to supply.
    # Confirmed: full user-set date+time, no derivation; falls back to
    # inception_date + implied 00:00:00 for portfolios created before
    # this field existed.
    if prior_cutoff is not None:
        opening_boundary = prior_cutoff
    else:
        portfolio_config = prep.get("portfolio_config") or {}
        spb = portfolio_config.get("start_period_boundary")
        if not spb:
            inception = portfolio_config.get("inception_date")
            spb = f"{inception}T00:00:00" if inception else None
        opening_boundary = pd.to_datetime(spb) if spb else None

    # -- Currency-investment scope --
    # is_currency lives on the investment master, not on the JE row
    # itself or in compute_classifications.py. Same source
    # classify_unreal_line() in proof_engine.py uses (is_currency=1/true
    # on the investment_master row). If the IM isn't reachable, every
    # row is excluded rather than silently included.
    im = _load_investment_master_for(portfolio, prep)
    currency_invs = {
        inv for inv, attrs in im.items()
        if str(attrs.get("is_currency", "")).strip() in ("1", "true", "True", "TRUE")
    }

    # -- OPENING / CLOSING: real point-in-time balances, AL-repo snapshot --
    open_lot_rows  = _extract_al_positions_keep_zeros(prep.get("prior_state"), im)
    close_lot_rows = _extract_al_positions_keep_zeros(prep.get("current_state"), im)
    opening_bal = _rollup_trade_date_cash(open_lot_rows, currency_invs)
    closing_bal = _rollup_trade_date_cash(close_lot_rows, currency_invs)

    rows_out = []
    for inv in sorted(set(opening_bal) | set(closing_bal)):
        ob = opening_bal.get(inv, {"local": 0.0, "book": 0.0})
        rows_out.append({
            "event_type": "OPENING", "investment": inv, "ibor_date": opening_boundary,
            # OPENING has no real settle_date (it's a point-in-time
            # snapshot, not a single JE) -- set equal to its own ibor_date,
            # same convention as CLOSING below, rather than leaving NaT.
            "settle_date": opening_boundary,
            "transaction": None, "financial_account": "",
            "local": ob["local"], "book": ob["book"],
            "running_local": ob["local"], "running_book": ob["book"],
            "tranid": None, "sequence": -1,
        })

    # -- ACTIVITY: roll up Cost + PriceGainInvestment + FXGainInvestment
    # from the non-currency (real instrument) side of each trade.
    # These three accounts together always equal the cash flow that hits
    # the currency investment's Payable/Receivable:
    #   Opens:  Cost only (cost of position acquired)
    #   Closes: Cost + PriceGainInvestment + FXGainInvestment
    #           (recovered cost plus realized P&L = total cash received)
    # This approach avoids the brittle transaction-name filtering that
    # failed when both trade and settlement legs exist within the same
    # period. The investment column is naturally the real traded instrument
    # (IBM, DXCM etc.), not the currency -- no join needed.
    CASH_FLOW_ACCOUNTS = frozenset({
        "Cost",
        "PriceGainInvestment",
        "FXGainInvestment",
    })

    if df is not None and not df.empty:

        # -- Path 1: non-currency investment side of trades
        # (Cost + PriceGainInvestment + FXGainInvestment on the real instrument)
        scoped = df[
            ~df["investment"].isin(currency_invs)
            & df["financial_account"].isin(CASH_FLOW_ACCOUNTS)
            & (df["event_type"] == "ACTIVITY")
        ].copy()

        # -- Path 2: direct currency cash flows (deposits, withdrawals, spot FX)
        # These have both sides on the currency investment itself -- no
        # non-currency leg exists, so Path 1 misses them entirely.
        # Only Cost -- same three-account rollup rule, no ContributedCost.
        DIRECT_CASH_TRANSACTIONS = frozenset({
            "CurrencyDeposit", "CurrencyWithdrawal", "SpotFX",
        })
        scoped_direct = df[
            df["investment"].isin(currency_invs)
            & df["financial_account"].isin(CASH_FLOW_ACCOUNTS)
            & (df["event_type"] == "ACTIVITY")
            & df["transaction"].isin(DIRECT_CASH_TRANSACTIONS)
        ].copy()

        # Build settle_date lookup once for both paths
        settle_by_tranid = {}
        for je in prep["journal_entries"]:
            tranid = getattr(je, "tranid", None)
            if tranid is not None:
                settle_by_tranid[tranid] = getattr(je, "settledate", None)

        # Build currency lookup for Path 1
        currency_by_tranid = {}
        ccy_rows = df[
            df["investment"].isin(currency_invs)
            & (df["event_type"] == "ACTIVITY")
        ]
        for _, row in ccy_rows.iterrows():
            tid = row["tranid"]
            if tid not in currency_by_tranid:
                currency_by_tranid[tid] = row["investment"]

        all_agg = []

        if not scoped.empty:
            scoped = scoped.reset_index(drop=True)
            scoped["settle_date"] = scoped["tranid"].map(
                lambda x: settle_by_tranid.get(x)
            )
            scoped["currency_investment"] = scoped["tranid"].map(
                lambda x: currency_by_tranid.get(x)
            )
            group_cols = ["investment", "ibor_date", "tranid", "transaction"]
            agg = scoped.groupby(group_cols, as_index=False).agg(
                local=("local", "sum"),
                book=("book", "sum"),
                settle_date=("settle_date", "first"),
                currency_investment=("currency_investment", "first"),
                sequence=("sequence", "min"),
            )
            # Negate: on the instrument leg, a buy posts positive Cost
            # (position opens) but cash leaves -- flip for cash view.
            # Sells post negative Cost but cash comes in -- same flip.
            # Path 2 (deposits/withdrawals) already carries correct sign.
            agg["local"] = -agg["local"]
            agg["book"]  = -agg["book"]
            all_agg.append(agg)

        if not scoped_direct.empty:
            scoped_direct = scoped_direct.reset_index(drop=True)
            scoped_direct["settle_date"] = scoped_direct["tranid"].map(
                lambda x: settle_by_tranid.get(x)
            )
            # For direct cash flows, currency IS the investment
            scoped_direct["currency_investment"] = scoped_direct["investment"]
            group_cols = ["investment", "ibor_date", "tranid", "transaction"]
            agg_direct = scoped_direct.groupby(group_cols, as_index=False).agg(
                local=("local", "sum"),
                book=("book", "sum"),
                settle_date=("settle_date", "first"),
                currency_investment=("currency_investment", "first"),
                sequence=("sequence", "min"),
            )
            all_agg.append(agg_direct)

        if all_agg:
            combined = pd.concat(all_agg, ignore_index=True)
            combined = combined.sort_values(
                by=["currency_investment", "ibor_date", "sequence"]
            ).reset_index(drop=True)
            combined["event_type"] = "TRADE_DATE_CASH"
            rows_out.extend(combined.to_dict("records"))

    # Build final output per currency: SECTION → OPENING → ACTIVITY → CLOSING
    # Pull all activity rows out of rows_out, rebuild per currency
    activity_rows = [r for r in rows_out if r.get("event_type") == "TRADE_DATE_CASH"]
    non_activity = [r for r in rows_out if r.get("event_type") != "TRADE_DATE_CASH"]

    # Group activity by currency_investment
    from collections import defaultdict as _defaultdict
    activity_by_ccy = _defaultdict(list)
    for r in activity_rows:
        ccy = r.get("currency_investment") or "USD"
        activity_by_ccy[ccy].append(r)

    # Rebuild rows_out in correct order: for each currency, SECTION → OPENING → ACTIVITY → CLOSING
    rows_out = []
    for ccy in sorted(activity_by_ccy.keys()):
        # SECTION header
        rows_out.append({
            "event_type": "SECTION",
            "investment": ccy,
            "currency_investment": ccy,
            "ibor_date": None, "settle_date": None,
            "tranid": None, "transaction": None,
            "local": None, "book": None,
            "running_local": None, "running_book": None,
            "sequence": -2,
        })
        # OPENING for this currency
        for r in non_activity:
            if r.get("event_type") == "OPENING" and r.get("investment") == ccy:
                rows_out.append(r)
        # ACTIVITY sorted by date
        for r in sorted(activity_by_ccy[ccy], key=lambda x: (
            x.get("ibor_date") or "", x.get("sequence") or 0
        )):
            rows_out.append(r)
        # CLOSING for this currency
        for r in non_activity:
            if r.get("event_type") == "CLOSING" and r.get("investment") == ccy:
                rows_out.append(r)

    for inv in sorted(set(opening_bal) | set(closing_bal)):
        cb = closing_bal.get(inv, {"local": 0.0, "book": 0.0})
        rows_out.append({
            "event_type": "CLOSING", "investment": inv, "ibor_date": current_cutoff,
            # CLOSING has no real settle_date either (same reasoning as
            # OPENING above) -- set equal to its own ibor_date rather
            # than None/NaT.
            "settle_date": current_cutoff,
            "transaction": None, "financial_account": "",
            "local": cb["local"], "book": cb["book"],
            "running_local": cb["local"], "running_book": cb["book"],
            "tranid": None, "sequence": 999999,
        })

    out_df = pd.DataFrame(rows_out)

    if not out_df.empty:
        # Structure is already correct from rows_out rebuild above.
        # Running balance per currency investment -- carry forward by ccy.
        running_local, running_book = [], []
        carry = {}
        for _, row in out_df.iterrows():
            inv = row.get("investment", "")
            et = row.get("event_type", "")
            if et == "OPENING":
                carry[inv] = {"local": row["local"] or 0.0, "book": row["book"] or 0.0}
                running_local.append(carry[inv]["local"])
                running_book.append(carry[inv]["book"])
            elif et == "CLOSING":
                running_local.append(row["running_local"] or 0.0)
                running_book.append(row["running_book"] or 0.0)
            elif et == "SECTION":
                running_local.append(None)
                running_book.append(None)
            else:
                # TRADE_DATE_CASH -- carry keyed by currency_investment
                ccy = row.get("currency_investment") or inv
                cur = carry.setdefault(ccy, {"local": 0.0, "book": 0.0})
                cur["local"] += row["local"] or 0.0
                cur["book"]  += row["book"] or 0.0
                running_local.append(cur["local"])
                running_book.append(cur["book"])

        out_df["running_local"] = running_local
        out_df["running_book"] = running_book

    col_order = [
        "event_type", "investment",
        "ibor_date", "settle_date",
        "tranid", "transaction",
        "local", "book", "running_local", "running_book",
        "sequence",
    ]
    if not out_df.empty:
        col_order = [c for c in col_order if c in out_df.columns]
        extras = [c for c in out_df.columns if c not in col_order]
        out_df = out_df[col_order + extras]
        out_df = out_df.fillna("")

    # -- RECON CHECK: opening + activity == closing, per currency investment --
    # CONFIRMED DESIGN: any variance beyond rounding tolerance is a real
    # anomaly, not expected noise. A horizon-excluded item still affects
    # the real CLOSING balance (an AL-repo snapshot). With horizon-based
    # exclusion removed, ACTIVITY now contains every Payable/Receivable
    # posting in the period, so this should tie cleanly under normal
    # operation. A variance here is a real finding: an event that should
    # move cash never posted, or a period was processed out of sequence
    # (e.g. a prior-period correction without reprocessing subsequent
    # periods). Same tolerance convention as the rest of the codebase
    # (AMOUNT_TOLERANCE / RESIDUAL_TOLERANCE in proof_engine.py):
    # ~$0.01-0.02, not a wider "expected variance" band.
    RECON_TOLERANCE = 0.02
    recon_failures = []
    for inv in sorted(set(opening_bal) | set(closing_bal)):
        inv_rows = out_df[out_df["investment"] == inv] if not out_df.empty else out_df
        opening_local = opening_bal.get(inv, {}).get("local", 0.0)
        closing_local = closing_bal.get(inv, {}).get("local", 0.0)
        activity_local = inv_rows[inv_rows["event_type"] == "TRADE_DATE_CASH"]["local"].sum() \
            if inv_rows is not None and not inv_rows.empty else 0.0
        predicted_closing = opening_local + (activity_local or 0.0)
        diff = round(predicted_closing - closing_local, 2)
        if abs(diff) > RECON_TOLERANCE:
            recon_failures.append(
                f"{inv}: opening {opening_local:,.2f} + activity "
                f"{activity_local:,.2f} = {predicted_closing:,.2f} != "
                f"closing {closing_local:,.2f} (diff {diff:,.2f}). "
                f"Check for a missing cash-impacting event, or "
                f"out-of-sequence period processing."
            )

    if recon_failures:
        print(f">>> TRADE DATE CASH RECON: {len(recon_failures)} "
              f"investment(s) do not tie:")
        for f in recon_failures[:5]:
            print(f"    {f}")
        if len(recon_failures) > 5:
            print(f"    ... and {len(recon_failures) - 5} more")

    elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
    valid = ledger.valid and len(recon_failures) == 0
    metadata = {
        **ledger.metadata,
        "category": "Cash — Trade Date",
        "near_cash_horizon_days": near_cash_horizon_days,
        "rows_after_filter": len(out_df) if out_df is not None else 0,
        "accounts_included": sorted(TRADE_DATE_CASH_ACCOUNTS),
        "elapsed_ms": round(elapsed_ms, 2),
        "investment_master_source": "TEMPORARY_BRIDGE_disk_csv",
        "recon_failures": len(recon_failures),
    }

    print(
        f">>> COMPUTE CASH TRADE DATE COMPLETE "
        f"| {portfolio} | {calendar} | {period_start} -> {period_end} "
        f"| horizon={near_cash_horizon_days}BD "
        f"| {metadata['rows_after_filter']} rows "
        f"| recon_fail={len(recon_failures)} "
        f"| {round(elapsed_ms, 1)}ms"
    )

    return ComputeResult(
        function="compute_cash_trade_date",
        portfolio=portfolio, calendar=calendar,
        period_start=period_start, period_end=period_end,
        shape="cash_trade_date",
        data=out_df, valid=valid,
        errors=list(ledger.errors) + recon_failures,
        metadata=metadata,
    )


def _load_investment_master_for(portfolio, prep):
    """
    Load the investment master for is_currency lookups.

    *** TEMPORARY BRIDGE — FLAGGED FOR RECONCILIATION ***
    This reads RefData/investment_master.csv directly from disk, the
    same pattern proof_engine.py's load_investment_master() already
    uses and that this codebase has confirmed working. It is NOT the
    same access pattern compute_position_ledger.py uses (which reads
    via compute_appraisal._INVESTMENT_MASTER, populated by
    _ensure_reference_data() inside compute_appraisal.py). That file
    was not available when this function was written, so this bridge
    was used instead to get both cash ledgers working against real
    data now rather than block on it.

    TODO: once compute_appraisal.py's reference-data loader is
    confirmed to expose is_currency in the same shape, repoint this
    function (and its twin in compute_cash_settle_date.py) to that
    shared source instead of reading the CSV independently here.
    Two IM loaders reading the same file by two different paths is a
    drift risk -- fine short-term, not the end state.

    funds_path is read from prep["portfolio_config"] if present,
    falling back to FUNDS_PATH from v_config, matching how the rest
    of this codebase resolves it.
    """
    import csv
    from pathlib import Path
    try:
        from v_config import FUNDS_PATH
    except ImportError:
        FUNDS_PATH = None

    funds_path = (prep.get("portfolio_config") or {}).get("funds_path") or FUNDS_PATH
    if not funds_path:
        print(">>> CASH LEDGER: no funds_path available -- IM not loaded, "
              "currency scope will be empty (TEMPORARY BRIDGE gap)")
        return {}

    path = Path(funds_path) / portfolio / "RefData" / "investment_master.csv"
    if not path.exists():
        print(f">>> CASH LEDGER: investment_master.csv not found at {path} "
              f"-- IM not loaded, currency scope will be empty")
        return {}

    result = {}
    try:
        with open(path, newline="", encoding="cp1252") as f:
            for row in csv.DictReader(f):
                inv = row.get("investment", "").strip()
                if inv:
                    result[inv] = row
    except Exception as e:
        print(f">>> CASH LEDGER: failed to read investment_master.csv: {e}")
        return {}
    return result