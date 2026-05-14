# ============================================================
# VISIBILITY — CENTRALIZED REPORTING HUB (CRH)
# Deterministic Reporting Kernel
# ============================================================

import os
import json
import pickle
from datetime import datetime
from typing import Dict, List, Any
from v_config import BASE_PATH, FUNDS_PATH, REFDATA_PATH, REPORTS_PATH, VIEWS_PATH

# ============================================================
# PATHS
# ============================================================


FUNDS_ROOT = f"{BASE_PATH}/funds"


# ============================================================
# CORE ENTRY POINT
# ============================================================

def run_crh(
    *,
    portfolio: str,
    calendar: str,
    start_period: str,
    end_period: str,
    mode: str = "cost_basis",       # cost_basis | market_value
    include_deltas: bool = True,    # balance deltas only (no JE flattening)
    include_journals: bool = True,  # raw JE detail inside range
) -> Dict[str, Any]:
    """
    CENTRALIZED REPORTING HUB

    Responsibilities:
    - Resolve calendar range
    - Load opening balance snapshot (prior to start_period)
    - Load closing balance snapshot (per period in range)
    - Optionally compute balance deltas
    - Optionally extract raw journal detail within range
    - Return structured deterministic payload

    NO SHAPING.
    NO PRESENTATION.
    NO SUBTOTALS.
    NO ORDERING.
    """

    records = _load_calendar_records(portfolio, calendar)
    range_records = _slice_calendar(records, start_period, end_period)

    first_idx = records.index(range_records[0])
    if first_idx == 0:
        raise RuntimeError("No prior period available for opening balance.")

    opening_period = records[first_idx - 1]["period_name"]

    payload: Dict[str, Any] = {
        "portfolio": portfolio,
        "calendar": calendar,
        "start_period": start_period,
        "end_period": end_period,
        "mode": mode,
        "periods": {},
    }

    prior_period = opening_period

    for rec in range_records:
        period = rec["period_name"]

        opening_state = _load_snapshot_state(
            portfolio, calendar, prior_period
        )

        closing_state = _load_snapshot_state(
            portfolio, calendar, period
        )

        period_block: Dict[str, Any] = {
            "opening_state": opening_state,
            "closing_state": closing_state,
        }

        if include_deltas:
            period_block["delta"] = _derive_balance_delta(
                opening_state,
                closing_state,
                mode,
            )

        if include_journals:
            period_block["journals"] = _extract_period_journals(
                portfolio,
                calendar,
                period,
                mode,
            )

        payload["periods"][period] = period_block

        prior_period = period

    return payload


# ============================================================
# CALENDAR HELPERS
# ============================================================

def _load_calendar_records(portfolio: str, calendar: str) -> List[dict]:
    path = f"{FUNDS_ROOT}/{portfolio}/Calendars/{calendar}/{calendar}.txt"
    records = []

    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            if ln.strip().startswith("{"):
                records.append(json.loads(ln))

    records.sort(key=lambda r: r["current_period_start"])
    return records


def _slice_calendar(
    records: List[dict],
    start_period: str,
    end_period: str,
) -> List[dict]:

    sel = [
        r for r in records
        if start_period <= r["period_name"] <= end_period
    ]

    if not sel:
        raise RuntimeError("No calendar records in specified range.")

    return sel


# ============================================================
# SNAPSHOT ACCESS
# ============================================================

def _resolve_snapshot_file(portfolio: str, calendar: str, period: str) -> str:
    snap_dir = f"{FUNDS_ROOT}/{portfolio}/Calendars/{calendar}/Snapshots"

    for fn in os.listdir(snap_dir):
        if fn.endswith(".json"):
            with open(f"{snap_dir}/{fn}", "r") as f:
                meta = json.load(f)
            if meta["period_name"] == period:
                return f"{snap_dir}/{fn.replace('.json', '.pkl')}"

    raise RuntimeError(f"Snapshot not found for period: {period}")


def _load_snapshot_state(
    portfolio: str,
    calendar: str,
    period: str,
) -> dict:

    pkl_path = _resolve_snapshot_file(portfolio, calendar, period)

    with open(pkl_path, "rb") as f:
        snap = pickle.load(f)

    return snap["state"]


# ============================================================
# BALANCE DELTA (STATE LEVEL ONLY)
# ============================================================

def _derive_balance_delta(
    opening_state: dict,
    closing_state: dict,
    mode: str,
) -> dict:
    """
    Placeholder — to be implemented next step.

    This will compute balance delta between two snapshot states.
    """

    return {
        "status": "delta_not_implemented_yet"
    }


# ============================================================
# JOURNAL EXTRACTION
# ============================================================

VALUATION_ACCOUNTS = {
    "UnrealPriceGL",
    "UnrealFXGL",
    "UnearnedIncome",
    "UnrealPriceGLOffset",
    "UnrealFXGLOffset",
    "MarketVal",
}


def _extract_period_journals(
    portfolio: str,
    calendar: str,
    period: str,
    mode: str,
) -> List[dict]:
    """
    Load raw journal detail for a period.

    - Loads both regular and adjusting journal files
    - Applies cost_basis filtering if required
    - Returns plain dict records (no objects)
    """

    journals_dir = (
        f"{FUNDS_ROOT}/{portfolio}/Calendars/{calendar}/Journals"
    )

    regular_path = None
    adjusting_path = None

    # Locate files for the period
    for fn in os.listdir(journals_dir):
        if fn.endswith(".regular.pkl"):
            with open(f"{journals_dir}/{fn}", "rb") as f:
                data = pickle.load(f)
            if data["period_name"] == period:
                regular_path = f"{journals_dir}/{fn}"

        if fn.endswith(".adjusting.pkl"):
            with open(f"{journals_dir}/{fn}", "rb") as f:
                data = pickle.load(f)
            if data["period_name"] == period:
                adjusting_path = f"{journals_dir}/{fn}"

    raw_entries = []

    # Load regular journals
    if regular_path:
        with open(regular_path, "rb") as f:
            data = pickle.load(f)
            raw_entries.extend(data.get("journals", []))

    # Load adjusting journals
    if adjusting_path:
        with open(adjusting_path, "rb") as f:
            data = pickle.load(f)
            raw_entries.extend(data.get("journals", []))

    # Convert objects → dicts
    output: List[dict] = []

    for je in raw_entries:

        # Cost basis filter
        if mode == "cost_basis" and je.financial_account in VALUATION_ACCOUNTS:
            continue

        output.append({
            "portfolio": je.portfolio,
            "investment": je.investment,
            "lotid": je.lotid,
            "tax_date": je.tax_date,
            "tradedate": getattr(je, "tradedate", None),
            "ls": je.ls,
            "location": je.location,
            "financial_account": je.financial_account,
            "quantity": je.quantity,
            "local": je.local,
            "book": je.book,
        })

    return output
