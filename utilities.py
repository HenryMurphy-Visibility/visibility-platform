print("IMPORTING UTILITIES")

import re



# Define the base path
BASE_PATH = "C:/users/hjmne/pycharmprojects/chest"

# Define a global switch for file format
USE_JSON = True  # Set to True for JSON, False for CSV

# Define the directory and the CSV file patterns to search for
chest_directory = BASE_PATH  # Use BASE_PATH for the chest directory
csv_files = [
    rf'{BASE_PATH}/refdata/:price_master\.csv',
    rf'{BASE_PATH}/refdata/:fx_master\.csv',
    rf'{BASE_PATH}/refdata/:bond_info\.csv',
    rf'{BASE_PATH}/refdata/:investment_master\.csv',
    rf'{BASE_PATH}/refdata/:chart_of_accounts\.csv',
    rf'{BASE_PATH}/refdata/pooltest/[^\s]+\.csv'  # Matches any portfolio CSV file in the pooltest directory
]

# Compile regular expressions for the CSV file patterns
csv_patterns = [re.compile(pattern) for pattern in csv_files]

# List to store results
results = []

# file: utils/logger.py
import inspect

# ============================================================
# 🔹 File Paths
# ============================================================
SYN_REGISTRY_PATH = "C:/users/hjmne/pycharmprojects/chest/refdata/synthetic_registry.csv"
investment_MASTER_PATH = "C:/users/hjmne/pycharmprojects/chest/refdata/investment_master.csv"
BOND_INFO_PATH = "C:/users/hjmne/pycharmprojects/chest/refdata/bond_info.csv"


# ============================================================
# 🔹 Helpers (no-clearing, incremental upsert)
# ============================================================
def _ensure_df(path, columns):
    import os, pandas as pd
    if os.path.exists(path):
        df = pd.read_csv(path)
        # guarantee columns exist; preserve extras if present
        for c in columns:
            if c not in df.columns:
                df[c] = ""
        return df
    else:
        return pd.DataFrame(columns=columns)

def _safe_set_aif(space, investment, mapping: dict):
    """Incrementally upsert AIF for a single investment into the live space."""
    # We assume a setter exists. Try common spellings defensively.
    for k, v in mapping.items():
        try:
            space.set_information_field(investment, "AIF", k, v)
        except AttributeError:
            try:
                space.set_information(investment, "AIF", k, v)
            except AttributeError:
                # Last-resort: some spaces expose a dict-like API.
                if hasattr(space, "information"):
                    space.information.setdefault(investment, {}).setdefault("AIF", {})[k] = v
#

# ============================================================
# 🔹 Synthetic investment Instantiation (fixed, incremental)
#    - No clearing
#    - Append to CSVs
#    - Immediately inject AIF into live space
# ============================================================
# def instantiate_synthetic_investment_if_needed(investment_id, tranid, terms, space):
#     """
#     If 'investment_id' is a template in synthetic_registry.csv, create an instance
#     (optionally suffixed by tranid), append to IM/BondInfo, and upsert AIF in-memory.
#
#     Returns the instantiated id (or the original id if no instantiation is needed).
#     """
#     import os, pandas as pd
#     from datetime import datetime
#
#     if not os.path.exists(SYN_REGISTRY_PATH):
#         # No registry; nothing to do.
#         return investment_id
#
#     reg = pd.read_csv(SYN_REGISTRY_PATH)
#     # Be tolerant of column naming; normalize
#     cols = {c.lower(): c for c in reg.columns}
#     sid_col = cols.get("synthetic_id", "synthetic_id")
#     itype_col = cols.get("investment_type", cols.get("type", "investment_type"))
#     desc_col = cols.get("description", "description")
#     curr_col = cols.get("currency", "currency")
#     princ_col = cols.get("principal", "principal")
#     rate_col = cols.get("rate", "rate")
#     freq_col = cols.get("frequency", "frequency")
#     mty_col = cols.get("maturity_date", "maturity_date")
#     use_ticket_col = cols.get("use_trade_ticket", "use_trade_ticket")
#
#     # Not a synthetic template? just return original id.
#     if sid_col not in reg.columns or investment_id not in reg[sid_col].values:
#         return investment_id
#
#     row = reg.loc[reg[sid_col] == investment_id].iloc[0]
#
#     investment_type = str(row.get(itype_col, "SYNTHETIC")).upper()
#     use_ticket = str(row.get(use_ticket_col, "NO")).strip().upper() == "YES"
#
#     # Instance id policy: suffix tranid only if template says to use trade ticket
#     new_id = f"{investment_id}_{tranid}" if use_ticket else investment_id
#
#     # -------------------------------
#     # Upsert investment Master (append only)
#     # -------------------------------
#     im_cols = [
#         "investment", "description", "investment_type",
#         "currency", "pricing_factor"
#     ]
#     df_inv = _ensure_df(investment_MASTER_PATH, im_cols)
#
#     if new_id not in df_inv["investment"].values:
#         new_inv = {
#             "investment": new_id,
#             "description": row.get(desc_col, f"{investment_id} instantiated"),
#             "investment_type": investment_type,
#             "currency": terms.get("currency", row.get(curr_col, "")),
#             # pricing_factor often maps to Notional/Principal for synthetic legs
#             "pricing_factor": terms.get("Notional", row.get(princ_col, 1)),
#         }
#         df_inv = pd.concat([df_inv, pd.DataFrame([new_inv])], ignore_index=True)
#         df_inv.to_csv(investment_MASTER_PATH, index=False)
#         print(f"✅ Created {new_id} in investment Master ({investment_type})")
#
#     # -------------------------------
#     # Upsert Bond Info if needed (append only)
#     # -------------------------------
#     if investment_type == "BOND":
#         bond_cols = [
#             "investment","investment_type","issue_date","first_coupon_date",
#             "day_count_convention","payment_frequency","next_to_last_coupon_date",
#             "maturity_date","coupon_rate","Face_Value","currency","pricing_factor","semi_split"
#         ]
#         df_bond = _ensure_df(BOND_INFO_PATH, bond_cols)
#
#         if new_id not in df_bond["investment"].values:
#             new_bond = {
#                 "investment": new_id,
#                 "investment_type": "BOND",
#                 "issue_date": terms.get("issue_date", datetime.today().strftime("%m/%d/%Y")),
#                 "first_coupon_date": terms.get("first_coupon_date", ""),
#                 "day_count_convention": terms.get("day_count_convention", "30/360"),
#                 "payment_frequency": terms.get("Frequency", row.get(freq_col, "")),
#                 "next_to_last_coupon_date": terms.get("next_to_last_coupon_date", ""),
#                 "maturity_date": terms.get("maturity_date", row.get(mty_col, "")),
#                 "coupon_rate": terms.get("coupon_rate", row.get(rate_col, 0.0)),
#                 "Face_Value": terms.get("Notional", row.get(princ_col, 1)),
#                 "currency": terms.get("currency", row.get(curr_col, "")),
#                 "pricing_factor": terms.get("Notional", row.get(princ_col, 1)),
#                 "semi_split": terms.get("semi_split", "A"),
#             }
#             df_bond = pd.concat([df_bond, pd.DataFrame([new_bond])], ignore_index=True)
#             df_bond.to_csv(BOND_INFO_PATH, index=False)
#             print(f"✅ Created {new_id} in Bond Info")
#
#     # -------------------------------
#     # 🔸 Critical: Inject AIF to live space (no clearing)
#     # -------------------------------
#     aif_map = {
#         "investment_type": investment_type,
#         "currency": terms.get("currency", row.get(curr_col, "")),
#         "pricing_factor": terms.get("Notional", row.get(princ_col, 1)),
#     }
#     _safe_set_aif(space, new_id, aif_map)
#
#     if investment_type == "BOND":
#         bond_aif = {
#             "issue_date": terms.get("issue_date", ""),
#             "first_coupon_date": terms.get("first_coupon_date", ""),
#             "day_count_convention": terms.get("day_count_convention", "30/360"),
#             "payment_frequency": terms.get("frequency", row.get(freq_col, "")),
#             "next_to_last_coupon_date": terms.get("next_to_last_coupon_date", ""),
#             "maturity_date": terms.get("maturity_date", row.get(mty_col, "")),
#             "coupon_rate": terms.get("coupon_rate", row.get(rate_col, 0.0)),
#             "semi_split": terms.get("semi_split", "A"),
#         }
#         _safe_set_aif(space, new_id, bond_aif)
#
#     return new_id

def log(msg):
    func = inspect.currentframe().f_back.f_code.co_name
    print(f"🔍 {func}: {msg}")

def load_csv(file_path):
    """Load data from a CSV file into a DataFrame."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    try:
        df = pd.read_csv(file_path)
        return df
    except Exception as e:
        raise ValueError(f"Failed to load CSV file: {e}")


def load_file(file_path):
    """
    Ensures only CSV files are loaded.
    Any attempt to load JSON is blocked.
    """
    if not file_path.endswith(".csv"):
        raise ValueError(f"Invalid file format: {file_path}. Expected CSV.")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    return load_csv(file_path)

def normalize_dt(value):
    from datetime import datetime, date

    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    raise TypeError(f"Unsupported date type: {type(value)}")


def direct_load_csv(file_path):
    """Directly loads a CSV file, enforcing that only CSV files are allowed."""
    return load_file(file_path)



def kivy_process_inputs(selected_fund, current_period_start, current_period_cutoff, current_knowledge_start,
                        prior_period_start, prior_period_cutoff, prior_knowledge_start):
    from datetime import datetime
    date_format = "%Y-%m-%d:%H:%M:%S"
    current_period_start = datetime.strptime(current_period_start, date_format)
    current_period_end = datetime.strptime(current_period_cutoff, date_format)
    current_knowledge_end = datetime.strptime(current_knowledge_start, date_format)
    prior_period_start = datetime.strptime(prior_period_start, date_format)
    prior_period_end = datetime.strptime(prior_period_cutoff, date_format)
    prior_knowledge_end = datetime.strptime(prior_knowledge_start, date_format)
    numport = 1
    process_current = "Yes"
    process_base = "Yes"

import pandas as pd

# Load the transaction data from an Excel file
#transactions_data = pd.read_csv('C:/Users/hjmne/PycharmProjects/chest/refdata/MyPortfolio.csv')

# Load the price master data from a CSV file
prices_data = pd.read_csv('C:/Users/hjmne/PycharmProjects/chest/refdata/price_master.csv')

# Define the function to check price ranges
def check_price_range(transactions, prices, percentage_range):
    """
    Checks each transaction's price against historical price data to determine if it falls within a specified percentage range.

    The function merges transactions with historical prices based on the investment and transaction date. If a direct price match is not found, it searches for the closest price within the previous three days. It then calculates a price range based on the specified percentage and checks if the transaction price falls within this range.

    Parameters:
    - transactions (DataFrame): A DataFrame containing transaction data.
    - prices (DataFrame): A DataFrame containing historical price data.
    - percentage_range (float): The percentage range within which the transaction price should fall relative to the historical price.

    Returns:
    - DataFrame: A DataFrame containing the original transaction data along with the price check results.
    """
    # Convert 'tradedate' to datetime and sort the transactions
    transactions['tradedate'] = pd.to_datetime(transactions['tradedate'], errors='coerce',
                                               format='%d/%m/%Y:%H:%M:%S')
    transactions.sort_values(by=['investment', 'tradedate'], inplace=True)
    transactions['trade_date_formatted'] = transactions['tradedate'].dt.date

    # Convert 'date' to datetime in the prices data
    prices['date'] = pd.to_datetime(prices['date'], errors='coerce', format='%m/%d/%Y')
    prices['date_formatted'] = prices['date'].dt.date

    # Merge transactions with prices based on investment/ticker
    merged_data = transactions.merge(prices, left_on=['investment', 'trade_date_formatted'],
                                     right_on=['ticker', 'date_formatted'], how='left')

    # For transactions with no price, find the price from the previous 3 days
    for index, row in merged_data[merged_data['price'].isnull()].iterrows():
        # Get the range of dates to look back
        lookback_dates = [row['trade_date_formatted'] - pd.Timedelta(days=x) for x in range(1, 4)]
        # Find the closest available price within the lookback period
        price_info = prices[(prices['ticker'] == row['investment']) &
                            (prices['date_formatted'].isin(lookback_dates))]
        if not price_info.empty:
            closest_price = price_info.iloc[-1]  # Get the latest available price within the lookback period
            merged_data.at[index, 'price'] = closest_price['price']
            merged_data.at[index, 'date'] = closest_price['date']

    # Calculate the price per quantity for the transactions
    merged_data['transaction_price'] = merged_data['total_amount'] / merged_data['quantity']

    # Calculate the acceptable price range based on the percentage range
    merged_data['lower_bound'] = merged_data['price'] * (1 - percentage_range / 100)
    merged_data['upper_bound'] = merged_data['price'] * (1 + percentage_range / 100)

    # Check if the transaction price per quantity is within the acceptable range
    merged_data['price_check'] = (merged_data['transaction_price'] >= merged_data['lower_bound']) & \
                                 (merged_data['transaction_price'] <= merged_data['upper_bound'])

    # Return the relevant columns
    return merged_data[['tradedate', 'investment', 'quantity', 'total_amount', 'price',
                        'transaction_price', 'lower_bound', 'upper_bound', 'price_check']]

# Set the percentage range for the price check
percentage_range = 5  # 5%

# # Call the function with the loaded data
# price_check_result = check_price_range(transactions_data, prices_data, percentage_range)
#
# # Display the first few rows of the result
# print(price_check_result.head())

def unpack_values(values):
    # Provide default values for notional, original_face, and settlement_status if they're missing
    quantity, local, book = values[:3]  # Always expected
    return quantity, local, book
def convert_to_structure(data, data_type):
    if data_type == 'df':
        # Convert to DataFrame
        if not data:
            return pd.DataFrame()  # Returning an empty DataFrame for consistency
        column_names = ['portfolio', 'investment', 'lotid', 'tax_date', 'ls', 'location', 'financial_account',
                        'quantity', 'local', 'book', 'notional']
        records_dicts = []
        for record in data:
            # Assuming record is structured correctly with all fields
            record_dict = {
                'portfolio': record[0],
                'investment': record[1],
                'lotid': record[2],
                'tax_date': record[3],
                'ls': record[4],
                'location': record[5],
                'financial_account': record[6],
                'quantity': record[7],
                'local': record[8],
                'book': record[9],
                'notional': record[10],
                'oface': record[11],

            }
            records_dicts.append(record_dict)
        return pd.DataFrame(records_dicts, columns=column_names)

    elif data_type == 3:
        # Ensure the full column list is used
        column_names = ['portfolio', 'investment', 'lotid', 'tax_date', 'ls', 'location', 'financial_account',
                        'quantity', 'local', 'book', 'notional', 'oface']
        if not data:
            return pd.DataFrame()  # Return an empty DataFrame if data is empty
        return pd.DataFrame(data, columns=column_names)

    # Handle other data types similarly, ensuring all necessary fields are included


def parse_datetime(date_str):
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        return None


def convert_to_dataframe(data, data_type):
    # This seems redundant if the logic is handled in `convert_to_structure`. If you need specific adjustments,
    # ensure data types and structures are handled as needed. Here's an example for a custom structure:

    if data_type == 2:  # Example custom handling
        column_names = ['portfolio', 'investment', 'lotid','tax_date', 'ls', 'location', 'financial_account',
                        'quantity', 'local', 'book', 'notional', 'oface']
        records_dicts = []
        for record in data:
            record_dict = {
                'portfolio': record[0],
                'investment': record[1],
                'lotid': record[2],
                'tax_date': record[3],
                'ls': record[4],
                'location': record[5],
                'financial_account': record[6],
                'quantity': record[7],
                'local': record[8],
                'book': record[9],
                'notional': record[10],
                'oface': record[11],
            }
            records_dicts.append(record_dict)
        return pd.DataFrame(records_dicts, columns=column_names)


def check_same_sign(num1, num2):
    if (num1 >= 0 and num2 >= 0) or (num1 <= 0 and num2 <= 0):
        return True
    else:
        return False

# ✅ Cache for price lookups
price_cache = {}

# ✅ Cache for FX data
fx_data_cache = {}


### ===================================================== ###
### 🔥 Utility Functions for Date Formatting and Lookups ###
### ===================================================== ###

def format_date(date, output_format="%Y-%m-%d"):
    """
    Converts a date to a standard format for lookups.
    - If input is 'M/D/YYYY', it converts to 'YYYY-MM-DD' (default).
    - Supports other formats if specified.
    """
    if isinstance(date, str):
        date = datetime.strptime(date, "%m/%d/%Y")  # Convert from "M/D/YYYY"

    return date.strftime(output_format)  # Convert to output format

from datetime import datetime

def serialize_event_for_csv(event: dict) -> dict:
    """
    Convert in-memory canonical event → CSV-safe event.
    """
    out = {}

    for k, v in event.items():
        if isinstance(v, datetime):
            out[k] = v.strftime("%Y-%m-%d:%H:%M:%S")
        else:
            out[k] = v

    return out
def serialize_event_for_ingest(row: dict) -> dict:
    """
    Serialize event row into CSV format expected by ingest_event.
    """
    from datetime import datetime

    out = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.strftime("%m/%d/%Y:%H:%M:%S")  # 🔥 REQUIRED FORMAT
        else:
            out[k] = v
    return out

def validate_dataframe(df, expected_columns):
    """Ensures DataFrame integrity before loading data."""
    missing_cols = set(expected_columns) - set(df.columns)
    if missing_cols:
        raise ValueError(f"❌ ERROR: Missing columns: {missing_cols}")

    if df.duplicated().any():
        print(f"⚠ WARNING: Duplicate rows detected. Removing duplicates...")
        df = df.drop_duplicates()

    if df.isna().any().any():
        print(f"⚠ WARNING: NaN values detected! Replacing with 'N/A'.")
        df = df.fillna("N/A")

    return df

def load_price_data_as_rows(filepath):
    """
    Load price (or FX) data as immutable ROW FACTS.

    Visibility rules:
    - Price/FX dates are M/D/YYYY (NO time component)
    - Dates are MARKET observation dates, not event datetimes
    - Leave them as strings; kernel will align temporally later
    """

    import os
    import pandas as pd

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Price file not found: {filepath}")

    # IMPORTANT:
    # - Do NOT parse dates here
    # - Do NOT attach time
    # - Do NOT call from_csv_date_to_app
    df = pd.read_csv(
        filepath,
        dtype={
            "date": str,
            "ticker": str,
            "currency": str,
            "price": float,
        },
        keep_default_na=False,
    )

    # Sanity check (cheap, defensive, fast)
    if "date" not in df.columns:
        raise RuntimeError("Price file missing 'date' column")

    rows = df.to_dict(orient="records")

    print(f"✅ Loaded price rows: {len(rows)}")
    return rows

def load_fx_data_as_rows(filepath):
    """
    Load FX data as immutable ROW FACTS.
    Shape: List[Dict]
    """

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"FX file not found: {filepath}")

    rows = []

    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)

        for r in reader:
            r["date"] = pd.to_datetime(r["date"], format="%m/%d/%Y", errors="raise")
            r["price"] = float(r["price"])
            rows.append(r)

    print(f"✅ Loaded FX rows: {len(rows)}")
    return rows

### ========================================== ###
### 🔥 Retrieve FX Rate with Correct Formatting ###
### ========================================== ###

_fx_cache = {}

def get_fx_rate(currency, date, fx_rows):
    """
    Retrieve FX rate from row-based FX facts.
    Falls back to most recent prior available date.
    """

    lookup_date = format_date(date)

    # Build cache once per currency
    if currency not in _fx_cache:
        rows = [r for r in fx_rows if r["currency"] == currency]

        if not rows:
            raise ValueError(f"❌ FX: currency '{currency}' not found in FX data")

        _fx_cache[currency] = {
            format_date(r["date"]): float(r["price"])
            for r in rows
        }

    fx_by_date = _fx_cache[currency]

    # Direct hit
    if lookup_date in fx_by_date:
        return fx_by_date[lookup_date]

    # Fallback: walk backward
    from datetime import datetime, timedelta

    d = datetime.strptime(lookup_date, "%Y-%m-%d")

    while True:
        d -= timedelta(days=1)
        k = d.strftime("%Y-%m-%d")

        if k in fx_by_date:
            return fx_by_date[k]

        if d.year < 1900:
            raise ValueError(
                f"❌ FX fallback exhausted for {currency} prior to {lookup_date}"
            )

_price_cache = {}

def get_price(investment, date, price_rows):
    """
    Retrieve price from row-based price facts.
    Falls back to most recent prior available date.
    """

    lookup_date = format_date(date)
    cache_key = (investment, lookup_date)

    # Fast path: exact hit already cached
    if cache_key in _price_cache:
        return _price_cache[cache_key]

    # Build per-investment cache once
    inv_key = ("__by_date__", investment)
    if inv_key not in _price_cache:
        rows = [r for r in price_rows if r["ticker"] == investment]

        if not rows:
            raise ValueError(
                f"❌ PRICE: investment '{investment}' not found in price data"
            )

        _price_cache[inv_key] = {
            format_date(r["date"]): float(r["price"])
            for r in rows
        }

    prices_by_date = _price_cache[inv_key]

    # Direct hit
    if lookup_date in prices_by_date:
        price = prices_by_date[lookup_date]
        _price_cache[cache_key] = price
        return price

    # Fallback: walk backward
    from datetime import datetime, timedelta

    d = datetime.strptime(lookup_date, "%Y-%m-%d")

    while True:
        d -= timedelta(days=1)
        k = d.strftime("%Y-%m-%d")

        if k in prices_by_date:
            price = prices_by_date[k]
            _price_cache[cache_key] = price
            return price

        if d.year < 1900:
            raise ValueError(
                f"❌ PRICE fallback exhausted for {investment} prior to {lookup_date}"
            )

def get_locations_into_json():
    import pandas as pd

    # Load the data from Excel
    df = pd.read_excel('C:/Users/hjmne/PycharmProjects/chest/refdata/locations.xlsx', engine='openpyxl')

    # Convert dataframe to JSON
    df.to_json('C:/Users/hjmne/PycharmProjects/chest/refdata/reference_tables/location_table.json', orient='records', indent=4)
import json

from datetime import datetime, timedelta


def get_previous_business_day(current_date, business_days):
    """
    Get the previous business day before the given date.

    :param current_date: The date from which to find the previous business day.
    :param business_days: A list or set of business days (datetime.date objects).
    :return: The previous business day as a datetime.date object.
    """
    # Convert to date if datetime
    if isinstance(current_date, datetime):
        current_date = current_date.date()

    # Find the previous business day
    prev_day = current_date - timedelta(days=1)

    # Keep going back until we find a business day
    while prev_day not in business_days:
        prev_day -= timedelta(days=1)

    return prev_day

def load_location_data():
    with open('C:/Users/hjmne/PycharmProjects/chest/refdata/reference_tables/location_table.json', 'r') as file:
        return json.load(file)

def flatten_nested_tuples(entries):
    """
    Convert a list of entries, each consisting of a tuple of two tuples,
    into a list of flat lists.

    Args:
        entries (list of tuple): The list of entries, each a tuple of two tuples.

    Returns:
        list of list: A list where each entry is a flat list.
    """
    # Flatten each entry and convert to a list
    flat_list = [list(entry1) + list(entry2) for entry1, entry2 in entries]
    return flat_list

# Example usage
# al = [
#     (('MyPortfolio', 'JPY', 0, 'n', 'Goldman', 'Cost'), (45938997397.61597, 45938997397.61597, 392319037.7756405)),
#     (('MyPortfolio', 'JPY', 0, 'n', 'Goldman', 'UnrealGLAsset'), (0, 0.0, -64527385.79260826)),
#     # Add more entries as needed...
# ]
#
# # Convert the nested tuple structure to a flat list structure
# al_flat = flatten_nested_tuples(al)
#
# # Now al_flat is ready for further processing, such as creating a DataFrame
# bookkeeping_space_list = []
# for entry in al_flat:
#     portfolio, investment, tax_lot_num, ls, location, financial_account, quantity, local, book = entry
#     booksp_row = [portfolio, investment, tax_lot_num, ls, location, financial_account, quantity, local, book]
#     bookkeeping_space_list.append(booksp_row)
#
# # Creating the DataFrame
# import pandas as pd
# df = pd.DataFrame(bookkeeping_space_list, columns=[
#     'Portfolio', 'investment', 'Tax Lot', 'LS', 'Location',
#     'Financial Account', 'Quantity', 'Local', 'Book'
# ])
#
# # The DataFrame df is now ready for reporting and further analysis
import os
import csv
import shutil

import pandas as pd


import csv

# ---- utilities.py (or wherever your loaders live) ----
import csv

KNOWN_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "AUD"}

def _get_investment_key(row):
    """
    Canonical investment identity resolution.

    Rules:
    1. If investment is explicitly provided, use it.
    2. Otherwise, ONLY allow currency-derived investments
       if currency is in the known currency set.
    3. Never silently skip.
    """

    investment = row.get("investment")
    if investment:
        return investment

    # currency = row.get("currency")
    # if currency in KNOWN_CURRENCIES:
    #     return currency

    raise ValueError(
        f"Cannot resolve investment identity from row: {row}"
    )

def _to_bool_flag(val):
    if val is None:
        return False
    s = str(val).strip().upper()
    return s in ('1', 'TRUE', 'YES', 'Y')

import os
import csv
from datetime import datetime

# ============================================================
# AUTHORITATIVE EVENT LOADER
# ============================================================

def load_events_csv(path: str):
    """
    AUTHORITATIVE event loader.

    External contract:
        - All dates are STRINGS in CSV
        - Event date format: MM/DD/YYYY:HH:MM:SS

    Internal invariant (post-ingest):
        - All event dates are datetime objects
        - No downstream parsing or normalization required
    """

    if not os.path.exists(path):
        raise RuntimeError(f"Event file missing: {path}")

    # --------------------------------------------------------
    # READ CSV (RAW STRINGS)
    # --------------------------------------------------------
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        records = [dict(r) for r in reader]

    if not records:
        raise RuntimeError(f"Event file empty: {path}")

    # --------------------------------------------------------
    # REQUIRED EVENT DATE FIELDS
    # --------------------------------------------------------
    EVENT_DATE_COLS = (
        "tradedate",
        "settledate",
        "kdbegin",
        "kdend",
        "knowledge_date",
    )

    # --------------------------------------------------------
    # NORMALIZE + VALIDATE
    # --------------------------------------------------------
    for r in records:
        # ---- Date normalization (ONCE) ----
        for col in EVENT_DATE_COLS:
            val = r.get(col)

            if val in (None, "", "NaT"):
                r[col] = None
                continue

            try:
                r[col] = datetime.strptime(
                    val,
                    "%m/%d/%Y:%H:%M:%S"
                )
            except Exception:
                raise RuntimeError(
                    f"Invalid {col} format '{val}' "
                    f"(expected MM/DD/YYYY:HH:MM:SS)"
                )

    return records

def remove_files_in_subdirectories(parent_directory):
    # Walk through all subdirectories of the given parent directory
    for root, dirs, files in os.walk(parent_directory):
        for name in files:
            # Construct the file path
            file_path = os.path.join(root, name)
            try:
                # Remove the file
                os.remove(file_path)
                print(f"Removed file: {file_path}")
            except Exception as e:
                print(f"Error removing file {file_path}: {e}")

# Example usage:
# replace '/path/to/your/directory' with the actual path to your parent directory
# parent_dir = '/path/to/your/directory'
# remove_files_in_subdirectories(parent_dir)

def compare_date_strings(date_str1, date_str2):
    return date_str1.split()[0] == date_str2.split()[0]

# # Example usage:
# date_str1 = "2024-01-15 00:00:00"
# date_str2 = "2024-01-15 12:30:45"
def lookup_pricing_factor(aif_pool, investment):
    # Implement the lookup logic for pricing factor from the AIF pool
    # This is a placeholder; you will need to replace it with the actual lookup logic
    return aif_pool.get_pricing_factor(investment)

import time
import logging

def benchmark(func, *args, **kwargs):
    start_time = time.time()
    result = func(*args, **kwargs)
    end_time = time.time()
    elapsed_time = end_time - start_time

    event_count = kwargs.get('event_count', 1)
    events_per_second = event_count / elapsed_time if elapsed_time > 0 else 0

    logging.info(f"{func.__name__} took {elapsed_time:.6f} seconds ({events_per_second:.2f} events per second)")
    return result, elapsed_time

import pandas as pd
from pandas.tseries.offsets import BDay

# List of holidays
holidays = ['2022-01-04', '2022-01-17','2022-02-21', '2022-05-30','2022-06-20', '2022-07-04','2022-09-05', '2022-10-10','2022-11-11', '2022-12-31',]  # Add your list of holidays here

def is_non_business_day(date):
    return date.weekday() >= 5 or str(date.date()) in holidays  # Saturday=5, Sunday=6

def adjust_to_next_business_day(date):
    while is_non_business_day(date):
        date += BDay(1)
    return date


from datetime import datetime
from datetime import datetime

from datetime import datetime

# Cache for parsed dates
date_cache = {
    'tradedate': {'last_str': None, 'last_date': None},
    'settledate': {'last_str': None, 'last_date': None},
    'kdbegin': {'last_str': None, 'last_date': None},
    'kdend': {'last_str': None, 'last_date': None}
}

def parse_date(date_str, date_key):
    # Define the date format with the colon between date and time
    date_format = '%m/%d/%Y:%H:%M:%S'
    # Check if the date_str is already cached
    if date_cache[date_key]['last_str'] == date_str:
        return date_cache[date_key]['last_date']
    else:
        # Parse the date and update the cache
        parsed_date = datetime.strptime(date_str, date_format)
        date_cache[date_key]['last_str'] = date_str
        date_cache[date_key]['last_date'] = parsed_date
        return parsed_date


def update_prices_start_of_day(sub_ledger):
    global priced_investments

    for item in priced_investments:
        investment = item['investment']
        price = item['price']
        subspace = sub_ledger.asset_liability_repository.get_subspace(investment)
        subspace.store_price(price)

from decimal import Decimal, ROUND_HALF_UP

def round_to_precision(value, precision='0.0001'):
    """Round a value to the specified precision using half-up rounding."""
    return Decimal(value).quantize(Decimal(precision), rounding=ROUND_HALF_UP)



def update_prices_from_list(sub_ledger, priced_investments):
    for investment in priced_investments:
        subspace = sub_ledger.asset_liability_repository.get_position_space(investment)
        price = subspace.retrieve_price()
        # Do whatever updates are necessary with the price
        # For example, logging or storing in a summary
        print(f"Updated price for {investment}: {price}")

import os
import pandas as pd

def save_report(dataframe, report_name, portfolio_name, directory="reports"):
    """
    Save the report with the portfolio name prepended.

    Args:
        dataframe (pd.DataFrame): The report data.
        report_name (str): The base report name (e.g., 'Events.xlsx').
        portfolio_name (str): The portfolio name to prepend.
        directory (str): Directory where the report will be saved.
    """
    # Prepend the portfolio name to the report name
    filename = f"{portfolio_name}_{report_name}"

    # Ensure the directory exists
    if not os.path.exists(directory):
        os.makedirs(directory)

    # Save the report
    filepath = os.path.join(directory, filename)
    dataframe.to_excel(filepath, index=False)
    print(f"Report saved: {filepath}")

import pickle
import concurrent.futures
import os


def enforce_sorted_dates(df, report_name):
    """
    Ensures that the DataFrame's 'date' column is sorted correctly.
    If it's not, an error is raised to prevent further execution.

    :param df: Pandas DataFrame containing a 'date' column.
    :param report_name: Name of the report being processed (for error messages).
    """
    if "date" not in df.columns:
        print(f"⚠ WARNING: '{report_name}' does not contain a 'date' column. Skipping sort validation.")
        return  # No action needed

    try:
        df["date"] = pd.to_datetime(df["date"])  # Ensure it's in datetime format
    except Exception as e:
        raise ValueError(f"❌ ERROR: Failed to convert 'date' column in '{report_name}' to datetime. Details: {e}")

    if not df["date"].is_monotonic_increasing:  # Check if already sorted
        raise ValueError(f"❌ ERROR: '{report_name}' is not sorted by date! Ensure sorting before passing to UI.")

    print(f"✅ Guardrail Check Passed: '{report_name}' is correctly sorted.")


def apply_position_valuation(bookkeeping_space, mark_date, price_data, fx_data):
    """
    Apply position-level valuation to the bookkeeping space.

    Args:
        bookkeeping_space (BookkeepingSpace): The bookkeeping space to update.
        mark_date (str): The valuation date.
        price_data (str): Path to the price data file.
        fx_data (str): Path to the FX data file.
    """
    # Convert bookkeeping space to a DataFrame for filtering and valuation
    bookkeeping_space_list = []
    for entry in bookkeeping_space.entries:
        portfolio, investment, tax_lot, ls, location, financial_account, quantity, local, book = entry
        bookkeeping_space_list.append([portfolio, investment, tax_lot, ls, location, financial_account, quantity, local, book])

    df = pd.DataFrame(bookkeeping_space_list, columns=[
        'Portfolio', 'investment', 'Tax Lot', 'LS', 'Location', 'Financial Account', 'Quantity', 'Local', 'Book'
    ])
    # Exclude market valuation entries
    df = filter_records(df, 'Financial Account', ['MktVal', 'MktValRE'], operator="OR", mode="exclude")

    # Convert DataFrame to dictionary for valuation
    bookkeeping_records = df.set_index([
        'Portfolio', 'investment', 'Tax Lot', 'LS', 'Location', 'Financial Account']).T.to_dict('list')

    # Perform valuation
    mark_type = "Valuation"
    df_valued = value_positions(bookkeeping_records, bookkeeping_space, price_data, fx_data, mark_date, mark_type)

    # Update the bookkeeping space with the valuation results
    for _, row in df_valued.iterrows():
        # Example: Create and post a journal entry for the valuation result
        je = bookkeeping.create_journal_entry(
            portfolio=row['Portfolio'],
            investment=row['investment'],
            tax_lot=None,  # Position-level valuation, so no tax lot
            financial_account='MktVal',
            quantity=row['Quantity'],
            local=row['LocalValuation'],
            book=row['BookValuation'],
            ibor_date=mark_date
        )
        bookkeeping_space.post_journal_entry(je)

def apply_tax_lot_valuation(bookkeeping_space, mark_date, price_data, fx_data):
    """
    Apply tax lot-level valuation to the bookkeeping space (fallback).

    Args:
        bookkeeping_space (BookkeepingSpace): The bookkeeping space to update.
        mark_date (str): The valuation date.
        price_data (str): Path to the price data file.
        fx_data (str): Path to the FX data file.
    """
    # Similar to apply_position_valuation but includes tax lot-level detail
    # Convert DataFrame to dictionary for valuation and include Tax Lot
    df = convert_to_dataframe(bookkeeping_space)
    bookkeeping_records = df.set_index([
        'Portfolio', 'investment', 'Tax Lot', 'LS', 'Location', 'Financial Account']).T.to_dict('list')

    # Perform tax lot-level valuation
    mark_type = "TaxLotValuation"
    df_valued = value_positions(bookkeeping_records, bookkeeping_space, price_data, fx_data, mark_date, mark_type)

    # Post valuation results to bookkeeping space
    for _, row in df_valued.iterrows():
        je = bookkeeping.create_journal_entry(
            portfolio=row['Portfolio'],
            investment=row['investment'],
            tax_lot=row['Tax Lot'],
            financial_account='MktVal',
            quantity=row['Quantity'],
            local=row['LocalValuation'],
            book=row['BookValuation'],
            ibor_date=mark_date
        )
        bookkeeping_space.post_journal_entry(je)
# 📌 Function to Load Historical Data

import os
import pandas as pd

import os
import pandas as pd


def load_report_file(report_name_or_path, portfolio_name=None,
                     base_path="BASE_PATH/reports"):
    """
    Attempts to load a report file (.xlsx or .csv) intelligently.

    Args:
        report_name_or_path (str): Either a full path or a report name without extension.
        portfolio_name (str, optional): If given, will prepend to the report name.
        base_path (str): Directory to search for the report if not full path.

    Returns:
        pd.DataFrame: The loaded DataFrame or empty DataFrame on failure.
    """

    # ✅ Use full path if provided directly
    if os.path.isfile(report_name_or_path):
        ext = os.path.splitext(report_name_or_path)[-1].lower()
        try:
            if ext == ".xlsx":
                return pd.read_excel(report_name_or_path)
            elif ext == ".csv":
                return pd.read_csv(report_name_or_path, encoding="utf-8", on_bad_lines="warn")
            else:
                raise ValueError(f"Unsupported file format: {ext}")
        except UnicodeDecodeError:
            print(f"⚠️ Unicode issue in {report_name_or_path}, retrying with ISO-8859-1...")
            return pd.read_csv(report_name_or_path, encoding="ISO-8859-1", on_bad_lines="warn")
        except Exception as e:
            print(f"❌ Failed to load report file: {e}")
            return pd.DataFrame()

    # ✅ Not a full path — build possibilities from known patterns
    candidates = []
    name_core = report_name_or_path

    if portfolio_name:
        name_core = f"{portfolio_name}_{report_name_or_path}"

    candidates.append(os.path.join(base_path, f"{name_core}.xlsx"))
    candidates.append(os.path.join(base_path, f"{name_core}.csv"))

    for path in candidates:
        if os.path.isfile(path):
            print(f"📂 Attempting to load: {path}")
            return load_report_file(path)  # Recursive call now that path is full

    print(f"❌ Report file not found: {report_name_or_path}")
    return pd.DataFrame()
def normalize_merged_fields(df):
    """
    Normalize merged column names to match expected query/filter/report standards.
    This is critical after merging COA, investment master, etc.
    """

    # Mapping of inconsistent → expected column names
    normalization_map = {
        "BSGroup": "BS_Group",
        "bs_group": "BS_Group",
        "SummaryReport": "Summary_Report",
        "summaryreport": "Summary_Report",
        "summary_report": "Summary_Report",
        "IncomeGroup": "Income_Group",
        "income_group": "Income_Group",
        "SystemName": "System_Name",  # if merge brings in wrong case
    }

    for raw_col, expected_col in normalization_map.items():
        if raw_col in df.columns:
            if expected_col not in df.columns:
                df[expected_col] = df[raw_col]
                print(f"🔄 Normalized column '{raw_col}' → '{expected_col}'")
            else:
                print(f"⚠️ Both '{raw_col}' and '{expected_col}' exist — consider de-duping.")

    return df
def validate_query_result(df, group_by=None, eligible_total_columns=None, filters=None):
    """
    Validate query shape, group keys, and total columns.
    Logs reasons for empty or unexpected results.
    """

    print("\n🔎 VALIDATING QUERY RESULT")
    print(f"🧾 DF shape: {df.shape}")

    if filters:
        print(f"🔍 Filters applied: {filters}")

    if df.empty:
        print("⚠️ Final DataFrame is EMPTY.")

        if filters:
            print("🔍 Likely cause: Filters may have excluded all rows.")
            for key, val in filters.items():
                if key not in df.columns:
                    print(f"❌ Filter column '{key}' not found in DataFrame.")
                else:
                    print(f"🔍 Available values for '{key}':", df[key].dropna().unique()[:5])
        else:
            print("🔍 No filters applied — likely cause is grouping or merge mismatch.")

    if group_by:
        print(f"📊 GroupBy: {group_by}")
        for col in group_by:
            if col not in df.columns:
                print(f"❌ GroupBy column '{col}' not found in DataFrame.")

    if eligible_total_columns:
        if "None" in eligible_total_columns:
            print("⚠️ ConfigTotals = None → Totals explicitly disabled.")
        else:
            numeric_totals = [
                col for col in eligible_total_columns
                if col in df.columns and pd.api.types.is_numeric_dtype(df[col])
            ]
            if not numeric_totals:
                print("⚠️ ConfigTotals defined, but no matching numeric columns found.")
            else:
                print(f"✅ Eligible totals columns: {numeric_totals}")
    else:
        print("⚠️ No ConfigTotals defined — using default aggregation.")

    print("✅ Validation complete.\n")

def enrich_journal_entries(journal_entries,
                            coa_tags=None,
                            inv_tags=None,
                            coa_path=None,
                            inv_master_path=None):
    import pandas as pd

    coa_tags = [tag.upper() for tag in (coa_tags or [])]
    inv_tags = [tag.upper() for tag in (inv_tags or [])]

    # --- Enrich from chart_of_accounts ---
    if coa_tags:
        try:
            if not coa_path:
                coa_path = "BASE_PATH/refdata/chart_of_accounts.csv"
            coa = pd.read_csv(coa_path)
            coa.columns = coa.columns.str.upper()
            coa["SYSTEM_NAME"] = coa["SYSTEM_NAME"].astype(str).str.upper()
            selected_cols = ["SYSTEM_NAME"] + coa_tags
            coa = coa[selected_cols].drop_duplicates()
            coa_lookup = coa.set_index("SYSTEM_NAME").to_dict(orient="index")

            for je in journal_entries:
                acct = str(getattr(je, "account", "")).upper()
                for tag in coa_tags:
                    value = coa_lookup.get(acct, {}).get(tag)
                    setattr(je, tag.lower(), value)  # e.g. je.bs_group
        except Exception as e:
            print(f"❌ COA enrichment failed: {e}")

    # --- Enrich from investment_master ---
    if inv_tags:
        try:
            if not inv_master_path:
                inv_master_path = "BASE_PATH/refdata/investment_master.csv"
            inv = pd.read_csv(inv_master_path)
            inv.columns = inv.columns.str.upper()
            inv["investment"] = inv["investment"].astype(str).str.upper()
            selected_cols = ["investment"] + inv_tags
            inv = inv[selected_cols].drop_duplicates()
            inv_lookup = inv.set_index("investment").to_dict(orient="index")

            for je in journal_entries:
                inv_id = str(getattr(je, "investment", "")).upper()
                for tag in inv_tags:
                    value = inv_lookup.get(inv_id, {}).get(tag)
                    setattr(je, tag.lower(), value)  # e.g. je.sector, je.strategy
        except Exception as e:
            print(f"❌ investment Master enrichment failed: {e}")

import os
import csv

def get_portfolios_to_process(portfolio_or_list: str, pooltest_dir: str = "chest/pooltest") -> list:
    """
    Determines whether the input is a single portfolio name or a CSV containing a list of portfolio names.
    If the filename starts with 'LIST_', it's treated as a list file.
    """
    portfolio_or_list = portfolio_or_list.strip()

    # 🗂 If it's a LIST_*.csv file, treat as a list of portfolios
    if portfolio_or_list.upper().startswith("ZLIST_") and portfolio_or_list.endswith(".csv"):
        full_path = os.path.join(pooltest_dir, portfolio_or_list)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"❌ Portfolio list file not found: {full_path}")

        with open(full_path, newline='') as f:
            reader = csv.reader(f)
            portfolios = [row[0].strip() for row in reader if row and row[0].strip()]
        return portfolios

    # 🧾 Otherwise, treat as a single portfolio name
    return [portfolio_or_list]
import os
import pandas as pd
#
# def resolve_portfolio_list(portfolio_name: str, directory: str) -> list:
#     """
#     Given a portfolio name, determine if it's a single portfolio or a list.
#     - If the name starts with 'ZLIST_', treat it as a CSV file containing portfolio names.
#     - Otherwise, return a list containing the single portfolio.
#
#     Args:
#         portfolio_name (str): Portfolio or list name.
#         directory (str): Directory to look for ZLIST_ files.
#
#     Returns:
#         List[str]: List of portfolios to process.
#     """
#     if portfolio_name.upper().startswith("ZLIST_"):
#         list_path = os.path.join(directory, f"{portfolio_name}.csv")
#         if not os.path.exists(list_path):
#             raise FileNotFoundError(f"Portfolio list file not found: {list_path}")
#
#         df = pd.read_csv(list_path, header=None)
#         portfolio_list = df.iloc[:, 0].dropna().astype(str).tolist()
#         print(f"📋 Loaded {len(portfolio_list)} portfolios from {portfolio_name}.csv")
#         return portfolio_list
#     else:
#         return [portfolio_name]
def clean_derived_fields(df, layout_spec):
    derived = layout_spec.get("derived", {})
    for col in derived:
        if col not in df.columns:
            continue

        # General handling: replace inf, fill NaNs with 0
        if df[col].dtype.kind in "fiu":  # numeric: float/int/unsigned
            df[col].replace([float("inf"), -float("inf")], pd.NA, inplace=True)

        # Field-specific cleanup rules
        if col == "PRICE":
            df[col] = df[col].where(df["QUANTITY"] != 0, pd.NA)
            df[col] = df[col].round(4)

        elif col == "TOTAL_VALUE":
            df[col] = df[col].fillna(0)

        elif col == "IS_CASH":
            df[col] = df[col].fillna(False)

        # You can extend with more derived rules as needed

    return df
print(" LEAVE UTILITIES")