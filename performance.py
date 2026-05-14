


#import report
investment_master_path = "C:/Users/hjmne/PycharmProjects/chest/refdata/investment_master.csv"

def merge_investment_master(df, investment_master_path):
    # Load and clean investment master
    inv_master = pd.read_csv(investment_master_path)
    inv_master.columns = inv_master.columns.str.upper()

    # Normalize keys for join
    df["investment"] = df["Investment"].astype(str).str.upper().str.strip()
    inv_master["Investment"] = inv_master["Ticker"].astype(str).str.upper().str.strip()

    # Define which columns to pull from investment master
    merge_columns = ["Ticker", "Analyst", "Sector", "Industry"]  # Adjust as needed
    merge_columns = [col for col in merge_columns if col in inv_master.columns]

    # Merge
    df = pd.merge(df, inv_master[merge_columns],
                  left_on="investment", right_on="ticker", how="left")

    # Clean up
    df.drop(columns=["ticker"], inplace=True, errors="ignore")
    df.columns = [c.strip().upper() for c in df.columns]

    return df

# ✅ Load price data (you can modify the path or pass it in externally)
#from utilities import load_price_data_as_rows

#price_raw_df = load_price_data_as_rows("C:/Users/hjmne/PycharmProjects/chest/refdata/price_master.csv")


def calculate_and_report_performance(portfolio_name, journal_entries):
    """Calculate and report performance."""
#    compute_daily_twr(journal_entries, 'portfolio', portfolio_name)
    create_performance_sheets(journal_entries, portfolio_name, historical_data_dir="C:/Users/hjmne/PycharmProjects/chest/historical_indices")
# Given functions...

def fill_blue_row_perf(ws, row_idx):
    """Fill a specific row in a worksheet with blue color."""
    fill = PatternFill(start_color="ADD8E6", end_color="ADD8E6", fill_type="solid")
    for cell in ws[row_idx]:
        cell.fill = fill


def check_for_duplicate_columns(df1, df2):
    """
    Check for duplicate columns between two DataFrames and raise an error if any are found.

    Args:
    df1 (pd.DataFrame): The first DataFrame.
    df2 (pd.DataFrame): The second DataFrame.

    Raises:
    ValueError: If duplicate columns are found.
    """
    # Get columns from both DataFrames
    df1_columns = set(df1.columns)
    df2_columns = set(df2.columns)

    # Find the intersection of columns
    duplicate_columns = df1_columns.intersection(df2_columns)

    if duplicate_columns:
        raise ValueError(
            f"Duplicate columns found: {duplicate_columns}. Please ensure there are no duplicate columns before merging.")
    else:
        print("No duplicate columns found. Safe to merge.")


def apply_perf_formatting(excel_file_path):
    workbook = openpyxl.load_workbook(excel_file_path)

    for sheet_name in ['Detail', 'Summary']:
        if sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]

            # Example: Freeze the first row
            sheet.freeze_panes = sheet['A2']

            # Example: Set column widths based on the content
            for column in sheet.columns:
                max_length = max((len(str(cell.value)) for cell in column if cell.value), default=0) + 2
                adjusted_width = (max_length + 2) * 1.1
                column_letter = get_column_letter(column[0].column)
                sheet.column_dimensions[column_letter].width = adjusted_width

            subtotal_column_index = 1  # Adjust as per your file

            # Iterate through rows and apply bold font to subtotal rows
            for row in sheet.iter_rows(min_row=2):  # Assuming the first row is headers
                if row[subtotal_column_index - 1].value == 'Subtotal':
                    for cell in row:
                        cell.font = Font(bold=True)

            # Apply zebra striping (assuming 'fill_blue_row' is a predefined function)
            for i, row in enumerate(sheet.iter_rows(min_row=2), start=2):
                if i % 2 == 0:  # Apply to every even row
                    for cell in row:
                        cell.fill = PatternFill(start_color='ADD8E6', end_color='ADD8E6', fill_type='solid')

            num_format = '#,##0.00'
            for row in sheet.iter_rows():
                for cell in row:
                    if isinstance(cell.value, int) or isinstance(cell.value, float):
                        cell.number_format = num_format
            # Save the changes to the workbook
            workbook.save(excel_file_path)

            # Apply any other specific formatting needed for performance sheets
            # ...

    workbook.save(excel_file_path)


def style_perf_report(je_data):
    """Style the performance report using specific functions."""
    # Convert the DataFrame to an openpyxl worksheet
    wb = openpyxl.Workbook()
    ws = wb.active = 0
    for r_idx, row in enumerate(je_data.values, 1):
        for c_idx, value in enumerate(row, 1):
            ws.cell(row=r_idx, column=c_idx, value=value)

    # Apply styles
    for i, row in enumerate(ws.iter_rows(min_row=2), start=2):
        if i % 2 == 0:  # If the row number is even
            fill_blue_row_perf(ws, i)
        if ws.cell(row=i, column=1).value.startswith('Subtotal'):
            report.underline_row(ws, row)
            report.bold_row(ws, row)

    report.format_numbers(ws)
    report.autosize_columns(ws)

    return ws  # Return the styled worksheet

import pandas as pd

def fetch_and_map_groupings(journal_entries, investment_master_path, coa_path):
    # Load the investment master and chart of accounts data
    investment_master_df = pd.read_csv(investment_master_path)
    coa_df = pd.read_csv(coa_path)

    # Assume that 'investment' and 'SystemName' are the primary keys to map
    investment_groupings = investment_master_df[['Investment', 'Asset_Class', 'Industry',  'Sector']]
    coa_groupings = coa_df[['SystemName', 'SystemType', 'Group1', 'BSGroup', 'PerformanceCategory']]

    # Map the groupings to the journal entries DataFrame
    journal_entries = journal_entries.merge(investment_groupings, on='Investment', how='left')
    journal_entries = journal_entries.merge(coa_groupings, left_on='financial_account', right_on='SystemName', how='left')

    return journal_entries

# Example usage
# journal_entries_df = pd.DataFrame(journal_entries)  # Convert your journal_entries to a DataFrame
# investment_master_path = 'path/to/investment_master.csv'
# coa_path = 'path/to/chart_of_accounts.csv'

import pandas as pd

def extract_prior_index(prior_df, level):
    if prior_df.empty:
        return pd.DataFrame(columns=[level, 'Prior_Index_Local', 'Prior_Index_Book'])

    prior_index = (
        prior_df
        .sort_values("ibor_date")
        .groupby(level)
        .last()[['Index_Local', 'Index_Book']]
        .reset_index()
        .rename(columns={
            'Index_Local': 'Prior_Index_Local',
            'Index_Book': 'Prior_Index_Book'
        })
    )

    return prior_index

def compute_capital_flows(je_data, level):

    external_accounts = [
        "ContributedCost",
        # add more if needed
    ]

    ext_flows = je_data[
        je_data["financial_account"].isin(external_accounts)
    ][[
        level,
        "ibor_date",
        "local",
        "book"
    ]].copy()

    ext_flows = (
        ext_flows.groupby([level, "ibor_date"], as_index=False)
        .agg({"local": "sum", "book": "sum"})
    )

    ext_flows.rename(columns={
        "local": "External_CF_Local",
        "book": "External_CF_Book"
    }, inplace=True)

    return ext_flows

def compute_opening_cash_flows_investments(investment_master, je_data, level):
    currencies = ['USD', 'AUD', 'GBP', 'EUR', 'JPY']
    valid_accounts = ['Cost']

    # Define grouping columns based on the level
    #group_by_cols = [level, 'ibor_date'] if level != 'ibor_date' else ['ibor_date']
    group_by_cols = [level, 'ibor_date']

    # For non-currencies, apply the 'Book' > 0 filter.- For currencies, just check the valid accounts.

    # Conditions for filtering rows
    condition1 = (~je_data['investment'].isin(currencies) & (je_data['book'] > 0))
    condition2 = je_data['financial_account'].isin(valid_accounts)

    # Combine conditions
    opening_flows = je_data[condition1 & condition2]

    opening_flows = opening_flows.groupby(group_by_cols).agg(
        {'local': 'sum', 'book': 'sum'}).reset_index()

    # Rename columns for clarity
    opening_flows.rename(columns={'local': 'Open_CF_Local', 'book': 'Open_CF_Book'}, inplace=True)

    return opening_flows

def compute_cash_flows_currencies(investment_master, je_data, level):
    currencies = ['USD', 'AUD', 'GBP', 'EUR', 'JPY']
    valid_accounts = ['Cost', 'Payable', 'Receivable', 'DividendsReceivable', 'DividendsPayable',
                      'AccruedInterestPayable', 'AccruedInterestReceivable', 'DividendsReceivable',
                      'DividendsPayable', 'ExpensesPayable', 'InterestPayable', 'InterestReceivable']

    # Define grouping columns based on the level
    group_by_cols = [level,'ibor_date'] if level != 'ibor_date' else ['ibor_date']

    # For non-currencies, apply the 'Book' > 0 filter. For currencies, just check the valid accounts.

    # Conditions for filtering rows
    condition1 = je_data['investment'].isin(currencies)
    condition2 = je_data['financial_account'].isin(valid_accounts)

    # Combine conditions
    currency_flows = je_data[condition1 & condition2]

    currency_flows = currency_flows.groupby(group_by_cols).agg(
        {'local': 'sum', 'book': 'sum'}).reset_index()

    # Rename columns for clarity
    currency_flows.rename(columns={'local': 'Currency_Flows_Local', 'book': 'Currency_Flows_Book'}, inplace=True)

    return currency_flows

def compute_closing_cash_flows_for_investments(investment_master, je_data, level):
    currencies = ['USD', 'AUD', 'GBP', 'EUR', 'JPY']
    # Condition 1
    condition1 = je_data['financial_account'].isin(['PriceGainInvestment', 'FXGainInvestment'])
    # Condition 2
    condition2 = (je_data['financial_account'] == 'Cost') & (je_data['book'] < 0) & (je_data['ls'] == 'l')
    # Condition 3
    condition3 = (je_data['financial_account'] == 'Cost') & (je_data['book'] > 0) & (je_data['ls'] == 's')
    # Condition 4
    condition4 = ~je_data['investment'].isin(currencies)

    # Combine conditions
    closing_flows = je_data[(condition1 | condition2 | condition3) & condition4]

    # Group by Investment, IBOR Date, and Tax Date
    closing_flows_agg = closing_flows.groupby([level, 'ibor_date']).agg(
        {'local': 'sum', 'book': 'sum'}).reset_index()

    # Rename columns for clarity
    closing_flows_agg.rename(columns={'local': 'Close_CF_Local', 'book': 'Close_CF_Book'}, inplace=True)

    return closing_flows_agg

def compute_income(investment_master, je_data, level):


    print(je_data['financial_account'].unique())

# Must use a bitwise | as Python evaluates the expression in aggregate if OR is used!!!
    income_entries = je_data[(je_data['financial_account'] == 'DividendReceipt') |
                         (je_data['financial_account'] == 'FXGainCurrency') |
                         (je_data['financial_account'] == 'FXGainTradeSettle') |
                         (je_data['financial_account'] == 'AccruedInterestReceipt') |
                         (je_data['financial_account'] == 'AccruedInterestIncome') |
                         (je_data['financial_account'] == 'DividendExpense')]

    print(income_entries.head())
    # Group by both 'Investment' and 'IBOR Date' and flip the sign on the sum
    income_je_data = income_entries.groupby([level, 'ibor_date'])[['local', 'book']].sum().reset_index()

    # Flip the sign
    income_je_data[['local', 'book']] *= -1

    income_je_data.rename(columns={'local': 'Income_Local', 'book': 'Income_Book'}, inplace=True)

    return income_je_data


def get_prior_emv(df, value_col, level):
    # This version looks for the prior EMV based on date, not row position
    from pandas.tseries.offsets import Day
    df = df.copy()
    df['prior_date'] = df['ibor_date'] - Day(1)

    keys = level if isinstance(level, list) else [level]

    # Create lookup DataFrame for prior day's EMV
    emv_prior = df[keys + ['ibor_date', value_col]].copy()
    emv_prior.rename(columns={
        'ibor_date': 'prior_date',
        value_col: f'Prior_{value_col}'
    }, inplace=True)

    # Merge onto main frame
    df = pd.merge(df, emv_prior, on=keys + ['prior_date'], how='left')

    return df[f'Prior_{value_col}']


def compute_daily_twr(journal_entries, level, period_key):
    import pandas as pd
    import numpy as np



    # -----------------------------------------
    # STEP 1: Build DataFrame
    # -----------------------------------------
    df = pd.DataFrame([je.to_dict() for je in journal_entries])

    if df.empty:
        return pd.DataFrame(), None, None

    df["ibor_date"] = pd.to_datetime(df["ibor_date"])

    # -----------------------------------------
    # STEP 2: COMPUTE CF + INCOME (YOUR FUNCTIONS)
    # -----------------------------------------
    ext_cf = compute_capital_flows(df, level)
    open_cf = compute_opening_cash_flows_investments(None, df, level)
    curr_cf = compute_cash_flows_currencies(None, df, level)
    close_cf = compute_closing_cash_flows_for_investments(None, df, level)

    income_df = compute_income(None, df, level)

    # Combine CF components
    cf = ext_cf.merge(open_cf, on=[level, "ibor_date"], how="outer") \
        .merge(curr_cf, on=[level, "ibor_date"], how="outer") \
        .merge(close_cf, on=[level, "ibor_date"], how="outer")

    cf = cf.fillna(0.0)

    cf["CF_Local"] = (
            cf.get("External_CF_Local", 0.0)
            + cf.get("Open_CF_Local", 0.0)
            + cf.get("Currency_Flows_Local", 0.0)
            + cf.get("Close_CF_Local", 0.0)
    )

    cf["CF_Book"] = (
            cf.get("External_CF_Book", 0.0)
            + cf.get("Open_CF_Book", 0.0)
            + cf.get("Currency_Flows_Book", 0.0)
            + cf.get("Close_CF_Book", 0.0)
    )

    # -----------------------------------------
    # STEP 3: AGGREGATE MARKET VALUES (UNCHANGED)
    # -----------------------------------------
    agg = (
        df
        .groupby([level, "ibor_date", "financial_account"], as_index=False)
        .agg({
            "local": "sum",
            "book": "sum",
            "quantity": "sum"
        })
    )

    pivot = agg.pivot_table(
        index=[level, "ibor_date"],
        columns="financial_account",
        values=["local", "book", "quantity"],
        aggfunc="sum"
    ).fillna(0.0)

    pivot.columns = ["_".join(col) for col in pivot.columns]
    pivot = pivot.reset_index()

    mv = pivot.copy()

    # -----------------------------------------
    # STEP 4: MARKET VALUE + QUANTITY (UNCHANGED)
    # -----------------------------------------
    mv["EMV_Local"] = mv.get("local_MarketVal", 0.0)
    mv["EMV_Book"] = mv.get("book_MarketVal", 0.0)
    mv["quantity"] = mv.get("quantity_MarketVal", 0.0)

    # -----------------------------------------
    # STEP 5: MERGE CF + INCOME INTO STATE
    # -----------------------------------------
    mv = mv.merge(
        cf[[level, "ibor_date", "CF_Local", "CF_Book"]],
        on=[level, "ibor_date"],
        how="left"
    )

    mv = mv.merge(
        income_df[[level, "ibor_date", "Income_Local", "Income_Book"]],
        on=[level, "ibor_date"],
        how="left"
    )

    mv["CF_Local"] = mv["CF_Local"].fillna(0.0)
    mv["CF_Book"] = mv["CF_Book"].fillna(0.0)

    mv["Income_Local"] = mv["Income_Local"].fillna(0.0)
    mv["Income_Book"] = mv["Income_Book"].fillna(0.0)

    # -----------------------------------------
    # STEP 6: SORT
    # -----------------------------------------
    mv = mv.sort_values([level, "ibor_date"])

    # -----------------------------------------
    # STEP 7: BMV
    # -----------------------------------------
    mv["BMV_Local"] = mv.groupby(level)["EMV_Local"].shift(1).fillna(0.0)
    mv["BMV_Book"] = mv.groupby(level)["EMV_Book"].shift(1).fillna(0.0)

    # -----------------------------------------
    # STEP 8: TWR
    # -----------------------------------------
    mv["TWR_Local"] = np.where(
        mv["BMV_Local"] != 0,
        (mv["EMV_Local"] - mv["BMV_Local"] - mv["CF_Local"]) / mv["BMV_Local"],
        0.0
    )

    mv["TWR_Book"] = np.where(
        mv["BMV_Book"] != 0,
        (mv["EMV_Book"] - mv["BMV_Book"] - mv["CF_Book"]) / mv["BMV_Book"],
        0.0
    )

    # -----------------------------------------
    # STEP 9: INDEX
    # -----------------------------------------
    mv["Period_Index_Local"] = (
        (1 + mv["TWR_Local"])
        .groupby(mv[level])
        .cumprod()
    )

    mv["Period_Index_Book"] = (
        (1 + mv["TWR_Book"])
        .groupby(mv[level])
        .cumprod()
    )

    # -----------------------------------------
    # STEP 10: CUMULATIVE
    # -----------------------------------------
    mv["CumCF_Local"] = mv.groupby(level)["CF_Local"].cumsum()
    mv["CumCF_Book"] = mv.groupby(level)["CF_Book"].cumsum()

    mv["CumInc_Local"] = mv.groupby(level)["Income_Local"].cumsum()
    mv["CumInc_Book"] = mv.groupby(level)["Income_Book"].cumsum()

    # -----------------------------------------
    # FINAL OUTPUT
    # -----------------------------------------
    cols = [
        level,
        "ibor_date",
        "quantity",
        "BMV_Local", "EMV_Local",
        "CF_Local", "CumCF_Local",
        "Income_Local", "CumInc_Local",
        "TWR_Local", "Period_Index_Local",
        "BMV_Book", "EMV_Book",
        "CF_Book", "CumCF_Book",
        "Income_Book", "CumInc_Book",
        "TWR_Book", "Period_Index_Book"
    ]

    mv = mv[cols]

    return mv, None, None

import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)


# ✅ 1. Load benchmark returns (keep in decimal form)

import pandas as pd

def load_historical_data(historical_data_dir):
    indices = {}
    index_files = {
        "S&P 500": "SPY_historical.csv",
        "NASDAQ": "QQQ_historical.csv",
        "Russell 2000": "IWM_historical.csv",
        "IEF30YrTreas": "TLT_historical.csv"
    }

    for name, filename in index_files.items():
        file_path = os.path.join(historical_data_dir, filename)
        if os.path.exists(file_path):
            print(f"📂 Loading saved historical data for {name}...")
            df = pd.read_csv(file_path, index_col=0, parse_dates=True)
            if name in df.columns:
                indices[name] = df[name].fillna(0) / 100  # scale to decimal returns
            else:
                print(f"⚠️ Column '{name}' not found in {filename}. Found: {df.columns.tolist()}")
                indices[name] = None
        else:
            print(f"⚠️ Missing file for {name}: {file_path}")
            indices[name] = None

    return indices

# ✅ 2. Main performance computation
def compute_risk_adjusted_trend_alpha_row(group_df: pd.DataFrame,
                                          benchmark_series: pd.Series,
                                          beta: float,
                                          level_value) -> dict:
    try:
        start_date = group_df['ibor_date'].min()
        end_date = group_df['ibor_date'].max()
        index_series = benchmark_series.loc[start_date:end_date].sort_index()
        port_series = group_df.set_index('ibor_date')['TWR_Book'].sort_index()

        cumulative = (1 + index_series).cumprod()
        peak = cumulative.cummax()
        drawdown = cumulative / peak - 1
        trough_idx = drawdown.idxmin()
        peak_idx = cumulative.loc[:trough_idx].idxmax()
        drawdown_window = index_series.loc[peak_idx:trough_idx]

        if drawdown_window.empty or peak_idx == trough_idx:
            return {
                "Drawdown_Window_Start": None,
                "Drawdown_Window_End": None,
                "SP500_Drawdown_Return": None,
                "Portfolio_Drawdown_Return": None,
                "Expected_Portfolio_Return": None,
                "Risk_Adjusted_Trend_Alpha": None
            }

        market_return = (1 + drawdown_window).prod() - 1
        portfolio_window = port_series.loc[peak_idx:trough_idx]
        portfolio_return = (1 + portfolio_window).prod() - 1
        expected_return = beta * market_return
        alpha = portfolio_return - expected_return

        return {
            "Drawdown_Window_Start": peak_idx,
            "Drawdown_Window_End": trough_idx,
            "SP500_Drawdown_Return": market_return,             # raw decimal
            "Portfolio_Drawdown_Return": portfolio_return,      # raw decimal
            "Expected_Portfolio_Return": expected_return,       # raw decimal
            "Risk_Adjusted_Trend_Alpha": alpha                  # raw decimal
        }

    except Exception as e:
        print(f"❌ Drawdown calc failed for {level_value}: {e}")
        return {
            "Drawdown_Window_Start": None,
            "Drawdown_Window_End": None,
            "SP500_Drawdown_Return": None,
            "Portfolio_Drawdown_Return": None,
            "Expected_Portfolio_Return": None,
            "Risk_Adjusted_Trend_Alpha": None
        }

def create_performance_sheets(journal_entries,
                              period_start, period_end,
                              portfolio_name=None, filters=None,
                              gw=None,
                              historical_data_dir="C:/Users/hjmne/PycharmProjects/chest/historical_indices"):
    valid_levels = {
        'portfolio': 'portfolio',
        'investment': 'investment',
        'analyst': 'Analyst',
        'sector': 'Sector',
        'industry': 'Industry',
        'asset_class': 'Asset_Class'
    }

    levels = filters
    if levels:
        normalized_levels = []
        for lvl in extract_filter_value(levels):
            lvl_key = lvl.strip().lower()
            if lvl_key in valid_levels:
                normalized_levels.append(valid_levels[lvl_key])
            else:
                print(f"⚠️ Unknown level '{lvl}' — skipping.")
        levels = normalized_levels
    else:
        levels = ['portfolio', 'investment', 'Analyst', 'Asset_Class', 'Sector', 'Industry']

    results = {}
    for level in levels:
        print(f"📈 Computing TWR for level: {level}")
        try:
            twr_result, _, _ = compute_daily_twr(
                journal_entries,
                period_start,
                period_end,
                level,
                level,
                include_local_currency=False
            )

            if twr_result.empty:
                print(f"⚠️ Empty result for {level}. Skipping.")
                continue

            detail_df = twr_result.drop(
                #  detail_df = detail_df.drop(
                columns=[
                    'EMV_Local', 'BMV_Local', 'Open_CF_Local',
                    'Currency_Flows_Local', 'Close_CF_Local', 'Income_Local',
                    'Investment_Changed', 'EMV_Local_Diff', 'EMV_Book_Diff',
                    'Previous_EMV_Local', 'Previous_EMV_Book', 'TWR_Local',
                    'LocalToDate', 'BookToDate', 'TWR_Local_Percent',
                    'TWR_Book_Percent', 'LocalToDate_Percent',
                    'Category_Flows_Local'
                ],
                errors='ignore'
            )

            twr_result = twr_result.drop(
                columns=[
                    'EMV_Local', 'BMV_Local', 'Open_CF_Local', 'Currency_Flows_Local', 'Close_CF_Local',
                    'Income_Local', 'Investment_Changed', 'EMV_Local_Diff', 'EMV_Book_Diff',
                    'Previous_EMV_Local', 'Previous_EMV_Book', 'TWR_Local',
                    'LocalToDate', 'BookToDate', 'TWR_Local_Percent', 'TWR_Book_Percent',
                    'LocalToDate_Percent', 'Category_Flows_Local'
                ],
                errors='ignore'
            )

            indices = load_historical_data(historical_data_dir)

            for name in indices.keys():
                if name in twr_result.columns:
                    twr_result = twr_result.drop(columns=[name])

            for name, series in indices.items():
                if series is not None:
                    twr_result = pd.merge(
                        twr_result,
                        series.rename(name),
                        left_on='ibor_date',
                        right_index=True,
                        how='left'
                    )
            # else:
            #         create_summary_and_analytics(twr_result,indices,level)

            if level.lower() == "investment":
                summary_df = create_summary_and_analytics_enhanced(twr_result, indices, level=level)
            else:
                summary_df = create_summary_and_analytics(twr_result, indices, level=level)


            # Enrich Investment summary with Analyst, Sector, Industry, Asset_Class
            if level.lower() == 'investment' and 'investment' in summary_df.columns:
                inv_master = pd.read_csv(investment_master_path)
                inv_master.columns = [col.strip().upper() for col in inv_master.columns]

                enrich_cols = ['TICKER', 'ANALYST', 'SECTOR', 'INDUSTRY', 'ASSET_CLASS']
                available_cols = [col for col in enrich_cols if col in inv_master.columns]

                if 'TICKER' in available_cols:
                    summary_df = summary_df.merge(
                        inv_master[available_cols],
                        left_on='investment', right_on='TICKER',
                        how='left'
                    )
                    summary_df.drop(columns=['TICKER'], inplace=True, errors='ignore')
                    # ✅ Force grouping level column (like Analyst) to appear first
                    if level in summary_df.columns:
                        cols = [level] + [c for c in summary_df.columns if c != level]
                        summary_df = summary_df[cols]

                    # ✅ Move grouping level (e.g., Analyst, Sector) to the front

            results[f"{level}ReturnsSum"] = summary_df
            results[f"{level}ReturnsDet"] = detail_df


        except Exception as e:
            import traceback
            print(f"❌ Error computing performance for level '{level}':")
            traceback.print_exc()

    return results

# ✅ 3. Enhanced analytics (inputs in decimal, convert to % for display at the end)
def create_summary_and_analytics(twr_result, indices, level):
    # Step 1: Convert percentages to decimals and handle NaN
    for col in ["S&P 500", "NASDAQ", "Russell 2000", "IEF30YrTreas"]:
        if col in twr_result.columns:
            twr_result[col] = twr_result[col] / 100  # Convert to decimal
            twr_result[col] = twr_result[col].fillna(0)  # Replace NaN with 0

    # Step 2: Perform aggregations for chain-linking
    summary = twr_result.groupby(level).agg(
        BMV_Book=('BMV_Book', 'first'),
        EMV_Book=('EMV_Book', 'last'),
        Income_Book=('Income_Book', 'sum'),
        Book_To_Date_Percent=('BookToDate_Percent', 'last'),
        SP500=('S&P 500', lambda x: (np.prod(1 + x) - 1) * 100),
        NASDAQ=('NASDAQ', lambda x: (np.prod(1 + x) - 1) * 100),
        Russell2000=('Russell 2000', lambda x: (np.prod(1 + x) - 1) * 100),
        IEF30YrTreas=('IEF30YrTreas', lambda x: (np.prod(1 + x) - 1) * 100),
    ).reset_index()

    # Step 3: Initialize analytics dictionary to store aggregated results
    analytics = {level_value: {'Beta': {}, 'R²': {}} for level_value in summary[level].unique()}

    # Calculate Beta and R² for each index and aggregate for each level
    try:
        grouped_returns = twr_result.groupby(level)
        for level_value, group in grouped_returns:
            portfolio_returns = group.groupby('ibor_date')['TWR_Book'].sum()
            min_date, max_date = portfolio_returns.index.min(), portfolio_returns.index.max()

            for index_name, index_data in indices.items():
                index_data = index_data.loc[min_date:max_date]
                aligned_data = pd.concat([portfolio_returns, index_data], axis=1, join='inner').dropna()

                if aligned_data.empty:
                    continue

                portfolio_aligned, index_aligned = aligned_data.iloc[:, 0], aligned_data.iloc[:, 1]
                beta, r_squared = np.nan, np.nan
                try:
                    beta = np.cov(portfolio_aligned, index_aligned)[0, 1] / np.var(index_aligned)
                    correlation = np.corrcoef(portfolio_aligned, index_aligned)[0, 1]
                    r_squared = correlation ** 2
                except FloatingPointError:
                    pass

                # Store results in the analytics dictionary
                analytics[level_value]['Beta'][index_name] = beta
                analytics[level_value]['R²'][index_name] = r_squared

        # Flatten analytics data and merge into summary
        for level_value in analytics.keys():
            avg_beta = np.nanmean(list(analytics[level_value]['Beta'].values()))
            avg_r_squared = np.nanmean(list(analytics[level_value]['R²'].values()))
            summary.loc[summary[level] == level_value, 'Beta'] = avg_beta
            summary.loc[summary[level] == level_value, 'R²'] = avg_r_squared
        # Add calculated columns
        summary['Alpha'] = summary['Book_To_Date_Percent'] - (summary['Beta'] * summary['SP500'])

    except Exception as e:
        print(f"Error during analytics calculation: {e}")

    return summary

def create_summary_and_analytics_enhanced(twr_result: pd.DataFrame, indices: dict, level: str) -> pd.DataFrame:
    if level not in twr_result.columns:
        print(f"⚠️ Column '{level}' not in TWR result. Attempting merge from investment_master.")
        from pathlib import Path
        master_path = Path("C:/Users/hjmne/PycharmProjects/chest/refdata/investment_master.csv")
        if master_path.exists():
            master = pd.read_csv(master_path)
            if 'Investment' in master.columns and level in master.columns:
                master = master[['Investment', level]].drop_duplicates()
                twr_result = pd.merge(
                    twr_result,
                    master,
                    how="left",
                    left_on="investment",
                    right_on="Investment"
                )
                print(f"✅ Successfully merged '{level}' column from investment_master.")
            else:
                raise ValueError(f"❌ Cannot merge '{level}' — missing columns in investment_master.")
        else:
            raise FileNotFoundError(f"❌ investment_master.csv not found at {master_path}")

    twr_result = twr_result.fillna(0)

    summary = twr_result.groupby(level).agg(
        BMV_Book=('BMV_Book', 'first'),
        EMV_Book=('EMV_Book', 'last'),
        Income_Book=('Income_Book', 'sum'),
        BookToDate_Percent=('BookToDate_Percent', 'last'),
        SP500=('S&P 500', lambda x: (np.prod(1 + x) - 1)),
        NASDAQ=('NASDAQ', lambda x: (np.prod(1 + x) - 1)),
        Russell2000=('Russell 2000', lambda x: (np.prod(1 + x) - 1)),
        IEF30YrTreas=('IEF30YrTreas', lambda x: (np.prod(1 + x) - 1)),
        TWR_Book=('TWR_Book', lambda x: (np.prod(1 + x) - 1)),
        Volatility=('TWR_Book', lambda x: np.std(x) * np.sqrt(252))
    ).reset_index()

    # Initialize
    analytics = {lv: {} for lv in summary[level].unique()}
    if level not in twr_result.columns:
        raise ValueError(f"❌ Column '{level}' not found in TWR result columns: {twr_result.columns.tolist()}")

    grouped = twr_result.groupby(level)

    for lv, group in grouped:
        port = group.groupby('ibor_date')['TWR_Book'].sum()
        min_date, max_date = port.index.min(), port.index.max()
        beta_list = []
        r2_list = []
        te_list = []
        up_list = []
        down_list = []
        alpha_list = []

        for idx_name, idx_series in indices.items():
            idx = idx_series.loc[min_date:max_date]
            aligned = pd.concat([port, idx], axis=1, join='inner').dropna()
            if aligned.empty:
                continue
            p, b = aligned.iloc[:, 0], aligned.iloc[:, 1]
            beta = np.cov(p, b)[0, 1] / np.var(b)
            corr = np.corrcoef(p, b)[0, 1]
            r2 = corr ** 2
            te = np.std(p - b) * np.sqrt(252)
            up = np.mean(p[b > 0]) / np.mean(b[b > 0]) if np.any(b > 0) else np.nan
            down = np.mean(p[b < 0]) / np.mean(b[b < 0]) if np.any(b < 0) else np.nan
            slope, intercept = np.polyfit(b, p, 1)
            alpha = intercept * 252

            beta_list.append(beta)
            r2_list.append(r2)
            te_list.append(te)
            up_list.append(up)
            down_list.append(down)
            alpha_list.append(alpha)

        summary.loc[summary[level] == lv, 'Beta'] = np.nanmean(beta_list)
        summary.loc[summary[level] == lv, 'R²'] = np.nanmean(r2_list)
        summary.loc[summary[level] == lv, 'Tracking_Error'] = np.nanmean(te_list)
        summary.loc[summary[level] == lv, 'Upside_Capture'] = np.nanmean(up_list)
        summary.loc[summary[level] == lv, 'Downside_Capture'] = np.nanmean(down_list)
        summary.loc[summary[level] == lv, 'Alpha'] = np.nanmean(alpha_list)
        ir = (np.nanmean(alpha_list) / np.nanmean(te_list)) if np.nanmean(te_list) else np.nan
        summary.loc[summary[level] == lv, 'Information_Ratio'] = ir

        # 🎯 Inject Risk-Adjusted Trend Alpha
        if 'S&P 500' in indices and not indices['S&P 500'].empty:
            drawdown_result = compute_risk_adjusted_trend_alpha_row(
                group_df=group,
                benchmark_series=indices['S&P 500'],
                beta=np.nanmean(beta_list),
                level_value=lv
            )
            for k, v in drawdown_result.items():
                summary.loc[summary[level] == lv, k] = v

    # Final display scaling
    for col in [
        'SP500', 'NASDAQ', 'Russell2000', 'IEF30YrTreas',
        'TWR_Book', 'Alpha', 'R²', 'Tracking_Error',
        'Upside_Capture', 'Downside_Capture', 'Volatility',
        'Max_Drawdown', 'Risk_Adjusted_Trend_Alpha'
    ]:
        if col in summary.columns:
            summary[col] *= 100

    summary['Sharpe_Ratio'] = (summary['BookToDate_Percent'] / 100 - 0.02) / summary['Volatility']
    summary['Value_Added_vs_SP500'] = summary['BookToDate_Percent'] - summary['SP500']
    summary['Pct_Of_Total_EMV'] = summary['EMV_Book'] / summary['EMV_Book'].sum()

    return summary

def extract_filter_value(expr):
    import ast

    # Handle dictionary-style input: {"LEVEL": "in ['Investment', 'Analyst']"}
    if isinstance(expr, dict):
        expr = expr.get("LEVEL", "")

    if isinstance(expr, str):
        expr = expr.strip()

        # Handle equality: "== 'Analyst'"
        if expr.startswith("=="):
            val = expr[2:].strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            return [val]

        # Handle in-list: "in ['Investment', 'Analyst']"
        if expr.lower().startswith("in"):
            try:
                list_expr = expr[2:].strip()
                parsed = ast.literal_eval(list_expr)
                return parsed if isinstance(parsed, list) else []
            except Exception as e:
                print(f"⚠️ Failed to parse list in LEVEL filter: {e}")
                return []

    return []

def sanitize_filename(filename):
    """Sanitize the filename by removing invalid characters."""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)


import os
import zipfile
import pandas as pd
import numpy as np

