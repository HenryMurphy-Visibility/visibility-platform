# financial_information_gateway/composite/top_holdings_composite.py

from collections import defaultdict


# ============================================================
# HELPERS
# ============================================================

def _accumulate_row(target, row):

    target["opening_qty"]   += row.get("opening_qty", 0.0)
    target["opening_local"] += row.get("opening_local", 0.0)
    target["opening_book"]  += row.get("opening_book", 0.0)

    target["movement_qty"]   += row.get("movement_qty", 0.0)
    target["movement_local"] += row.get("movement_local", 0.0)
    target["movement_book"]  += row.get("movement_book", 0.0)

    target["closing_qty"]   += row.get("closing_qty", 0.0)
    target["closing_local"] += row.get("closing_local", 0.0)
    target["closing_book"]  += row.get("closing_book", 0.0)

    # append JE lines (optional)
    if "je_lines" in row:
        target["je_lines"].extend(row["je_lines"])


def _empty_row():
    return {
        "opening_qty": 0.0,
        "opening_local": 0.0,
        "opening_book": 0.0,
        "movement_qty": 0.0,
        "movement_local": 0.0,
        "movement_book": 0.0,
        "closing_qty": 0.0,
        "closing_local": 0.0,
        "closing_book": 0.0,
        "je_lines": [],
    }


# ============================================================
# AGGREGATE MODE
# ============================================================

def build_aggregate_top_holdings(states):
    """
    states:
        { portfolio → { investment → metrics dict } }

    returns:
        { investment → aggregated metrics }
    """

    aggregate = {}

    for portfolio, holdings in states.items():

        if not isinstance(holdings, dict):
            print(f"⚠️ Skipping invalid state for {portfolio}")
            continue

        for inv, row in holdings.items():

            if inv not in aggregate:
                aggregate[inv] = {}

            for k, v in row.items():
                if isinstance(v, (int, float)):
                    aggregate[inv][k] = aggregate[inv].get(k, 0) + v
                else:
                    # preserve non-numeric (optional)
                    aggregate[inv][k] = v

    return aggregate

# ============================================================
# LIST MODE
# ============================================================

def build_list_top_holdings(states_by_portfolio, top_n=10):

    result = {}

    for portfolio, state in states_by_portfolio.items():

        sorted_items = sorted(
            state.balances.items(),
            key=lambda x: x[1]["closing_book"],
            reverse=True
        )

        top_items = sorted_items[:top_n]

        result[portfolio] = {k: v for k, v in top_items}

    return result