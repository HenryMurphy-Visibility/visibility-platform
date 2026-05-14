from collections import defaultdict


def top_holdings(states, top_n=10):
    totals = {}

    for portfolio, state in states:

        balances = state.balances

        for key, row in balances.items():

            investment = key[0]
            account = key[-1]

            # only market value rows
            if account != "MarketVal":
                continue

            value = row.get("closing_book", 0.0)

            totals[investment] = totals.get(investment, 0.0) + value

    results = [
        {"investment": inv, "market_value": mv}
        for inv, mv in totals.items()
    ]

    results.sort(key=lambda x: abs(x["market_value"]), reverse=True)

    return results[:top_n]

def holdings_change(start_states, end_states):

    start_totals = {}
    end_totals = {}

    # start
    for portfolio, state in start_states:

        for key, row in state.balances.items():

            investment = key[0]
            account = key[-1]

            if account != "MarketVal":
                continue

            value = row.get("closing_book", 0.0)

            start_totals[investment] = start_totals.get(investment, 0.0) + value

    # end
    for portfolio, state in end_states:

        for key, row in state.balances.items():

            investment = key[0]
            account = key[-1]

            if account != "MarketVal":
                continue

            value = row.get("closing_book", 0.0)

            end_totals[investment] = end_totals.get(investment, 0.0) + value

    investments = set(start_totals) | set(end_totals)

    results = []

    for inv in investments:

        change = end_totals.get(inv, 0.0) - start_totals.get(inv, 0.0)

        results.append({
            "investment": inv,
            "change": change
        })

    results.sort(key=lambda x: abs(x["change"]), reverse=True)

    return results