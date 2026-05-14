from financial_information_gateway.occ.occ_engine import collect_states
from financial_information_gateway.occ.occ_queries import top_holdings, holdings_change

import pickle
import time


# ============================================================
# SNAPSHOT INSPECTION
# ============================================================

def inspect_snapshot(snapshot_file):

    print("\n================ SNAPSHOT INSPECTION ================\n")

    with open(snapshot_file, "rb") as f:
        snapshot = pickle.load(f)

    state = snapshot["state"]
    repo = state["asset_liability_repository"]

    print("SNAPSHOT TYPE:", type(snapshot))
    print("STATE TYPE:", type(state))

    print("\nSTATE KEYS:")
    for k in state.keys():
        print("   ", k)

    print("\nREPOSITORY TYPE:", type(repo))

    print("\nREPOSITORY ATTRIBUTES:")
    for attr in dir(repo):
        if not attr.startswith("_"):
            print("   ", attr)

    print("\n=====================================================\n")

    return snapshot


# ============================================================
# REAL LOT METRICS FROM SNAPSHOT
# ============================================================

def inspect_lots(snapshot):

    repo = snapshot["state"]["asset_liability_repository"]

    print("\n================ SNAPSHOT LOT METRICS ================\n")

    total_lots = 0
    max_lots_per_investment = 0
    investment_count = 0

    for inv, subspace in repo.investment_positions.items():

        lot_count = len(subspace.entries)

        total_lots += lot_count
        investment_count += 1

        if lot_count > max_lots_per_investment:
            max_lots_per_investment = lot_count

    avg_lots = (
        total_lots / investment_count
        if investment_count else 0
    )

    print("Investments:", investment_count)
    print("Total lots:", total_lots)
    print("Max lots per investment:", max_lots_per_investment)
    print("Avg lots per investment:", round(avg_lots, 2))

    print("\n=====================================================\n")


# ============================================================
# LOAD FIG STATES
# ============================================================

def load_states(portfolios, calendar, period_start, period_end):
    print("\n================ LOADING STATES =====================\n")

    import time
    t0 = time.time()

    # ------------------------------------------------
    # COLLECT STATES
    # ------------------------------------------------
    states = collect_states(
        portfolios=portfolios,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
    )

    # ------------------------------------------------
    # STRUCTURED STATE INSPECTION (ADD THIS)
    # ------------------------------------------------
    print("\n================ STRUCTURED STATE INSPECTION ================\n")

    portfolio, state = states[0]

    print("PORTFOLIO:", portfolio)
    print("STATE TYPE:", type(state))

    print("\nSTATE ATTRIBUTES:")
    for attr in dir(state):
        if not attr.startswith("_"):
            print("   ", attr)

    print("\nSTATE __dict__ KEYS:")
    if hasattr(state, "__dict__"):
        for k in state.__dict__.keys():
            print("   ", k)

    print("\n==============================================================\n")

    # ------------------------------------------------
    # LOAD TIME
    # ------------------------------------------------
    elapsed = time.time() - t0

    print("PORTFOLIOS LOADED:", len(states))
    print("LOAD TIME:", round(elapsed, 3), "seconds")

    print("\n=====================================================\n")

    return states
# ============================================================
# RUN OCC QUERIES
# ============================================================

def run_queries(start_states, end_states):
    print("\n================ BALANCES INSPECTION ================\n")

    portfolio, state = end_states[0]

    balances = state.balances

    portfolio, state = end_states[0]

    print("BALANCES TYPE:", type(state.balances))
    print("BALANCES CONTENT:", state.balances)

    print("\n================ TOP HOLDINGS =======================\n")

    results = top_holdings(end_states, top_n=10)

    for r in results:
        print(r)

    print("\n================ HOLDINGS CHANGE ====================\n")

    delta = holdings_change(start_states, end_states)

    for r in delta[:10]:
        print(r)

    print("\n=====================================================\n")


# ============================================================
# MAIN
# ============================================================

def main():

    # ------------------------------------------------
    # USER INPUT
    # ------------------------------------------------

    portfolios = [f"Portfolio{i}" for i in range(1, 2)]

    calendar = "Quarterly"

    period_start = "2023-Q3"
    period_end = "2023-Q4"

    snapshot_file = r"C:\Users\hjmne\PycharmProjects\chest\funds\Portfolio1\Calendars\Quarterly\Snapshots\2023-09-30T23-59-59.pkl"

    # ------------------------------------------------
    # SNAPSHOT INSPECTION
    # ------------------------------------------------

    snapshot = inspect_snapshot(snapshot_file)

    # ------------------------------------------------
    # LOT METRICS
    # ------------------------------------------------

    inspect_lots(snapshot)

    # ------------------------------------------------
    # LOAD STATES
    # ------------------------------------------------

    start_states = load_states(
        portfolios,
        calendar,
        period_start,
        period_start
    )

    end_states = load_states(
        portfolios,
        calendar,
        period_end,
        period_end
    )

    # ------------------------------------------------
    # RUN OCC QUERIES
    # ------------------------------------------------

    run_queries(start_states, end_states)


if __name__ == "__main__":
    main()