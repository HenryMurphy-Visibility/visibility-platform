# ============================================================
# Visibility — Compute Appraisal
# compute_appraisal.py
#
# Point-in-time appraisal at tax lot level.
# Asset/liability positions only — revenue/expense excluded.
#
# Two modes:
#   period_open  — closing state of prior period (opening snapshot)
#   period_close — closing state of current period
#
# Calculated columns derived from price and FX data at query time.
# GL unrealized accounts excluded — market value calculated fresh.
# Currency investments collapsed to net position across accounts.
# Investment type grouping with correct column visibility rules.
# ============================================================

import time
import pandas as pd
from datetime import datetime
from pathlib import Path
from itertools import groupby

from v_config import FUNDS_PATH, REFDATA_PATH

from financial_information_gateway.fig_code.compute_result import ComputeResult
from financial_information_gateway.fig_code.fig_core import prep_state, render

# ============================================================
# CONSTANTS
# ============================================================

UNREALIZED_ACCOUNTS = {
    "UnrealizedGainLoss",
    "UnrealizedFX",
    "UnrealizedGainLossLocal",
    "UnrealizedFXLocal",
}


# ============================================================
# APPLICATION-LEVEL REFERENCE DATA CACHE
# Loaded once on first call — never reloaded during session
# Eliminates per-request file IO for reference data
# ============================================================

_PRICE_ROWS        = None
_FX_ROWS           = None
_INVESTMENT_MASTER = None
_PRICE_CACHE       = {}
_FX_CACHE          = {}


def _ensure_reference_data():
    """
    Load reference data once and cache at module level.
    First call loads from disk — all subsequent calls are instant.
    """
    global _PRICE_ROWS, _FX_ROWS, _INVESTMENT_MASTER

    if _PRICE_ROWS is None:
        t0 = time.perf_counter()
        print(">>> LOADING reference data (first call)...")
        _PRICE_ROWS        = _load_price_rows()
        _FX_ROWS           = _load_fx_rows()
        _INVESTMENT_MASTER = _load_investment_master()
        print(f">>> Reference data loaded and cached "
              f"| {len(_PRICE_ROWS)} price rows "
              f"| {len(_FX_ROWS)} fx rows "
              f"| {len(_INVESTMENT_MASTER)} investments "
              f"| {(time.perf_counter()-t0)*1000:.1f}ms")


# ============================================================
# REFERENCE DATA LOADERS
# ============================================================

def _load_price_rows():
    """
    Load price master from REFDATA_PATH.
    Returns list of dicts: date, ticker, currency, price
    Date kept as string — _get_price handles formatting.
    """
    path = Path(REFDATA_PATH) / "price_master.csv"

    df = pd.read_csv(
        path,
        dtype={
            "date":     str,
            "ticker":   str,
            "currency": str,
            "price":    float,
        },
        keep_default_na=False,
        encoding="cp1252",
    )

    return df.to_dict(orient="records")


def _load_fx_rows():
    """
    Load FX master from REFDATA_PATH.
    Returns list of dicts: date, currency, price
    """
    path = Path(REFDATA_PATH) / "fx_master.csv"

    df = pd.read_csv(
        path,
        dtype={
            "date":     str,
            "currency": str,
            "price":    float,
        },
        keep_default_na=False,
        encoding="cp1252",
    )

    return df.to_dict(orient="records")


def _load_investment_master():
    """
    Load investment master from REFDATA_PATH.
    Returns dict keyed by investment name.
    Carries is_currency flag for account collapsing logic.
    """
    path = Path(REFDATA_PATH) / "investment_master.csv"

    df = pd.read_csv(
        path,
        keep_default_na=False,
        encoding="cp1252"
    )

    master = {}
    for _, row in df.iterrows():
        inv = row.get("investment", "")
        if inv:
            master[inv] = {
                "currency":        row.get("currency", "USD"),
                "pricing_factor":  float(row.get("pricing_factor", 1) or 1),
                "investment_type": row.get("investment_type", "EQUITY"),
                "is_currency":     int(row.get("is_currency", 0) or 0),
                "ticker":          row.get("ticker", inv),
                "full_name":       row.get("full_name", ""),
                "sector":          row.get("sector", ""),
                "country":         row.get("country", ""),
                "analyst":         row.get("analyst", ""),
            }

    return master


# ============================================================
# DATE FORMATTING
# ============================================================

def _format_date(date):
    """Convert date to YYYY-MM-DD string for price/FX lookups."""
    if isinstance(date, str):
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%Y:%H:%M:%S"):
            try:
                return datetime.strptime(date, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return date
    if hasattr(date, "strftime"):
        return date.strftime("%Y-%m-%d")
    return str(date)


# ============================================================
# PRICE LOOKUP WITH FALLBACK
# ============================================================

def _get_price(investment, date, price_rows=None):
    """
    O(1) price lookup using pre-built index.
    Falls back to most recent prior date.
    """
    from datetime import timedelta

    _ensure_price_index()

    lookup_date = _format_date(date)
    prices_by_date = _PRICE_INDEX.get(investment)

    if not prices_by_date:
        return None

    if lookup_date in prices_by_date:
        return prices_by_date[lookup_date]

    # Fallback — walk backward
    d = datetime.strptime(lookup_date, "%Y-%m-%d")
    for _ in range(365):
        d -= timedelta(days=1)
        k = d.strftime("%Y-%m-%d")
        if k in prices_by_date:
            return prices_by_date[k]

    return None


def _get_fx_rate(currency, date, fx_rows=None):
    """
    O(1) FX lookup using pre-built index.
    USD always returns 1.0.
    Falls back to most recent prior date.
    """
    from datetime import timedelta

    if not currency or currency == "USD":
        return 1.0

    _ensure_price_index()

    lookup_date = _format_date(date)
    fx_by_date = _FX_INDEX.get(currency)

    if not fx_by_date:
        print(f"⚠ FX: '{currency}' not found — defaulting to 1.0")
        return 1.0

    if lookup_date in fx_by_date:
        return fx_by_date[lookup_date]

    # Fallback — walk backward
    d = datetime.strptime(lookup_date, "%Y-%m-%d")
    for _ in range(365):
        d -= timedelta(days=1)
        k = d.strftime("%Y-%m-%d")
        if k in fx_by_date:
            return fx_by_date[k]

    print(f"⚠ FX fallback exhausted for '{currency}' — defaulting to 1.0")
    return 1.0


# ============================================================
# PRE-INDEX PRICE ROWS BY TICKER
# Converts 826K row list into O(1) lookup dict
# Built once after reference data loads
# ============================================================

_PRICE_INDEX = {}   # ticker → {date_str → price}
_FX_INDEX    = {}   # currency → {date_str → price}


def _ensure_price_index():
    """
    Build ticker and FX indexes from loaded reference data.
    Called once after _ensure_reference_data().
    Converts linear scan O(n) to dict lookup O(1).
    """
    global _PRICE_INDEX, _FX_INDEX

    if _PRICE_INDEX:
        return  # Already built

    _ensure_reference_data()

    print(">>> BUILDING price index...")
    import time
    t0 = time.perf_counter()

    # Build price index
    for r in _PRICE_ROWS:
        ticker = r.get("ticker", "")
        date   = _format_date(r["date"])
        price  = float(r["price"])

        if ticker not in _PRICE_INDEX:
            _PRICE_INDEX[ticker] = {}
        _PRICE_INDEX[ticker][date] = price

    # Build FX index
    for r in _FX_ROWS:
        ccy   = r.get("currency", "")
        date  = _format_date(r["date"])
        price = float(r["price"])

        if ccy not in _FX_INDEX:
            _FX_INDEX[ccy] = {}
        _FX_INDEX[ccy][date] = price

    print(f">>> Price index built | "
          f"{len(_PRICE_INDEX)} tickers | "
          f"{len(_FX_INDEX)} currencies | "
          f"{(time.perf_counter()-t0)*1000:.1f}ms")

# ============================================================
# EXTRACT APPRAISAL ROWS FROM STATE
# ============================================================

def _extract_appraisal_rows(state, investment_master):
    """
    Extract asset/liability positions from state snapshot.
    Revenue/expense excluded.
    Currency investments collapsed to net position.
    """
    if not state:
        return []

    al_repo = state.get("asset_liability_repository")
    if not al_repo:
        return []

    raw          = []
    currency_nets = {}

    for subspace in al_repo.investment_positions.values():
        for key, row in subspace.entries.items():

            (_, inv, lotid, tax_date, ls, loc, fa) = key

            # Skip unrealized GL accounts
            if fa in UNREALIZED_ACCOUNTS:
                continue

            qty   = row[0] if len(row) > 0 else 0.0
            local = row[1] if len(row) > 1 else 0.0
            book  = row[2] if len(row) > 2 else 0.0

            attrs       = investment_master.get(inv, {})
            is_currency = attrs.get("is_currency", 0)

            if is_currency == 1:
                # Collapse all accounts to net position
                if inv not in currency_nets:
                    currency_nets[inv] = {
                        "investment":        inv,
                        "full_name":         attrs.get("full_name", ""),
                        "lotid":             None,
                        "tax_date":          None,
                        "location":          loc,
                        "ls":                ls,
                        "financial_account": "NET",
                        "currency":          attrs.get("currency", "USD"),
                        "pricing_factor":    attrs.get("pricing_factor", 1.0),
                        "investment_type":   attrs.get("investment_type", "CURRENCY"),
                        "is_currency":       1,
                        "sector":            attrs.get("sector", ""),
                        "country":           attrs.get("country", ""),
                        "analyst":           attrs.get("analyst", ""),
                        "qty":               0.0,
                        "local_cost":        0.0,
                        "book_cost":         0.0,
                    }
                currency_nets[inv]["qty"]        += qty
                currency_nets[inv]["local_cost"] += local
                currency_nets[inv]["book_cost"]  += book

            else:
                # Skip zero quantity lots
                if abs(qty) < 1e-9:
                    continue

                raw.append({
                    "investment":        inv,
                    "full_name":         attrs.get("full_name", ""),
                    "lotid":             lotid,
                    "tax_date":          tax_date,
                    "location":          loc,
                    "ls":                ls,
                    "financial_account": fa,
                    "currency":          attrs.get("currency", "USD"),
                    "pricing_factor":    attrs.get("pricing_factor", 1.0),
                    "investment_type":   attrs.get("investment_type", "EQUITY"),
                    "is_currency":       0,
                    "sector":            attrs.get("sector", ""),
                    "country":           attrs.get("country", ""),
                    "analyst":           attrs.get("analyst", ""),
                    "qty":               qty,
                    "local_cost":        local,
                    "book_cost":         book,
                })

    # Add non-zero currency nets
    for inv, net in currency_nets.items():
        if abs(net["qty"]) >= 1e-9 or abs(net["book_cost"]) >= 1e-9:
            raw.append(net)

    return raw


# ============================================================
# CALCULATE MARKET VALUES
# ============================================================

def _calculate_market_values(rows, appraisal_date, price_rows, fx_rows):
    """
    Add calculated columns to appraisal rows.
    Market value and price gain derived from prices at appraisal_date.
    Vectorized — builds price and FX lookups once for all investments.
    """

    if not rows:
        return rows

    lookup_date = _format_date(appraisal_date)

    # --------------------------------------------------
    # BUILD PRICE LOOKUP DICT ONCE FOR ALL INVESTMENTS
    # Key: ticker → price at appraisal_date (with fallback)
    # Much faster than per-investment lookup in a loop
    # --------------------------------------------------
    all_investments = set(r["investment"] for r in rows)

    price_lookup = {}
    for inv in all_investments:
        price_lookup[inv] = _get_price(inv, appraisal_date, price_rows)

    # --------------------------------------------------
    # BUILD FX LOOKUP DICT ONCE FOR ALL CURRENCIES
    # --------------------------------------------------
    all_currencies = set(r["currency"] for r in rows)

    fx_lookup = {}
    for ccy in all_currencies:
        fx_lookup[ccy] = _get_fx_rate(ccy, appraisal_date, fx_rows)

    # --------------------------------------------------
    # APPLY TO ALL ROWS — pure dict lookups, no IO
    # --------------------------------------------------
    enriched = []

    for r in rows:
        inv = r["investment"]
        qty = r["qty"]
        local_cost = r["local_cost"]
        book_cost = r["book_cost"]
        currency = r["currency"]
        pricing_factor = r["pricing_factor"]

        price = price_lookup.get(inv)
        fx_rate = fx_lookup.get(currency, 1.0)

        if price is None:
            r["price"] = None
            r["fx_rate"] = fx_rate
            r["market_value_local"] = None
            r["market_value_book"] = None
            r["price_gain_local"] = None
            r["price_gain_book"] = None
            r["cost_per_unit"] = round(
                local_cost / qty, 6
            ) if qty != 0 else None
        else:
            market_value_local = qty * price * pricing_factor * fx_rate
            market_value_book = qty * price * pricing_factor

            r["price"] = price
            r["fx_rate"] = fx_rate
            r["market_value_local"] = round(market_value_local, 2)
            r["market_value_book"] = round(market_value_book, 2)
            r["price_gain_local"] = round(
                market_value_local - local_cost, 2
            )
            r["price_gain_book"] = round(
                market_value_book - book_cost, 2
            )
            r["cost_per_unit"] = round(
                local_cost / qty, 6
            ) if qty != 0 else None

        enriched.append(r)

    return enriched

# ============================================================
# BUILD DATAFRAME WITH SUBTOTALS
# ============================================================

def _build_appraisal_dataframe(rows):
    """
    Build appraisal DataFrame with investment type grouping,
    investment subtotals, and grand total.

    Column visibility rules:
        Detail              — all columns
        Investment subtotal — qty, local, book, gain (same instrument)
        Type total          — book columns only (mixed currencies)
        Grand total         — book columns only

    Qty summing rules:
        Investment subtotal — sum qty (same instrument)
        Type total          — no qty (mixed instruments)
        Grand total         — no qty
    """

    if not rows:
        return pd.DataFrame()

    # Sort: investment_type → investment → tax_date
    rows = sorted(rows, key=lambda r: (
        r.get("investment_type", ""),
        r.get("investment",      ""),
        r.get("tax_date") or datetime.min
    ))

    numeric_qty   = ["qty"]
    numeric_local = ["local_cost", "market_value_local", "price_gain_local"]
    numeric_book  = ["book_cost",  "market_value_book",  "price_gain_book"]
    all_numeric   = numeric_qty + numeric_local + numeric_book

    output_rows  = []
    grand_book   = {col: 0.0 for col in numeric_book}

    # ── GROUP BY INVESTMENT TYPE ──────────────────────────
    type_groups = groupby(rows, key=lambda r: r.get("investment_type", ""))

    for inv_type, type_iter in type_groups:

        type_rows = list(type_iter)
        type_book = {col: 0.0 for col in numeric_book}

        # ── GROUP BY INVESTMENT ───────────────────────────
        inv_groups = groupby(
            type_rows,
            key=lambda r: r.get("investment", "")
        )

        for inv, inv_iter in inv_groups:

            inv_rows  = list(inv_iter)
            inv_qty   = 0.0
            inv_local = {col: 0.0 for col in numeric_local}
            inv_book  = {col: 0.0 for col in numeric_book}

            for r in inv_rows:

                # Detail row
                detail             = dict(r)
                detail["row_type"] = "detail"
                output_rows.append(detail)

                # Accumulate qty
                qty = r.get("qty", 0.0)
                if isinstance(qty, (int, float)):
                    inv_qty += qty

                # Accumulate local
                for col in numeric_local:
                    val = r.get(col)
                    if isinstance(val, (int, float)):
                        inv_local[col] += val

                # Accumulate book
                for col in numeric_book:
                    val = r.get(col)
                    if isinstance(val, (int, float)):
                        inv_book[col]  += val
                        type_book[col] += val
                        grand_book[col]+= val

            # Investment subtotal
            subtotal = {
                "investment":        inv,
                "full_name":         "",
                "lotid":             "",
                "tax_date":          "",
                "location":          "",
                "ls":                "",
                "financial_account": "",
                "currency":          inv_rows[0].get("currency", ""),
                "investment_type":   inv_type,
                "is_currency":       inv_rows[0].get("is_currency", 0),
                "sector":            "",
                "country":           "",
                "analyst":           "",
                "qty":               inv_qty,
                "price":             None,
                "fx_rate":           None,
                "cost_per_unit":     None,
                "row_type":          "subtotal",
            }

            for col in numeric_local:
                subtotal[col] = inv_local[col]

            for col in numeric_book:
                subtotal[col] = inv_book[col]

            output_rows.append(subtotal)

        # Investment type total — book only, no qty, no local
        type_total = {
            "investment":        f"{inv_type} TOTAL",
            "full_name":         "",
            "lotid":             "",
            "tax_date":          "",
            "location":          "",
            "ls":                "",
            "financial_account": "",
            "currency":          "",
            "investment_type":   inv_type,
            "is_currency":       0,
            "sector":            "",
            "country":           "",
            "analyst":           "",
            "qty":               None,
            "price":             None,
            "fx_rate":           None,
            "cost_per_unit":     None,
            "row_type":          "type_total",
        }

        for col in numeric_local:
            type_total[col] = None

        for col in numeric_book:
            type_total[col] = type_book[col]

        output_rows.append(type_total)

    # Grand total — book only
    grand_total = {
        "investment":        "GRAND TOTAL",
        "full_name":         "",
        "lotid":             "",
        "tax_date":          "",
        "location":          "",
        "ls":                "",
        "financial_account": "",
        "currency":          "",
        "investment_type":   "",
        "is_currency":       0,
        "sector":            "",
        "country":           "",
        "analyst":           "",
        "qty":               None,
        "price":             None,
        "fx_rate":           None,
        "cost_per_unit":     None,
        "row_type":          "grand_total",
    }

    for col in numeric_local:
        grand_total[col] = None

    for col in numeric_book:
        grand_total[col] = grand_book[col]

    output_rows.append(grand_total)

    df = pd.DataFrame(output_rows)

    # ── FORMAT NUMERIC COLUMNS ───────────────────────────
    # Two decimal places, comma separated, no scientific notation
    # Empty string for None/NaN display values

    for col in numeric_local + numeric_book:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: f"{x:,.2f}"
                if isinstance(x, (int, float)) and x == x
                else ""
            )

    if "qty" in df.columns:
        df["qty"] = df["qty"].apply(
            lambda x: f"{x:,.2f}"
            if isinstance(x, (int, float)) and x == x
            else ""
        )

    if "cost_per_unit" in df.columns:
        df["cost_per_unit"] = df["cost_per_unit"].apply(
            lambda x: f"{x:,.6f}"
            if isinstance(x, (int, float)) and x == x
            else ""
        )

    if "price" in df.columns:
        df["price"] = df["price"].apply(
            lambda x: f"{x:,.4f}"
            if isinstance(x, (int, float)) and x == x
            else ""
        )

    if "fx_rate" in df.columns:
        df["fx_rate"] = df["fx_rate"].apply(
            lambda x: f"{x:,.4f}"
            if isinstance(x, (int, float)) and x == x
            else ""
        )

    # Fill remaining None/NaN
    df = df.fillna("")

    # ── COLUMN ORDER ─────────────────────────────────────
    col_order = [
        "investment",
        "full_name",
        "lotid",
        "tax_date",
        "location",
        "ls",
        "financial_account",
        "currency",
        "investment_type",
        "qty",
        "cost_per_unit",
        "local_cost",
        "book_cost",
        "price",
        "fx_rate",
        "market_value_local",
        "market_value_book",
        "price_gain_local",
        "price_gain_book",
        "row_type",
        "sector",
        "country",
        "analyst",
    ]

    col_order = [c for c in col_order if c in df.columns]
    df        = df[col_order]

    return df


# ============================================================
# COMPUTE APPRAISAL — PUBLIC INTERFACE
# ============================================================

def compute_appraisal(
        portfolio,
        calendar,
        period_start,
        period_end,
        mode="period_close",
        uber_filter=None,
        prep=None
):
    """
    Point-in-time appraisal at tax lot level.
    Asset/liability positions only — revenue/expense excluded.
    Market value and price gain calculated fresh from price data.
    Currency investments collapsed to net position across accounts.

    Parameters
    ----------
    portfolio    : str   — portfolio identifier
    calendar     : str   — calendar name
    period_start : str   — period start YYYY-MM
    period_end   : str   — period end YYYY-MM
    mode         : str   — 'period_open' or 'period_close'
    uber_filter  : dict  — optional e.g. {"investment": "GOOG"}
                          pass None for full portfolio
    prep         : dict  — optional pre-loaded prep package

    Returns
    -------
    ComputeResult with shape='appraisal'
    """

    t0 = time.perf_counter()

    # --------------------------------------------------
    # PREP
    # --------------------------------------------------
    if prep is None:
        prep = prep_state(portfolio, calendar, period_start, period_end)

    t1 = time.perf_counter()
    print(f">>> TIMING prep_state:           {(t1-t0)*1000:.1f}ms")

    # --------------------------------------------------
    # SELECT STATE
    # --------------------------------------------------
    if mode == "period_open":
        state          = prep["prior_state"]
        appraisal_date = prep["prior_cutoff_datetime"]
        mode_label     = "Opening"
    else:
        state          = prep["current_state"]
        appraisal_date = prep["current_cutoff_datetime"]
        mode_label     = "Closing"

    if state is None:
        print(f"⚠ No state available for mode='{mode}'")
        return ComputeResult(
            function="compute_appraisal",
            portfolio=portfolio,
            calendar=calendar,
            period_start=period_start,
            period_end=period_end,
            shape="appraisal",
            data=pd.DataFrame(),
            valid=False,
            errors=[f"No state available for mode='{mode}'"],
            metadata={}
        )

    # --------------------------------------------------
    # LOAD REFERENCE DATA (CACHED AFTER FIRST CALL)
    # --------------------------------------------------
    _ensure_reference_data()
    price_rows        = _PRICE_ROWS
    fx_rows           = _FX_ROWS
    investment_master = _INVESTMENT_MASTER

    t2 = time.perf_counter()
    print(f">>> TIMING reference data:       {(t2-t1)*1000:.1f}ms")

    # --------------------------------------------------
    # EXTRACT POSITIONS FROM STATE
    # --------------------------------------------------
    rows = _extract_appraisal_rows(state, investment_master)

    t3 = time.perf_counter()
    print(f">>> TIMING extract positions:    {(t3-t2)*1000:.1f}ms")

    # --------------------------------------------------
    # APPLY UBER FILTER
    # --------------------------------------------------
    if uber_filter:
        inv_filter = uber_filter.get("investment")
        if inv_filter:
            rows = [r for r in rows if r["investment"] == inv_filter]

    # --------------------------------------------------
    # CALCULATE MARKET VALUES
    # --------------------------------------------------
    rows = _calculate_market_values(rows, appraisal_date, price_rows, fx_rows)

    t4 = time.perf_counter()
    print(f">>> TIMING market value calc:    {(t4-t3)*1000:.1f}ms")

    # --------------------------------------------------
    # BUILD DATAFRAME WITH SUBTOTALS
    # --------------------------------------------------
    df = _build_appraisal_dataframe(rows)

    t5 = time.perf_counter()
    print(f">>> TIMING build dataframe:      {(t5-t4)*1000:.1f}ms")
    print(f">>> TIMING total V-side:         {(t5-t0)*1000:.1f}ms")

    # --------------------------------------------------
    # METADATA
    # --------------------------------------------------
    elapsed_ms    = (t5 - t0) * 1000
    detail_count  = len([r for r in rows])
    inv_count     = len(set(r["investment"] for r in rows))

    metadata = {
        "mode": mode_label,
        "appraisal_date": str(appraisal_date),
        "row_count": len(df),
        "detail_rows": detail_count,
        "investments": inv_count,
        "elapsed_ms": round(elapsed_ms, 2),
        "prep_ms": round((t1 - t0) * 1000, 1),
        "refdata_ms": round((t2 - t1) * 1000, 1),
        "extract_ms": round((t3 - t2) * 1000, 1),
        "calc_ms": round((t4 - t3) * 1000, 1),
        "dataframe_ms": round((t5 - t4) * 1000, 1),
        "uber_filter": uber_filter,
        "journal_count": len(prep["journal_entries"]),
    }

    print(
        f">>> COMPUTE APPRAISAL COMPLETE "
        f"| {portfolio} | {calendar} | {mode_label} "
        f"| {inv_count} investments "
        f"| {detail_count} lots "
        f"| {round(elapsed_ms, 1)}ms"
    )

    return ComputeResult(
        function="compute_appraisal",
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        shape="appraisal",
        data=df,
        valid=True,
        errors=[],
        metadata=metadata,
    )