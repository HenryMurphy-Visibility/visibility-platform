# ============================================================
# input_event_validator.py
# ------------------------------------------------------------
# Input Event Validator (IEV) — Line of Defense #1
# PURPOSE: External data validation ONLY
# ------------------------------------------------------------
# - No scheduling logic
# - No posting logic
# - No interpretation of method
# - Field-driven validation only
# ============================================================

from datetime import date, datetime
from typing import Dict, Any


class IEVValidationError(Exception):
    pass


class InputEventValidator:
    """
    Input Event Validator (IEV)

    Enforces:
    - Mandatory-for-all fields
    - Temporal coherence (facts only)
    - Reference existence (IM)
    - Field-driven data coherence
    """

    # --------------------------------------------------------
    # 🔒 Mandatory fields — ALL events (LOCKED)
    # --------------------------------------------------------
    MANDATORY_FIELDS = {
        # Identity / provenance
        "last_updated",
        "portfolio",
        "method",
        "source",
        "tranid",
        "transaction",

        # Temporal facts
        "tradedate",
        "settledate",
        "kdbegin",
        "kdend",

        # Instrument anchor (ONLY Type 3 mandatory)
        "investment",
    }

    def __init__(self, investment_master: Dict[str, Dict[str, Any]], calendar):
        """
        investment_master:
            { investment_id: {...} }

        calendar:
            exposes is_business_day(date) -> bool
        """
        self.im = investment_master
        self.calendar = calendar

    # ========================================================
    # Public entry point
    # ========================================================
    def validate(self, event: Dict[str, Any]) -> None:
        """
        Validate a single input event.
        Raises IEVValidationError on failure.
        """
        self._validate_mandatory_fields(event)
        self._validate_temporal_facts(event)
        self._validate_reference_facts(event)
        self._validate_amount_pairing(event)
        self._validate_field_driven_shapes(event)

    # ========================================================
    # Universal validation (ALL events)
    # ========================================================
    def _validate_mandatory_fields(self, event: Dict[str, Any]) -> None:
        missing = self.MANDATORY_FIELDS - event.keys()
        if missing:
            raise IEVValidationError(f"Missing mandatory fields: {missing}")

    def _validate_temporal_facts(self, event: Dict[str, Any]) -> None:
        td = event["tradedate"]
        sd = event["settledate"]
        kdb = event["kdbegin"]
        kde = event["kdend"]
        lu = event["last_updated"]

        # Type checks
        for fld, val in {
            "tradedate": td,
            "settledate": sd,
            "kdbegin": kdb,
            "kdend": kde,
        }.items():
            if not isinstance(val, date):
                raise IEVValidationError(f"{fld} must be a date")

        if not isinstance(lu, datetime):
            raise IEVValidationError("last_updated must be datetime")

        # Fact coherence (no scheduling semantics)
        if td > sd:
            raise IEVValidationError("tradedate after settledate")

        if kdb > kde:
            raise IEVValidationError("kdbegin after kdend")

        if not (kdb <= td <= kde):
            raise IEVValidationError("tradedate outside knowledge window")

        if lu < datetime.combine(td, datetime.min.time()):
            raise IEVValidationError("last_updated before tradedate")

        # Calendar sanity
        if not self.calendar.is_business_day(td):
            raise IEVValidationError("tradedate is not a business day")

        if not self.calendar.is_business_day(sd):
            raise IEVValidationError("settledate is not a business day")

    def _validate_reference_facts(self, event: Dict[str, Any]) -> None:
        inv = event["investment"]
        if inv not in self.im:
            raise IEVValidationError(f"Unknown investment: {inv}")

    # ========================================================
    # 🔒 GLOBAL RULE — Amount pairing (ALL events)
    # ========================================================
    def _validate_amount_pairing(self, event: Dict[str, Any]) -> None:
        """
        total_amount and total_amount_base are inseparable facts.

        Legal states:
        - both == 0
        - both != 0
        """
        ta = event.get("total_amount", 0)
        tab = event.get("total_amount_base", 0)

        if (ta == 0 and tab != 0) or (ta != 0 and tab == 0):
            raise IEVValidationError(
                "total_amount and total_amount_base must be asserted together"
            )

    # ========================================================
    # Field-driven shape validation
    # ========================================================
    def _validate_field_driven_shapes(self, event: Dict[str, Any]) -> None:
        """
        Validation is driven by WHICH FIELDS ARE POPULATED,
        not by method or transaction.
        """

        qty = event.get("quantity", 0)
        price = event.get("price", 0)
        ta = event.get("total_amount", 0)
        mark = event.get("mark_price", 0)

        # ----------------------------------------------------
        # Trade-like data shape
        # quantity/price populated → trade-like facts
        # ----------------------------------------------------
        if qty != 0 or price != 0:
            if qty == 0:
                raise IEVValidationError("price present with zero quantity")

            if price <= 0:
                raise IEVValidationError("trade price must be positive")

            # If trade-like, amount must be asserted
            if ta == 0:
                raise IEVValidationError(
                    "trade-like data requires total_amount assertion"
                )

        # ----------------------------------------------------
        # Mark-like data shape
        # ----------------------------------------------------
        if mark != 0:
            if qty != 0:
                raise IEVValidationError("mark events must not assert quantity")

            if price != 0:
                raise IEVValidationError("mark events must not assert trade price")

        # ----------------------------------------------------
        # Cash-only data shape (payments, JE, etc.)
        # ----------------------------------------------------
        if ta != 0 and qty == 0 and price == 0 and mark == 0:
            # Cash fact asserted — nothing else to enforce here
            pass

        # ----------------------------------------------------
        # System-gen intent (no cash, no trade, no mark)
        # ----------------------------------------------------
        if qty == 0 and price == 0 and ta == 0 and mark == 0:
            # Valid: entitlement, trigger, structural event
            pass
