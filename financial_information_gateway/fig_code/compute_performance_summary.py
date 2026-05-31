"""
compute_performance_summary.py
──────────────────────────────────────────────────────────────────────────────
Performance Summary Report

Produces a single summary table per investment showing:
  MTD | QTD | YTD | 1YR | 3YR | 5YR | Annualized | Beta | Alpha | Sharpe

Benchmarks (SPY, AGG, TLT) appear as separate rows at bottom.
Beta, Alpha, Sharpe calculated vs SPY using full history daily returns.

Input:  chained daily state DataFrame from _build_chained_daily_state
Output: summary DataFrame ready for UI rendering

Register in compute_registry.py:
  from financial_information_gateway.fig_code.compute_performance_summary import compute_performance_summary
  COMPUTE_REGISTRY["compute_performance_summary"] = compute_performance_summary
"""

from __future__ import annotations

import time
from typing import Optional
import numpy as np
import pandas as pd

from financial_information_gateway.fig_code.compute_result import ComputeResult
from financial_information_gateway.fig_code.compute_performance import (
    _get_cached_daily_state,
    _get_available_periods,
    _sorted_periods,
    _merge_aif,
    _load_investment_master,
    clear_performance_cache,
)
from v_config import REFDATA_PATH, FUNDS_PATH

# ── CONSTANTS ─────────────────────────────────────────────────────────────────
BENCHMARK_SYMBOLS = {"SPY", "AGG", "TLT"}
PRIMARY_BENCHMARK = "SPY"
RISK_FREE_RATE    = 0.0   # configurable — set to T-bill rate when needed


# ── RETURN CALCULATION ────────────────────────────────────────────────────────

def _index_return(start_index: float, end_index: float) -> Optional[float]:
    """Calculate return from two index values."""
    if start_index is None or start_index == 0:
        return None
    return (end_index / start_index) - 1.0


def _annualize(total_return: float, days: int) -> Optional[float]:
    """Annualize a total return over a number of calendar days."""
    if days <= 0 or total_return <= -1.0:
        return None
    return (1.0 + total_return) ** (365.0 / days) - 1.0


def _period_return(
    df: pd.DataFrame,
    investment: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    level: str = "investment",
) -> Optional[float]:
    """
    Get return for investment between start_date and end_date.
    Uses Index_Local — the fully chained index.
    """
    inv_df = df[df[level] == investment].sort_values("ibor_date")

    # Get rows within range
    in_range = inv_df[
        (inv_df["ibor_date"] >= start_date) &
        (inv_df["ibor_date"] <= end_date)
    ]

    if in_range.empty:
        return None

    # Start index: last value BEFORE the range starts (or first in range)
    prior = inv_df[inv_df["ibor_date"] < start_date]
    if not prior.empty:
        start_idx = float(prior.iloc[-1]["Index_Local"])
    else:
        start_idx = float(in_range.iloc[0]["Index_Local"]) / (
            1 + float(in_range.iloc[0]["TWR_Local"])
            if float(in_range.iloc[0]["TWR_Local"]) != -1 else 1
        )

    end_idx = float(in_range.iloc[-1]["Index_Local"])

    return _index_return(start_idx, end_idx)


# ── ANALYTICS ─────────────────────────────────────────────────────────────────

def _compute_daily_returns(df: pd.DataFrame, investment: str, level: str = "investment") -> pd.Series:
    """Extract daily TWR returns for an investment as a Series indexed by date."""
    inv_df = df[df[level] == investment].sort_values("ibor_date")
    return inv_df.set_index("ibor_date")["TWR_Local"]


def _compute_beta(
    inv_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> Optional[float]:
    """Beta = Cov(inv, benchmark) / Var(benchmark) using full history."""
    aligned = pd.concat([inv_returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 30:
        return None
    aligned.columns = ["inv", "bench"]
    cov = aligned["inv"].cov(aligned["bench"])
    var = aligned["bench"].var()
    if var == 0:
        return None
    return round(cov / var, 4)


def _compute_alpha(
    ann_return: Optional[float],
    beta: Optional[float],
    benchmark_ann_return: Optional[float],
    risk_free: float = RISK_FREE_RATE,
) -> Optional[float]:
    """Jensen's Alpha = Ann_Return - (RF + Beta * (Benchmark_Ann - RF))"""
    if any(v is None for v in [ann_return, beta, benchmark_ann_return]):
        return None
    return round(ann_return - (risk_free + beta * (benchmark_ann_return - risk_free)), 4)


def _compute_sharpe(
    daily_returns: pd.Series,
    ann_return: Optional[float],
    risk_free: float = RISK_FREE_RATE,
) -> Optional[float]:
    """Sharpe = (Ann_Return - RF) / (Daily_Std * sqrt(252))"""
    if ann_return is None or len(daily_returns) < 30:
        return None
    std = daily_returns.std()
    if std == 0:
        return None
    ann_std = std * np.sqrt(252)
    return round((ann_return - risk_free) / ann_std, 4)


# ── PERIOD DATE HELPERS ───────────────────────────────────────────────────────

def _get_period_dates(as_of: pd.Timestamp) -> dict:
    """Return start dates for MTD, QTD, YTD, 1YR, 3YR, 5YR."""
    return {
        "MTD": pd.Timestamp(as_of.year, as_of.month, 1),
        "QTD": pd.Timestamp(as_of.year, ((as_of.month - 1) // 3) * 3 + 1, 1),
        "YTD": pd.Timestamp(as_of.year, 1, 1),
        "1YR": as_of - pd.DateOffset(years=1),
        "3YR": as_of - pd.DateOffset(years=3),
        "5YR": as_of - pd.DateOffset(years=5),
    }


# ── MAIN SUMMARY BUILDER ──────────────────────────────────────────────────────

def build_performance_summary(
    daily_state: pd.DataFrame,
    level: str = "investment",
    uber_filter: Optional[dict] = None,
) -> pd.DataFrame:
    """
    Build the summary performance table from chained daily state.

    Returns DataFrame with columns:
    investment | MTD | QTD | YTD | 1YR | 3YR | 5YR | Annualized | Beta | Alpha | Sharpe | is_benchmark
    """

    if daily_state.empty:
        return pd.DataFrame()

    daily_state = daily_state.copy()
    daily_state["ibor_date"] = pd.to_datetime(daily_state["ibor_date"])

    # Apply uber_filter if provided
    if uber_filter:
        field = list(uber_filter.keys())[0]
        value = str(uber_filter[field]).upper()
        if field in daily_state.columns:
            daily_state = daily_state[
                daily_state[field].astype(str).str.upper() == value
            ].copy()

    investments = sorted(daily_state[level].unique())

    # As-of date = last date in dataset
    as_of = daily_state["ibor_date"].max()
    period_starts = _get_period_dates(as_of)

    # Inception date
    inception = daily_state["ibor_date"].min()
    inception_days = (as_of - inception).days

    # ── BENCHMARK DAILY RETURNS ───────────────────────────────────────
    spx_returns = None
    spx_ann_return = None
    if PRIMARY_BENCHMARK in investments:
        spx_returns = _compute_daily_returns(daily_state, PRIMARY_BENCHMARK, level)
        spx_total = _period_return(daily_state, PRIMARY_BENCHMARK, inception, as_of, level)
        if spx_total is not None:
            spx_ann_return = _annualize(spx_total, inception_days)

    # ── BUILD ROWS ────────────────────────────────────────────────────
    rows = []

    for inv in investments:
        is_benchmark = inv in BENCHMARK_SYMBOLS

        inv_df = daily_state[daily_state[level] == inv].sort_values("ibor_date")
        if inv_df.empty:
            continue

        # Period returns
        period_returns = {}
        for period_name, start_date in period_starts.items():
            period_returns[period_name] = _period_return(
                daily_state, inv, start_date, as_of, level
            )

        # Inception to date
        total_return = _period_return(daily_state, inv, inception, as_of, level)
        ann_return   = _annualize(total_return, inception_days) if total_return is not None else None

        # Analytics — skip for benchmarks
        beta   = None
        alpha  = None
        sharpe = None

        if not is_benchmark and spx_returns is not None:
            inv_returns = _compute_daily_returns(daily_state, inv, level)
            beta        = _compute_beta(inv_returns, spx_returns)
            alpha       = _compute_alpha(ann_return, beta, spx_ann_return)
            sharpe      = _compute_sharpe(inv_returns, ann_return)

        rows.append({
            level:          inv,
            "MTD":          period_returns.get("MTD"),
            "QTD":          period_returns.get("QTD"),
            "YTD":          period_returns.get("YTD"),
            "1YR":          period_returns.get("1YR"),
            "3YR":          period_returns.get("3YR"),
            "5YR":          period_returns.get("5YR"),
            "Annualized":   ann_return,
            "Beta":         beta,
            "Alpha":        alpha,
            "Sharpe":       sharpe,
            "is_benchmark": is_benchmark,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Sort: investments first (alphabetical), benchmarks last
    investments_df = df[~df["is_benchmark"]].sort_values(level)
    benchmarks_df  = df[df["is_benchmark"]].sort_values(level)
    df = pd.concat([investments_df, benchmarks_df], ignore_index=True)

    return df


# ── FORMATTING HELPER ─────────────────────────────────────────────────────────

def format_performance_summary(df: pd.DataFrame, level: str = "investment") -> pd.DataFrame:
    """
    Format the summary DataFrame for display.
    Converts decimals to percentage strings, rounds analytics.
    """
    if df.empty:
        return df

    out = df.copy()

    pct_cols = ["MTD", "QTD", "YTD", "1YR", "3YR", "5YR", "Annualized", "Alpha"]
    for col in pct_cols:
        if col in out.columns:
            out[col] = out[col].apply(
                lambda x: f"{x*100:.2f}%" if pd.notna(x) and x is not None else "—"
            )

    float_cols = ["Beta", "Sharpe"]
    for col in float_cols:
        if col in out.columns:
            out[col] = out[col].apply(
                lambda x: f"{x:.2f}" if pd.notna(x) and x is not None else "—"
            )

    # Drop internal flag from display
    if "is_benchmark" in out.columns:
        out = out.drop(columns=["is_benchmark"])

    return out


# ── REGISTERED COMPUTE FUNCTION ───────────────────────────────────────────────

def compute_performance_summary(
    portfolio:    str,
    calendar:     str,
    period_start: str,
    period_end:   str,
    level:        str            = "investment",
    uber_filter:  Optional[dict] = None,
    prep:         Optional[dict] = None,
) -> ComputeResult:
    """
    Registered compute function for the FIG architecture.
    Returns formatted performance summary table.
    """

    t_total = time.perf_counter()

    if prep is None:
        raise ValueError("prep is required.")

    journal_entries = prep["journal_entries"]
    if not journal_entries:
        return ComputeResult(
            function="compute_performance_summary",
            portfolio=portfolio,
            calendar=calendar,
            period_start=period_start,
            period_end=period_end,
            shape="performance_summary",
            data=pd.DataFrame(),
            valid=False,
            errors=["No journal entries"],
            metadata={},
        )

    # ── GET AVAILABLE PERIODS ─────────────────────────────────────────
    available_periods = _get_available_periods(portfolio, calendar)
    periods = _sorted_periods(period_start, period_end, available_periods)

    # ── GET CACHED DAILY STATE ────────────────────────────────────────
    cache_key = (portfolio, calendar, period_start, period_end)

    daily_state, build_ms, cache_hit = _get_cached_daily_state(
        cache_key=cache_key,
        journal_entries=journal_entries,
        periods=periods,
        calendar=calendar,
        portfolio=portfolio,
    )

    if daily_state.empty:
        return ComputeResult(
            function="compute_performance_summary",
            portfolio=portfolio,
            calendar=calendar,
            period_start=period_start,
            period_end=period_end,
            shape="performance_summary",
            data=pd.DataFrame(),
            valid=False,
            errors=["No daily state"],
            metadata={},
        )

    # ── BUILD SUMMARY ─────────────────────────────────────────────────
    summary_df = build_performance_summary(
        daily_state=daily_state,
        level=level,
        uber_filter=uber_filter,
    )

    # ── FORMAT FOR DISPLAY ────────────────────────────────────────────
    output_df = format_performance_summary(summary_df, level=level)

    t_total_ms = (time.perf_counter() - t_total) * 1000

    print(
        f">>> compute_performance_summary COMPLETE "
        f"| {len(output_df)} rows "
        f"| {t_total_ms:.0f}ms total"
    )

    return ComputeResult(
        function="compute_performance_summary",
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        shape="performance_summary",
        data=output_df,
        valid=True,
        errors=[],
        metadata={
            "elapsed_ms":  round(t_total_ms, 1),
            "cache_hit":   cache_hit,
            "rows":        len(output_df),
            "as_of":       str(daily_state["ibor_date"].max().date()),
            "inception":   str(daily_state["ibor_date"].min().date()),
        },
    )