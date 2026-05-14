# financial_information_gateway/fig.py

from typing import Optional, Dict, Any, Tuple
from pathlib import Path

from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from .extraction.box_extractor import extract_box_components
from .engine.box_state_engine import materialize_box_state
from .projection.base_projection import apply_projection
from financial_information_gateway.extraction.period_normalizer import period_key
from financial_information_gateway.shapes import financial_statement

def apply_balance_filter(balances, filter_spec):
    """
    Applies post-materialization filtering to balances.
    Filtering is consumer driven (FIG shapes, OCC queries, etc).
    """

    if not filter_spec:
        return balances

    excluded_fa = set(filter_spec.get("exclude_fa", []))

    filtered = {}

    for key, row in balances.items():

        # key format:
        # (investment, location, ls, financial_account)

        financial_account = key[3]

        if financial_account in excluded_fa:
            continue

        filtered[key] = row

    return filtered


def run_box_balance_view(
        portfolio: str,
        calendar: str,
        period_start: str,
        period_end: str,
        uber_filter: Optional[Dict[str, Any]] = None,
        group_by: Optional[Tuple[str, ...]] = None,
        include_je_detail: bool = True,
        mode: str = "range",
        period_chain_render_order: str = "period_first",
        shape: str = "rollover",
):
    """
    Production FIG entry.

    Loads box range, materializes canonical state,
    applies optional projection, returns structured balances.
    """

    # ============================================================
    # RANGE MODE
    # ============================================================

    if mode == "range":

        import time
        t0 = time.time()

        extracted = extract_box_components(
            portfolio=portfolio,
            calendar=calendar,
            period_start=period_start,
            period_end=period_end,
            uber_filter=uber_filter,
        )

        print("EXTRACTED KEYS:", extracted.keys())
        print("EXTRACT TIME:", time.time() - t0)

        state = materialize_box_state(
            prior_structural=extracted["prior_structural"],
            current_structural=extracted["current_structural"],
            journal_entries=extracted["journal_entries"],
            prior_kd=extracted["prior_kd"],
            current_kd=extracted["current_kd"],
            uber_filter=extracted["uber_filter"],
        )

        # ============================================================
        # APPLY POST-MATERIALIZATION FILTER
        # ============================================================

        # Example FIG default filter
        filter_spec = {
            "exclude_fa": {
                "MarketVal",
                "UnrealPriceGLOffset",
                "UnrealFXGLOffset",
                "UnrealPriceGL",
                "UnrealFXGL",
            }
        }

        state._balances = apply_balance_filter(state.balances, filter_spec)

        # ------------------------------------------------------------
        # SHAPE DISPATCH
        # ------------------------------------------------------------

        if shape == "reconciled_financial_state":
            return financial_statement.build(state)

        if group_by:
            state._balances = apply_projection(
                state._balances,
                group_by=group_by,
                include_je_detail=include_je_detail,
            )

        return state

    # ============================================================
    # PERIOD CHAIN MODE
    # ============================================================

    elif mode == "period_chain":

        base_dir = (
                Path("C:/Users/hjmne/PycharmProjects/chest/funds")
                / portfolio
                / "Calendars"
                / calendar
        )

        snapshots_dir = base_dir / "Snapshots"

        def derive_calendar_identity(base_date_str: str, calendar: str) -> str:

            dt = datetime.strptime(base_date_str, "%Y-%m-%d")

            if calendar == "Yearly":
                return f"{dt.year}"

            if calendar == "Quarterly":
                quarter = (dt.month - 1) // 3 + 1
                return f"{dt.year}-Q{quarter}"

            if calendar == "Monthly":
                return f"{dt.year}-{dt.month:02d}"

            if calendar == "Daily":
                return dt.strftime("%Y-%m-%d")

            if calendar == "Operational":
                return f"{dt.year}-{dt.month:02d}"

            raise ValueError(f"Unsupported calendar: {calendar}")

        period_names = sorted(
            list({
                derive_calendar_identity(
                    snap.stem.split("T")[0],
                    calendar,
                )
                for snap in snapshots_dir.glob("*.pkl")
            }),
            key=period_key,
        )

        if period_start not in period_names:
            raise ValueError(f"period_start '{period_start}' not found in snapshots")

        if period_end not in period_names:
            raise ValueError(f"period_end '{period_end}' not found in snapshots")

        start_index = period_names.index(period_start)
        end_index = period_names.index(period_end)

        period_results = []

        for i in range(start_index, end_index + 1):
            p = period_names[i]

            state_single = run_box_balance_view(
                portfolio=portfolio,
                calendar=calendar,
                period_start=p,
                period_end=p,
                uber_filter=uber_filter,
                group_by=group_by,
                include_je_detail=include_je_detail,
                mode="range",
            )

            period_results.append((p, state_single))

        return {
            "period_results": period_results,
            "period_chain_render_order": period_chain_render_order,
        }

    else:
        raise ValueError(f"Unsupported mode: {mode}")
