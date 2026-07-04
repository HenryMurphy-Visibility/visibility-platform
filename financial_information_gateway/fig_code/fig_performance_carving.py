def performance_carving_periods(
    df,
    level,
    cadence=None,      # None, "D", "W", "M", "Q"
    start_date=None,
    end_date=None
):

    import pandas as pd

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["ibor_date"] = pd.to_datetime(df["ibor_date"])

    # --------------------------------------------------
    # STEP 1: FILTER RANGE (if provided)
    # --------------------------------------------------
    if start_date:
        df = df[df["ibor_date"] >= pd.to_datetime(start_date)]

    if end_date:
        df = df[df["ibor_date"] <= pd.to_datetime(end_date)]

    if df.empty:
        return pd.DataFrame()

    # --------------------------------------------------
    # STEP 2: SORT (critical)
    # --------------------------------------------------
    df = df.sort_values([level, "ibor_date"])

    # --------------------------------------------------
    # STEP 3: AGG SPEC — flow/income totals only when the columns exist.
    # The built daily state carries Cum_Open_CF_Local etc., not
    # CumCF_Local/CumInc_Local (those come from performance_carve_aggregate).
    # Referencing a missing column in .agg raises KeyError, which would
    # crash any cadence selection against the built frame.
    # --------------------------------------------------
    agg_spec = dict(
        start_index=("Index_Local", "first"),
        end_index=("Index_Local", "last"),
        start_date=("ibor_date", "first"),
        end_date=("ibor_date", "last"),
    )
    if "CumCF_Local" in df.columns:
        agg_spec["total_cf"] = ("CumCF_Local", lambda x: x.iloc[-1] - x.iloc[0])
    if "CumInc_Local" in df.columns:
        agg_spec["total_income"] = ("CumInc_Local", lambda x: x.iloc[-1] - x.iloc[0])

    # --------------------------------------------------
    # STEP 4: HANDLE NO CADENCE (FULL RANGE)
    # --------------------------------------------------
    if cadence is None:

        result = (
            df
            .groupby(level)
            .agg(**agg_spec)
        )

        result["return"] = result["end_index"] / result["start_index"] - 1

        return result.reset_index()

    # --------------------------------------------------
    # STEP 5: DERIVE PERIODS FROM DATA (KEY DESIGN)
    # --------------------------------------------------
    df["period"] = df["ibor_date"].dt.to_period(cadence)

    # --------------------------------------------------
    # STEP 6: GROUP INTO PERIODS
    # --------------------------------------------------
    result = (
        df
        .groupby([level, "period"])
        .agg(**agg_spec)
        .reset_index()
    )

    # --------------------------------------------------
    # STEP 7: COMPUTE RETURNS
    # --------------------------------------------------
    result["return"] = result["end_index"] / result["start_index"] - 1

    return result

def performance_carve_aggregate(
    df,
    from_level,         # e.g. "investment"
    to_level,           # e.g. "asset_class"
    mapping_df,         # maps investment → new level
):
    import pandas as pd
    import numpy as np

    if df is None or df.empty:
        return pd.DataFrame()

    # -----------------------------------------
    # STEP 1: MAP TO NEW LEVEL
    # -----------------------------------------
    df = df.copy()

    df = df.merge(
        mapping_df[[from_level, to_level]],
        on=from_level,
        how="left"
    )

    if df[to_level].isna().any():
        print("⚠️ Missing mapping for some rows")

    # -----------------------------------------
    # STEP 2: AGGREGATE DAILY STATE
    # -----------------------------------------
    agg = (
        df
        .groupby([to_level, "ibor_date"], as_index=False)
        .agg({
            "BMV_Local": "sum",
            "EMV_Local": "sum",
            "CF_Local": "sum",
        })
    )

    agg = agg.sort_values([to_level, "ibor_date"])

    # -----------------------------------------
    # STEP 3: RECOMPUTE DAILY TWR
    # -----------------------------------------
    agg["TWR_Local"] = np.where(
        agg["BMV_Local"] != 0,
        (agg["EMV_Local"] - agg["BMV_Local"] - agg["CF_Local"]) / agg["BMV_Local"],
        0.0
    )

    # -----------------------------------------
    # STEP 4: REBUILD INDEX
    # -----------------------------------------
    agg["Index_Local"] = (
        (1 + agg["TWR_Local"])
        .groupby(agg[to_level])
        .cumprod()
    )

    agg["CumCF_Local"] = agg.groupby(to_level)["CF_Local"].cumsum()
    agg["CumInc_Local"] = 0.0

    return agg

def aggregate_by_aif(df, aif_field):
    """
    Aggregate investment-level daily state up to a grouping level
    (sector, analyst, country, portfolio, etc.) then recompute TWR
    using the SAME formula logic as compute_daily_twr.

    CRITICAL — two distinct TWR formulas:

      Every level EXCEPT 'portfolio':
        denominator = Previous_EMV + Open_CF + (Currency if same_sign)
        numerator   = EMV - Previous_EMV - Open_CF - Close_CF - Currency + Income

      'portfolio' ONLY:
        denominator = Previous_EMV
        numerator   = EMV - Previous_EMV - Open_CF - Close_CF - Currency + Income
        (no flows in denominator — only external capital affects
         total portfolio)

    The three flow types (Open_CF, Close_CF, Currency_Flows) are kept
    SEPARATE so a performance analyst can validate every TWR by hand.

    TWR is computed vectorized (numpy) — identical arithmetic to the
    prior row-wise apply, including the same-sign rule and the portfolio
    branch. A zero denominator yields NaN (the apply version returned
    None, which pandas stored as NaN — same downstream behavior).
    """
    import numpy as np
    import pandas as pd

    if df is None or df.empty:
        return pd.DataFrame()

    if aif_field not in df.columns:
        raise ValueError(f"AIF field '{aif_field}' not found in DataFrame")

    # ── SUM EACH COMPONENT SEPARATELY BY LEVEL + DATE ─────────────────────────
    # Keep the three flow types separate — required for validation and
    # for the correct denominator/numerator construction below.
    agg = (
        df
        .groupby([aif_field, "ibor_date"], as_index=False)
        .agg({
            "EMV_Local":            "sum",
            "EMV_Book":             "sum",
            "Open_CF_Local":        "sum",
            "Open_CF_Book":         "sum",
            "Close_CF_Local":       "sum",
            "Close_CF_Book":        "sum",
            "Currency_Flows_Local": "sum",
            "Currency_Flows_Book":  "sum",
            "Income_Local":         "sum",
            "Income_Book":          "sum",
        })
    )

    agg[aif_field] = agg[aif_field].astype(str)
    agg = agg.sort_values([aif_field, "ibor_date"]).reset_index(drop=True)

    # ── BMV = prior day's EMV per group ───────────────────────────────────────
    agg["BMV_Local"] = agg.groupby(aif_field)["EMV_Local"].shift(1).fillna(0.0)
    agg["BMV_Book"]  = agg.groupby(aif_field)["EMV_Book"].shift(1).fillna(0.0)

    # Previous_EMV is the same as BMV here (prior day's ending value)
    agg["Previous_EMV_Local"] = agg["BMV_Local"]
    agg["Previous_EMV_Book"]  = agg["BMV_Book"]

    # ── TWR — SAME LOGIC AS compute_daily_twr, vectorized ─────────────────────
    is_portfolio = (aif_field == "portfolio")

    prev_l  = agg["Previous_EMV_Local"].to_numpy(dtype=float)
    prev_b  = agg["Previous_EMV_Book"].to_numpy(dtype=float)
    emv_l   = agg["EMV_Local"].to_numpy(dtype=float)
    emv_b   = agg["EMV_Book"].to_numpy(dtype=float)
    open_l  = agg["Open_CF_Local"].to_numpy(dtype=float)
    open_b  = agg["Open_CF_Book"].to_numpy(dtype=float)
    close_l = agg["Close_CF_Local"].to_numpy(dtype=float)
    close_b = agg["Close_CF_Book"].to_numpy(dtype=float)
    ccy_l   = agg["Currency_Flows_Local"].to_numpy(dtype=float)
    ccy_b   = agg["Currency_Flows_Book"].to_numpy(dtype=float)
    inc_l   = agg["Income_Local"].to_numpy(dtype=float)
    inc_b   = agg["Income_Book"].to_numpy(dtype=float)

    num_l = emv_l - prev_l - open_l - close_l - ccy_l + inc_l
    num_b = emv_b - prev_b - open_b - close_b - ccy_b + inc_b

    if not is_portfolio:
        same_sign_l = (prev_l >= 0) == (ccy_l >= 0)
        same_sign_b = (prev_b >= 0) == (ccy_b >= 0)
        den_l = prev_l + open_l + np.where(same_sign_l, ccy_l, 0.0)
        den_b = prev_b + open_b + np.where(same_sign_b, ccy_b, 0.0)
    else:
        den_l = prev_l
        den_b = prev_b

    agg["TWR_Local"] = np.where(
        den_l != 0, num_l / np.where(den_l != 0, den_l, 1.0), np.nan
    )
    agg["TWR_Book"] = np.where(
        den_b != 0, num_b / np.where(den_b != 0, den_b, 1.0), np.nan
    )

    # ── CHAINED INDEX (within this range) ─────────────────────────────────────
    agg["LocalToDate"] = agg.groupby(aif_field)["TWR_Local"].transform(
        lambda x: (1 + x.fillna(0)).cumprod()
    )
    agg["BookToDate"] = agg.groupby(aif_field)["TWR_Book"].transform(
        lambda x: (1 + x.fillna(0)).cumprod()
    )

    agg["BookToDate_Percent"]  = (agg["BookToDate"]  - 1) * 100
    agg["LocalToDate_Percent"] = (agg["LocalToDate"] - 1) * 100

    # ── CATEGORY FLOWS — presentation only (points to the relevant flow) ──────
    agg["Category_Flows_Local"] = (
        agg["Open_CF_Local"] + agg["Close_CF_Local"] + agg["Currency_Flows_Local"]
    )
    agg["Category_Flows_Book"] = (
        agg["Open_CF_Book"] + agg["Close_CF_Book"] + agg["Currency_Flows_Book"]
    )

    return agg