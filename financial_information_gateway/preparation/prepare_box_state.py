# financial_information_gateway/preparation/prepare_box_state.py

from financial_information_gateway.extraction.box_extractor import extract_box_components

def prepare_box_state(
        portfolio,
        calendar,
        period_start,
        period_end,
        uber_filter=None,
):
    """
    PURE PREPARATION STEP

    No filtering
    No transformation
    Just extraction
    """

    return extract_box_components(
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        uber_filter=uber_filter,  # pass-through only

    )