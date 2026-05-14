def qa_twr_explained(df, investment):
    import pandas as pd

    df = df[df["investment"] == investment].copy()

    if df.empty:
        print(f"No data for {investment}")
        return

    df = df.sort_values("ibor_date")

    # -----------------------------------------
    # BASIC STATE
    # -----------------------------------------
    start_date = df["ibor_date"].iloc[0]
    end_date = df["ibor_date"].iloc[-1]

    BMV = df["BMV_Local"].iloc[0]
    EMV = df["EMV_Local"].iloc[-1]

    CF = df["CF_Local"].sum()

    pnl = EMV - BMV - CF

    # TWR from index
    start_index = df["Index_Local"].iloc[0]
    end_index = df["Index_Local"].iloc[-1]

    twr = (end_index / start_index) - 1 if start_index != 0 else 0

    # -----------------------------------------
    # PRICE RETURN (baseline)
    # -----------------------------------------
    # Approximate price using EMV / quantity
    df["Price"] = df["EMV_Local"] / df["quantity"].replace(0, pd.NA)

    P_start = df["Price"].dropna().iloc[0]
    P_end = df["Price"].dropna().iloc[-1]

    price_return = (P_end / P_start) - 1 if P_start else 0

    # -----------------------------------------
    # FLOW-WEIGHTED ENTRY PRICE
    # -----------------------------------------
    flow_days = df[df["CF_Local"] != 0].copy()

    if not flow_days.empty:
        flow_days["Price"] = flow_days["EMV_Local"] / flow_days["quantity"].replace(0, pd.NA)

        weighted_price = (
                (flow_days["CF_Local"] * flow_days["Price"]).sum() /
                flow_days["CF_Local"].sum()
        )

        flow_return = (P_end / weighted_price) - 1 if weighted_price else 0
    else:
        weighted_price = None
        flow_return = None

    # -----------------------------------------
    # OUTPUT
    # -----------------------------------------
    print("\n=== QA: TWR EXPLAINED ===\n")

    print(f"Investment: {investment}")
    print(f"Period: {start_date.date()} → {end_date.date()}")

    print("\n--- SYSTEM (TWR) ---")
    print(f"BMV: {BMV:,.2f}")
    print(f"EMV: {EMV:,.2f}")
    print(f"CF : {CF:,.2f}")
    print(f"P&L: {pnl:,.2f}")
    print(f"TWR: {twr:.5f}")

    print("\n--- PRICE BASELINE ---")
    print(f"P_start: {P_start:.2f}")
    print(f"P_end  : {P_end:.2f}")
    print(f"Return : {price_return:.5f}")

    print("\n--- FLOW TIMING ---")
    if weighted_price is not None:
        print(f"Weighted Entry Price: {weighted_price:.2f}")
        print(f"Flow-Adjusted Return: {flow_return:.5f}")
    else:
        print("No flows detected")

    print("\n--- INTERPRETATION ---")

    if flow_return is not None:
        diff = twr - price_return
        print(f"Price Return      : {price_return:.5f}")
        print(f"TWR               : {twr:.5f}")
        print(f"Difference        : {diff:.5f}")

        if abs(diff) > 0.05:
            print("→ Significant flow timing impact")
        else:
            print("→ Return mostly explained by price movement")
    else:
        print("→ No flows — TWR should match price return")
def qa_inspect_aifs(
    df,
    level="investment",
    show_values=True,
    max_values=20
):
    import pandas as pd

    if df is None or df.empty:
        print("No data to inspect.")
        return

    print("\n" + "="*80)
    print("AIF INSPECTION")
    print("="*80)

    # -----------------------------------------
    # STEP 1: Identify non-core columns
    # -----------------------------------------
    core_cols = {
        level,
        "ibor_date",
        "BMV_Local", "EMV_Local", "CF_Local",
        "TWR_Local", "Index_Local",
        "CumCF_Local", "CumInc_Local",
        "BMV_Book", "EMV_Book", "CF_Book",
        "TWR_Book", "Index_Book",
        "CumCF_Book", "CumInc_Book",
        "Daily_Return"
    }

    aif_cols = [col for col in df.columns if col not in core_cols]

    print("\n--- AIF COLUMNS DETECTED ---\n")
    for col in aif_cols:
        print(col)

    # -----------------------------------------
    # STEP 2: Show unique values
    # -----------------------------------------
    if show_values:
        print("\n--- AIF VALUES (SAMPLE) ---\n")

        for col in aif_cols:
            print(f"\n>>> {col}")
            try:
                vals = df[col].dropna().unique()
                print(vals[:max_values])
            except Exception as e:
                print(f"Error reading {col}: {e}")

    # -----------------------------------------
    # STEP 3: Check investment → AIF consistency
    # -----------------------------------------
    print("\n--- INVESTMENT → AIF CONSISTENCY ---\n")

    for col in aif_cols:
        try:
            mapping = (
                df[[level, col]]
                .drop_duplicates()
                .groupby(level)
                .size()
            )

            multi = mapping[mapping > 1]

            if not multi.empty:
                print(f"⚠️ {col} varies within {level}:")
                print(multi.head())
            else:
                print(f"✔ {col} is consistent per {level}")

        except Exception as e:
            print(f"Error checking {col}: {e}")

    print("\n" + "="*80 + "\n")

    print("\n--- AGGREGATION READINESS CHECK ---\n")

    candidate_cols = []

    for col in aif_cols:
        try:
            mapping = (
                df[[level, col]]
                .drop_duplicates()
                .groupby(level)
                .size()
            )

            if (mapping <= 1).all():
                candidate_cols.append(col)

        except:
            pass

    print("✔ Suitable for aggregation:")
    print(candidate_cols)