# ============================================================
# financial_information_gateway/fig.py
# FIG 1.0 – Positions (State Projection)
# ============================================================

from financial_information_gateway.extraction.box_extractor import extract_box_components
from financial_information_gateway.extraction.journal_to_df import build_journal_df
from financial_information_gateway.extraction.journal_to_df import build_positions_df


def run_box_balance_view(
        portfolio,
        calendar,
        period_start,
        period_end,
        mode=None,
        include_je_detail=None,
        shape=None,
        group_by=None,
        **kwargs
):

    """
    FIG 1.0 entry point

    Returns:
        positions_df → ready for GWI rendering
    """

    # ------------------------------------------------------------
    # 1. EXTRACT COMPONENTS (snapshots + journals)
    # ------------------------------------------------------------
    components = extract_box_components(
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
    )

    # ------------------------------------------------------------
    # 2. JOURNAL → DATAFRAME
    # ------------------------------------------------------------
    journal_entries = components["journal_entries"]

    journal_df = build_journal_df(journal_entries)

    # ------------------------------------------------------------
    # 3. BUILD POSITIONS (FIG 1.0)
    # ------------------------------------------------------------
    positions_df = build_positions_df(journal_df)

    # ------------------------------------------------------------
    # 4. RETURN FOR GWI
    # ------------------------------------------------------------
    class SimpleState:
        def __init__(self, balances):
            self.balances = balances

    # ---- PRESERVE ORIGINAL INTERFACE ----
    # Always return 4 values, because callers expect it

    state = SimpleState(positions_df)  # you already built positions_df

    return state, None, None, None
