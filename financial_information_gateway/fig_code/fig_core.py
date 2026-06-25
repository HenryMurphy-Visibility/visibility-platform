# ============================================================
# Visibility — FIG Core
# fig_core.py
#
# Shared infrastructure for all compute functions.
# Three responsibilities only:
#   1. prep_state   — load state and journals for a period
#   2. render       — route compute results to GWI or API
#   3. Shared imports and constants
#
# Compute functions import from here.
# Nothing else belongs here.
# ============================================================

import pickle
import calendar as cal
from pathlib import Path
from datetime import datetime

import pandas as pd

from v_config import FUNDS_PATH
from financial_information_gateway.fig_code.compute_result import ComputeResult

import re

_THREE_DECIMAL_COLS = re.compile(r"(qty|quantity|notional)", re.IGNORECASE)

def _round_for_column(col, val):
    return round(val, 3) if _THREE_DECIMAL_COLS.search(col) else round(val, 2)


def _parse_period_to_cutoff(period_key: str, end_of_period: bool = True) -> datetime:
    """
    Parse any period key format to a cutoff datetime.
    end_of_period=True  → last moment of the period (23:59:59)
    end_of_period=False → first moment of the period (00:00:00)
    """
    if 'Q' in period_key:
        year, q = period_key.split('-Q')
        month = (int(q) - 1) * 3 + 1
        dt = datetime(int(year), month, 1)
        # End of quarter = end of last month in quarter
        end_month = month + 2
        last_day = cal.monthrange(int(year), end_month)[1]
        dt = datetime(int(year), end_month, last_day)
    elif len(period_key) == 4:
        # Yearly
        dt = datetime(int(period_key), 12, 31)
    elif len(period_key) == 7:
        # Monthly
        dt = datetime.strptime(period_key + "-01", "%Y-%m-%d")
        last_day = cal.monthrange(dt.year, dt.month)[1]
        dt = dt.replace(day=last_day)
    else:
        # Daily
        dt = datetime.strptime(period_key, "%Y-%m-%d")

    if end_of_period:
        return dt.replace(hour=23, minute=59, second=59)
    return dt
# ============================================================
# CONSTANTS
# ============================================================

ENGINE_TOLERANCE = 1e-9
TOLERANCE        = 1e-6
# ============================================================
# SESSION PREP CACHE
# Keyed by (portfolio, calendar, period_start, period_end)
# ============================================================

_PREP_CACHE = {}


def prep_state_cached(portfolio, calendar_name, period_start, period_end):
    """
    Cached version of prep_state.
    First call loads from disk and caches.
    Subsequent calls return instantly.
    Cache persists for the server session.

    NOTE: cache key intentionally EXCLUDES period_start. Prep loads
    journals inception→period_end regardless of the display window
    (period_start is a display filter applied downstream, same as in
    compute_performance's daily-state cache). Keying on period_start
    would force a needless 3.38M-JE reload every time only the display
    window changes while period_end stays put.
    """
    cache_key = (portfolio, calendar_name, period_end)

    if cache_key in _PREP_CACHE:
        print(f">>> PREP CACHE HIT | {portfolio} | {calendar_name} "
              f"| → {period_end}")
        return _PREP_CACHE[cache_key]

    print(f">>> PREP CACHE MISS | loading from disk...")
    result = prep_state(portfolio, calendar_name, period_start, period_end)
    _PREP_CACHE[cache_key] = result
    return result


def clear_prep_cache():
    """Clear the prep cache. Call when data changes."""
    global _PREP_CACHE
    _PREP_CACHE = {}
    print(">>> PREP CACHE CLEARED")


# ============================================================
# PREP
# ============================================================

def prep_state(portfolio, calendar_name, period_start, period_end):
    """
    Load state snapshots and journal entries for a period range.
    Returns a prep package consumed by all compute functions.
    Called once per session — cache the result if calling
    multiple compute functions against the same period.

    Journals are tagged at load time with is_adjustment=True/False
    based on which file they came from. This is the authoritative
    way to identify adjusting entries — the field does not exist
    on the journal objects themselves.
    """

    base_dir = (
        Path(FUNDS_PATH)
        / portfolio
        / "Calendars"
        / calendar_name
        / "Snapshots"
    )

    journals_dir = (
        Path(FUNDS_PATH)
        / portfolio
        / "Calendars"
        / calendar_name
        / "Journals"
    )

    # Load portfolio config once (currency, benchmark, etc.)
    cfg_path = Path(FUNDS_PATH) / portfolio / "portfolio.json"
    portfolio_config = {}
    if cfg_path.exists():
        import json
        with open(cfg_path) as f:
            portfolio_config = json.load(f)
    base_currency = portfolio_config.get("base_currency", "USD")
    primary_benchmark = portfolio_config.get("primary_benchmark", "SPX")
    # --------------------------------------------------
    # BUILD PERIOD MAP
    # --------------------------------------------------
    # --------------------------------------------------
    # BUILD PERIOD MAP
    # Supports all four calendar cadences:
    #   Yearly:    2021
    #   Quarterly: 2021-Q1
    #   Monthly:   2021-01
    #   Daily:     2021-01-01
    # --------------------------------------------------
    period_map = {}

    for snap in base_dir.glob("*.pkl"):
        try:
            date_str = snap.stem.split("T")[0]
            dt = datetime.strptime(date_str, "%Y-%m-%d")

            # Derive period key based on calendar cadence
            if calendar_name == "Yearly":
                period_key = f"{dt.year}"

            elif calendar_name == "Quarterly":
                q = (dt.month - 1) // 3 + 1
                period_key = f"{dt.year}-Q{q}"

            elif calendar_name == "Daily":
                period_key = dt.strftime("%Y-%m-%d")

            else:
                # Monthly and Operational
                period_key = f"{dt.year}-{dt.month:02d}"

            period_map[period_key] = snap

        except Exception:
            continue

    periods = sorted(period_map.keys())

    if period_start not in periods:
        raise ValueError(
            f"period_start '{period_start}' not found in snapshots. "
            f"Available: {periods}"
        )
    if period_end not in periods:
        raise ValueError(
            f"period_end '{period_end}' not found in snapshots. "
            f"Available: {periods}"
        )

    si = periods.index(period_start)
    ei = periods.index(period_end)

    # --------------------------------------------------
    # LOAD PRIOR STATE
    # --------------------------------------------------
    prior_state           = None
    prior_cutoff_datetime = None

    if si > 0:
        prior_period = periods[si - 1]

        with open(period_map[prior_period], "rb") as f:
            prior_state = pickle.load(f)["state"]

        prior_cutoff_datetime = _parse_period_to_cutoff(prior_period)

    # --------------------------------------------------
    # LOAD CURRENT STATE
    # --------------------------------------------------
    with open(period_map[period_end], "rb") as f:
        current_state = pickle.load(f)["state"]

    current_cutoff_datetime = _parse_period_to_cutoff(period_end)

    # --------------------------------------------------
    # LOAD JOURNALS
    # Tag each entry with is_adjustment at load time.
    # Print ONCE per file — not once per journal entry.
    # Regular file   → is_adjustment = False
    # Adjusting file → is_adjustment = True
    # --------------------------------------------------
    journals = []

    print(f">>> LOOP RANGE: si={si} ei={ei} "
          f"total_periods={len(periods[si:ei + 1])}")

    for i in range(si, ei + 1):
        stub = period_map[periods[i]].stem

        for suffix in ["regular", "adjusting"]:
            fpath = journals_dir / f"{stub}.{suffix}.pkl"

            if not fpath.exists():
                continue

            data = pickle.load(open(fpath, "rb"))

            if not isinstance(data, dict) or "journals" not in data:
                continue

            batch       = data["journals"]
            is_adj_flag = (suffix == "adjusting")

            # Tag all entries in this batch
            for j in batch:
                j.is_adjustment = is_adj_flag

            # Print ONCE per file
            print(f">>> TAGGED {len(batch)} entries as "
                  f"{'adjusting' if is_adj_flag else 'regular'} "
                  f"from {fpath.name}")

            journals.extend(batch)

    print(
        f">>> PREP COMPLETE | {portfolio} | {calendar_name} "
        f"| {period_start} → {period_end} "
        f"| {len(journals)} journal entries "
        f"| {sum(1 for j in journals if j.is_adjustment)} adjusting"
    )

    return {
        "portfolio":               portfolio,
        "calendar":                calendar_name,
        "period_start":            period_start,
        "period_end":              period_end,
        "prior_state":             prior_state,
        "current_state":           current_state,
        "journal_entries":         journals,
        "prior_cutoff_datetime":   prior_cutoff_datetime,
        "current_cutoff_datetime": current_cutoff_datetime,
        "base_currency": base_currency,
        "primary_benchmark": primary_benchmark,
        "portfolio_config": portfolio_config,
    }
# ============================================================
# RENDER
# ============================================================

def render(result: ComputeResult, target: str, options: dict = None):
    """
    Route a ComputeResult to the appropriate delivery mechanism.

    target='gwi'  — returns a PySide6 tab widget
    target='api'  — returns a JSON-serializable dict

    This is the only place in the architecture where GWI
    and API paths diverge. Everything upstream is identical.
    """

    options = options or {}

    if target == "gwi":
        return _render_gwi(result, options)

    elif target == "api":
        return _render_api(result, options)

    else:
        raise ValueError(f"Unknown render target: '{target}'. "
                         f"Use 'gwi' or 'api'.")


def _render_gwi(result: ComputeResult, options: dict):
    """
    Format a ComputeResult for the GWI tab system.
    Returns a QWidget ready for insertion into the tab widget.
    """
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableView
    from PySide6.QtGui import QStandardItemModel, QStandardItem, QColor
    from PySide6.QtCore import Qt, QSortFilterProxyModel

    df = result.data

    if df is None or df.empty:
        widget = QWidget()
        return widget

    visible_columns = options.get("visible_columns")
    if visible_columns:
        df = df[[c for c in visible_columns if c in df.columns]]

    # Build model
    model   = QStandardItemModel()
    columns = list(df.columns)
    model.setColumnCount(len(columns))
    model.setHorizontalHeaderLabels(columns)

    for _, row in df.iterrows():
        items      = []
        is_adjustment = (
            "entry_type" in df.columns and
            row.get("entry_type") == "adjustment"
        )
        for val in row:
            item = QStandardItem("" if val is None else str(val))
            item.setEditable(False)
            if is_adjustment:
                item.setBackground(QColor(255, 230, 230))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            items.append(item)
        model.appendRow(items)

    # Proxy for sorting and filtering
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)

    table = QTableView()
    table.setModel(proxy)
    table.setSortingEnabled(True)
    table.horizontalHeader().setStretchLastSection(True)

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.addWidget(table)

    return widget


def _render_api(result: ComputeResult, options: dict):
    """
    Serialize a ComputeResult to a JSON-compatible dict
    for the FastAPI response layer.
    """

    df = result.data
    page = options.get("page", 1)
    page_size = options.get("page_size", 20000)

    # Paginate
    if df is not None and not df.empty:
        total_rows = len(df)
        start = (page - 1) * page_size
        end = start + page_size
        page_df = df.iloc[start:end]

        records = []
        for _, row in page_df.iterrows():
            record = {}
            for col, val in row.items():
                if pd.isna(val):
                    record[col] = None
                elif hasattr(val, "isoformat"):
                    record[col] = val.isoformat(sep=":")
                elif isinstance(val, float):
                    record[col] = _round_for_column(col, val)
                else:
                    record[col] = val
            records.append(record)
    else:
        records = []
        total_rows = 0

    meta = result.metadata
    v_side_ms = meta.get("elapsed_ms", 0)
    rows_returned = min(page_size, total_rows - (page - 1) * page_size)
    rows_returned = max(0, rows_returned)

    # ── SUMMARY — readable by anyone ──────────────────────────
    summary = {
        "what_you_asked_for": (
            f"{result.portfolio} · {result.calendar} · "
            f"{result.period_start} to {result.period_end} · "
            f"{result.function.replace('compute_', '').replace('_', ' ').title()}"
        ),
        "rows_returned": rows_returned,
        "total_rows": total_rows,
        "time_to_compute": f"{v_side_ms / 1000:.2f} seconds",
        "time_to_compute_ms": round(v_side_ms, 1),
        "computed_on": "Cloud Server · No Database · Pure Python",
        "investments_in_portfolio": meta.get("investments", 0),
        "cache": "HIT — sub-second" if meta.get("cache_hit") else "MISS — built fresh",
        "dataset": {
            "history": "5 years · 2021–2025",
            "journals": "3.8 million journal entries",
            "states": "1,300+ immutable period snapshots",
            "calendars": "Daily · Monthly · Quarterly · Yearly",
        },
        "page": page,
        "pages": max(1, -(-total_rows // page_size)),
    }

    # ── PERFORMANCE — for techies ──────────────────────────────
    performance = {
        "v_side_total_ms": round(v_side_ms, 1),
        "v_side_readable": f"{v_side_ms / 1000:.2f} seconds",
        "breakdown": {
            "state_load_ms": round(meta.get("prep_ms", 0), 1),
            "reference_data_ms": round(meta.get("refdata_ms", 0), 1),
            "position_extract_ms": round(meta.get("extract_ms", 0), 1),
            "market_value_calc_ms": round(meta.get("calc_ms", 0), 1),
            "dataframe_build_ms": round(meta.get("dataframe_ms", 0), 1),
        },
        "processed": {
            "investments": meta.get("investments", 0),
            "tax_lots": meta.get("detail_rows", 0),
            "journal_entries": meta.get("journal_count", 0),
        },
        "pagination": {
            "total_rows": total_rows,
            "page": page,
            "page_size": page_size,
            "pages": max(1, -(-total_rows // page_size)),
            "rows_returned": rows_returned,
        }
    }

    return {
        "summary": summary,
        "function": result.function,
        "portfolio": result.portfolio,
        "calendar": result.calendar,
        "period_start": result.period_start,
        "period_end": result.period_end,
        "shape": result.shape,
        "valid": result.valid,
        "errors": result.errors,
        "data": records,
        "performance": performance,
    }
quit()