"""
compute_performance.py
──────────────────────────────────────────────────────────────────────────────
Registered compute function for the fig_code architecture.

Architecture:
  - prep_state provides all journal entries for the full requested range
  - Journals are split into calendar periods internally
  - compute_daily_twr runs at daily grain for each period
  - Period_Index is chained: ending index of period N becomes the Prior_Index
    multiplier for period N+1
  - The fully chained daily state is cached at module level after first build
  - All subsequent calls (any cadence, level, filter) hit the cache instantly
  - Carving and aggregation run on the cached state — sub-second always

Cache key: (portfolio, calendar, period_start, period_end)
Cache holds: investment-level chained daily state DataFrame
Cache scope: server session — persists until server restart

This is the same pattern as _PRICE_INDEX in compute_appraisal.py.
First call builds and caches. Every call after is a cache hit.

Drop into:
  financial_information_gateway/fig_code/compute_performance.py

Register in compute_registry.py:
  from financial_information_gateway.fig_code.compute_performance import compute_performance
  COMPUTE_REGISTRY["compute_performance"] = compute_performance
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

import pandas as pd

from financial_information_gateway.fig_code.compute_result import ComputeResult
from performance import compute_daily_twr
from financial_information_gateway.fig_performance_carving import (
    performance_carving_periods,
    aggregate_by_aif,
)
from v_config import REFDATA_PATH, FUNDS_PATH


# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

VALID_LEVELS = {
    "investment",
    "sector",
    "analyst",
    "country",
    "currency",
    "asset_class",
    "investment_type",
    "portfolio",
}

VALID_CADENCES = {None, "D", "M", "Q", "Y"}

AIF_FIELDS = {
    "sector", "analyst", "country", "currency", "asset_class", "investment_type"
}


# ──────────────────────────────────────────────────────────────────────────────
# MODULE-LEVEL DAILY STATE CACHE
# Keyed by (portfolio, calendar, period_start, period_end)
# Value: investment-level chained daily state DataFrame
# Same pattern as _PRICE_INDEX in compute_appraisal.py
# ──────────────────────────────────────────────────────────────────────────────

_DAILY_STATE_CACHE: dict[tuple, pd.DataFrame] = {}


def clear_performance_cache():
    """
    Clear the daily state cache.
    Call when underlying data changes and cache needs to be rebuilt.
    """
    global _DAILY_STATE_CACHE
    _DAILY_STATE_CACHE = {}
    print(">>> PERFORMANCE CACHE CLEARED")


def _get_cached_daily_state(
        cache_key: tuple,
        journal_entries: list,
        periods: list[str],
        calendar: str,
        portfolio: str,  # ADD THIS
) -> tuple[pd.DataFrame, float, bool]:


    """
    Return (daily_state, build_ms, cache_hit).

    If cache_key exists → return cached DataFrame instantly.
    If not → build chained daily state, cache it, return it.

    Build time is only paid once per server session per range.
    """
    global _DAILY_STATE_CACHE

    if cache_key in _DAILY_STATE_CACHE:
        print(f">>> PERFORMANCE CACHE HIT | {cache_key}")
        return _DAILY_STATE_CACHE[cache_key], 0.0, True

    print(f">>> PERFORMANCE CACHE MISS | building {len(periods)} periods...")
    t_build = time.perf_counter()

    daily_state = _build_chained_daily_state(
        journal_entries=journal_entries,
        periods=periods,
        calendar=calendar,
        level="investment",
        portfolio=portfolio,  # ADD THIS
    )

    build_ms = (time.perf_counter() - t_build) * 1000

    if not daily_state.empty:
        _DAILY_STATE_CACHE[cache_key] = daily_state
        print(
            f">>> PERFORMANCE CACHE STORED | {cache_key} "
            f"| {len(daily_state)} rows "
            f"| {build_ms:.0f}ms build time"
        )

    return daily_state, build_ms, False


# ──────────────────────────────────────────────────────────────────────────────
# PERIOD UTILITIES
# ──────────────────────────────────────────────────────────────────────────────

def _derive_period_key(date: pd.Timestamp, calendar: str) -> str:
    """Convert a date to a period key matching the calendar format."""
    cal = calendar.lower()
    if cal == "monthly":
        return date.strftime("%Y-%m")
    elif cal == "quarterly":
        q = (date.month - 1) // 3 + 1
        return f"{date.year}-Q{q}"
    elif cal == "yearly":
        return str(date.year)
    else:
        return date.strftime("%Y-%m-%d")


def _period_boundaries(
    period_key: str, calendar: str
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return (start_date, end_date) for a period key."""
    cal = calendar.lower()
    if cal == "monthly":
        start = pd.to_datetime(period_key + "-01")
        end = start + pd.offsets.MonthEnd(0)
    elif cal == "quarterly":
        year, q = period_key.split("-Q")
        month_start = (int(q) - 1) * 3 + 1
        start = pd.Timestamp(year=int(year), month=month_start, day=1)
        end = start + pd.offsets.QuarterEnd(0)
    elif cal == "yearly":
        start = pd.Timestamp(year=int(period_key), month=1, day=1)
        end = pd.Timestamp(year=int(period_key), month=12, day=31)
    else:
        start = pd.to_datetime(period_key)
        end = start
    return start, end


def _sorted_periods(
    period_start: str,
    period_end: str,
    available_periods: list[str],
) -> list[str]:
    """
    Return the slice of available_periods between period_start and
    period_end inclusive. Uses actual snapshot-derived period list.
    """
    si = available_periods.index(period_start)
    ei = available_periods.index(period_end)
    return available_periods[si: ei + 1]


def _get_available_periods(portfolio: str, calendar: str) -> list[str]:
    """
    Scan snapshot files on disk and return sorted list of period keys.
    Same logic as prep_state — ensures period keys always match.
    """
    from pathlib import Path

    snap_dir = (
        Path(FUNDS_PATH)
        / portfolio
        / "Calendars"
        / calendar
        / "Snapshots"
    )

    available = []
    for snap in sorted(snap_dir.glob("*.pkl")):
        try:
            date_str = snap.stem.split("T")[0]
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            pk = _derive_period_key(pd.Timestamp(dt), calendar)
            available.append(pk)
        except Exception:
            continue

    return sorted(set(available))


# ──────────────────────────────────────────────────────────────────────────────
# INVESTMENT MASTER — module-level cache
# ──────────────────────────────────────────────────────────────────────────────

_INVESTMENT_MASTER: Optional[pd.DataFrame] = None


def _load_investment_master() -> pd.DataFrame:
    """Load investment_master.csv once and cache at module level."""
    global _INVESTMENT_MASTER
    if _INVESTMENT_MASTER is None:
        import os
        path = os.path.join(REFDATA_PATH, "investment_master.csv")
        df = pd.read_csv(path, encoding="cp1252")
        df.columns = [c.strip().lower() for c in df.columns]
        if "ticker" in df.columns and "investment" not in df.columns:
            df = df.rename(columns={"ticker": "investment"})
        df["investment"] = df["investment"].astype(str).str.upper().str.strip()
        _INVESTMENT_MASTER = df
    return _INVESTMENT_MASTER


def _merge_aif(df: pd.DataFrame, level: str) -> pd.DataFrame:
    """Merge AIF field from investment_master onto investment-level daily state."""
    master = _load_investment_master()

    if level not in master.columns:
        raise ValueError(
            f"Level '{level}' not found in investment_master. "
            f"Available: {master.columns.tolist()}"
        )

    mapping = (
        master[["investment", level]]
        .drop_duplicates()
        .dropna(subset=[level])
    )

    df = df.merge(mapping, on="investment", how="left")

    unmapped = df[level].isna().sum()
    if unmapped > 0:
        print(f"⚠️  {unmapped} rows have no '{level}' mapping in investment_master")

    return df


# ──────────────────────────────────────────────────────────────────────────────
# PERIOD CHAINING ENGINE
# ──────────────────────────────────────────────────────────────────────────────

def _build_chained_daily_state(
        journal_entries: list,
        periods: list[str],
        calendar: str,
        level: str,
        portfolio: str,  # ADD THIS
) -> pd.DataFrame:


    """
    Core chaining engine. Runs compute_daily_twr at daily grain for each
    period and chains the resulting Index across period boundaries.

    For each period, loads the PRIOR period's journal entries alongside
    the current period so BMV is correctly seeded on day 1 via shift(1).

    Prior_Index tracked independently per level-value so each investment
    carries its own unbroken chain.
    """
    from financial_information_gateway.extraction.box_extractor import extract_box_components

    prior_index: dict[str, dict] = {}
    all_frames: list[pd.DataFrame] = []

    for i, period_key in enumerate(periods):
        p_start, p_end = _period_boundaries(period_key, calendar)

        # ── LOAD JOURNALS ─────────────────────────────────────────
        # If first period — use current period only
        # If subsequent — load prior + current so shift(1) seeds BMV
        if i == 0:
            extracted = extract_box_components(
                portfolio=_portfolio_from_journals(journal_entries),
                calendar=calendar,
                period_start=period_key,
                period_end=period_key,
            )
        else:
            prior_period_key = periods[i - 1]
            extracted = extract_box_components(
                portfolio=_portfolio_from_journals(journal_entries),
                calendar=calendar,
                period_start=prior_period_key,
                period_end=period_key,
            )

        period_jes = extracted["journal_entries"]

        if not period_jes:
            print(f">>> No journals for period {period_key} — skipping")
            continue

        # ── COMPUTE DAILY TWR ─────────────────────────────────────
        period_df, _, _ = compute_daily_twr(period_jes, level, period_key)

        if period_df is None or period_df.empty:
            print(f">>> Empty TWR result for {period_key} — skipping")
            continue

        # ── FILTER TO CURRENT PERIOD ONLY ────────────────────────
        # Prior period journals seed BMV via shift(1) but we only
        # keep current period rows in the output
        period_df["ibor_date"] = pd.to_datetime(period_df["ibor_date"])
        period_df = period_df[
            (period_df["ibor_date"] >= p_start) &
            (period_df["ibor_date"] <= p_end)
            ].copy()

        if period_df.empty:
            print(f">>> Empty after date filter for {period_key} — skipping")
            continue

        period_df = period_df.sort_values([level, "ibor_date"]).copy()

        # ── CHAIN INDEX ───────────────────────────────────────────
        period_df["Index_Local"] = 0.0
        period_df["Index_Book"] = 0.0

        for lv in period_df[level].unique():
            lv_key = str(lv)
            mask = period_df[level] == lv
            prior = prior_index.get(lv_key, {"local": 1.0, "book": 1.0})

            period_df.loc[mask, "Index_Local"] = (
                    period_df.loc[mask, "Period_Index_Local"] * prior["local"]
            )
            period_df.loc[mask, "Index_Book"] = (
                    period_df.loc[mask, "Period_Index_Book"] * prior["book"]
            )

            prior_index[lv_key] = {
                "local": float(period_df.loc[mask, "Index_Local"].iloc[-1]),
                "book": float(period_df.loc[mask, "Index_Book"].iloc[-1]),
            }

        all_frames.append(period_df)

    if not all_frames:
        return pd.DataFrame()

    final = (
        pd.concat(all_frames, ignore_index=True)
        .sort_values([level, "ibor_date"])
        .drop_duplicates(subset=[level, "ibor_date"], keep="last")
        .reset_index(drop=True)
    )

    return final


def _portfolio_from_journals(journal_entries: list) -> str:
    """Extract portfolio name from first journal entry."""
    if journal_entries:
        return getattr(journal_entries[0], "portfolio", "Portfolio1")
    return "Portfolio1"



# ──────────────────────────────────────────────────────────────────────────────
# AGGREGATED LEVEL HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _rechain_aggregated_state(df: pd.DataFrame, level: str) -> pd.DataFrame:
    """Add Book columns if missing after aggregate_by_aif."""
    df = df.copy()
    if "Index_Book"   not in df.columns:
        df["Index_Book"]   = df["Index_Local"]
    if "CumCF_Book"   not in df.columns:
        df["CumCF_Book"]   = df.get("CumCF_Local",  0.0)
    if "CumInc_Book"  not in df.columns:
        df["CumInc_Book"]  = df.get("CumInc_Local", 0.0)
    return df


_INDEX_CACHE: dict = {}

def _load_index_returns(refdata_path: str) -> pd.DataFrame:
    """Load SPY, AGG, TLT daily returns from prices.csv. Cached at module level."""
    global _INDEX_CACHE
    if _INDEX_CACHE:
        return _INDEX_CACHE.get("returns", pd.DataFrame())

    import os
    prices_path = os.path.join(refdata_path, "price_master.csv")
    if not os.path.exists(prices_path):
        return pd.DataFrame()

    try:
        df = pd.read_csv(prices_path)
        indices = ["SPY", "AGG", "TLT"]
        df = df[df["symbol"].isin(indices)].copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(["symbol", "date"])

        # Compute daily return per index
        df["daily_return"] = df.groupby("symbol")["price"].pct_change()

        # Pivot to wide format: date | SPY | AGG | TLT
        pivot = df.pivot(index="date", columns="symbol", values="daily_return")
        pivot = pivot.reset_index().rename(columns={"date": "ibor_date"})

        # Build chain index for each
        for sym in indices:
            if sym in pivot.columns:
                pivot[f"{sym}_index"] = (1 + pivot[sym].fillna(0)).cumprod()

        _INDEX_CACHE["returns"] = pivot
        return pivot

    except Exception as e:
        print(f">>> Index returns load failed: {e}")
        return pd.DataFrame()

# ──────────────────────────────────────────────────────────────────────────────
# MAIN COMPUTE FUNCTION
# ──────────────────────────────────────────────────────────────────────────────

def compute_performance(
    portfolio:    str,
    calendar:     str,
    period_start: str,
    period_end:   str,
    level:        str           = "investment",
    cadence:      Optional[str] = None,
    uber_filter:  Optional[dict] = None,
    prep:         Optional[dict] = None,
) -> ComputeResult:
    """
    Compute chained Time-Weighted Returns for the requested range,
    level, and cadence.

    First call for a given portfolio/calendar/range builds the chained
    daily state and caches it. All subsequent calls are cache hits —
    carving and aggregation run on the cached state in sub-second time.

    prep is required. It is a dict returned by prep_state().
    All access via prep["key"].

    Daily grain is always the computational foundation.
    Cadence controls output presentation only.
    """

    t_total = time.perf_counter()

    # ── VALIDATION ────────────────────────────────────────────────────
    if level not in VALID_LEVELS:
        raise ValueError(
            f"Invalid level '{level}'. Valid: {sorted(VALID_LEVELS)}"
        )
    if cadence not in VALID_CADENCES:
        raise ValueError(
            f"Invalid cadence '{cadence}'. Valid: {VALID_CADENCES}"
        )
    if prep is None:
        raise ValueError(
            "prep is required. Call prep_state() and pass the result."
        )

    # ── JOURNALS FROM PREP DICT ───────────────────────────────────────
    t_state = time.perf_counter()

    journal_entries = prep["journal_entries"]

    if not journal_entries:
        return ComputeResult(
            function="compute_performance",
            portfolio=portfolio,
            calendar=calendar,
            period_start=period_start,
            period_end=period_end,
            shape="performance",
            data=pd.DataFrame(),
            valid=False,
            errors=["No journal entries in prep state"],
            metadata={},
        )

    # Apply uber_filter for single-investment queries
    # Filter BEFORE cache lookup — cache always holds full portfolio state
    filtered_entries = journal_entries
    if uber_filter:
        field = list(uber_filter.keys())[0]
        value = str(uber_filter[field]).upper()
        filtered_entries = [
            je for je in journal_entries
            if str(getattr(je, field, "")).upper() == value
        ]
        print(
            f">>> uber_filter {field}={value} "
            f"→ {len(filtered_entries)} journal entries"
        )

    t_state_ms = (time.perf_counter() - t_state) * 1000

    # ── PERIOD LIST ───────────────────────────────────────────────────
    available_periods = _get_available_periods(portfolio, calendar)

    if period_start not in available_periods:
        raise ValueError(
            f"period_start '{period_start}' not found in snapshots."
        )
    if period_end not in available_periods:
        raise ValueError(
            f"period_end '{period_end}' not found in snapshots."
        )

    periods = _sorted_periods(period_start, period_end, available_periods)

    print(
        f">>> compute_performance | {portfolio} | {calendar} "
        f"| {period_start} → {period_end} "
        f"| {len(periods)} periods | level={level} | cadence={cadence}"
    )

    # ── CACHE KEY ─────────────────────────────────────────────────────
    # Cache is keyed on full portfolio range only — NOT on uber_filter.
    # uber_filter is applied after cache retrieval so the full portfolio
    # state is always cached and any single investment can be served
    # from it instantly without a separate cache entry per investment.
    cache_key = (portfolio, calendar, period_start, period_end)

    # ── GET OR BUILD CHAINED DAILY STATE ─────────────────────────────
    # Pass filtered_entries to the builder when uber_filter is set —
    # smaller dataset, faster build on first filtered call.
    # For full portfolio (no filter) the full journal list is used
    # and the result is cached for all subsequent calls.
    entries_for_build = filtered_entries if uber_filter else journal_entries

    daily_state, build_ms, cache_hit = _get_cached_daily_state(
        cache_key=cache_key if not uber_filter else None,
        journal_entries=entries_for_build,
        periods=periods,
        calendar=calendar,
        portfolio=portfolio,  # ADD THIS
    )

    if daily_state.empty:
        return ComputeResult(
            function="compute_performance",
            portfolio=portfolio,
            calendar=calendar,
            period_start=period_start,
            period_end=period_end,
            shape="performance",
            data=pd.DataFrame(),
            valid=False,
            errors=["No daily state produced — check journals and period range"],
            metadata={},
        )

    # ── FILTER CACHED STATE for uber_filter ──────────────────────────
    # If we hit the full-portfolio cache, filter the DataFrame now
    if cache_hit and uber_filter:
        field = list(uber_filter.keys())[0]
        value = str(uber_filter[field]).upper()
        if field in daily_state.columns:
            daily_state = daily_state[
                daily_state[field].astype(str).str.upper() == value
            ].copy()

    # ── AGGREGATE to requested level ──────────────────────────────────
    t_agg = time.perf_counter()

    if level == "investment":
        level_state = daily_state

    elif level == "portfolio":
        ws = daily_state.copy()
        ws["portfolio"] = portfolio
        level_state = aggregate_by_aif(ws, "portfolio")
        level_state = _rechain_aggregated_state(level_state, "portfolio")

    else:
        ws = _merge_aif(daily_state.copy(), level)
        level_state = aggregate_by_aif(ws, level)
        level_state = _rechain_aggregated_state(level_state, level)

    t_agg_ms = (time.perf_counter() - t_agg) * 1000

    # ── CARVING — presentation layer only ────────────────────────────
    t_carve = time.perf_counter()

    if cadence is None or cadence == "D":
        output_df = level_state.copy()
        if "ibor_date" in output_df.columns:
            output_df["ibor_date"] = pd.to_datetime(
                output_df["ibor_date"]
            ).dt.strftime("%Y-%m-%d")
    else:
        output_df = performance_carving_periods(
            level_state,
            level=level,
            cadence=cadence,
        )

    t_carve_ms = (time.perf_counter() - t_carve) * 1000

    # ── MERGE INDEX RETURNS ───────────────────────────────────────────
    try:
        index_returns = _load_index_returns(REFDATA_PATH)
        if not index_returns.empty and "ibor_date" in output_df.columns:
            index_returns["ibor_date"] = pd.to_datetime(
                index_returns["ibor_date"]
            ).dt.strftime("%Y-%m-%d")
            output_df = output_df.merge(
                index_returns,
                on="ibor_date",
                how="left"
            )
    except Exception as e:
        print(f">>> Index merge failed (non-fatal): {e}")

    # ── METADATA ──────────────────────────────────────────────────────
    t_total_ms = (time.perf_counter() - t_total) * 1000

    n_investments = (
        daily_state["investment"].nunique()
        if "investment" in daily_state.columns else 0
    )

    metadata = {
        "elapsed_ms":      round(t_total_ms, 1),
        "prep_ms":         round(t_state_ms, 1),
        "twr_chain_ms":    round(build_ms, 1),
        "aggregation_ms":  round(t_agg_ms, 1),
        "carving_ms":      round(t_carve_ms, 1),
        "cache_hit":       cache_hit,
        "investments":     n_investments,
        "periods_chained": len(periods),
        "journal_count":   len(filtered_entries),
        "output_rows":     len(output_df),
        "uber_filter":     uber_filter,
    }

    print(
        f">>> compute_performance COMPLETE "
        f"| {'CACHE HIT' if cache_hit else 'CACHE MISS — built'} "
        f"| {n_investments} investments "
        f"| {len(periods)} periods "
        f"| {len(output_df)} output rows "
        f"| {t_total_ms:.0f}ms total"
    )

    return ComputeResult(
        function="compute_performance",
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        shape="performance",
        data=output_df,
        valid=True,
        errors=[],
        metadata=metadata,
    )