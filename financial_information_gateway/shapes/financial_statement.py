# ============================================================
# financial_statement.py
# Visibility — Financial Statement Shape
# ============================================================

import pandas as pd
from shape_definitions import (
    STATEMENT_CLASS,
    STATEMENT_ORDER,
    FA_ORDER_WITHIN_CLASS,
)


def build(structured_state):
    """
    Builds Financial Statement view from StructuredState.

    Returns flat DataFrame with:
        statement_class
        financial_account
        investment
        location
        ls
        opening / movement / closing
    """

    rows = []

    for key, bal in structured_state.balances.items():

        investment, location, ls, fa = key

        rows.append({
            "statement_class": STATEMENT_CLASS.get(fa, "UNCLASSIFIED"),
            "financial_account": fa,
            "investment": investment,
            "location": location,
            "ls": ls,

            "opening_qty": bal["opening_qty"],
            "movement_qty": bal["movement_qty"],
            "closing_qty": bal["closing_qty"],

            "opening_local": bal["opening_local"],
            "movement_local": bal["movement_local"],
            "closing_local": bal["closing_local"],

            "opening_book": bal["opening_book"],
            "movement_book": bal["movement_book"],
            "closing_book": bal["closing_book"],

            "je_lines": bal["je_lines"],
        })

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    # --------------------------------------------------------
    # Apply Statement Ordering
    # --------------------------------------------------------

    class_order_map = {name: i for i, name in enumerate(STATEMENT_ORDER)}

    df["class_order"] = df["statement_class"].map(class_order_map).fillna(999)

    fa_rank_map = {}
    for cls, fas in FA_ORDER_WITHIN_CLASS.items():
        for i, fa in enumerate(fas):
            fa_rank_map[(cls, fa)] = i

    df["fa_order"] = df.apply(
        lambda r: fa_rank_map.get(
            (r["statement_class"], r["financial_account"]),
            999,
        ),
        axis=1,
    )

    df = df.sort_values(
        by=[
            "class_order",
            "fa_order",
            "financial_account",
            "investment",
        ]
    )

    df = df.drop(columns=["class_order", "fa_order"])

    return df