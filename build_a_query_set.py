import os
#import xlwings as xw
import pandas as pd
from datetime import datetime
import shutil
from openpyxl import load_workbook
from openpyxl.styles import PatternFill
from v_config import BASE_PATH

# Define paths
BASE_PATH = "C:/users/hjmne/pycharmprojects/chest"
POOLTEST_PATH = os.path.join(BASE_PATH, "refdata/pooltest")
GUI_DATA_PATH = os.path.join(BASE_PATH, "gui_data")
INVESTMENT_MASTER_PATH = os.path.join(BASE_PATH, "refdata/investment_master.csv")
PRICES_PATH = os.path.join(BASE_PATH, "refdata/price_master.csv")
FX_RATES_PATH = os.path.join(BASE_PATH, "refdata/fx_master.csv")
BOND_INFO_PATH = os.path.join(BASE_PATH, "refdata/bond_info.csv")
COA_INFO_PATH = os.path.join(BASE_PATH, "refdata/chart_of_accounts.csv")
REPORTS_PATH = os.path.join(BASE_PATH, "reports")

SAVE_MODE = "multiple"  # Options: "single" for one workbook, "multiple" for individual files


def close_all_excel_instances():
    for app in xw.apps:
        app.quit()
    print("Closed all Excel instances.")


def remove_existing_workbook(file_path):
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Removed existing workbook at: {file_path}")
    except Exception as e:
        print(f"Error removing existing workbook: {e}")


def clean_nans(df):
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            df[col].fillna(0, inplace=True)
        elif pd.api.types.is_string_dtype(df[col]):
            df[col].fillna("", inplace=True)
        else:
            df[col].fillna("UNKNOWN", inplace=True)
    return df


import os
import pandas as pd

def retrieve_events(fund, period_start, period_end, save_path=None):
    """
    Retrieve events from the portfolio's CSV file, filter by date, and save the filtered events.

    Args:
        fund (str): The portfolio name (e.g., 'XYZMutualFund1').
        period_start (datetime): Start of the filtering period.
        period_end (datetime): End of the filtering period.
        save_path (str): Optional path to save the filtered events.

    Returns:
        List[Dict]: Filtered events as a list of dictionaries.
    """
    csv_file_path = os.path.join(POOLTEST_PATH, f"{fund}.csv")  # Updated to CSV

    try:
        # ✅ Load data from CSV (instead of JSON)
        events_data = pd.read_csv(csv_file_path)

        # ✅ Clean missing values
        events_data = clean_nans(events_data)

        # ✅ Convert tradedate to datetime
        events_data["tradedate"] = pd.to_datetime(
            events_data["tradedate"], format="%m/%d/%Y:%H:%M:%S", errors="coerce"
        )

        # ✅ Drop rows with invalid dates in "tradedate"
        events_data.dropna(subset=["tradedate"], inplace=True)

        # ✅ Filter by period_start and period_end
        filtered_events = events_data[
            (events_data["tradedate"] >= period_start) & (events_data["tradedate"] <= period_end)
        ]

        # ✅ Save the filtered events to CSV (instead of JSON)
        if save_path is None:
            save_path = os.path.join(BASE_PATH, "reports", f"{fund}_QueriedEvents.csv")

        filtered_events.to_csv(save_path, index=False)
        print(f"✅ Filtered events saved to {save_path}")

        # ✅ Return the filtered data as a list of dictionaries
        return filtered_events.to_dict("records")

    except Exception as e:
        print(f"❌ Error retrieving and saving events from {csv_file_path}: {e}")
        return []

def build_candidates(retrieved_events_records, period_end):
    candidates = {}
    investment_details_list = []
    for event_record in retrieved_events_records:
        tradedate = event_record["tradedate"]
        if tradedate > period_end:
            continue
        investment = event_record["investment"]
        portfolio = event_record["portfolio"]
        key = (portfolio, investment)
        if key not in candidates:
            candidates[key] = tradedate
            investment_info = get_security_info(investment)
            if not investment_info.empty:
                investment_details_list.append(investment_info)
    investment_details_df = pd.concat(investment_details_list, ignore_index=True) if investment_details_list else pd.DataFrame()
    return candidates, investment_details_df


def get_security_info(investment):
    try:
        investment_master = pd.read_csv(INVESTMENT_MASTER_PATH)
        security_info = investment_master[investment_master["Investment"] == investment]
        return security_info if not security_info.empty else pd.DataFrame()
    except FileNotFoundError:
        print("Investment master file not found.")
        return pd.DataFrame()


def fetch_prices_data(candidates, period_end):
    try:
        prices_data = pd.read_csv(PRICES_PATH, parse_dates=["date"])
        filtered_prices = prices_data[(prices_data["ticker"].isin([investment for _, investment in candidates.keys()])) &
                                      (prices_data["date"] <= period_end)]
        return filtered_prices
    except FileNotFoundError:
        print("Prices file not found.")
        return pd.DataFrame()


def fetch_fx_rates_data(period_end):
    try:
        fx_rates_data = pd.read_csv(FX_RATES_PATH, parse_dates=["date"])
        return fx_rates_data[fx_rates_data["date"] <= period_end]
    except FileNotFoundError:
        print("FX rates file not found.")
        return pd.DataFrame()


def fetch_bond_info_data(candidates):
    try:
        bond_info_data = pd.read_csv(BOND_INFO_PATH)
        return bond_info_data[bond_info_data["Investment"].isin([investment for _, investment in candidates.keys()])]
    except FileNotFoundError:
        print("Bond info file not found.")
        return pd.DataFrame()


def fetch_coa_info_data():
    try:
        coa_info_data = pd.read_csv(COA_INFO_PATH)
        return coa_info_data
    except FileNotFoundError:
        print("Chart of Accounts file not found.")
        return pd.DataFrame()


def populate_excel_with_candidates_and_details(candidates, investment_details, period_end, portfolio, events_file_path):
    # Prepend portfolio name with an underscore for sheet and file names
    portfolio_prefix = f"{portfolio}_Queried"

    temp_file_path = os.path.join(GUI_DATA_PATH, f"temp_{portfolio_prefix}consolidated.xlsx")
    if SAVE_MODE == "single":
        remove_existing_workbook(temp_file_path)

    app = xw.App(visible=False)
    try:
        if SAVE_MODE == "single":
            wb = app.books.add()
            wb.save(temp_file_path)

        def save_sheet(sheet_name, data):
            data = data.reset_index(drop=True)
            # Adjust sheet names with portfolio prefix
            prefixed_sheet_name = f"{portfolio_prefix}{sheet_name}"
            if SAVE_MODE == "single":
                sheet = wb.sheets.add(prefixed_sheet_name) if prefixed_sheet_name not in [s.name for s in wb.sheets] else wb.sheets[prefixed_sheet_name]
                sheet.clear()
                sheet.range("A1").value = data
                sheet.range("A1").expand("table").columns.autofit()
                print(f"Populated and auto-fitted {prefixed_sheet_name} sheet.")
            elif SAVE_MODE == "multiple":
                # Adjust file paths with portfolio prefix
                file_path = os.path.join(REPORTS_PATH, f"{portfolio_prefix}{sheet_name}.xlsx")
                remove_existing_workbook(file_path)
                temp_wb = app.books.add()
                temp_sheet = temp_wb.sheets[0]
                temp_sheet.name = prefixed_sheet_name
                temp_sheet.range("A1").value = data
                temp_sheet.range("A1").expand("table").columns.autofit()
                temp_wb.save(file_path)
                temp_wb.close()
                print(f"Saved {prefixed_sheet_name} as an individual workbook at {file_path}.")

        # Save data to sheets/files with portfolio prefix
        save_sheet("InvestmentMaster", investment_details)
        save_sheet("Prices", fetch_prices_data(candidates, period_end))
        save_sheet("FXRates", fetch_fx_rates_data(period_end))
        save_sheet("BondInfo", fetch_bond_info_data(candidates))
        save_sheet("ChartOfAccounts", fetch_coa_info_data())

        # Process events data with portfolio prefix
        events_data = pd.read_csv(events_file_path)
        save_sheet("Events", events_data)

        if SAVE_MODE == "single":
            wb.save(temp_file_path)
            print(f"Workbook saved with input data at {temp_file_path}")

    except Exception as e:
        print(f"Error in populating Excel: {e}")
    finally:
        app.quit()
        print("Excel application closed.")

def copy_events_file_to_gui_data(portfolio):
    source_file_path = os.path.join(POOLTEST_PATH, f"{portfolio}.csv")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    destination_file_path = os.path.join(GUI_DATA_PATH, f"{portfolio}_events_{timestamp}.csv")

    if not os.path.exists(GUI_DATA_PATH):
        os.makedirs(GUI_DATA_PATH)

    try:
        shutil.copyfile(source_file_path, destination_file_path)
        print(f"Copied events file to {destination_file_path}")
    except Exception as e:
        print(f"Error copying events file: {e}")

    return destination_file_path

def inputs_main(portfolio, period_start, period_end):
    # Process the inputs and generate the required files
    events_file_path = copy_events_file_to_gui_data(portfolio)

    retrieved_events_records = retrieve_events(portfolio, period_start, period_end)
    candidates, investment_details = build_candidates(retrieved_events_records, period_end)
    populate_excel_with_candidates_and_details(candidates, investment_details, period_end, portfolio, events_file_path)


if __name__ == "__main__":
    # Accept dynamic inputs from the calling script or command line
    import sys
    from datetime import datetime

    # Example: Provide values through sys.argv for command-line use
    if len(sys.argv) < 4:
        print("Usage: python script_name.py <portfolio> <period_start> <period_end>")
        sys.exit(1)

    portfolio = sys.argv[1]
    period_start = datetime.strptime(sys.argv[2], "%Y-%m-%d")
    period_end = datetime.strptime(sys.argv[3], "%Y-%m-%d")

    # Call the function with the dynamically provided arguments
    inputs_main(portfolio, period_start, period_end)
