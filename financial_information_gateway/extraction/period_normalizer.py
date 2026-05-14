# ============================================================
# period_normalizer.py
# Canonical Period Parsing for Visibility
# ============================================================

import re


def normalize_period_name(period_name: str):
    """
    Returns:
        {
            "type": <"yearly" | "monthly" | "daily" | "quarterly">,
            "key": comparable_tuple,
            "original": original_string
        }

    Examples:
        2025        -> yearly      (2025,)
        2025-01     -> monthly     (2025, 1)
        2025-01-01  -> daily       (2025, 1, 1)
        2025-Q1     -> quarterly   (2025, 1)
    """

    period_name = period_name.strip()

    # Daily: YYYY-MM-DD
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", period_name):
        year, month, day = map(int, period_name.split("-"))
        return {
            "type": "daily",
            "key": (year, month, day),
            "original": period_name,
        }

    # Monthly: YYYY-MM
    if re.fullmatch(r"\d{4}-\d{2}", period_name):
        year, month = map(int, period_name.split("-"))
        return {
            "type": "monthly",
            "key": (year, month),
            "original": period_name,
        }

    # Quarterly: YYYY-QX
    if re.fullmatch(r"\d{4}-Q[1-4]", period_name):
        year = int(period_name[:4])
        quarter = int(period_name[-1])
        return {
            "type": "quarterly",
            "key": (year, quarter),
            "original": period_name,
        }

    # Yearly: YYYY
    if re.fullmatch(r"\d{4}", period_name):
        return {
            "type": "yearly",
            "key": (int(period_name),),
            "original": period_name,
        }

    raise ValueError(f"Unsupported period format: {period_name}")

def period_key(period_name: str):
    return normalize_period_name(period_name)["key"]