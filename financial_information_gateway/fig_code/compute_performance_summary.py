"""
compute_performance_summary.py
──────────────────────────────────────────────────────────────────────────────
Performance Summary Report

Produces a single summary table per entity showing:
  TWR | days_held | Contribution <ccy> | Contribution BPS | Beta | Alpha | Sharpe
INCEPT additionally appends the period scan MTD..5YR + Annualized, and — when a
benchmark is configured — a per-period EXCESS column ("YTD vs SPX") plus a
benchmark row at the bottom.

Benchmark series is fed from refdata/index_master.csv (rebased levels), with the
symbol resolved from the portfolio's primary_benchmark config (via prep).
Beta / Alpha / Sharpe and the excess columns are all computed against it.

Input:  chained daily state DataFrame from _build_chained_daily_state
Output: summary DataFrame ready for UI rendering
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd

from financial_information_gateway.fig_code.compute_result import ComputeResult
from financial_information_gateway.fig_code.compute_performance import (
    _get_cached_daily_state,
    _get_available_periods,
    _sorted_periods,
    _merge_aif,
    _rechain_aggregated_state,
)

from financial_information_gateway.fig_code.fig_performance_carving import aggregate_by_aif
from v_config import REFDATA_PATH, FUNDS_PATH

# ── CONSTANTS ─────────────────────────────────────────────────────────────────
# Canonical index keys (match index_master.csv columns and portfolio.json)
INDEX_KEYS        = {"SPX", "IXIC", "RUT", "IEF"}
INDEX_DISPLAY     = {"SPX": "S&P 500", "IXIC": "NASDAQ",
                     "RUT": "Russell 2000", "IEF": "Treasury (IEF)"}
DEFAULT_BENCHMARK = "SPX"
RISK_FREE_RATE    = 0.0   # configurable — set via portfolio.json risk_free_rate


# ── RETURN CALCULATION ────────────────────────────────────────────────────────

def _index_return(start_index: float, end_index: float) -> Optional[float]:
    """Calculate return from two index values."""
    if start_index is None or start_index == 0:
        return None
    return (end_index / start_index) - 1.0


def _annualize(total_return: float, days: int) -> Optional[float]:
    """Annualize a total return over a number of calendar days."""
    if total_return is None or days <= 0 or total_return <= -1.0:
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
    Trailing-window return for investment between start_date and end_date,
    using Index_Local (the fully chained index).

    Anchoring:
      - If a row exists STRICTLY BEFORE start_date -> anchor to it (normal
        trailing window).
      - If NO row exists before start_date but the entity has rows at/after it,
        the window opens at/before the entity's inception. Anchor to the
        entity's own first row (inception-style) rather than returning None.
      - If the entity has no rows in range at all -> None ("—").
    """
    inv_df = df[df[level] == investment].sort_values("ibor_date")
    if inv_df.empty:
        return None

    in_range = inv_df[
        (inv_df["ibor_date"] >= start_date) &
        (inv_df["ibor_date"] <= end_date)
        ]
    if in_range.empty:
        return None

    prior = inv_df[inv_df["ibor_date"] < start_date]
    if not prior.empty:
        start_idx = float(prior.iloc[-1]["Index_Local"])
    else:
        first = in_range.iloc[0]
        twr0 = first["TWR_Local"]
        if pd.isna(twr0):
            start_idx = 1.0
        elif float(twr0) == -1.0:
            return None
        else:
            start_idx = float(first["Index_Local"]) / (1.0 + float(twr0))

    if start_idx == 0:
        return None
    end_idx = float(in_range.iloc[-1]["Index_Local"])
    return _index_return(start_idx, end_idx)


def _inception_return(
    df: pd.DataFrame,
    investment: str,
    end_date: pd.Timestamp,
    level: str = "investment",
) -> Optional[float]:
    """
    Inception-to-date return for investment, anchored to its OWN first row
    (day-one), through end_date. Uses Index_Local.
    """
    inv_df = df[df[level] == investment].sort_values("ibor_date")
    if inv_df.empty:
        return None

    first = inv_df.iloc[0]
    twr0 = first["TWR_Local"]
    if pd.isna(twr0):
        start_idx = 1.0
    elif float(twr0) == -1.0:
        return None
    else:
        start_idx = float(first["Index_Local"]) / (1.0 + float(twr0))
    if start_idx == 0:
        return None

    at_or_before = inv_df[inv_df["ibor_date"] <= end_date]
    if at_or_before.empty:
        return None
    end_idx = float(at_or_before.iloc[-1]["Index_Local"])

    return _index_return(start_idx, end_idx)


# ── ANALYTICS ─────────────────────────────────────────────────────────────────

def _compute_daily_returns(df: pd.DataFrame, investment: str, level: str = "investment") -> pd.Series:
    """Extract daily TWR returns for an investment as a Series indexed by date."""
    inv_df = df[df[level] == investment].sort_values("ibor_date")
    s = inv_df.set_index("ibor_date")["TWR_Local"]
    s.index = pd.to_datetime(s.index).normalize()
    return s


def _compute_beta(inv_returns: pd.Series, benchmark_returns: pd.Series) -> Optional[float]:
    """Beta = Cov(inv, benchmark) / Var(benchmark) using aligned daily history."""
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
    if ann_return is None or daily_returns is None or len(daily_returns) < 30:
        return None
    std = daily_returns.std()
    if std == 0:
        return None
    ann_std = std * np.sqrt(252)
    return round((ann_return - risk_free) / ann_std, 4)


# ── BENCHMARK FEED (from index_master.csv) ────────────────────────────────────

def _load_benchmark_levels(symbol: str) -> Optional[pd.Series]:
    """
    Load the rebased LEVEL series for one index key from refdata/index_master.csv.
    Returns a date-indexed Series, or None (fail-soft) if the file or column is
    missing — callers then skip benchmark columns and the benchmark row.
    """
    try:
        path = Path(REFDATA_PATH) / "index_master.csv"
        if not path.exists():
            print(f">>> index_master.csv not found at {path} — benchmark columns blank")
            return None
        df = pd.read_csv(path, parse_dates=["date"]).set_index("date")
        df.index = pd.to_datetime(df.index).normalize()
        if symbol not in df.columns:
            print(f">>> benchmark '{symbol}' not in index_master columns {list(df.columns)}")
            return None
        return df[symbol].sort_index()
    except Exception as e:
        print(f">>> _load_benchmark_levels failed: {e}")
        return None


def _build_benchmark_frame(levels: pd.Series, level: str, symbol: str,
                           as_of: pd.Timestamp) -> Optional[pd.DataFrame]:
    """
    Shape the benchmark level series like an entity frame so the existing
    _period_return / _inception_return logic works on it unchanged:
        ibor_date | Index_Local (rebased level) | TWR_Local (daily return) | <level>=symbol
    """
    s = levels[levels.index <= as_of]
    if s.empty:
        return None
    frame = pd.DataFrame({
        "ibor_date":   s.index,
        "Index_Local": s.values.astype(float),
        "TWR_Local":   s.pct_change().values,   # row-0 NaN -> base anchor (=1.0)
    })
    frame[level] = symbol
    return frame


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
        cadence: str = "INCEPT",
        base_currency: str = "USD",
        portfolio_period: Optional[dict] = None,
        benchmark_symbol: Optional[str] = None,
        benchmark_levels: Optional[pd.Series] = None,
        risk_free: float = RISK_FREE_RATE,
) -> pd.DataFrame:
    """
    Build the performance summary table from chained daily state.

    Benchmark (optional): if benchmark_symbol + benchmark_levels are supplied,
    each period gets an EXCESS column ("<PERIOD> vs <SYMBOL>" = entity - bench),
    Beta/Alpha/Sharpe are computed vs the benchmark, and a benchmark row is
    appended (its own period returns; contribution blank; Beta=1, Alpha=0).
    All benchmark features are fail-soft: absent series -> none of them appear.
    """
    if daily_state.empty:
        return pd.DataFrame()

    if uber_filter:
        field = list(uber_filter.keys())[0]
        value = str(uber_filter[field]).upper()
        if field in daily_state.columns:
            mask = daily_state[field].astype(str).str.upper() == value
            daily_state = daily_state[mask]

    daily_state = daily_state.copy()
    daily_state["ibor_date"] = pd.to_datetime(daily_state["ibor_date"])
    if daily_state.empty:
        return pd.DataFrame()

    investments = sorted(daily_state[level].unique())
    as_of = daily_state["ibor_date"].max()
    inception = daily_state["ibor_date"].min()
    inception_days = (as_of - inception).days
    period_starts = _get_period_dates(as_of)

    is_portfolio_level = (level == "portfolio")
    cadence = cadence.upper()
    portfolio_period = portfolio_period or {}

    if cadence == "INCEPT":
        sel_start = None
    else:
        sel_start = period_starts.get(cadence)

    contrib_col = f"Contribution {base_currency}"

    # ── BENCHMARK SETUP (fail-soft) ───────────────────────────────────
    bench_frame = None
    bench_daily = None
    bench_ann_return = None
    bench_label = benchmark_symbol
    if benchmark_symbol and benchmark_levels is not None and not benchmark_levels.empty:
        bench_frame = _build_benchmark_frame(benchmark_levels, level, benchmark_symbol, as_of)
        if bench_frame is not None and not bench_frame.empty:
            bench_daily = benchmark_levels.pct_change().dropna()
            bench_daily.index = pd.to_datetime(bench_daily.index).normalize()
            bench_incept = _period_return(bench_frame, benchmark_symbol, inception, as_of, level)
            bench_ann_return = _annualize(bench_incept, inception_days)

    def _bench_window(start):
        if bench_frame is None:
            return None
        return _period_return(bench_frame, benchmark_symbol, start or inception, as_of, level)

    def _excess(entity_val, bench_val):
        if entity_val is None or bench_val is None:
            return None
        return entity_val - bench_val

    def _window_earnings(inv_df, start, end):
        """Sum the TWR numerator over [start, end]. None if no rows in range."""
        w = inv_df[(inv_df["ibor_date"] >= (start or inv_df["ibor_date"].min())) &
                   (inv_df["ibor_date"] <= end)]
        if w.empty:
            return None, 0
        earn = (
                w["EMV_Book"] - w["Previous_EMV_Book"]
                - w["Open_CF_Book"] - w["Close_CF_Book"] - w["Currency_Flows_Book"]
        ).sum()
        if not is_portfolio_level:
            earn += w["Income_Book"].sum()
        days_held = int((w["EMV_Book"] != 0).sum())
        return float(earn), days_held

    rows = []
    for inv in investments:
        inv_df = daily_state[daily_state[level] == inv].sort_values("ibor_date")
        if inv_df.empty:
            continue

        # Selected-window return
        if cadence == "INCEPT" or sel_start is None:
            sel_return = _inception_return(daily_state, inv, as_of, level)
        else:
            sel_return = _period_return(daily_state, inv, sel_start, as_of, level)

        # Selected-window earnings + days_held
        earn, days_held = _window_earnings(inv_df, sel_start, as_of)

        # Contribution BPS
        contrib_bps = None
        pp = portfolio_period.get("INCEPT" if (cadence == "INCEPT" or sel_start is None)
                                  else cadence)
        if earn is not None and pp is not None:
            p_earn = pp.get("earnings")
            p_twr = pp.get("twr")
            if p_earn not in (None, 0) and p_twr is not None:
                contrib_bps = (earn / p_earn) * p_twr * 10000.0

        # Analytics
        ann_return = _annualize(
            _inception_return(daily_state, inv, as_of, level), inception_days
        )
        beta = alpha = sharpe = None
        if bench_daily is not None:
            inv_returns = _compute_daily_returns(daily_state, inv, level)
            beta = _compute_beta(inv_returns, bench_daily)
            alpha = _compute_alpha(ann_return, beta, bench_ann_return, risk_free)
            sharpe = _compute_sharpe(inv_returns, ann_return, risk_free)

        row = {
            level: inv,
            "TWR": sel_return,
            "days_held": days_held,
            contrib_col: earn,
            "Contribution BPS": contrib_bps,
            "Beta": beta,
            "Alpha": alpha,
            "Sharpe": sharpe,
            "is_benchmark": False,
        }

        # Selected-window excess
        if bench_frame is not None:
            row[f"TWR vs {bench_label}"] = _excess(sel_return, _bench_window(sel_start))

        # INCEPT appends the period scan (+ per-period excess).
        if cadence == "INCEPT":
            for pname, pstart in period_starts.items():
                e = _period_return(daily_state, inv, pstart, as_of, level)
                row[pname] = e
                if bench_frame is not None:
                    row[f"{pname} vs {bench_label}"] = _excess(e, _bench_window(pstart))
            row["Annualized"] = ann_return
            if bench_frame is not None:
                row[f"Annualized vs {bench_label}"] = _excess(ann_return, bench_ann_return)

        rows.append(row)

    # ── BENCHMARK ROW (its own returns; contribution blank; flagged) ──
    if bench_frame is not None:
        b_sel = _bench_window(sel_start)
        b_row = {
            level: bench_label,
            "TWR": b_sel,
            "days_held": None,
            contrib_col: None,
            "Contribution BPS": None,
            "Beta": 1.0,
            "Alpha": 0.0,
            "Sharpe": _compute_sharpe(bench_daily, bench_ann_return, risk_free),
            "is_benchmark": True,
            f"TWR vs {bench_label}": None,
        }
        if cadence == "INCEPT":
            for pname, pstart in period_starts.items():
                b_row[pname] = _bench_window(pstart)
                b_row[f"{pname} vs {bench_label}"] = None
            b_row["Annualized"] = bench_ann_return
            b_row[f"Annualized vs {bench_label}"] = None
        rows.append(b_row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    investments_df = df[~df["is_benchmark"]].sort_values(level)
    benchmarks_df = df[df["is_benchmark"]].sort_values(level)
    df = pd.concat([investments_df, benchmarks_df], ignore_index=True)
    return df


# ── FORMATTING HELPER ─────────────────────────────────────────────────────────

def format_performance_summary(df: pd.DataFrame, level: str = "investment") -> pd.DataFrame:
    """
    Format the summary DataFrame for display. Column-driven, so it handles every
    cadence and the optional benchmark columns.

    Formatting rules:
      - Return/percent columns (TWR, MTD..5YR, Annualized, Alpha) -> "x.xx%"
      - Excess columns ("<period> vs <bench>")                    -> "+x.xx%" (signed)
      - Contribution BPS                                          -> "x.x"
      - Contribution <ccy>                                        -> thousands-grouped
      - days_held                                                 -> integer
      - Beta, Sharpe                                              -> "x.xx"
    """
    if df.empty:
        return df

    out = df.copy()

    # ── EXCESS COLUMNS (signed percent) — handle first so they aren't ──
    #    swept up by the plain percent loop below.
    vs_cols = [c for c in out.columns if " vs " in c]
    for col in vs_cols:
        out[col] = out[col].apply(
            lambda x: f"{x * 100:+.2f}%" if pd.notna(x) and x is not None else "—"
        )

    # ── PERCENT COLUMNS ───────────────────────────────────────────────
    pct_cols = ["TWR", "MTD", "QTD", "YTD", "1YR", "3YR", "5YR",
                "Annualized", "Alpha"]
    for col in pct_cols:
        if col in out.columns:
            out[col] = out[col].apply(
                lambda x: f"{x * 100:.2f}%" if pd.notna(x) and x is not None else "—"
            )

    # ── CONTRIBUTION BPS ──────────────────────────────────────────────
    if "Contribution BPS" in out.columns:
        out["Contribution BPS"] = out["Contribution BPS"].apply(
            lambda x: f"{x:.1f}" if pd.notna(x) and x is not None else "—"
        )

    # ── CONTRIBUTION <CCY> ────────────────────────────────────────────
    contrib_ccy_cols = [
        c for c in out.columns
        if c.startswith("Contribution ") and c != "Contribution BPS"
    ]
    for col in contrib_ccy_cols:
        out[col] = out[col].apply(
            lambda x: f"{x:,.0f}" if pd.notna(x) and x is not None else "—"
        )

    # ── DAYS HELD ─────────────────────────────────────────────────────
    if "days_held" in out.columns:
        out["days_held"] = out["days_held"].apply(
            lambda x: f"{int(x):,}" if pd.notna(x) and x is not None else "—"
        )

    # ── FLOAT ANALYTICS (Beta, Sharpe) ────────────────────────────────
    for col in ["Beta", "Sharpe"]:
        if col in out.columns:
            out[col] = out[col].apply(
                lambda x: f"{x:.2f}" if pd.notna(x) and x is not None else "—"
            )

    # ── DROP INTERNAL FLAG ────────────────────────────────────────────
    if "is_benchmark" in out.columns:
        out = out.drop(columns=["is_benchmark"])

    # ── COLUMN ORDER (period beside its excess; analytics last) ───────
    # Safe reorder: build a preferred sequence from columns present, then
    # append anything not listed so no column is ever lost.
    periods_order = ["MTD", "QTD", "YTD", "1YR", "3YR", "5YR", "Annualized"]
    preferred = [level, "TWR"]
    preferred += [c for c in out.columns if c.startswith("TWR vs ")]
    preferred += ["days_held"]
    preferred += [c for c in out.columns
                  if c.startswith("Contribution ")]  # ccy + BPS
    for p in periods_order:
        if p in out.columns:
            preferred.append(p)
        preferred += [c for c in out.columns if c.startswith(p + " vs ")]
    preferred += ["Beta", "Alpha", "Sharpe"]
    final = [c for c in preferred if c in out.columns]
    final += [c for c in out.columns if c not in final]  # safety net
    out = out[final]

    return out


# ── REGISTERED COMPUTE FUNCTION ───────────────────────────────────────────────

def compute_performance_summary(
        portfolio: str,
        calendar: str,
        period_start: str,
        period_end: str,
        level: str = "investment",
        cadence: str = "INCEPT",
        uber_filter: Optional[dict] = None,
        prep: Optional[dict] = None,
) -> ComputeResult:
    """
    Registered compute function for the FIG architecture.
    Builds investment-level chained daily state from inception (cached),
    aggregates to the requested level, computes the portfolio-level period
    earnings + TWR (for Contribution BPS), feeds the configured benchmark from
    index_master.csv, and derives the summary.
    """
    t_total = time.perf_counter()

    if prep is None:
        raise ValueError("prep is required.")

    journal_entries = prep["journal_entries"]
    if not journal_entries:
        return ComputeResult(
            function="compute_performance_summary",
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            shape="performance_summary", data=pd.DataFrame(),
            valid=False, errors=["No journal entries"], metadata={},
        )

    available_periods = _get_available_periods(portfolio, calendar)
    periods = _sorted_periods(period_start, period_end, available_periods)

    cache_key = (portfolio, calendar, period_start, period_end)
    daily_state, build_ms, cache_hit = _get_cached_daily_state(
        cache_key=cache_key, journal_entries=journal_entries,
        periods=periods, calendar=calendar, portfolio=portfolio,
    )
    if daily_state.empty:
        return ComputeResult(
            function="compute_performance_summary",
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            shape="performance_summary", data=pd.DataFrame(),
            valid=False, errors=["No daily state"], metadata={},
        )

    # ── PORTFOLIO PERIOD FIGURES (denominators for Contribution BPS) ──
    ws_pf = daily_state.copy()
    ws_pf["portfolio"] = portfolio
    pf_state = aggregate_by_aif(ws_pf, "portfolio")
    pf_state = _rechain_aggregated_state(pf_state, "portfolio")
    pf_state["ibor_date"] = pd.to_datetime(pf_state["ibor_date"])

    pf_as_of = pf_state["ibor_date"].max()
    pf_starts = _get_period_dates(pf_as_of)

    def _pf_window(start):
        w = pf_state[(pf_state["ibor_date"] >= (start or pf_state["ibor_date"].min())) &
                     (pf_state["ibor_date"] <= pf_as_of)]
        if w.empty:
            return {"earnings": None, "twr": None}
        earn = (
                w["EMV_Book"] - w["Previous_EMV_Book"]
                - w["Open_CF_Book"] - w["Close_CF_Book"] - w["Currency_Flows_Book"]
        ).sum()
        twr = _period_return(pf_state, str(portfolio), (start or w["ibor_date"].min()),
                             pf_as_of, "portfolio")
        if start is None:
            twr = _inception_return(pf_state, str(portfolio), pf_as_of, "portfolio")
        return {"earnings": float(earn), "twr": twr}

    portfolio_period = {"INCEPT": _pf_window(None)}
    for pname, pstart in pf_starts.items():
        portfolio_period[pname] = _pf_window(pstart)

    # ── AGGREGATE to requested level ──────────────────────────────────
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

    # ── CONFIG-DRIVEN INPUTS (currency, benchmark, risk-free) ─────────
    base_currency     = prep.get("base_currency", "USD") if isinstance(prep, dict) else "USD"
    primary_benchmark = prep.get("primary_benchmark", DEFAULT_BENCHMARK) if isinstance(prep, dict) else DEFAULT_BENCHMARK
    pcfg              = prep.get("portfolio_config", {}) if isinstance(prep, dict) else {}
    risk_free         = float(pcfg.get("risk_free_rate", RISK_FREE_RATE) or 0.0)
    benchmark_levels  = _load_benchmark_levels(primary_benchmark)

    summary_df = build_performance_summary(
        daily_state=level_state, level=level, uber_filter=uber_filter,
        cadence=cadence, base_currency=base_currency,
        portfolio_period=portfolio_period,
        benchmark_symbol=primary_benchmark, benchmark_levels=benchmark_levels,
        risk_free=risk_free,
    )
    output_df = format_performance_summary(summary_df, level=level)

    t_total_ms = (time.perf_counter() - t_total) * 1000
    print(f">>> compute_performance_summary COMPLETE | level={level} "
          f"| cadence={cadence} | benchmark={primary_benchmark} "
          f"| {len(output_df)} rows | {t_total_ms:.0f}ms")

    return ComputeResult(
        function="compute_performance_summary",
        portfolio=portfolio, calendar=calendar,
        period_start=period_start, period_end=period_end,
        shape="performance_summary", data=output_df,
        valid=True, errors=[],
        metadata={
            "elapsed_ms": round(t_total_ms, 1), "cache_hit": cache_hit,
            "level": level, "cadence": cadence, "rows": len(output_df),
            "benchmark": primary_benchmark,
        },
    )