import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime
import ast


from reports.refdata.chest.kivygui import sub_ledger
from bookkeeping import SpaceManager

# -----------------------------------------------------
# ✅ Parse Card Values from CSV with substitution logic
# -----------------------------------------------------
def parse_card_value(value, portfolio, period_start, period_end):
    if pd.isna(value):
        return None

    replaced = str(value).replace("{portfolio}", portfolio)
    replaced = replaced.replace("{period_start}", period_start.strftime("%Y-%m-%d"))
    replaced = replaced.replace("{period_end}", period_end.strftime("%Y-%m-%d"))

    try:
        parsed = ast.literal_eval(replaced)
        return parsed
    except Exception:
        # If not parsable, return as string
        return replaced
# -----------------------------------------------------
# ✅ Run Query From Card (Calls `run_query`)
# -----------------------------------------------------
def run_query_from_card(card_name, portfolio, period_start, period_end, override_filters=None, card_type="MAIN"):
    import pandas as pd
    import ast

    query_card_path = "BASE_PATH/refdata/query_cards.csv"

    try:
        card_df = pd.read_csv(query_card_path)
    except Exception as e:
        print(f"❌ Failed to load query_cards.csv: {e}")
        return

    # ✅ Clean up CardName and Type fields
    card_df["CardName"] = card_df["CardName"].astype(str).str.strip()
    card_df["Type"] = card_df["Type"].astype(str).str.strip().str.upper()

    # ✅ Strip prefix to match with 'CardName'
    stripped_name = card_name.replace("QueryGet_", "", 1)

    # ✅ Locate correct row
    card_row = card_df[
        (card_df["CardName"] == stripped_name) &
        (card_df["Type"] == card_type.upper())
    ]

    if card_row.empty:
        print(f"❌ Query card '{card_name}' (type={card_type}) not found.")
        print(f"📋 Available cards: {card_df[['CardName', 'Type']].drop_duplicates().to_dict('records')}")
        return

    card = card_row.iloc[0].to_dict()

    # ✅ Parse values
    group_by = parse_card_value(card.get("GroupBy"), portfolio, period_start, period_end)
    filters = override_filters or parse_card_value(card.get("Filters"), portfolio, period_start, period_end)
    sort_by = parse_card_value(card.get("SortBy"), portfolio, period_start, period_end)
    report_name = parse_card_value(card.get("ReportName") or stripped_name, portfolio, period_start, period_end)
    include_totals = str(card.get("IncludeTotals", "True")).strip().lower() != "false"
    connect = str(card.get("Connect", "False")).strip().lower() == "true"
    je_detail = str(card.get("JEDetail", "False")).strip().lower() == "true"

    print(f"🚀 Running query card '{card_name}' (type={card_type}) for portfolio '{portfolio}'")

    from master_queries_new import run_query  # Update this if local import not needed

    df = run_query(
        portfolio=portfolio,
        period_start=pd.to_datetime(period_start),
        period_end=pd.to_datetime(period_end),
        group_by=group_by,
        filters=filters,
        sort_by=sort_by,
        report_name=report_name,
        include_totals=include_totals,
        connect=connect,
        je_detail=je_detail
    )

    return df


# -----------------------------------------------------
# ✅ Core Function to Execute the Query
# -----------------------------------------------------
def run_query(portfolio, period_start, period_end, group_by=None, filters=None,
              sort_by=None, report_name=None, include_totals=True, connect=False,
              je_detail=False):
    import pandas as pd
    import os
    import sys
    from bookkeeping import SpaceManager
    from reports.refdata.chest.kivygui import sub_ledger

    mqs_path = f{BASE_PATH}/funds/{portfolio}/Open/periods/mqs.pkl"
    try:
        journal_entries = pd.read_pickle(mqs_path)
    except Exception as e:
        print(f"❌ Error loading MQS from {mqs_path}. ({e})")
        sys.exit(1)

    journal_entries = [je for je in journal_entries if je.portfolio == portfolio]

    # ✅ EARLY FILTER: Filter journal entries by investment if je_detail + investment filter
    if je_detail and filters:
        inv_filter = filters.get("Investment")
        if inv_filter and not inv_filter.startswith("!="):  # Only support == for now
            journal_entries = [je for je in journal_entries if je.investment == inv_filter]
            print(f"⚡ Early JE filter applied: Investment == {inv_filter} → {len(journal_entries)} entries")

    space_manager = SpaceManager()
    space_manager.clear_space("sub_ledger")
    sub_ledger = space_manager.get_space("sub_ledger")

    for idx, je in enumerate(journal_entries):
        if je.tradedate <= period_end:
            sub_ledger.post_journal_entry(je)
        if idx % 5000 == 0:
            print(f"📌 Posted {idx} journal entries...")

    print(f"✅ Bookkeeping Space rebuilt with {len(journal_entries)} journal entries.")

    # Opening Balance
    space_opening = SpaceManager()
    sub_opening = space_opening.get_space("sub_ledger")
    for je in journal_entries:
        if je.tradedate <= period_start:
            sub_opening.post_journal_entry(je)

    df_open = pd.DataFrame(sub_opening.all_bookkeeping_accounts_info(), columns=[
        'Portfolio', 'Investment', 'Lot_ID', 'Tax_Date', 'Ls', 'Location',
        'Financial Account', 'Quantity', 'Local_Cost', 'Book_Cost', 'Notional', 'Original_Face'
    ])
    df_open['Source'] = 'Opening'

    # Closing Balance
    df_close = pd.DataFrame(sub_ledger.all_bookkeeping_accounts_info(), columns=[
        'Portfolio', 'Investment', 'Lot_ID', 'Tax_Date', 'Ls', 'Location',
        'Financial Account', 'Quantity', 'Local_Cost', 'Book_Cost', 'Notional', 'Original_Face'
    ])
    df_close['Source'] = 'Closing'

    # Activity
    df_activity = []
    import inspect

    # 🔹 Dynamically capture all attributes from the Journal Entry class
    if connect:
        df_activity = []

        for je in journal_entries:
            if period_start < je.tradedate <= period_end:
                row = je.__dict__.copy()  # or use vars(je) — same effect
                row['Source'] = 'Activity'
                df_activity.append(row)

        # Convert to DataFrame
        df_activity = pd.DataFrame(df_activity)
    else:
        df_activity = pd.DataFrame()

    df = pd.concat([df_open, df_activity, df_close], ignore_index=True)

    # Merge logic — Summary vs Drilldown

    # Summary → merge investment master
    inv_path = "BASE_PATH/refdata/investment_master.csv"
    if os.path.exists(inv_path):
        try:
            invest_master = pd.read_csv(inv_path)
            df = pd.merge(df, invest_master, on='Investment', how='left')
            print(f"✅ investment_master merged (summary)")
        except Exception as e:
            print(f"❌ Error merging investment_master: {e}")
    coa_path = "BASE_PATH/refdata/chart_of_accounts.csv"
    if os.path.exists(coa_path):
        try:
            coa = pd.read_csv(coa_path)
            # Perform the merge
            df = pd.merge(
                df,
                coa,
                left_on="Financial Account",
                right_on="System_Name",
                how="left"
            )
            print(f"✅ investment_master merged (summary)")
        except Exception as e:
            print(f"❌ Error merging investment_master: {e}")

    # # Drilldown → merge events
    # events_path = f{BASE_PATH}/refdata/pooltest/{portfolio}.csv"
    # if os.path.exists(events_path):
    #     try:
    #         events_df = pd.read_csv(events_path)
    #         df_activity_only = df[df['Source'] == 'Activity']
    #         df_non_activity = df[df['Source'] != 'Activity']
    #         df_activity_only = pd.merge(df_activity_only, events_df, on="tranid", how="left")
    #         df = pd.concat([df_non_activity, df_activity_only], ignore_index=True)
    #         print(f"✅ Events merged into Activity using 'tranid' ({len(df_activity_only)} rows)")
    #     except Exception as e:
    #         print(f"❌ Error loading/merging events file: {e}")
    #

    # 🔹 Apply filters (if any)
    # ✅ Apply clean filter logic

    print("\n🧪 DEBUG FILTER CHECK")
    print("Columns in df:", list(df.columns))
    print("Incoming filters:", filters)

    if filters:
        print("\n🧪 RAW FILTER DEBUG")
        for k, v in filters.items():
            print(f"   {k} = {repr(v)} (type: {type(v)})")

        for key, val in filters.items():
            if key not in df.columns:
                print(f"❌ Skipping filter — column '{key}' not found.")
                continue

            try:
                # Not equal: "!=UnrealPriceGL"
                if isinstance(val, str) and val.startswith("!="):
                    target = val[2:].strip()
                    df = df[df[key].astype(str) != target]
                    print(f"🔹 Applied: {key} != {target}")

                # Greater than: ">100"
                elif isinstance(val, str) and val.startswith(">"):
                    target = float(val[1:].strip())
                    df = df[df[key].astype(float) > target]
                    print(f"🔹 Applied: {key} > {target}")

                # Less than: "<50"
                elif isinstance(val, str) and val.startswith("<"):
                    target = float(val[1:].strip())
                    df = df[df[key].astype(float) < target]
                    print(f"🔹 Applied: {key} < {target}")

                # List of values: ["Equity", "Bond"]
                elif isinstance(val, list):
                    df = df[df[key].isin(val)]
                    print(f"🔹 Applied: {key} in {val}")

                # Default: direct equality
                else:
                    df = df[df[key] == val]
                    print(f"🔹 Applied: {key} == {val}")

            except Exception as e:
                print(f"❌ Error applying filter {key}: {e}")

    # 🔹 Apply grouping (summary mode)
    # 🔹 Final Grouping + Detail Logic
    # 🔹 Final Grouping + Detail Logic
    if group_by:
        if not isinstance(group_by, list):
            group_by = [group_by]

        if je_detail:
            print("🔎 Showing detail per group — no aggregation")
            df_grouped = df.sort_values(group_by + ['Source'])
        else:
            print("🔎 Summarizing per group — applying aggregation")
            df_grouped = df.groupby(group_by + ['Source']).sum(numeric_only=True).reset_index()
    else:
        if je_detail:
            print("🔎 Showing all raw JE detail (no grouping)")
            df_grouped = df.copy()
        else:
            print("🔎 Summarizing entire dataset by Source")
            df_grouped = df.groupby(['Source']).sum(numeric_only=True).reset_index()

    # ✅ Final return
    return df_grouped

# -----------------------------------------------------
# ✅ Run Standalone for Testing
# -----------------------------------------------------
if __name__ == "__main__":
    run_query_from_card(
        card_name="PositionReportBySector",
        portfolio="XYZMutualFund1",
        period_start=pd.to_datetime("2023-01-28"),
        period_end=pd.to_datetime("2023-03-31")
    )
