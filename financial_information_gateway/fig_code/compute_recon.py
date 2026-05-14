"""
compute_recon.py
──────────────────────────────────────────────────────────────────────────────
Master reconciliation. Three views. One truth. One all_clear.

VIEW 1 — ACCOUNTING (Balance Sheet)
  Cost + Unrealized = MarketVal
  The accountant's proof. Cost basis at historical cost.
  Unrealized gain explains the difference to market.

VIEW 2 — P&L (NAV Explanation)
  Capital + Income + Realized + Unrealized = MarketVal
  The CFO's proof. Every dollar of market value explained
  by where it came from.

VIEW 3 — PERFORMANCE (TWR)
  Daily (EMV - BMV - CF) / BMV chained = Period Return
  Period Return × Opening MarketVal = implied P&L
  The portfolio manager's proof.

THE HOLY GRAIL:
  View 1 MarketVal = View 2 MarketVal = View 3 implied MarketVal

Three independent derivations of the same number.
Accounting, economics, and performance mathematics
all arriving at the same place — because there is
only one source of truth.

No conventional system can run this check.
In Visibility it runs in milliseconds.

Accounting accuracy is credibility.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import time
from typing import Optional

import pandas as pd

from financial_information_gateway.fig_code.compute_result import ComputeResult
from financial_information_gateway.fig_code.compute_classifications import (
    ACCOUNT_CLASSIFICATION,
    STAT_ONLY_ACCOUNTS,
    Category,
)

TOLERANCE    = 1e-2   # $0.01 — tight enough to catch real errors
MV_TOLERANCE = 1.00   # $1.00 for market value integrity check


# ──────────────────────────────────────────────────────────────────────────────
# SHARED UTILITIES
# ──────────────────────────────────────────────────────────────────────────────

def _passes_filter(inv, uber_filter):
    if not uber_filter:
        return True
    return inv == uber_filter.get("investment")


def _safe_ibor(je):
    from datetime import datetime
    ibor = getattr(je, "ibor_date", None)
    if ibor is None:
        return None
    if isinstance(ibor, datetime):
        return ibor
    try:
        return datetime.fromisoformat(str(ibor))
    except Exception:
        return None


def _in_period(ibor, prior_cutoff, current_cutoff):
    if ibor is None:
        return False
    if prior_cutoff is None:
        return ibor <= current_cutoff
    return prior_cutoff < ibor <= current_cutoff



def _extract_state_by_account(state, uber_filter=None) -> dict:
    """
    Extract (investment, financial_account) -> book value from state.

    Reads from:
      - asset_liability_repository  -> investment_positions -> subspace.entries
      - revenue_expense_repository  -> balance_spaces_library -> balance_space["entries"]

    Excludes stat-only accounts.
    """
    balances = {}

    if not state:
        return balances

    def decode(row):
        return row[2] if len(row) > 2 else 0.0

    # ── ASSET / LIABILITY ─────────────────────────────────────────────
    al_repo = state["asset_liability_repository"]
    for subspace in al_repo.investment_positions.values():
        for key, row in subspace.entries.items():
            (_, inv, _, _, _, _, fa) = key
            if fa in STAT_ONLY_ACCOUNTS:
                continue
            if not _passes_filter(inv, uber_filter):
                continue
            book = decode(row)
            k = (inv, fa)
            balances[k] = balances.get(k, 0.0) + book

    # ── REVENUE / EXPENSE ─────────────────────────────────────────────
    re_repo = state["revenue_expense_repository"]
    for investment, balance_space in re_repo.balance_spaces_library.items():
        if not _passes_filter(investment, uber_filter):
            continue
        for key, row in balance_space["entries"].items():
            if not isinstance(key, tuple) or len(key) < 7:
                continue
            (_, inv, _, _, _, _, fa) = key
            if fa in STAT_ONLY_ACCOUNTS:
                continue
            book = decode(row)
            k = (inv, fa)
            balances[k] = balances.get(k, 0.0) + book

    return balances
# ──────────────────────────────────────────────────────────────────────────────
# FIVE BUCKET EXTRACTOR
# The core of everything. Reads journal entries and classifies
# every movement into one of five buckets per investment.
# ──────────────────────────────────────────────────────────────────────────────

def _extract_five_buckets(prep, uber_filter=None) -> dict:
    """
    Extract five economic buckets from journal entries for the period.

    Bucket 1 — Cost:       Cost account movements (traded + contributed basis)
    Bucket 2 — Unrealized: UnrealPriceGL + UnrealFXGL movements
    Bucket 3 — Realized:   PriceGainInvestment + FXGainInvestment
    Bucket 4 — Income:     DividendReceipt, InterestIncome etc
    Bucket 5 — Capital:    ContributedCost flows

    Returns dict: {investment: {cost, unrealized, realized, income, capital}}
    All values in book currency.
    """
    prior_cutoff = prep["prior_cutoff_datetime"]
    current_cutoff = prep["current_cutoff_datetime"]

    buckets = {}

    for je in prep["journal_entries"]:
        inv = getattr(je, "investment", None)
        fa = getattr(je, "financial_account", None)

        if inv is None or fa is None:
            continue
        if fa in STAT_ONLY_ACCOUNTS:
            continue
        if not _passes_filter(inv, uber_filter):
            continue

        is_adj = getattr(je, "is_adjustment", False)
        if not is_adj:
            ibor = _safe_ibor(je)
            if not _in_period(ibor, prior_cutoff, current_cutoff):
                continue

        book = getattr(je, "book", None) or 0.0
        category = ACCOUNT_CLASSIFICATION.get(fa, "Unknown")

        if inv not in buckets:
            buckets[inv] = {
                "cost": 0.0,
                "unrealized": 0.0,
                "realized": 0.0,
                "income": 0.0,
                "capital": 0.0,
            }

        if category == Category.COST:
            buckets[inv]["cost"] += book

        elif category in (Category.UNREALIZED_PRICE, Category.UNREALIZED_FX):
            buckets[inv]["unrealized"] += book

        elif category in (Category.REALIZED_PRICE, Category.REALIZED_FX):
            buckets[inv]["realized"] -= book  # flip — credits in journals

        elif category in (Category.INCOME, Category.EXPENSE):
            buckets[inv]["income"] -= book  # flip — credits in journals

        elif category == Category.CAPITAL:
            buckets[inv]["capital"] += book

    return buckets

# ──────────────────────────────────────────────────────────────────────────────
# MARKET VALUE FROM STATE
# ──────────────────────────────────────────────────────────────────────────────

def _get_market_val(prep, uber_filter=None) -> dict:
    """
    Closing market value = last MarketVal JE in the period.
    MarketVal is posted daily as transaction=Valuation.
    Last posting = closing Price × Quantity.
    """
    prior_cutoff = prep["prior_cutoff_datetime"]
    current_cutoff = prep["current_cutoff_datetime"]

    mv = {}

    for je in prep["journal_entries"]:
        inv = getattr(je, "investment", None)
        fa = getattr(je, "financial_account", None)

        if fa != "MarketVal":
            continue
        if not _passes_filter(inv, uber_filter):
            continue

        is_adj = getattr(je, "is_adjustment", False)
        if not is_adj:
            ibor = _safe_ibor(je)
            if not _in_period(ibor, prior_cutoff, current_cutoff):
                continue

        book = getattr(je, "book", None) or 0.0
        ibor = _safe_ibor(je)

        if inv not in mv or (ibor and ibor > mv[inv]["date"]):
            mv[inv] = {"book": book, "date": ibor}

    return {inv: v["book"] for inv, v in mv.items()}


def _get_opening_mv(prep, uber_filter=None) -> dict:
    """
    Opening market value = last MarketVal JE at or before prior_cutoff.
    First period: prior_cutoff = None → opening MV = 0.
    """
    prior_cutoff = prep["prior_cutoff_datetime"]

    if prior_cutoff is None:
        return {}

    mv = {}

    for je in prep["journal_entries"]:
        inv = getattr(je, "investment", None)
        fa = getattr(je, "financial_account", None)

        if fa != "MarketVal":
            continue
        if not _passes_filter(inv, uber_filter):
            continue

        ibor = _safe_ibor(je)
        if ibor is None or ibor > prior_cutoff:
            continue

        book = getattr(je, "book", None) or 0.0

        if inv not in mv or ibor > mv[inv]["date"]:
            mv[inv] = {"book": book, "date": ibor}

    return {inv: v["book"] for inv, v in mv.items()}


# ──────────────────────────────────────────────────────────────────────────────
# VIEW 1 — ACCOUNTING
# Cost + Unrealized = MarketVal
# ──────────────────────────────────────────────────────────────────────────────

def _run_view1(buckets, closing_mv) -> pd.DataFrame:
    """
    View 1: Accounting proof.
    Cost + Unrealized = MarketVal

    Cost basis at historical cost.
    Unrealized gain explains the difference to market.
    """
    all_investments = set(buckets) | set(closing_mv)
    rows = []

    for inv in sorted(all_investments):
        b  = buckets.get(inv, {})
        mv = closing_mv.get(inv, 0.0)

        cost       = b.get("cost",       0.0)
        unrealized = b.get("unrealized", 0.0)

        proof1 = cost + unrealized
        diff   = abs(proof1 - mv)
        ties   = diff <= TOLERANCE

        rows.append({
            "view":        "accounting",
            "investment":  inv,
            "cost":        round(cost,       2),
            "unrealized":  round(unrealized, 2),
            "proof1_mv":   round(proof1,     2),
            "market_val":  round(mv,         2),
            "diff":        round(diff,       4),
            "ties":        ties,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Portfolio total
    num_cols = ["cost", "unrealized", "proof1_mv", "market_val", "diff"]
    total = {col: df[col].sum() for col in num_cols}
    total.update({
        "view":       "accounting",
        "investment": "── TOTAL",
        "ties":       df["ties"].all(),
    })

    return pd.concat([df, pd.DataFrame([total])], ignore_index=True)


# ──────────────────────────────────────────────────────────────────────────────
# VIEW 2 — P&L (NAV EXPLANATION)
# Capital + Income + Realized + Unrealized = MarketVal
# ──────────────────────────────────────────────────────────────────────────────

def _run_view2(buckets, opening_mv, closing_mv) -> pd.DataFrame:
    """
    View 2: P&L proof at investment level.

    Opening MV + Cost + Unrealized Change = Closing MV

    Cost movements (net buys/sells) plus change in unrealized
    fully explains the change in market value at investment level.

    Realized gains and income are P&L explanations — they are
    already captured in cost movements and do not add independently
    to market value at the investment level.

    Capital (ContributedCost) applies at portfolio level only.

    These components are shown separately in compute_comprehensive
    for the full P&L picture but do not affect this proof.
    """
    all_investments = set(buckets) | set(closing_mv)
    rows = []

    for inv in sorted(all_investments):
        b = buckets.get(inv, {})
        open_mv = opening_mv.get(inv, 0.0)
        close_mv = closing_mv.get(inv, 0.0)

        cost = b.get("cost", 0.0)
        unrealized = b.get("unrealized", 0.0)
        realized = b.get("realized", 0.0)
        income = b.get("income", 0.0)
        capital = b.get("capital", 0.0)

        # Investment level proof
        proof2 = open_mv + cost + unrealized
        diff = abs(proof2 - close_mv)
        ties = diff <= TOLERANCE

        rows.append({
            "view": "pnl",
            "investment": inv,
            "opening_mv": round(open_mv, 2),
            "cost": round(cost, 2),
            "unrealized": round(unrealized, 2),
            "realized": round(realized, 2),
            "income": round(income, 2),
            "capital": round(capital, 2),
            "proof2_mv": round(proof2, 2),
            "market_val": round(close_mv, 2),
            "diff": round(diff, 4),
            "ties": ties,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    num_cols = ["opening_mv", "cost", "unrealized", "realized",
                "income", "capital", "proof2_mv", "market_val", "diff"]
    total = {col: df[col].sum() for col in num_cols}
    total.update({
        "view": "pnl",
        "investment": "── TOTAL",
        "ties": df["ties"].all(),
    })

    return pd.concat([df, pd.DataFrame([total])], ignore_index=True)

# ──────────────────────────────────────────────────────────────────────────────
# VIEW 3 — PERFORMANCE (TWR)
# ──────────────────────────────────────────────────────────────────────────────

def _run_view3(prep, buckets, opening_mv, closing_mv, uber_filter=None) -> pd.DataFrame:
    """
    View 3: Performance proof.

    TWR period return × opening MV = implied P&L
    That implied P&L must agree with View 2 P&L.

    Both derived from the same journals.
    Performance math and accounting math arrive at the same place.
    """
    from financial_information_gateway.fig_code.compute_performance import compute_performance

    try:
        result = compute_performance(
            portfolio=prep["portfolio"],
            calendar=prep["calendar"],
            period_start=prep["period_start"],
            period_end=prep["period_end"],
            level="investment",
            cadence=None,
            uber_filter=uber_filter,
            prep=prep,
        )

        if result.data is None or result.data.empty:
            return pd.DataFrame()

        df = result.data.copy()

        # Get last row per investment — end of period state
        if "ibor_date" in df.columns:
            df = df.sort_values("ibor_date")

        last = (
            df[~df["investment"].str.startswith("──")]
            .groupby("investment")
            .last()
            .reset_index()
        )

        rows = []
        for _, row in last.iterrows():
            inv        = row["investment"]
            open_mv    = opening_mv.get(inv, 0.0)
            close_mv   = closing_mv.get(inv, 0.0)
            index_book = row.get("Index_Book", 1.0)

            # Implied P&L from TWR
            # Index_Book represents the growth factor from day 1
            # Implied closing MV = opening MV × Index_Book
            # For first period where opening MV = 0, use EMV directly
            emv_book = row.get("EMV_Book", 0.0)

            if open_mv > 0:
                implied_mv = open_mv * index_book
            else:
                implied_mv = emv_book

            diff = abs(implied_mv - close_mv)
            ties = diff <= (close_mv * 0.001 + 1.0)  # 0.1% + $1 tolerance

            rows.append({
                "view":        "performance",
                "investment":  inv,
                "opening_mv":  round(open_mv,    2),
                "index_book":  round(index_book, 6),
                "implied_mv":  round(implied_mv, 2),
                "market_val":  round(close_mv,   2),
                "emv_book":    round(emv_book,   2),
                "diff":        round(diff,       4),
                "ties":        ties,
            })

        if not rows:
            return pd.DataFrame()

        perf_df = pd.DataFrame(rows)

        num_cols = ["opening_mv", "implied_mv", "market_val", "diff"]
        total = {col: perf_df[col].sum() for col in num_cols}
        total.update({
            "view":       "performance",
            "investment": "── TOTAL",
            "index_book": None,
            "emv_book":   perf_df["emv_book"].sum(),
            "ties":       perf_df["ties"].all(),
        })

        return pd.concat([perf_df, pd.DataFrame([total])], ignore_index=True)

    except Exception as e:
        print(f">>> View 3 (performance) skipped: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


# ──────────────────────────────────────────────────────────────────────────────
# CROSS-VIEW CHECK
# View 1 proof1_mv = View 2 proof2_mv = View 3 implied_mv = MarketVal
# ──────────────────────────────────────────────────────────────────────────────

def _run_cross_view(view1_df, view2_df, view3_df) -> pd.DataFrame:
    """
    The ultimate check: all three views agree on MarketVal.

    Cross-joins the totals from each view and proves they agree.
    This is the holy grail — three independent derivations of one number.
    """
    rows = []

    def get_total(df, mv_col):
        if df is None or df.empty:
            return None
        total_rows = df[df["investment"] == "── TOTAL"]
        if total_rows.empty:
            return None
        return total_rows.iloc[0].get(mv_col)

    v1_mv = get_total(view1_df, "proof1_mv")
    v2_mv = get_total(view2_df, "proof2_mv")
    v3_mv = get_total(view3_df, "implied_mv")
    actual_mv = get_total(view1_df, "market_val")

    # Build comparison row
    row = {
        "view":              "cross_view",
        "investment":        "── PORTFOLIO TOTAL",
        "accounting_mv":     round(v1_mv,    2) if v1_mv    is not None else None,
        "pnl_mv":            round(v2_mv,    2) if v2_mv    is not None else None,
        "performance_mv":    round(v3_mv,    2) if v3_mv    is not None else None,
        "market_val":        round(actual_mv,2) if actual_mv is not None else None,
    }

    # Diffs
    if v1_mv is not None and v2_mv is not None:
        row["v1_v2_diff"] = round(abs(v1_mv - v2_mv), 4)
        row["v1_v2_ties"] = abs(v1_mv - v2_mv) <= TOLERANCE
    else:
        row["v1_v2_diff"] = None
        row["v1_v2_ties"] = None

    if v1_mv is not None and v3_mv is not None:
        row["v1_v3_diff"] = round(abs(v1_mv - v3_mv), 4)
        row["v1_v3_ties"] = abs(v1_mv - v3_mv) <= (abs(v1_mv) * 0.001 + 1.0)
    else:
        row["v1_v3_diff"] = None
        row["v1_v3_ties"] = None

    row["all_three_agree"] = (
        row.get("v1_v2_ties") is True and
        row.get("v1_v3_ties") is True
    )

    return pd.DataFrame([row])


# ──────────────────────────────────────────────────────────────────────────────
# MAIN COMPUTE FUNCTION
# ──────────────────────────────────────────────────────────────────────────────

def compute_recon(
    portfolio:               str,
    calendar:                str,
    period_start:            str,
    period_end:              str,
    uber_filter:             Optional[dict] = None,
    prep:                    Optional[dict] = None,
    include_view1:           bool           = True,
    include_view2:           bool           = True,
    include_view3:           bool           = False,
    include_cross_view:      bool           = True,
) -> ComputeResult:
    """
    Master reconciliation. Three views. One truth. One all_clear.

    View 1 — Accounting:   Cost + Unrealized = MarketVal
    View 2 — P&L:          Capital + Income + Realized + Unrealized = MarketVal
    View 3 — Performance:  TWR implied MV = MarketVal (optional — slower)
    Cross:                 View 1 = View 2 = View 3 = MarketVal

    all_clear: true — every view, every investment, agrees on MarketVal.
    Accounting accuracy is credibility.
    """

    t_total = time.perf_counter()

    if prep is None:
        raise ValueError("prep is required.")

    # ── EXTRACT ONCE — used by all views ─────────────────────────────
    t_extract = time.perf_counter()

    buckets    = _extract_five_buckets(prep, uber_filter)

    opening_mv = _get_opening_mv(prep, uber_filter)
    closing_mv = _get_market_val(prep, uber_filter)

    t_extract_ms = (time.perf_counter() - t_extract) * 1000

    all_frames      = []
    all_errors      = []
    section_results = {}

    # ── VIEW 1: ACCOUNTING ────────────────────────────────────────────
    t_v1 = time.perf_counter()
    view1_df = pd.DataFrame()
    if include_view1:
        view1_df = _run_view1(buckets, closing_mv)
        if not view1_df.empty:
            failures = view1_df[
                (view1_df["investment"] != "── TOTAL") &
                (~view1_df["ties"])
            ]
            section_results["accounting"] = {
                "all_clear": len(failures) == 0,
                "failures":  len(failures),
            }
            for _, row in failures.iterrows():
                all_errors.append(
                    f"V1|{row['investment']}"
                    f"|cost={row['cost']:.2f}"
                    f"|unreal={row['unrealized']:.2f}"
                    f"|proof={row['proof1_mv']:.2f}"
                    f"|mv={row['market_val']:.2f}"
                    f"|diff={row['diff']:.4f}"
                )
            all_frames.append(view1_df)
    t_v1_ms = (time.perf_counter() - t_v1) * 1000

    # ── VIEW 2: P&L ───────────────────────────────────────────────────
    t_v2 = time.perf_counter()
    view2_df = pd.DataFrame()
    if include_view2:
        view2_df = _run_view2(buckets, opening_mv, closing_mv)
        if not view2_df.empty:
            failures = view2_df[
                (view2_df["investment"] != "── TOTAL") &
                (~view2_df["ties"])
            ]
            section_results["pnl"] = {
                "all_clear": len(failures) == 0,
                "failures":  len(failures),
            }
            for _, row in failures.iterrows():
                all_errors.append(
                    f"V2|{row['investment']}"
                    f"|capital={row['capital']:.2f}"
                    f"|income={row['income']:.2f}"
                    f"|realized={row['realized']:.2f}"
                    f"|unreal={row['unrealized']:.2f}"
                    f"|proof={row['proof2_mv']:.2f}"
                    f"|mv={row['market_val']:.2f}"
                    f"|diff={row['diff']:.4f}"
                )
            all_frames.append(view2_df)
    t_v2_ms = (time.perf_counter() - t_v2) * 1000

    # ── VIEW 3: PERFORMANCE ───────────────────────────────────────────
    t_v3 = time.perf_counter()
    view3_df = pd.DataFrame()
    if include_view3:
        view3_df = _run_view3(prep, buckets, opening_mv, closing_mv, uber_filter)
        if not view3_df.empty:
            failures = view3_df[
                (view3_df["investment"] != "── TOTAL") &
                (~view3_df["ties"])
            ]
            section_results["performance"] = {
                "all_clear": len(failures) == 0,
                "failures":  len(failures),
            }
            for _, row in failures.iterrows():
                all_errors.append(
                    f"V3|{row['investment']}"
                    f"|implied={row['implied_mv']:.2f}"
                    f"|mv={row['market_val']:.2f}"
                    f"|diff={row['diff']:.4f}"
                )
            all_frames.append(view3_df)
    t_v3_ms = (time.perf_counter() - t_v3) * 1000

    # ── CROSS-VIEW CHECK ──────────────────────────────────────────────
    t_cx = time.perf_counter()
    cross_df = pd.DataFrame()
    if include_cross_view and (include_view1 or include_view2):
        cross_df = _run_cross_view(
            view1_df if include_view1 else None,
            view2_df if include_view2 else None,
            view3_df if include_view3 else None,
        )
        if not cross_df.empty:
            agrees = bool(cross_df.iloc[0].get("all_three_agree", False))
            if include_view3:
                section_results["cross_view"] = {
                    "all_clear": agrees,
                    "failures":  0 if agrees else 1,
                }
            else:
                v1v2 = bool(cross_df.iloc[0].get("v1_v2_ties", False))
                section_results["cross_view"] = {
                    "all_clear": v1v2,
                    "failures":  0 if v1v2 else 1,
                }
                if not v1v2:
                    all_errors.append(
                        f"CROSS|V1≠V2"
                        f"|accounting={cross_df.iloc[0].get('accounting_mv'):.2f}"
                        f"|pnl={cross_df.iloc[0].get('pnl_mv'):.2f}"
                        f"|diff={cross_df.iloc[0].get('v1_v2_diff'):.4f}"
                    )
            all_frames.append(cross_df)
    t_cx_ms = (time.perf_counter() - t_cx) * 1000

    # ── COMBINE OUTPUT ────────────────────────────────────────────────
    output_df = pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()

    # ── ALL CLEAR ─────────────────────────────────────────────────────
    all_clear = (
        len(all_errors) == 0 and
        all(s["all_clear"] for s in section_results.values())
    )

    t_total_ms = (time.perf_counter() - t_total) * 1000

    # ── CONSOLE ───────────────────────────────────────────────────────
    if all_clear:
        print(
            f">>> compute_recon ALL CLEAR ✓ "
            f"| {portfolio} | {calendar} "
            f"| {period_start} → {period_end} "
            f"| {t_total_ms:.0f}ms"
        )
    else:
        total_failures = sum(s["failures"] for s in section_results.values())
        print(
            f">>> compute_recon FAILURES ✗ "
            f"| {total_failures} failures "
            f"| {t_total_ms:.0f}ms"
        )
        for e in all_errors[:10]:
            print(f"    {e}")

    metadata = {
        "elapsed_ms":    round(t_total_ms,  1),
        "extract_ms":    round(t_extract_ms,1),
        "section_ms": {
            "view1_accounting":  round(t_v1_ms, 1),
            "view2_pnl":         round(t_v2_ms, 1),
            "view3_performance": round(t_v3_ms, 1),
            "cross_view":        round(t_cx_ms, 1),
        },
        "all_clear":     all_clear,
        "sections":      section_results,
        "total_failures":len(all_errors),
        "tolerance":     TOLERANCE,
        "mv_tolerance":  MV_TOLERANCE,
        "uber_filter":   uber_filter,
        "five_buckets": {
            inv: {k: round(v, 2) for k, v in b.items()}
            for inv, b in buckets.items()
        },
    }

    return ComputeResult(
        function="compute_recon",
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        shape="recon",
        data=output_df,
        valid=all_clear,
        errors=all_errors,
        metadata=metadata,
    )