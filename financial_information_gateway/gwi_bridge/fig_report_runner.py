# ============================================================
# fig_report_runner.py
# ============================================================

from financial_information_gateway.fig import run_box_balance_view


def run_fig_report(
    session,
    report_perspective="positions",
    group_by=("investment",),
    mode="range",
):
    """
    GWI → FIG Bridge

    Uses SessionContext to call FIG and return structured result.
    """

    if not session.portfolio_name:
        raise RuntimeError("Session missing portfolio_name")

    if not session.calendar:
        raise RuntimeError("Session missing calendar")

    if not session.period_start or not session.period_end:
        raise RuntimeError("Session missing period range")

    result = run_box_balance_view(
        portfolio=session.portfolio_name,
        calendar=session.calendar,
        period_start=session.period_start,
        period_end=session.period_end,
        group_by=group_by,
        include_je_detail=(report_perspective == "je_detail"),
        mode=mode,
    )

    return result