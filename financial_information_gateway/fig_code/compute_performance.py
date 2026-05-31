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

def compute_capital_flows(je_data, level):

    external_accounts = [
        "ContributedCost",
        # add more if needed
    ]

    ext_flows = je_data[
        je_data["financial_account"].isin(external_accounts)
    ][[
        level,
        "ibor_date",
        "local",
        "book"
    ]].copy()

    ext_flows = (
        ext_flows.groupby([level, "ibor_date"], as_index=False)
        .agg({"local": "sum", "book": "sum"})
    )

    ext_flows.rename(columns={
        "local": "External_CF_Local",
        "book": "External_CF_Book"
    }, inplace=True)

    return ext_flows

def compute_opening_cash_flows_investments(investment_master, je_data, level):
    currencies = ['USD', 'AUD', 'GBP', 'EUR', 'JPY']
    valid_accounts = ['Cost']

    # Define grouping columns based on the level
    #group_by_cols = [level, 'ibor_date'] if level != 'ibor_date' else ['ibor_date']
    group_by_cols = [level, 'ibor_date']

    # For non-currencies, apply the 'Book' > 0 filter.- For currencies, just check the valid accounts.

    # Conditions for filtering rows
    condition1 = (~je_data['investment'].isin(currencies) & (je_data['book'] > 0))
    condition2 = je_data['financial_account'].isin(valid_accounts)

    # Combine conditions
    opening_flows = je_data[condition1 & condition2]

    opening_flows = opening_flows.groupby(group_by_cols).agg(
        {'local': 'sum', 'book': 'sum'}).reset_index()

    # Rename columns for clarity
    opening_flows.rename(columns={'local': 'Open_CF_Local', 'book': 'Open_CF_Book'}, inplace=True)

    return opening_flows

def compute_cash_flows_currencies(investment_master, je_data, level):
    currencies = ['USD', 'AUD', 'GBP', 'EUR', 'JPY']
    valid_accounts = ['Cost', 'Payable', 'Receivable', 'DividendsReceivable', 'DividendsPayable',
                      'AccruedInterestPayable', 'AccruedInterestReceivable', 'DividendsReceivable',
                      'DividendsPayable', 'ExpensesPayable', 'InterestPayable', 'InterestReceivable']

    # Define grouping columns based on the level
    group_by_cols = [level,'ibor_date'] if level != 'ibor_date' else ['ibor_date']

    # For non-currencies, apply the 'Book' > 0 filter. For currencies, just check the valid accounts.

    # Conditions for filtering rows
    condition1 = je_data['investment'].isin(currencies)
    condition2 = je_data['financial_account'].isin(valid_accounts)

    # Combine conditions
    currency_flows = je_data[condition1 & condition2]

    currency_flows = currency_flows.groupby(group_by_cols).agg(
        {'local': 'sum', 'book': 'sum'}).reset_index()

    # Rename columns for clarity
    currency_flows.rename(columns={'local': 'Currency_Flows_Local', 'book': 'Currency_Flows_Book'}, inplace=True)

    return currency_flows

def compute_closing_cash_flows_for_investments(investment_master, je_data, level):
    currencies = ['USD', 'AUD', 'GBP', 'EUR', 'JPY']
    # Condition 1
    condition1 = je_data['financial_account'].isin(['PriceGainInvestment', 'FXGainInvestment'])
    # Condition 2
    condition2 = (je_data['financial_account'] == 'Cost') & (je_data['book'] < 0) & (je_data['ls'] == 'l')
    # Condition 3
    condition3 = (je_data['financial_account'] == 'Cost') & (je_data['book'] > 0) & (je_data['ls'] == 's')
    # Condition 4
    condition4 = ~je_data['investment'].isin(currencies)

    # Combine conditions
    closing_flows = je_data[(condition1 | condition2 | condition3) & condition4]

    # Group by Investment, IBOR Date, and Tax Date
    closing_flows_agg = closing_flows.groupby([level, 'ibor_date']).agg(
        {'local': 'sum', 'book': 'sum'}).reset_index()

    # Rename columns for clarity
    closing_flows_agg.rename(columns={'local': 'Close_CF_Local', 'book': 'Close_CF_Book'}, inplace=True)

    return closing_flows_agg

def compute_income(investment_master, je_data, level):


    print(je_data['financial_account'].unique())

# Must use a bitwise | as Python evaluates the expression in aggregate if OR is used!!!
    income_entries = je_data[(je_data['financial_account'] == 'DividendReceipt') |
                         (je_data['financial_account'] == 'FXGainCurrency') |
                         (je_data['financial_account'] == 'FXGainTradeSettle') |
                         (je_data['financial_account'] == 'AccruedInterestReceipt') |
                         (je_data['financial_account'] == 'AccruedInterestIncome') |
                         (je_data['financial_account'] == 'DividendExpense')]

    print(income_entries.head())
    # Group by both 'Investment' and 'IBOR Date' and flip the sign on the sum
    income_je_data = income_entries.groupby([level, 'ibor_date'])[['local', 'book']].sum().reset_index()

    # Flip the sign
    income_je_data[['local', 'book']] *= -1

    income_je_data.rename(columns={'local': 'Income_Local', 'book': 'Income_Book'}, inplace=True)

    return income_je_data

# ══════════════════════════════════════════════════════════════════════════════
# ORIGINAL compute_daily_twr — DOMAIN CODE — verbatim, do not alter logic.
# This REPLACES the collapsed refactored version in performance.py that
# calls compute_capital_flows. Signature is 5-arg:
#   (journal_entries, period_start, period_end, agg_level, level, include_local_currency=True)
# Returns: (finalized_inputs, summary_finalized_inputs, indices)
#
# The adapter _compute_daily_twr_period in compute_performance.py calls this
# with period_start/period_end derived from the journal date span.
# ══════════════════════════════════════════════════════════════════════════════

def compute_daily_twr(journal_entries, period_start, period_end, agg_level, level, include_local_currency=True):
    import os
    import pandas as pd

    # ✅ Load reference data
    coa_je_data = pd.read_csv("C:/Users/hjmne/PycharmProjects/chest/refdata/chart_of_accounts.csv", encoding="cp1252")
    investment_master = pd.read_csv("C:/Users/hjmne/PycharmProjects/chest/refdata/investment_master.csv",
                                    encoding="cp1252")

    # ✅ Normalize journal entries
    def normalize_journal_entries(journal_entries):
        data = [entry.to_dict() for entry in journal_entries]
        return pd.DataFrame(data)

    je_data = normalize_journal_entries(journal_entries)

    from business_days import get_previous_business_day
    adj_period_start = get_previous_business_day(period_start)

    # Fetch EMV from day before period_start — POLICY: day-1 BMV comes from
    # prior business day's ending market value.
    prior_je = [je.to_dict() for je in journal_entries if
                pd.to_datetime(je.ibor_date) == adj_period_start and je.financial_account == 'MarketVal']
    prior_df = pd.DataFrame(prior_je)

    if not prior_df.empty and 'investment' in prior_df.columns:
        prior_df = pd.merge(prior_df, investment_master[['Ticker', 'Analyst']],
                            left_on='investment', right_on='Ticker', how='left')
        prior_df.drop(columns='Ticker', inplace=True)

    if not prior_df.empty:
        prior_emv = prior_df.groupby(level).agg({
            'local': 'sum',
            'book': 'sum'
        }).reset_index().rename(columns={'local': 'BMV_Local', 'book': 'BMV_Book'})
    else:
        prior_emv = pd.DataFrame(columns=[level, 'BMV_Local', 'BMV_Book'])

    # ✅ Convert and filter by ibor_date
    je_data["ibor_date"] = pd.to_datetime(je_data["ibor_date"], errors="coerce")
    je_data = je_data[(je_data["ibor_date"] >= period_start) & (je_data["ibor_date"] <= period_end)]

    # ✅ Merge journal entries with investment master
    je_data = pd.merge(je_data, investment_master, left_on='investment', right_on='ticker', how='left').drop('ticker',
                                                                                                             axis=1)
    je_data.rename(columns=lambda col: col.replace('_y', '') if col.endswith('_y') else col, inplace=True)

    # ✅ Process market values
    market_values = je_data[je_data['financial_account'] == 'MarketVal']
    market_values = market_values.rename(columns={'local': 'EMV_Local', 'book': "EMV_Book"})
    market_values = market_values.groupby([level, 'ibor_date']).agg(
        {'EMV_Local': 'sum', 'EMV_Book': 'sum'}).reset_index()

    # ✅ Apply BMV logic
    market_values['ibor_date'] = pd.to_datetime(market_values['ibor_date'])
    market_values = market_values.sort_values(by=[level, 'ibor_date'])

    # Seed BMV from prior row's EMV within the period. First row of each
    # level-value gets 0 here (no prior row → NaN → 0). The prior-business-day
    # MarketVal patch below overwrites the first row ONLY for positions that
    # already existed. A level-value with no prior-day MarketVal keeps BMV = 0
    # on its first day — genuine inception — so the opening flow drives the
    # denominator: TWR = (EMV - Open_CF) / Open_CF.
    market_values['BMV_Local'] = market_values.groupby(level)['EMV_Local'].shift(1).fillna(0.0)
    market_values['BMV_Book'] = market_values.groupby(level)['EMV_Book'].shift(1).fillna(0.0)


    first_dates = market_values.groupby(level)['ibor_date'].min().reset_index()
    first_rows_mask = market_values.merge(first_dates, on=[level, 'ibor_date'], how='left', indicator=True)[
                          '_merge'] == 'both'

    market_values = pd.merge(market_values, prior_emv, on=level, how='left', suffixes=('', '_from_prior'))

    # Only overwrite where the prior value is actually present (not NaN).
    # Newer pandas raises on assigning an all-NaN array into float64 via .loc mask,
    # so guard with notna and coerce explicitly.
    prior_local = market_values['BMV_Local_from_prior']
    prior_book = market_values['BMV_Book_from_prior']

    local_mask = first_rows_mask & prior_local.notna()
    book_mask = first_rows_mask & prior_book.notna()

    market_values.loc[local_mask, 'BMV_Local'] = prior_local[local_mask].astype(float).values
    market_values.loc[book_mask, 'BMV_Book'] = prior_book[book_mask].astype(float).values

    market_values['BMV_Local'] = market_values['BMV_Local'].fillna(0)
    market_values['BMV_Book'] = market_values['BMV_Book'].fillna(0)
    market_values.drop(columns=['BMV_Local_from_prior', 'BMV_Book_from_prior'], inplace=True)

    # ✅ Merge cash flows and income data (three flow types kept SEPARATE)
    opening_flows = compute_opening_cash_flows_investments(investment_master, je_data, level)
    currency_flows = compute_cash_flows_currencies(investment_master, je_data, level)
    closing_flows = compute_closing_cash_flows_for_investments(investment_master, je_data, level)
    income_data = compute_income(investment_master, je_data, level)

    for df in [opening_flows, currency_flows, closing_flows, income_data]:
        df['ibor_date'] = pd.to_datetime(df['ibor_date'])
        market_values = pd.merge(market_values, df, on=[level, 'ibor_date'], how='left').fillna(0)

    # ✅ Initialize finalized_inputs
    finalized_inputs = market_values
    finalized_inputs = finalized_inputs.sort_values(by=[level, 'ibor_date'])

    finalized_inputs['Previous_EMV_Local'] = finalized_inputs.groupby(level)['EMV_Local'].shift(1)
    finalized_inputs['Previous_EMV_Book'] = finalized_inputs.groupby(level)['EMV_Book'].shift(1)

    bmv_map_local = market_values.groupby(level)['BMV_Local'].first().to_dict()
    bmv_map_book = market_values.groupby(level)['BMV_Book'].first().to_dict()
    first_rows = finalized_inputs.groupby(level).head(1).index

    for i in first_rows:
        lv = finalized_inputs.at[i, level]
        if lv in bmv_map_local:
            finalized_inputs.at[i, 'Previous_EMV_Local'] = bmv_map_local[lv]
        if lv in bmv_map_book:
            finalized_inputs.at[i, 'Previous_EMV_Book'] = bmv_map_book[lv]

    finalized_inputs['Previous_EMV_Local'] = finalized_inputs['Previous_EMV_Local'].fillna(0)
    finalized_inputs['Previous_EMV_Book'] = finalized_inputs['Previous_EMV_Book'].fillna(0)

    # ✅ Compute TWR — POLICY: level formula vs portfolio formula
    #   Non-portfolio: Open_CF in denominator, Currency conditional (same-sign),
    #                  income in numerator.
    #   Portfolio:     denominator = Previous_EMV only, no income term.
    def calculate_twr(row):
        if row[level] != 'portfolio':
            same_sign_local = (row['Previous_EMV_Local'] >= 0) == (row['Currency_Flows_Local'] >= 0)
            same_sign_book = (row['Previous_EMV_Book'] >= 0) == (row['Currency_Flows_Book'] >= 0)

            denominator_local = (row['Previous_EMV_Local'] + row['Open_CF_Local'] + (
                row['Currency_Flows_Local'] if same_sign_local else 0))
            denominator_book = (row['Previous_EMV_Book'] + row['Open_CF_Book'] + (
                row['Currency_Flows_Book'] if same_sign_book else 0))

            numerator_local = (
                    row['EMV_Local'] - row['Previous_EMV_Local'] - row['Open_CF_Local'] - row['Close_CF_Local'] -
                    row['Currency_Flows_Local'] + row['Income_Local'])
            numerator_book = (
                    row['EMV_Book'] - row['Previous_EMV_Book'] - row['Open_CF_Book'] - row['Close_CF_Book'] - row[
                'Currency_Flows_Book'] + row['Income_Book'])
        else:  # Portfolio Level Calculation
            numerator_local = (
                    row['EMV_Local'] - row['Previous_EMV_Local'] - row['Open_CF_Local'] - row['Close_CF_Local'] -
                    row['Currency_Flows_Local'])
            denominator_local = row['Previous_EMV_Local']

            numerator_book = (
                    row['EMV_Book'] - row['Previous_EMV_Book'] - row['Open_CF_Book'] - row['Close_CF_Book'] - row[
                'Currency_Flows_Book'])
            denominator_book = row['Previous_EMV_Book']

        twr_local = None if denominator_local == 0 else numerator_local / denominator_local
        twr_book = None if denominator_book == 0 else numerator_book / denominator_book

        return pd.Series([twr_local, twr_book], index=['TWR_Local', 'TWR_Book'])

    finalized_inputs[['TWR_Local', 'TWR_Book']] = finalized_inputs.apply(calculate_twr, axis=1)

    # ✅ Compute Cumulative Returns (within-period chain)
    finalized_inputs['LocalToDate'] = finalized_inputs.groupby(level)['TWR_Local'].transform(
        lambda x: (1 + x).cumprod())
    finalized_inputs['BookToDate'] = finalized_inputs.groupby(level)['TWR_Book'].transform(
        lambda x: (1 + x).cumprod())

    finalized_inputs['TWR_Local_Percent'] = finalized_inputs['TWR_Local'] * 100
    finalized_inputs['TWR_Book_Percent'] = finalized_inputs['TWR_Book'] * 100
    finalized_inputs['LocalToDate_Percent'] = (finalized_inputs['LocalToDate'] - 1) * 100
    finalized_inputs['BookToDate_Percent'] = (finalized_inputs['BookToDate'] - 1) * 100

    # ✅ Category Flows — REPORTING combination of the three types.
    #   Single net flow for the chosen level. Both sides ADD all three
    #   (the prior Book-side minus on Currency was a latent bug — fixed).
    finalized_inputs['Category_Flows_Local'] = (
            finalized_inputs['Open_CF_Local']
            + finalized_inputs['Close_CF_Local']
            + finalized_inputs['Currency_Flows_Local']
    )
    finalized_inputs['Category_Flows_Book'] = (
            finalized_inputs['Open_CF_Book']
            + finalized_inputs['Close_CF_Book']
            + finalized_inputs['Currency_Flows_Book']
    )

    return finalized_inputs

# ──────────────────────────────────────────────────────────────────────────────
# THIN ADAPTER — maps the period-by-period caller to the original
# compute_daily_twr signature WITHOUT touching its domain logic.
# The original compute_daily_twr stays exactly as written in performance.py.
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# PERIOD CHAINING ENGINE
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# THIN ADAPTER — maps the period-by-period caller to the original
# compute_daily_twr signature WITHOUT touching its domain logic.
# The original compute_daily_twr stays exactly as written in performance.py.
# ──────────────────────────────────────────────────────────────────────────────

def _compute_daily_twr_period(journal_entries, level, period_key):
    """
    Adapter for the period-by-period chaining caller.

    The original compute_daily_twr signature is:
        compute_daily_twr(journal_entries, period_start, period_end,
                          agg_level, level, include_local_currency=True)
        → returns (finalized_inputs, summary_finalized_inputs, indices)

    The caller passes prior+current period journals so BMV seeds correctly.
    period_start/period_end are derived from the journal entries' date span.
    No domain logic is altered — this only maps arguments.
    """
    dates = [pd.to_datetime(je.ibor_date) for je in journal_entries]
    period_start = min(dates)
    period_end = max(dates)

    finalized_inputs = compute_daily_twr(
        journal_entries,
        period_start,
        period_end,
        level,
        level,
        include_local_currency=True,
    )
    return finalized_inputs


# ──────────────────────────────────────────────────────────────────────────────
# PERIOD CHAINING ENGINE
# ──────────────────────────────────────────────────────────────────────────────

def _build_chained_daily_state(
        journal_entries: list,
        periods: list[str],
        calendar: str,
        level: str,
        portfolio: str,
) -> pd.DataFrame:
    """
    Core chaining engine. Calls the ORIGINAL compute_daily_twr (via thin
    adapter) per period and chains across period boundaries from inception.

    The original compute_daily_twr returns all domain columns, untouched:
      EMV_Local/Book, BMV_Local/Book, Previous_EMV_Local/Book,
      Open_CF_Local/Book, Close_CF_Local/Book,
      Currency_Flows_Local/Book, Income_Local/Book,
      Category_Flows_Local/Book,
      TWR_Local/Book, LocalToDate, BookToDate,
      TWR_*_Percent, LocalToDate_Percent, BookToDate_Percent

    This function PRESERVES every one of those columns and ADDS chained /
    cumulative columns carried from inception:
      - Index_Local/Book           = LocalToDate/BookToDate × prior ending index
      - Cum_Open_CF_Local/Book     = cumulative opening flows from inception
      - Cum_Close_CF_Local/Book    = cumulative closing flows from inception
      - Cum_Currency_Flows_*       = cumulative currency flows from inception
      - Cum_Income_Local/Book      = cumulative income from inception

    The three flow types stay SEPARATE and are RETURNED so a performance
    analyst can validate every TWR by hand. Delta of any cumulative between
    two dates = flows of that type over the range.
    """
    from financial_information_gateway.extraction.box_extractor import extract_box_components

    # ── PRIOR STATE TRACKERS — per level-value, carried from inception ────────
    prior_index: dict[str, dict] = {}
    prior_open_cf: dict[str, dict] = {}
    prior_close_cf: dict[str, dict] = {}
    prior_currency_cf: dict[str, dict] = {}
    prior_income: dict[str, dict] = {}

    all_frames: list[pd.DataFrame] = []

    for i, period_key in enumerate(periods):
        p_start, p_end = _period_boundaries(period_key, calendar)

        # ── LOAD JOURNALS (prior + current seeds BMV via shift) ───────────────
        if i == 0:
            extracted = extract_box_components(
                portfolio=portfolio, calendar=calendar,
                period_start=period_key, period_end=period_key,
            )
        else:
            prior_period_key = periods[i - 1]
            extracted = extract_box_components(
                portfolio=portfolio, calendar=calendar,
                period_start=prior_period_key, period_end=period_key,
            )

        period_jes = extracted["journal_entries"]
        if not period_jes:
            print(f">>> No journals for period {period_key} — skipping")
            continue

        # ── COMPUTE DAILY TWR via original domain function (adapter) ──────────
        period_df = _compute_daily_twr_period(period_jes, level, period_key)

        if period_df is None or period_df.empty:
            print(f">>> Empty TWR result for {period_key} — skipping")
            continue

        # ── FILTER TO CURRENT PERIOD ONLY ─────────────────────────────────────
        period_df["ibor_date"] = pd.to_datetime(period_df["ibor_date"])
        period_df = period_df[
            (period_df["ibor_date"] >= p_start) &
            (period_df["ibor_date"] <= p_end)
            ].copy()

        if period_df.empty:
            print(f">>> Empty after date filter for {period_key} — skipping")
            continue

        period_df = period_df.sort_values([level, "ibor_date"]).copy()

        # ── INITIALIZE CHAIN + CUMULATIVE COLUMNS ─────────────────────────────
        period_df["Index_Local"] = 0.0
        period_df["Index_Book"] = 0.0
        period_df["Cum_Open_CF_Local"] = 0.0
        period_df["Cum_Open_CF_Book"] = 0.0
        period_df["Cum_Close_CF_Local"] = 0.0
        period_df["Cum_Close_CF_Book"] = 0.0
        period_df["Cum_Currency_Flows_Local"] = 0.0
        period_df["Cum_Currency_Flows_Book"] = 0.0
        period_df["Cum_Income_Local"] = 0.0
        period_df["Cum_Income_Book"] = 0.0

        for lv in period_df[level].unique():
            lv_key = str(lv)
            mask = period_df[level] == lv

            # ── INDEX — within-period LocalToDate × prior ending index ────────
            prior_idx = prior_index.get(lv_key, {"local": 1.0, "book": 1.0})
            period_df.loc[mask, "Index_Local"] = (
                    period_df.loc[mask, "LocalToDate"] * prior_idx["local"]
            )
            period_df.loc[mask, "Index_Book"] = (
                    period_df.loc[mask, "BookToDate"] * prior_idx["book"]
            )

            # ── CUMULATIVE OPEN CF = within-period cumsum + prior ending ──────
            p_ocf = prior_open_cf.get(lv_key, {"local": 0.0, "book": 0.0})
            period_df.loc[mask, "Cum_Open_CF_Local"] = (
                    period_df.loc[mask, "Open_CF_Local"].cumsum() + p_ocf["local"]
            )
            period_df.loc[mask, "Cum_Open_CF_Book"] = (
                    period_df.loc[mask, "Open_CF_Book"].cumsum() + p_ocf["book"]
            )

            # ── CUMULATIVE CLOSE CF ───────────────────────────────────────────
            p_ccf = prior_close_cf.get(lv_key, {"local": 0.0, "book": 0.0})
            period_df.loc[mask, "Cum_Close_CF_Local"] = (
                    period_df.loc[mask, "Close_CF_Local"].cumsum() + p_ccf["local"]
            )
            period_df.loc[mask, "Cum_Close_CF_Book"] = (
                    period_df.loc[mask, "Close_CF_Book"].cumsum() + p_ccf["book"]
            )

            # ── CUMULATIVE CURRENCY FLOWS ─────────────────────────────────────
            p_fx = prior_currency_cf.get(lv_key, {"local": 0.0, "book": 0.0})
            period_df.loc[mask, "Cum_Currency_Flows_Local"] = (
                    period_df.loc[mask, "Currency_Flows_Local"].cumsum() + p_fx["local"]
            )
            period_df.loc[mask, "Cum_Currency_Flows_Book"] = (
                    period_df.loc[mask, "Currency_Flows_Book"].cumsum() + p_fx["book"]
            )

            # ── CUMULATIVE INCOME ─────────────────────────────────────────────
            p_inc = prior_income.get(lv_key, {"local": 0.0, "book": 0.0})
            period_df.loc[mask, "Cum_Income_Local"] = (
                    period_df.loc[mask, "Income_Local"].cumsum() + p_inc["local"]
            )
            period_df.loc[mask, "Cum_Income_Book"] = (
                    period_df.loc[mask, "Income_Book"].cumsum() + p_inc["book"]
            )

            # ── UPDATE PRIORS for next period ─────────────────────────────────
            prior_index[lv_key] = {
                "local": float(period_df.loc[mask, "Index_Local"].iloc[-1]),
                "book": float(period_df.loc[mask, "Index_Book"].iloc[-1]),
            }
            prior_open_cf[lv_key] = {
                "local": float(period_df.loc[mask, "Cum_Open_CF_Local"].iloc[-1]),
                "book": float(period_df.loc[mask, "Cum_Open_CF_Book"].iloc[-1]),
            }
            prior_close_cf[lv_key] = {
                "local": float(period_df.loc[mask, "Cum_Close_CF_Local"].iloc[-1]),
                "book": float(period_df.loc[mask, "Cum_Close_CF_Book"].iloc[-1]),
            }
            prior_currency_cf[lv_key] = {
                "local": float(period_df.loc[mask, "Cum_Currency_Flows_Local"].iloc[-1]),
                "book": float(period_df.loc[mask, "Cum_Currency_Flows_Book"].iloc[-1]),
            }
            prior_income[lv_key] = {
                "local": float(period_df.loc[mask, "Cum_Income_Local"].iloc[-1]),
                "book": float(period_df.loc[mask, "Cum_Income_Book"].iloc[-1]),
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

    Performance is a PERSPECTIVE on accounting. The chain and cumulative
    flows depend on ALL history from inception, so the build ALWAYS starts
    at inception (available_periods[0]) regardless of the requested
    period_start. The requested period_start controls DISPLAY only — the
    output is filtered to the display window after the chain is built,
    aggregated, and carved.

    First call for a given portfolio/calendar/inception→period_end span
    builds the chained daily state and caches it. All subsequent calls are
    cache hits — carving, aggregation, and display-window filtering run on
    the cached state in sub-second time.

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

    # Build ALWAYS starts at inception — the chain and cumulative flows
    # depend on all prior history. period_start controls display only.
    inception = available_periods[0]

    build_periods   = _sorted_periods(inception, period_end, available_periods)
    display_periods = _sorted_periods(period_start, period_end, available_periods)
    periods = build_periods  # builder chains the full inception→period_end span

    print(
        f">>> compute_performance | {portfolio} | {calendar} "
        f"| build {inception} → {period_end} ({len(build_periods)} periods) "
        f"| display {period_start} → {period_end} ({len(display_periods)} periods) "
        f"| level={level} | cadence={cadence}"
    )

    # ── CACHE KEY ─────────────────────────────────────────────────────
    # Build span is inception → period_end, so the cache keys on that span —
    # NOT the display period_start. Any display window ending at period_end
    # reuses the same built chain. uber_filter is applied AFTER cache
    # retrieval so the full portfolio state is always cached and any single
    # investment is served from it instantly without a per-investment entry.
    cache_key = (portfolio, calendar, inception, period_end)

    # ── GET OR BUILD CHAINED DAILY STATE ─────────────────────────────
    # Always build the FULL portfolio with the full journal list and full
    # cache_key. uber_filter is applied to the cached DataFrame afterward,
    # so single-investment queries hit the cache instantly instead of
    # triggering a fresh build every call.
    daily_state, build_ms, cache_hit = _get_cached_daily_state(
        cache_key=cache_key,
        journal_entries=journal_entries,
        periods=periods,
        calendar=calendar,
        portfolio=portfolio,
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
    # Single-investment queries filter the full cached state here.
    if uber_filter:
        field = list(uber_filter.keys())[0]
        value = str(uber_filter[field]).upper()
        if field in daily_state.columns:
            daily_state = daily_state[
                daily_state[field].astype(str).str.upper() == value
            ].copy()
            print(
                f">>> uber_filter {field}={value} "
                f"→ {len(daily_state)} daily-state rows"
            )

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

    # ── FILTER TO DISPLAY WINDOW ──────────────────────────────────────
    # The chain was built from inception. Now restrict the output to the
    # requested display window [period_start, period_end] inclusive. The
    # build covered inception → period_end; trimming the leading periods
    # leaves the chain/cumulatives intact (they were computed with full
    # history) while showing only the dates the caller asked for.
    if "ibor_date" in output_df.columns and display_periods:
        disp_start_dt, _ = _period_boundaries(display_periods[0], calendar)
        _, disp_end_dt   = _period_boundaries(display_periods[-1], calendar)
        od = pd.to_datetime(output_df["ibor_date"])
        output_df = output_df[
            (od >= disp_start_dt) & (od <= disp_end_dt)
        ].copy()

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
        "build_periods":   len(build_periods),
        "display_periods": len(display_periods),
        "inception":       inception,
        "output_rows":     len(output_df),
        "uber_filter":     uber_filter,
    }

    print(
        f">>> compute_performance COMPLETE "
        f"| {'CACHE HIT' if cache_hit else 'CACHE MISS — built'} "
        f"| {n_investments} investments "
        f"| build {len(build_periods)} / display {len(display_periods)} periods "
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