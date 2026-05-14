from typing import List, Tuple

from financial_information_gateway.fig import run_box_balance_view


def collect_states(
    portfolios: List[str],
    calendar: str,
    period_start: str,
    period_end: str,
):

    results = []

    for p in portfolios:

        state = run_box_balance_view(
            portfolio=p,
            calendar=calendar,
            period_start=period_start,
            period_end=period_end,
            mode="range",
            include_je_detail=False,
        )

        results.append((p, state))

    return results
