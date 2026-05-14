def flatten_states_for_gwi(states):
    """
    Convert {portfolio: StructuredState}
    → list of flat rows for GWI grid
    """

    rows = []

    for portfolio, state in states.items():

        for key, bal in state.balances.items():

            investment, location, ls, account = key

            rows.append({
                "portfolio": portfolio,
                "investment": investment,
                "location": location,
                "ls": ls,
                "account": account,

                "open_qty": bal["opening_qty"],
                "open_local": bal["opening_local"],
                "open_book": bal["opening_book"],

                "mov_qty": bal["movement_qty"],
                "mov_local": bal["movement_local"],
                "mov_book": bal["movement_book"],

                "close_qty": bal["closing_qty"],
                "close_local": bal["closing_local"],
                "close_book": bal["closing_book"],
            })

    return rows