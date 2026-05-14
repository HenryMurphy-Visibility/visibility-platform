import pandas as pd

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

import pandas as pd
# fx_file_path = r"C:\Users\UserPC\documents\chest\refdata\fx_master.csv"
# fx_data = pd.read_csv(fx_file_path)
fx_rate_cache = {}

# def get_fx_rate(currency, date, fx_rates_df):
#     # Check if the FX rate is available in the cache
#     cache_key = (currency, date)
#     if cache_key in fx_rate_cache:
#         return fx_rate_cache[cache_key]
#
#     # Convert date to the proper datetime format if necessary
#     #date = pd.to_datetime(date, format='%m/%d/%Y')
#
#     # Filter the FX rates DataFrame for the specified currency
#     currency_rates_df = fx_rates_df[fx_rates_df['currency'] == currency]
#
#     # If the date is not found, use the nearest previous date
#     if date not in currency_rates_df['date'].values:
#         past_dates = currency_rates_df[currency_rates_df['date'] < date]['date']
#         if not past_dates.empty:
#             nearest_date = max(past_dates)
#             fx_rate = currency_rates_df[currency_rates_df['date'] == nearest_date]['price'].iloc[0]
#         else:
#             # Handle scenario where no past rates are available
#             fx_rate = None  # or some default action/behavior
#     else:
#         fx_rate = currency_rates_df[currency_rates_df['date'] == date]['price'].iloc[0]
#
#     # Store the FX rate in the cache for future lookups
#     fx_rate_cache[cache_key] = fx_rate
#
#     return fx_rate
#
import pandas as pd
from datetime import datetime

# Initialize FX rate cache
fx_rate_cache = {}
fx_rate_cache = {}
import pandas as pd

from datetime import datetime


def get_fx_rate(currency, date, fx_data):
    # Ensure the date is in the correct format (MM/DD/YYYY with leading zeros)
    formatted_date = format_date(date)

    if currency in fx_data and formatted_date in fx_data[currency]:
        return fx_data[currency][formatted_date]
    else:
        raise ValueError(f"FX rate for {currency} on {formatted_date} not found")


def format_date(date):
    # Convert the date to a datetime object if it is a string
    if isinstance(date, str):
        date = datetime.strptime(date, '%m/%d/%Y')
    # Manually format the date without leading zeros for month and day
    return f"{date.month}/{date.day}/{date.year}"



price_cache = {}

def get_price(investment, date, prices_df):
    formatted_date = format_date(date)
    cache_key = (investment, formatted_date)
    if cache_key in price_cache:
        return price_cache[cache_key]

    investment_prices_df = prices_df[prices_df['ticker'] == investment]
    if formatted_date not in investment_prices_df['date'].values:
        try:
            latest_date = max(investment_prices_df['date'])
            price = investment_prices_df[investment_prices_df['date'] == latest_date]['price'].iloc[0]
        except Exception:
            price = 1
    else:
        price = investment_prices_df[investment_prices_df['date'] == formatted_date]['price'].iloc[0]

    price_cache[cache_key] = price
    return price

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
#     'Portfolio', 'Investment', 'Tax Lot', 'LS', 'Location',
#     'Financial Account', 'Quantity', 'Local', 'Book'
# ])
#
# # The DataFrame df is now ready for reporting and further analysis
import os
import csv
import shutil

import pandas as pd


import csv

def load_investment_master_to_aif(repository, investment_master_path):
    try:
        with open(investment_master_path, mode='r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                investment = row['Investment']
                repository.update_investment_space(investment, 'AIF', 'Investment_Type', row.get('Investment_Type', None))
                repository.update_investment_space(investment, 'AIF', 'Contract_Size', row.get('Contract_Size', None))
                repository.update_investment_space(investment, 'AIF', 'IsCurrency', row.get('Is_Currency', None))
                repository.update_investment_space(investment, 'AIF', 'Pricing_Factor', row.get('Pricing_Factor', None))
                repository.update_investment_space(investment, 'AIF', 'Currency', row.get('Currency', None))
    except FileNotFoundError:
        print(f"File not found: {investment_master_path}")
    except Exception as e:
        print(f"Error reading investment master: {e}")

def load_bond_info_to_aif(repository, bond_info_path):
    try:
        with open(bond_info_path, mode='r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                investment = row['Investment']
                for key, value in row.items():
                    repository.update_investment_space(investment, 'AIF', key, value)
    except FileNotFoundError:
        print(f"File not found: {bond_info_path}")
    # except Exception as e:
    #     print(f"Error reading bond info: {e}")

def fetch_investment_master(investment):
    investment_master_path = 'c:/BASE_PATH/refdata/investment_master.csv'
    try:
        with open(investment_master_path, mode='r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:

                if row['Investment'] == investment:
                    is_currency_value = row.get('Is_Currency', '0').strip().upper()
                    is_currency = True if is_currency_value in ['1', 'TRUE'] else False

                    return {
                        'Investment_Type': row.get('Investment_Type', ''),
                        'Contract_Size': row.get('Contract_Size', ''),
                        'IsCurrency': is_currency,
                        'Pricing_Factor': row.get('Pricing_Factor', ''),
                        'Currency': row.get('Currency', '')
                    }
    except FileNotFoundError:
        print(f"File not found: {investment_master_path}")
    except Exception as e:
        print(f"Error reading investment master: {e}")
    return None
def fetch_bond_info(investment):
    bond_info_path = 'c:/BASE_PATH/refdata/bond_info.csv'
    try:
        with open(bond_info_path, mode='r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row['Investment'] == investment:
                    return row
    except FileNotFoundError:
        print(f"File not found: {bond_info_path}")
    # except Exception as e:
    #     print(f"Error reading bond info: {e}")
    return None

def read_investment_master(file_path):
    investment_master = {}
    with open(file_path, mode='r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            investment_master[row['Investment']] = row
    return investment_master

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


# mark_to_market.py
#
# def mark_to_market(sub_ledger):
#     marked_results = []
#     priced_investments = []  # List to keep track of priced investments
#
#     for investment, subspace in sub_ledger.asset_liability_repository.investment_spaces_library.items():
#         price = subspace.retrieve_price()
#
#         if price is None:
#             price = subspace.fetch_price_from_source(investment)
#
#         if price is not None:
#             priced_investments.append(investment)  # Add investment name (string) to priced list
#             for entry_key, entry_values in subspace.entries.items():
#                 portfolio, inv, lotid, tax_date, ls, location, financial_account = entry_key
#                 quantity, local, book, notional, oface = entry_values
#
#                 market_value_local = quantity * price - (notional if notional else 0)
#                 market_value_book = market_value_local  # Simplified for this example
#                 price_gain_local = market_value_local - local
#                 price_gain_book = price_gain_local
#                 fx_gain_book = market_value_book - book - price_gain_book
#
#                 record_to_add = (
#                     entry_key,  # The key tuple
#                     (quantity, local, book, market_value_local, market_value_book,
#                      price_gain_local, price_gain_book, fx_gain_book, price)  # The values tuple
#                 )
#
#                 marked_results.append(record_to_add)
#
#     return marked_results, priced_investments


def update_prices_from_list(sub_ledger, priced_investments):
    for investment in priced_investments:
        subspace = sub_ledger.asset_liability_repository.get_position_space(investment)
        price = subspace.retrieve_price()
        # Do whatever updates are necessary with the price
        # For example, logging or storing in a summary
        print(f"Updated price for {investment}: {price}")

