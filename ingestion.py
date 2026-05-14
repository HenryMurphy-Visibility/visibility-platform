# ============================================================
# ingestion.py — Visibility Platform v1.0 (Production)
# ============================================================
# Handles ingestion of base events and scheduler-generated marks
# ============================================================
import importlib

import pandas as pd
import logging
from event_definitions import (
    METHOD_EVENT_CLASS_MAP,
    PriceMarkEvent,
    BondAccrualEvent,
    TradeEvent,
    IncomeEvent,
    SpinOffEvent,
    ExpenseEvent,
    FxContractEvent,
    SwapContractEvent,
    CapitalEvent,
    SplitEvent,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ------------------------------------------------------------
# 🔹 Utility: normalize numeric
# ------------------------------------------------------------
def normalize_numeric(value):
    """Convert numeric-like strings safely to float or int."""
    if value in (None, "", " ", "NA"):
        return None
    try:
        value = str(value).replace(",", "")
        return float(value) if "." in value else int(value)
    except Exception:
        return value


# ============================================================
# 🔹 EVENT INGESTION (user/system events)
# ============================================================
def dispatch_event_record(record: dict):
    """
    Creates the appropriate Event object based on its fully qualified method name.
    Deterministic: either the method resolves to a known rule or ingestion fails.
    """

    method = record.get("method", "").strip()
    if not method:
        raise ValueError("❌ Missing 'method' in event record")

    # 🔹 Normalize to fully qualified form if not already (e.g. "buy_equity" → "equity_domain.buy_equity")
    if "." not in method:
        if "bond" in method:
            method = f"bond_domain.{method}"
        elif "equity" in method:
            method = f"equity_domain.{method}"
        elif "future" in method:
            method = f"futures_domain.{method}"
        elif "swap" in method:
            method = f"swaps_domain.{method}"
        elif any(x in method for x in ("currency", "deposit", "withdraw", "expense", "fx")):
            method = f"currency_domain.{method}"
        elif "capital" in method:
            method = f"currency_domain.{method}"
        else:
            raise ValueError(f"❌ Cannot determine domain for method: {method}")

    # 🔹 Lookup event class
    event_class_name = METHOD_EVENT_CLASS_MAP.get(method)
    if not event_class_name:
        raise ValueError(f"❌ Unknown or unmapped method: {method}")

    # 🔹 Import and instantiate
    module = importlib.import_module("event_definitions")
    event_class = getattr(module, event_class_name)

    # 🔹 Normalize numerics
    numeric_fields = [
        "quantity", "price", "local", "book", "accrued_local", "accrued_book",
        "buy_amt", "sell_amt", "notional", "per_share", "amount_local",
        "amount_book", "rate", "fx_rate", "mark_price", "new_shares", "old_shares"
    ]
    for f in numeric_fields:
        if f in record:
            record[f] = normalize_numeric(record[f])

    return event_class(**record)


def ingest_events(filepath: str):
    """
    Loads the unified events CSV (excluding marks/accruals)
    and instantiates corresponding event objects.
    """
    df = pd.read_csv(filepath, dtype=str)

    # ✅ Add this line to normalize all header names
    df.columns = [c.strip().lower() for c in df.columns]

    records = df.to_dict(orient="records")
    events = []
    for idx, rec in enumerate(records, start=1):
        try:
            events.append(dispatch_event_record(rec))
        except Exception as e:
            logger.warning(f"⚠️ Skipped record {idx}: {e}")
    logger.info(f"✅ Ingested {len(events)} base events from {filepath}")
    return events

# ============================================================
# 🔹 MARKS INGESTION (mark_prices / mark_bond_accruals)
# ============================================================
def ingest_marks(filepath: str):
    """Loads scheduler-generated marks/accruals."""
    try:
        df = pd.read_csv(filepath, dtype=str)
    except FileNotFoundError:
        raise FileNotFoundError(f"❌ Marks file not found: {filepath}")

    required = {"Portfolio", "Investment", "MarkDate", "EventType"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"❌ Missing columns: {missing}")

    events = []
    for _, row in df.iterrows():
        event_type = row["EventType"].strip().lower()
        portfolio = row["Portfolio"].strip()
        investment = row["Investment"].strip()
        mark_date = row["MarkDate"].strip()

        if event_type == "price":
            event = PriceMarkEvent(
                last_updated=mark_date,
                portfolio=portfolio,
                investment=investment,
                location=None,
                method="mark_prices",
                event_type="mark_prices",
                tradedate=mark_date,
                settledate=mark_date,
                kdbegin=mark_date,
                kdend="12/31/2099",
                tranid=-1,
                transaction="Mark Price",
                source="Scheduler",
                price=normalize_numeric(row.get("Price")),
                currency=None,
                fx_rate=normalize_numeric(row.get("FXRate")),
            )
        elif event_type == "accrual":
            event = BondAccrualEvent(
                last_updated=mark_date,
                portfolio=portfolio,
                investment=investment,
                location=None,
                method="mark_bond_accruals",
                event_type="mark_bond_accruals",
                tradedate=mark_date,
                settledate=mark_date,
                kdbegin=mark_date,
                kdend="12/31/2099",
                tranid=-2,
                transaction="Mark Bond Accrual",
                source="Scheduler",
                accrued_local=normalize_numeric(row.get("AccrualFactor")),
                accrued_book=None,
                payment_currency=None,
            )
        else:
            logger.warning(f"⚠️ Unknown EventType: {event_type}")
            continue

        events.append(event)

    logger.info(f"✅ Loaded {len(events)} mark/accrual events from {filepath}")
    return events
