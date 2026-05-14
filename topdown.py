import pandas as pd
import ast
import os
from datetime import datetime

# Replace with the real path to your internal modules
from centralized_reporting_hub import run_query_topdown_activity, parse_card_value, normalize_filters


def load_query_card(card_name, query_card_path):
    df_cards = pd.read_csv(query_card_path)
    df_cards["CardName"] = df_cards["CardName"].astype(str).str.strip()
    stripped_name = card_name.replace("QueryGet_", "")
    row = df_cards[df_cards["CardName"] == stripped_name]

    if row.empty:
        raise ValueError(f"❌ No query card found for {card_name}")

    return row.iloc[0].to_dict()


def main():
    # === Config ===
    card_name = "QueryGet_FlowActivity"
    portfolio = "RealPortfolioName"  # ✅ Replace with actual portfolio
    period_start = "2023-01-18"
    period_end = "2023-03-31"
    query_card_path = "BASE_PATH/refdata/query_cards.csv"
    output_dir = "./debug_outputs"
    os.makedirs(output_dir, exist_ok=True)

    print(f"🚀 Running standalone query test for: {card_name}")

    # === Load query card ===
    card = load_query_card(card_name, query_card_path)
    start_dt = pd.to_datetime(period_start)
    end_dt = pd.to_datetime(period_end)

    group_by = parse_card_value(card.get("GroupBy"), portfolio, start_dt, end_dt)
    filters = normalize_filters(parse_card_value(card.get("Filters"), portfolio, start_dt, end_dt))
    sort_by = parse_card_value(card.get("SortBy"), portfolio, start_dt, end_dt)
    visible_columns = parse_card_value(card.get("VisibleColumns"), portfolio, start_dt, end_dt)
    report_name = parse_card_value(card.get("ReportName"), portfolio, start_dt, end_dt)

    # === Run topdown activity ===
    result = run_query_topdown_activity(
        portfolio=portfolio,
        period_start=start_dt,
        period_end=end_dt,
        filters=filters,
        sort_by=sort_by,
        group_by=group_by,
        visible_columns=visible_columns,
        gw=None,
        report_name=report_name or "TopDownActivity"
    )

    # === Analyze & Export ===
    if not isinstance(result, dict):
        print("❌ Unexpected return value — expected dictionary.")
        return

    for key in ["df_start", "df_je", "df_end"]:
        df = result.get(key)
        if isinstance(df, pd.DataFrame):
            print(f"📊 {key}: shape={df.shape}")
            if df.empty:
                print(f"⚠ {key} is EMPTY.")
            else:
                output_path = os.path.join(output_dir, f"{key}.csv")
                df.to_csv(output_path, index=False)
                print(f"✅ Saved: {output_path}")
        else:
            print(f"❌ {key} is missing or not a DataFrame.")

    print("✅ Standalone query finished.")


def main():
    # === User Configurable ===
    card_name = "QueryGet_FlowActivity"
    portfolio = "XYZMutualFund1"  # Update this
    period_start = "2023-01-18"
    period_end = "2023-03-31"
    query_card_path = "BASE_PATH/refdata/query_cards.csv"
    output_dir = "."  # Folder to save CSVs

    print(f"🚀 Running standalone query test for: {card_name}")

    # === Load & Parse Query Card ===
    card = load_query_card(card_name, query_card_path)
    period_start_dt = pd.to_datetime(period_start)
    period_end_dt = pd.to_datetime(period_end)

    group_by = parse_card_value(card.get("GroupBy"), portfolio, period_start_dt, period_end_dt)
    filters = normalize_filters(parse_card_value(card.get("Filters"), portfolio, period_start_dt, period_end_dt))
    sort_by = parse_card_value(card.get("SortBy"), portfolio, period_start_dt, period_end_dt)
    visible_columns = parse_card_value(card.get("VisibleColumns"), portfolio, period_start_dt, period_end_dt)
    report_name = parse_card_value(card.get("ReportName"), portfolio, period_start_dt, period_end_dt)
    portfolio = "XYZMutualFund1"
    # === Run Topdown Activity Report ===
    result = run_query_topdown_activity(
        portfolio=portfolio,
        period_start=period_start_dt,
        period_end=period_end_dt,
        filters=filters,
        sort_by=sort_by,
        group_by=group_by,
        visible_columns=visible_columns,
        gw=None,
        report_name=report_name or "TopDownActivity"
    )

    # === Export CSV Results ===
    if not isinstance(result, dict):
        print("❌ Unexpected result type — not a dictionary.")
        return

    for key, df in result.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            output_path = f"{output_dir}/{key}.csv"
            df.to_csv(output_path, index=False)
            print(f"✅ Saved: {output_path} ({df.shape[0]} rows)")
        else:
            print(f"⚠ {key} is empty or invalid.")

    print("✅ All done.")


if __name__ == "__main__":
    main()
