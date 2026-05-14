def apply_projection(
    balances,
    group_by,
    include_je_detail=True,
):
    """
    Transforms canonical balances into grouped projection.

    group_by: tuple of fields, e.g.
        ("investment", "financial_account")
    """

    projected = {}

    for key, bal in balances.items():

        # key structure:
        # (investment, location, ls, financial_account)

        base = {
            "investment": key[0],
            "location": key[1],
            "ls": key[2],
            "financial_account": key[3],
        }

        projection_key = tuple(base[field] for field in group_by)

        if projection_key not in projected:
            projected[projection_key] = {
                "opening_qty": 0.0,
                "opening_local": 0.0,
                "opening_book": 0.0,
                "movement_qty": 0.0,
                "movement_local": 0.0,
                "movement_book": 0.0,
                "closing_qty": 0.0,
                "closing_local": 0.0,
                "closing_book": 0.0,
                "je_lines": [] if include_je_detail else None,
            }

        tgt = projected[projection_key]

        for field in (
            "opening_qty",
            "opening_local",
            "opening_book",
            "movement_qty",
            "movement_local",
            "movement_book",
            "closing_qty",
            "closing_local",
            "closing_book",
        ):
            tgt[field] += bal[field]

        if include_je_detail and bal["je_lines"]:
            tgt["je_lines"].extend(bal["je_lines"])

    return projected