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
    # STEP 3: HANDLE NO CADENCE (FULL RANGE)
    # --------------------------------------------------
    if cadence is None:

        result = (
            df
            .groupby(level)
            .agg(
                start_index=("Index_Local", "first"),
                end_index=("Index_Local", "last"),
                start_date=("ibor_date", "first"),
                end_date=("ibor_date", "last"),
                total_cf=("CumCF_Local", lambda x: x.iloc[-1] - x.iloc[0]),
                total_income=("CumInc_Local", lambda x: x.iloc[-1] - x.iloc[0]),
            )
        )

        result["return"] = result["end_index"] / result["start_index"] - 1

        return result.reset_index()

    # --------------------------------------------------
    # STEP 4: DERIVE PERIODS FROM DATA (KEY DESIGN)
    # --------------------------------------------------
    df["period"] = df["ibor_date"].dt.to_period(cadence)

    # --------------------------------------------------
    # STEP 5: GROUP INTO PERIODS
    # --------------------------------------------------
    result = (
        df
        .groupby([level, "period"])
        .agg(
            start_index=("Index_Local", "first"),
            end_index=("Index_Local", "last"),
            start_date=("ibor_date", "first"),
            end_date=("ibor_date", "last"),
            total_cf=("CumCF_Local", lambda x: x.iloc[-1] - x.iloc[0]),
            total_income=("CumInc_Local", lambda x: x.iloc[-1] - x.iloc[0]),
        )
        .reset_index()
    )

    # --------------------------------------------------
    # STEP 6: COMPUTE RETURNS
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

    # 🔥 ADD THIS
    agg["CumCF_Local"] = agg.groupby(to_level)["CF_Local"].cumsum()
    agg["CumInc_Local"] = 0.0

    return agg


def aggregate_by_aif(df, aif_field):
    import numpy as np
    import pandas as pd

    if df is None or df.empty:
        return pd.DataFrame()

    # -----------------------------------------
    # VALIDATION
    # -----------------------------------------
    if aif_field not in df.columns:
        raise ValueError(f"AIF field '{aif_field}' not found in DataFrame")

    # -----------------------------------------
    # GROUP (CORE AGGREGATION)
    # -----------------------------------------
    agg = (
        df
        .groupby([aif_field, "ibor_date"], as_index=False)
        .agg({
            "BMV_Local": "sum",
            "EMV_Local": "sum",
            "CF_Local": "sum",
            "Income_Local": "sum"
        })
    )

    # -----------------------------------------
    # ENSURE GROUP COLUMN PERSISTS (CRITICAL FOR TOTAL)
    # -----------------------------------------
    agg[aif_field] = agg[aif_field].astype(str)

    # -----------------------------------------
    # SORT (CRITICAL FOR TIME SERIES)
    # -----------------------------------------
    agg = agg.sort_values([aif_field, "ibor_date"])

    # -----------------------------------------
    # TWR CALCULATION
    # -----------------------------------------
    agg["TWR_Local"] = np.where(
        agg["BMV_Local"] != 0,
        (agg["EMV_Local"] - agg["BMV_Local"] - agg["CF_Local"]) / agg["BMV_Local"],
        0.0
    )

    # -----------------------------------------
    # INDEX (CHAINED RETURN)
    # -----------------------------------------
    agg["Index_Local"] = (
        (1 + agg["TWR_Local"])
        .groupby(agg[aif_field])
        .cumprod()
    )

    # -----------------------------------------
    # CUMULATIVE FLOWS
    # -----------------------------------------
    agg["CumCF_Local"] = (
        agg.groupby(aif_field)["CF_Local"].cumsum()
    )

    agg["CumInc_Local"] = (
        agg.groupby(aif_field)["Income_Local"].cumsum()
    )

    return agg
