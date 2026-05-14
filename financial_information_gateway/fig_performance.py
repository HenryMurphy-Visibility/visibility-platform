import pandas as pd
from pathlib import Path
from datetime import datetime
from performance import compute_daily_twr
from v_config import BASE_PATH, FUNDS_PATH, REFDATA_PATH, REPORTS_PATH, VIEWS_PATH


pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)
pd.set_option('display.max_colwidth', None)

def get_all_periods(portfolio, calendar):
    from pathlib import Path
    from financial_information_gateway.extraction.box_extractor import derive_calendar_identity



    base_path = Path(FUNDS_PATH) / portfolio / "Calendars" / calendar / "Snapshots"

    periods = []

    for file in base_path.glob("*.pkl"):
        stem = file.stem
        base_date = stem.split("T")[0]
        period = derive_calendar_identity(base_date, calendar)
        periods.append(period)

    return sorted(set(periods))

# =========================
# PERIOD HELPERS
# =========================
def get_previous_period(portfolio, calendar, period_key):
    from financial_information_gateway.extraction.box_extractor import derive_calendar_identity

    base_path = Path(f"C:/Users/hjmne/PycharmProjects/chest/funds/{portfolio}/Calendars/{calendar}/Snapshots")

    periods = []

    for file in base_path.glob("*.pkl"):
        stem = file.stem
        base_date = stem.split("T")[0]
        period = derive_calendar_identity(base_date, calendar)
        periods.append(period)

    periods = sorted(set(periods))

    if period_key not in periods:
        raise RuntimeError(f"{period_key} not found in snapshots")

    idx = periods.index(period_key)

    if idx == 0:
        return None

    return periods[idx - 1]


# =========================
# EXTRACTION
# =========================
def extract_je_data(portfolio, calendar, period_key):
    from financial_information_gateway.extraction.box_extractor import extract_box_components

    previous_period = get_previous_period(portfolio, calendar, period_key)

    if previous_period is None:
        print(f"No prior period for {period_key} — using initial state")

        # Use only current period as extraction window
        extracted = extract_box_components(
            portfolio=portfolio,
            calendar=calendar,
            period_start=period_key,
            period_end=period_key,
            uber_filter=None,

        )

        journal_entries = extracted["journal_entries"]

        print(f"JEs extracted (initial): {len(journal_entries)}")

        return journal_entries

    print(f"Using periods: {previous_period} → {period_key}")

    extracted = extract_box_components(
        portfolio=portfolio,
        calendar=calendar,
        period_start=previous_period,
        period_end=period_key,
        uber_filter=None,

    )

    journal_entries = extracted["journal_entries"]

    print(f"JEs extracted: {len(journal_entries)}")

    return journal_entries


# =========================
# PERFORMANCE CORE
# =========================
def compute_performance_inputs(journal_entries, level, period_key):
    from performance import compute_daily_twr

    start = pd.to_datetime(period_key + "-01")
    end = start + pd.offsets.MonthEnd(0)

    detail_df, _, _ = compute_daily_twr(
        journal_entries,
        level,
        period_key
    )

    detail_df = detail_df[
        (detail_df["ibor_date"] >= start) &
        (detail_df["ibor_date"] <= end)
    ]

    return detail_df


# =========================
# LOAD PRIOR CONSTRUCTION (NEW)
# =========================
def load_prior_performance_state(portfolio, calendar, period_key, level):
    from pathlib import Path
    import pandas as pd

    base_path = Path(
        f"C:/Users/hjmne/PycharmProjects/chest/funds/{portfolio}/Calendars/{calendar}/Constructions/performance"
    )

    # --------------------------------------------------
    # Ensure directory exists
    # --------------------------------------------------
    if not base_path.exists():
        return None

    # --------------------------------------------------
    # Get constructed files
    # --------------------------------------------------
    files = list(base_path.glob("*.pkl"))

    if not files:
        return None

    # --------------------------------------------------
    # Normalize period_key (CRITICAL)
    # --------------------------------------------------
    period_key = str(period_key)[:7]

    # --------------------------------------------------
    # Build sorted period list (robust ordering)
    # --------------------------------------------------
    periods = sorted({f.stem[:7] for f in files})

    if period_key not in periods:
        return None

    idx = periods.index(period_key)

    if idx == 0:
        # First period → no prior
        return None

    prior_period = periods[idx - 1]
    prior_file = base_path / f"{prior_period}.pkl"

    if not prior_file.exists():
        return None

    # --------------------------------------------------
    # Load prior construction
    # --------------------------------------------------
    payload = pd.read_pickle(prior_file)

    if not isinstance(payload, dict) or "data" not in payload:
        raise RuntimeError(f"Invalid payload format in {prior_file}")

    df = payload["data"]

    if df is None or df.empty:
        return None

    # --------------------------------------------------
    # Validate required columns
    # --------------------------------------------------
    required_cols = [
        "Index_Local",
        "Index_Book",
        "CumCF_Local",
        "CumCF_Book",
        "CumInc_Local",
        "CumInc_Book"
    ]

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise RuntimeError(f"Missing columns in prior construction: {missing}")

    if level not in df.columns:
        raise RuntimeError(f"Missing level column '{level}' in prior construction")

    if "ibor_date" not in df.columns:
        raise RuntimeError("Missing 'ibor_date' in prior construction")

    # --------------------------------------------------
    # Extract LAST STATE PER LEVEL
    # --------------------------------------------------
    prior = (
        df
        .sort_values("ibor_date")
        .groupby(level)
        .last()[required_cols]
        .reset_index()
        .rename(columns={
            "Index_Local": "Prior_Index_Local",
            "Index_Book": "Prior_Index_Book",
            "CumCF_Local": "Prior_CumCF_Local",
            "CumCF_Book": "Prior_CumCF_Book",
            "CumInc_Local": "Prior_CumInc_Local",
            "CumInc_Book": "Prior_CumInc_Book"
        })
    )

    return prior


# =========================
# SAVE CONSTRUCTION
# =========================
def save_performance_construction(portfolio, calendar, period_key, df):
    print(f"Saving construction: {period_key}")
    path = Path(
        f"C:/Users/hjmne/PycharmProjects/chest/funds/{portfolio}/Calendars/{calendar}/Constructions/performance"
    )

    path.mkdir(parents=True, exist_ok=True)

    file = path / f"{period_key}.pkl"

    payload = {
        "data": df,
        "metadata": {
            "portfolio": portfolio,
            "calendar": calendar,
            "period": period_key,
            "construction": "performance",
            "created_at": datetime.now()
        }
    }

    pd.to_pickle(payload, file)


# =========================
# SINGLE BOX CONSTRUCT
# =========================
def build_performance_construct(portfolio, calendar, boxes, level):
    import pandas as pd

    all_frames = []

    prior_index_local = 1.0
    prior_index_book = 1.0

    prior_cumcf_local = 0.0
    prior_cumcf_book = 0.0

    prior_cuminc_local = 0.0
    prior_cuminc_book = 0.0

    for box in boxes:

        print(f"Processing box: {box}")

        # -----------------------------------------
        # LOAD JEs FOR PERIOD
        # -----------------------------------------
        journal_entries = extract_je_data(portfolio, calendar, box)

        if not journal_entries:
            continue

        # -----------------------------------------
        # BUILD DAILY STATE (YOUR TWR)
        # -----------------------------------------
        df, _, _ = compute_daily_twr(journal_entries, level, box)

        if df is None or df.empty:
            continue

        df = df.sort_values([level, "ibor_date"]).copy()

        # -----------------------------------------
        # ADD PRIOR VALUES (FIRST ROW ONLY)
        # -----------------------------------------
        df["Prior_Index_Local"] = None
        df["Prior_Index_Book"] = None

        df["Prior_CumCF_Local"] = None
        df["Prior_CumCF_Book"] = None

        df["Prior_CumInc_Local"] = None
        df["Prior_CumInc_Book"] = None

        first_idx = df.index[0]

        df.loc[first_idx, "Prior_Index_Local"] = prior_index_local
        df.loc[first_idx, "Prior_Index_Book"] = prior_index_book

        df.loc[first_idx, "Prior_CumCF_Local"] = prior_cumcf_local
        df.loc[first_idx, "Prior_CumCF_Book"] = prior_cumcf_book

        df.loc[first_idx, "Prior_CumInc_Local"] = prior_cuminc_local
        df.loc[first_idx, "Prior_CumInc_Book"] = prior_cuminc_book

        # -----------------------------------------
        # BUILD FULL INDEX (CHAINED)
        # -----------------------------------------
        df["Index_Local"] = (
                df["Period_Index_Local"] * df["Prior_Index_Local"].ffill()
        )

        df["Index_Book"] = (
                df["Period_Index_Book"] * df["Prior_Index_Book"].ffill()
        )

        # -----------------------------------------
        # UPDATE PRIOR VALUES FOR NEXT PERIOD
        # -----------------------------------------
        prior_index_local = df["Index_Local"].iloc[-1]
        prior_index_book = df["Index_Book"].iloc[-1]

        prior_cumcf_local += df["CF_Local"].sum()
        prior_cumcf_book += df["CF_Book"].sum()

        prior_cuminc_local += df["Income_Local"].sum()
        prior_cuminc_book += df["Income_Book"].sum()

        # -----------------------------------------
        # APPEND (CORRECT)
        # -----------------------------------------
        all_frames.append(df)

    # -----------------------------------------
    # FINAL CONCAT
    # -----------------------------------------
    if not all_frames:
        return pd.DataFrame()

    final_df = pd.concat(all_frames).reset_index(drop=True)

    # -----------------------------------------
    # REMOVE DUPLICATES (CRITICAL FIX)
    # -----------------------------------------
    final_df = final_df.sort_values([level, "ibor_date"])

    final_df = final_df.drop_duplicates(
        subset=[level, "ibor_date"],
        keep="last"
    )

    return final_df

# =========================
# MULTI-BOX CONSTRUCT
# =========================
def construct_range(portfolio, calendar, boxes, level):
    boxes = sorted(boxes)

    df = build_performance_construct(
        portfolio,
        calendar,
        boxes,
        level
    )

    if df is None or df.empty:
        print("No data returned.")
        return pd.DataFrame()

    return df

# =========================
# CARVE
# =========================
def carve_performance(df, group_by):

    grouped = df.groupby(group_by)

    summary = grouped.agg({
        "Index_Local": ["first", "last"],
        "Index_Book": ["first", "last"],
        "CumCF_Local": "last",
        "CumCF_Book": "last",
        "CumInc_Local": "last",
        "CumInc_Book": "last"
    })

    summary.columns = ["_".join(col) for col in summary.columns]

    summary["Return"] = (
        summary["Index_Book_last"] /
        summary["Index_Book_first"] - 1
    )

    return summary


# =========================
# RUN VIEW
# =========================
def run_performance_view(portfolio, calendar, boxes, level, group_by=None):

    df = construct_range(portfolio, calendar, boxes, level)

    if df.empty:
        return df

    if group_by:
        return carve_performance(df, group_by)

    return df


# =========================
# DEBUG
# =========================
def debug_single_investment_month(df, investment):

    print("\n========================================")
    print(f"INVESTMENT VIEW: {investment}")
    print("========================================\n")

    df_i = df[df["investment"] == investment].copy()

    if df_i.empty:
        print("No data for investment.")
        return

    df_i = df_i.sort_values("ibor_date")

    print("\n=== DAILY STATE ===\n")
    print(df_i[[
        "ibor_date",
        "BMV_Local",
        "EMV_Local",
        "CF_Local",
        "CumCF_Local",
        "Income_Local",
        "CumInc_Local",
        "Index_Local"
    ]].to_string(index=False))

# =========================
# HIGH-LEVEL CARVE WRAPPER
# =========================
def performance_carve(
    portfolio,
    calendar,
    boxes,
    level,
    cadence=None,
    start_date=None,
    end_date=None,
    reuse_df=None
):

    from financial_information_gateway.fig_performance_carving import performance_carving_periods

    # -----------------------------------------
    # Resolve df
    # -----------------------------------------
    if reuse_df is not None:
        df = reuse_df
    else:
        df = run_performance_view(portfolio, calendar, boxes, level)

    if df is None or df.empty:
        return df

    # -----------------------------------------
    # Carve
    # -----------------------------------------
    return performance_carving_periods(
        df,
        level,
        cadence=cadence,
        start_date=start_date,
        end_date=end_date
    )


def main():
    print(">>> MAIN STARTED <<<")

    import pandas as pd

    from financial_information_gateway.fig_performance_carving import (
        performance_carving_periods,
        aggregate_by_aif
    )
    from financial_information_gateway.fig_performance_qa import qa_twr_explained

    # -----------------------------------------
    # DISPLAY SETTINGS
    # -----------------------------------------
    pd.set_option("display.float_format", "{:,.5f}".format)
    pd.set_option("display.width", 1400)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.expand_frame_repr", False)
    pd.set_option("display.max_rows", 5000)

    portfolio = "Portfolio1"
    calendar = "Monthly"
    level = "investment"

    boxes = ["2021-01", "2021-02"]
 #   boxes = ["2021-01", "2021-02", "2021-03", "2021-04", "2021-05", "2021-06", "2021-07", "2021-08", "2021-09", "2021-10", "2021-11", "2021-12"]
    # -----------------------------------------
    # LOAD INVESTMENT MASTER (AIF SOURCE)
    # -----------------------------------------
    investment_master_path = (
        r"C:\Users\hjmne\PycharmProjects\chest\refdata\investment_master.csv"
    )

    # Windows-safe encoding
    investment_master = pd.read_csv(investment_master_path, encoding="cp1252")

    # -----------------------------------------
    # BUILD ONCE (CANONICAL STATE)
    # -----------------------------------------
    print("\n" + "=" * 80)
    print("BUILD: INVESTMENT LEVEL STATE")
    print("=" * 80)

    df = run_performance_view(
        portfolio,
        calendar,
        boxes,
        level
    )

    if df is None or df.empty:
        print("No data")
        return

    df = df.sort_values(["investment", "ibor_date"])

    # -----------------------------------------
    # MERGE AIF
    # -----------------------------------------
    print("\n--- MERGING AIF (investment_master) ---\n")

    df = df.merge(
        investment_master[
            [
                "investment",
                "investment_type",
                "asset_class",
                "sector",
                "industry",
                "country",
                "analyst",
                "currency"
            ]
        ],
        on="investment",
        how="left"
    )

    # -----------------------------------------
    # ADD PORTFOLIO TOTAL
    # -----------------------------------------
    df["portfolio"] = "TOTAL"

    # -----------------------------------------
    # VERIFY
    # -----------------------------------------
    print("\n--- SAMPLE AIF MAPPING ---\n")
    print(
        df[
            ["investment", "investment_type", "sector", "country", "currency", "analyst"]
        ]
        .drop_duplicates()
        .head(300)
    )

    # =========================================================
    # 🔹 INVESTMENT VIEW
    # =========================================================
    print("\n" + "=" * 80)
    print("VIEW: INVESTMENT")
    print("=" * 80)

    print(df.head(500))

    inv_monthly = performance_carving_periods(
        df,
        level="investment",
        cadence="M"
    )

    print("\n--- MONTHLY (INVESTMENT) ---\n")
    print(inv_monthly.head(300))

    # =========================================================
    # 🔹 INVESTMENT TYPE (EQUITY / CURRENCY)
    # =========================================================
    print("\n" + "=" * 80)
    print("VIEW: INVESTMENT TYPE")
    print("=" * 80)

    df_type = aggregate_by_aif(df, "investment_type")

    print("\n--- DAILY (TYPE) ---\n")
    print(df_type.head(500))

    type_monthly = performance_carving_periods(
        df_type,
        level="investment_type",
        cadence="M"
    )

    print("\n--- MONTHLY (TYPE) ---\n")
    print(type_monthly)

    # =========================================================
    # 🔹 SECTOR
    # =========================================================
    print("\n" + "=" * 80)
    print("VIEW: SECTOR")
    print("=" * 80)

    total_monthly = performance_carving_periods(
        df_total,
        level="portfolio",
        cadence="M"
    )

    print("\n--- MONTHLY (TOTAL) ---\n")
    print(total_monthly)

    # =========================================================
    # 🔹 QA
    # =========================================================
    print("\n" + "=" * 80)
    print("QA CHECK (GOOG)")
    print("=" * 80)

    qa_twr_explained(df, "GOOG")

    df_sector = aggregate_by_aif(df, "sector")

    print("\n--- DAILY (SECTOR) ---\n")
    print(df_sector.head(500))

    sector_monthly = performance_carving_periods(
        df_sector,
        level="sector",
        cadence="M"
    )

    print("\n--- MONTHLY (SECTOR) ---\n")
    print(sector_monthly)

    # =========================================================
    # 🔹 COUNTRY
    # =========================================================
    print("\n" + "=" * 80)
    print("VIEW: COUNTRY")
    print("=" * 80)

    df_country = aggregate_by_aif(df, "country")

    print("\n--- DAILY (COUNTRY) ---\n")
    print(df_country.head(500))

    country_monthly = performance_carving_periods(
        df_country,
        level="country",
        cadence="M"
    )

    print("\n--- MONTHLY (COUNTRY) ---\n")
    print(country_monthly)

    # =========================================================
    # 🔹 CURRENCY
    # =========================================================
    print("\n" + "=" * 80)
    print("VIEW: CURRENCY")
    print("=" * 80)

    df_currency = aggregate_by_aif(df, "currency")

    print("\n--- DAILY (CURRENCY) ---\n")
    print(df_currency.head(500))

    currency_monthly = performance_carving_periods(
        df_currency,
        level="currency",
        cadence="M"
    )

    print("\n--- MONTHLY (CURRENCY) ---\n")
    print(currency_monthly)
    
    # =========================================================
    # 🔹 ANALYST
    # =========================================================
    print("\n" + "=" * 80)
    print("VIEW: ANALYST")
    print("=" * 80)

    df_analyst = aggregate_by_aif(df, "analyst")

    print("\n--- DAILY (ANALYST) ---\n")
    print(df_analyst.head(500))

    analyst_monthly = performance_carving_periods(
        df_analyst,
        level="analyst",
        cadence="M"
    )

    print("\n--- MONTHLY (ANALYST) ---\n")
    print(analyst_monthly)


    # =========================================================
    # 🔹 PORTFOLIO TOTAL
    # =========================================================
    print("\n" + "=" * 80)
    print("VIEW: TOTAL PORTFOLIO")
    print("=" * 80)

    df_total = aggregate_by_aif(df, "portfolio")

    print("\n--- DAILY (TOTAL) ---\n")
    print(df_total.head(500))


if __name__ == "__main__":
    main()
