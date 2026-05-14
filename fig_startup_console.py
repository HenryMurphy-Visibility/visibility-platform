# ============================================================
# fig_startup_console.py  (UNIFIED ENTRY POINT)
# ============================================================

from typing import List
from financial_information_gateway.fig import run_box_balance_view

from financial_information_gateway.composite.top_holdings_composite import (
    build_aggregate_top_holdings,
    build_list_top_holdings,
)
from financial_information_gateway.preparation.prepare_box_state import (
    prepare_box_state,
)


# ============================================================
# ZLIST RESOLUTION (SIMPLE VERSION)
# ============================================================

def resolve_zlist(zlist_name: str) -> List[str]:
    """
    Replace this with your real loader later.
    For now: assumes Portfolio1..Portfolio99
    """

    if not zlist_name.startswith("ZLIST"):
        return [zlist_name]

    # 🔧 TEMP — replace with file-driven later
    return [f"Portfolio{i}" for i in range(1, 20)]


# ============================================================
# MAIN
# ============================================================

def main():
    # ------------------------------------------------------------
    # USER INPUT
    # ------------------------------------------------------------

    portfolio = "ZLIST_8Portfolios"  # ← can be "Portfolio1" OR "ZLIST_*"
    calendar = "Quarterly"
    period_start = "2024-Q2"
    period_end = "2024-Q2"

    mode = "range"
    shape = "top_holdings"  # ← change as needed

    # optional
    uber_filter = None
    group_by = None
    include_je_detail = False

    composite_mode = "aggregate"  # or "list"
    top_n = 10

    # ------------------------------------------------------------
    # RESOLVE PORTFOLIOS
    # ------------------------------------------------------------

    portfolios = resolve_zlist(portfolio)

    print("\n======================================")
    print("PORTFOLIOS:", portfolios[:5], "...", len(portfolios))
    print("======================================\n")

    # ------------------------------------------------------------
    # BUILD STATES (USING PREP)
    # ------------------------------------------------------------

    states = {}



    for p in portfolios:
        print(f"\n--- PREPARING + RUNNING: {p} ---")

        prep = prepare_box_state(
            portfolio=p,
            calendar=calendar,
            period_start=period_start,
            period_end=period_end,
        )

        state = run_box_balance_view_from_state(
            prep,
            include_je_detail=True,
            shape="rollover",
        )

        states[p] = state

    # ------------------------------------------------------------
    # FLATTEN FOR GWI / GRID VIEW
    # ------------------------------------------------------------

    from financial_information_gateway.rendering.gwi_adapter import flatten_states_for_gwi

    rows = flatten_states_for_gwi(states)

    print(f"\nTOTAL ROWS: {len(rows)}\n")

    for r in rows[:10]:
        print(r)

    # ------------------------------------------------------------
    # COMPOSITE TOP HOLDINGS
    # ------------------------------------------------------------

    if composite_mode == "aggregate":

        result = build_aggregate_top_holdings(states, top_n=top_n)

        print("\n=== COMPOSITE TOP HOLDINGS ===\n")

        for key, row in result.items():
            print(key, row)

    elif composite_mode == "list":

        result = build_list_top_holdings(states, top_n=top_n)

        print("\n=== PORTFOLIO TOP HOLDINGS ===\n")

        for portfolio, holdings in result.items():

            print(f"\n--- {portfolio} ---")

            for key, row in holdings.items():
                print(key, row)

    # ------------------------------------------------------------
    # HANDLE SHAPE OUTPUT
    # ------------------------------------------------------------

    if shape == "top_holdings":

        print("\n================ TOP HOLDINGS =======================\n")

        combined = []

        for p, state in states.items():
            # assuming state is iterable like (investment, row)
            for inv, row in state:
                combined.append((p, inv, row))

        # sort by book value
        combined.sort(key=lambda x: x[2].get("closing_book", 0.0), reverse=True)

        for p, inv, row in combined[:10]:
            print(f"{p} | {inv} | {row}")

        print("\n=====================================================\n")

        return

    # ------------------------------------------------------------
    # DEFAULT (STRUCTURED STATE)
    # ------------------------------------------------------------

    for p, state in states.items():

        print("=" * 60)
        print(f"PORTFOLIO: {p}")
        print("=" * 60)

        if hasattr(state, "is_valid") and not state.is_valid:
            print("⚠ INVARIANT FAILURES")
            for failure in state.validation_failures:
                print(f"KEY: {failure['key']}")
                print(f"  DIFF_BOOK : {failure['diff_book']}")
                print(f"  DIFF_LOCAL: {failure['diff_local']}")
                print(f"  DIFF_QTY  : {failure['diff_qty']}")

        # fallback simple print
        if hasattr(state, "balances"):
            print(f"Balance count: {len(state.balances)}")
# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
