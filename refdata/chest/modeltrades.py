
import numpy as np
import random
import pandas as pd
from datetime import timedelta
from bookkeeping import load_price_data, load_fx_data
price_data = load_price_data("C:/Users/hjmne/PycharmProjects/chest/refdata/price_master.csv")
fx_data = load_fx_data("C:/Users/hjmne/PycharmProjects/chest/refdata/fx_master.csv")


from datetime import datetime

import random
from datetime import datetime

def fetch_price_and_fx(ticker_with_currency, price_data, fx_data, date_string):
    # Split the ticker and currency
    ticker, currency = ticker_with_currency.split()

    # Convert the date string to a datetime object
    date_object = datetime.strptime(date_string, '%m/%d/%Y')

    # Manually format the date to match your data file's format
    month = str(date_object.month).lstrip("0")  # Remove leading zero
    day = str(date_object.day)
    year = str(date_object.year)
    formatted_date = f"{month}/{day}/{year}"

    # Check if the data is available for the given ticker and date
    if formatted_date in price_data.get(ticker, {}):
        # Fetch the actual price data
        initial_price = price_data[ticker][formatted_date]
    else:
        # Use a random price between 50 and 100 if data is not available
        initial_price = random.uniform(50, 100)

    # Assuming fx_data is a dictionary with currency as the key and FX rate as the value
    initial_fx_rate = fx_data.get(currency, 1)  # Default FX rate to 1 if not found

    return initial_price, initial_fx_rate


def randomize_value(base_value, lower_pct=-0.02, upper_pct=0.10):
    return base_value * (1 + np.random.uniform(lower_pct, upper_pct))

# Sample currencies and equity positions
currencies = ['USD', 'EUR', 'JPY', 'GBP', 'AUD']
equity_positions = ['ABC', 'XYZ', 'UUU', 'RRR', 'TTT', 'DBA', 'ZLU', 'MAR', 'POP', 'MJH', 'OOJ', 'IKI', 'KLM', 'MKL', 'PPL', 'NNN', 'NPM', 'ZAS','XXD', 'DED'
                    'DDD', 'EEE', 'FFF', 'GGG', 'HHH', 'III', 'JJJ', 'KKK', 'LLL', 'MMM', 'NNN', 'OOO', 'PPP', 'QQQ', 'RRR', 'SSS', 'TTT', 'UUU','VVV', 'WWW'

                                                                                                                                                        'ABCX',
                    'XYZXx', 'UUUX', 'RRRX', 'TTTX', 'DBAX', 'ZLUX', 'MARX', 'POPX', 'MJHX', 'OOJX', 'IKIX', 'KLMX', 'MKLX', 'PPLX',
                    'NNNX', 'NPMX', 'ZASX', 'XXDX', 'DEDX'
                                                'DDDX', 'EEEX', 'FFFX', 'GGGX', 'HHHX', 'IIIX', 'JJJX', 'KKKX', 'LLLX', 'MMMX',
                    'NNNX', 'OOOX', 'PPPX', 'QQQX', 'RRRX', 'SSSX', 'TTTX', 'UUUX', 'VVVX', 'WWWX'
                    ]

# equity_positions = ['ABC', 'XYZ', 'UUU', 'RRR', 'TTT', 'DBA', 'ZLU', 'MAR', 'POP', 'MJH', 'OOJ', 'IKI', 'KLM', 'MKL', 'PPL', 'NNN', 'NPM', 'ZAS','XXD', 'DED'
#                     'DDD', 'EEE', 'FFF', 'GGG', 'HHH', 'III', 'JJJ', 'KKK', 'LLL', 'MMM', 'NNN', 'OOO', 'PPP', 'QQQ', 'RRR', 'SSS', 'TTT', 'UUU','VVV', 'WWW'
#                     ]

# Generate 'tickers' from equity_positions and currencies
tickers = [f"{ep} {cur}" for ep in equity_positions for cur in currencies]

# Generate a year's worth of business days
dates = pd.date_range(start='2022-01-01', end='2022-12-31', freq='B')

# Initialize an empty list to store transactions
transactions = []

# Dummy conversion rates - replace this with your actual rates
conversion_rates = {cur: random.uniform(0.5, 1.5) for cur in currencies}


#################enter lots here#################################

for ticker in tickers:
    equity_position, payment_currency = ticker.split()
    numlots = 50  # number of lots that will be purchased per investment


    from datetime import datetime

    initial_tradedate_str = '01-05-2022'
    initial_tradedate = datetime.strptime(initial_tradedate_str, '%d-%m-%Y')



    print(initial_tradedate)

    for i in range(1, numlots):  # This loop will generate initial buy transactions
        # ... Existing code ...

        # Randomly select a second of the day for tradedate
        seconds_in_a_day = 24 * 60 * 60  # Total seconds in a day
        random_second = random.randint(0, seconds_in_a_day - 1)
        initial_tradedate = initial_tradedate.replace(hour=random_second // 3600, minute=(random_second // 60) % 60,
                                                      second=random_second % 60)
        # For the first transaction, use the fetched initial price and fx rate
        if i == 1:
            randomized_price = 50
            randomized_fx_rate = 1
        else:
            # For subsequent transactions, use randomized values based on the initial prices and rates
            randomized_price = randomize_value(50)
            randomized_fx_rate = randomize_value(1)

        initial_quantity = np.random.randint(100, 1000) * 100
        initial_total_amount = initial_quantity * randomized_price
        initial_total_amount_base = initial_total_amount / randomized_fx_rate

        # Randomly select tradedate and settledate within the date range for the transaction
        #initial_tradedate = random.choice(dates)
        initial_settledate = initial_tradedate + pd.Timedelta(days=random.randint(1, 3))

        # For JPY, modify the initial_total_amount
        if payment_currency == 'JPY':
            initial_total_amount *= 120

        # Update the transactions list with the generated transaction data
        # Assuming other transaction details like 'ticker', 'equity_position', 'payment_currency', etc., are also included
#        transactions.append(transaction)
        # Create the initial buy transaction record and add it to the list
        initial_transaction = {
            'portfolio': 'MyPortfolio',
            'method': 'buy',
            'source': 'trading',
            'tradedate': initial_tradedate.strftime('%m/%d/%Y:%H:%M:%S'),
            'settledate': initial_settledate.strftime('%m/%d/%Y:%H:%M:%S'),
            'kdbegin': initial_tradedate.strftime('%m/%d/%Y:%H:%M:%S'),
            'kdend': '12/31/2099:00:00:00',
            'investment': equity_position,
            'payment_currency': payment_currency,
            'location': 'Goldman',
            'strategy': 'Growth',
            'quantity': initial_quantity,
            'total_amount': initial_total_amount,
            'total_amount_base': initial_total_amount_base,
            'tranid': len(transactions) + 1,
            'transaction': 'BuyLong',
            'old_shares': '',
            'new_shares': '',
            'per_share': '',
            'legin': "",
            'legout': "",
            'allocation_entities': "",
            'allocation_percents': "",
            'allocation_percents': "",
            'financial_account': "",
            'buy_currency': "",
            'sell_currency': "",
            'buy_amt': "",
            'sell_amt': "",
            'feeder': "",
            'financial_accounts':""
        }

        transactions.append(initial_transaction)
equity_positions_for_sales = []
equity_positions_for_sales = ['ABC', 'XYZ', 'UUU', 'RRR', 'TTT', 'DBA', 'ZLU', 'MAR', 'POP', 'MJH', 'OOJ', 'IKI', 'KLM', 'MKL', 'PPL', 'NNN', 'NPM', 'ZAS','XXD', 'DED'
                    'DDD', 'EEE', 'FFF', 'GGG', 'HHH', 'III', 'JJJ', 'KKK', 'LLL', 'MMM', 'NNN', 'OOO', 'PPP', 'QQQ', 'RRR', 'SSS', 'TTT', 'UUU','VVV', 'WWW'
                    ]

# equity_positions_for_sales = []
# equity_positions_for_sales = ['ABC', 'XYZ', 'UUU', 'RRR',  'NNN', 'NPM', 'ZAS','XXD', 'DED'
#                     ]




#equity_positions_for_sales = ['ABC', 'XYZ', 'UUU']  # Example subset
sells_per_position = 100  # Example: 3 sells per position
# Generate 'tickers' from equity_positions and currencies
#tickers = [f"{ep} {cur}" for ep in equity_positions_for_sales for cur in currencies]
for equity_position in equity_positions_for_sales:
    for _ in range(sells_per_position):
        # Generate sell transactions

        # Adjust the sell_quantity and sell_total_amount as per your logic
        sell_quantity = initial_quantity * 2
        sell_total_amount = initial_total_amount * 2

        possible_sell_dates = dates[dates > pd.Timestamp('2022-07-01') + pd.Timedelta(days=100)]
        if len(possible_sell_dates) == 0:
            continue
        sell_tradedate = random.choice(possible_sell_dates)
        sell_settledate = sell_tradedate + pd.Timedelta(days=random.randint(1, 3))

        # Assuming 'USD' as the payment currency for simplification. Adjust as needed.
        sell_total_amount_base = sell_total_amount / conversion_rates['USD']

        sell_transaction = {
            'portfolio': 'MyPortfolio',
            'method': 'sell',
            'source': 'trading',
            'tradedate': sell_tradedate.strftime('%m/%d/%Y:%H:%M:%S'),
            'settledate': sell_settledate.strftime('%m/%d/%Y:%H:%M:%S'),
            'kdbegin': sell_tradedate.strftime('%m/%d/%Y:%H:%M:%S'),
            'kdend': '12/31/2099:00:00:00',
            'investment': equity_position,
            'payment_currency': 'USD',  # Simplified for demonstration
            'location': 'Goldman',
            'strategy': 'Growth',
            'quantity': sell_quantity,
            'total_amount': sell_total_amount,
            'total_amount_base': sell_total_amount_base,
            'tranid': len(transactions) + 1,
            'transaction': 'SellLong',
            'old_shares': '',
            'new_shares': '',
            'per_share': '',
            'legin': "",
            'legout': "",
            'allocation_entities': "",
            'allocation_percents': "",
            'financial_account': "",
            'buy_currency': "",
            'sell_currency': "",
            'buy_amt': "",
            'sell_amt': "",
            'feeder': ""

        }

        transactions.append(sell_transaction)  # Add the sell transaction within the inner loop


actions = []
for action in actions:
    print(action)

    if action == "dividend":
        tran = 'StockCashDiv'
        per_share = 1
        old_shares = ''
        new_shares = ''
        tradedate ='06/15/2022:00:00:00'
        settledate ='06/16/2022:00:00:00'
        kdbegin =  '06/15/2022:00:00:00'
        kdend =  '12/31/2099:00:00:00'
        total_amount_base = ""
        total_amount = ""
        quantity = ""
        location = ""
        strategy = ""
        source ="operations"
        investment = 'ABC1'
        payment_currency = 'USD'

    if action == "split":
        tran = 'StockSplit'
        tradedate = '06/15/2022:00:00:00'
        settledate = '06/16/2022:00:00:00'
        kdbegin = '06/15/2022:00:00:00'
        kdend = '12/31/2099:00:00:00'
        total_amount_base = ""
        total_amount = ""
        quantity = ""
        location = ""
        strategy = ""
        per_share = ""
        old_shares = 2
        new_shares = 1
        source = 'operations'
        investment = 'ABC1'
        payment_currency = 'USD'
        allocation_entities = ""
        allocation_percents = ""

    if action == "deposit":
        tradedate = '01/04/2022:00:00:00'
        settledate = '01/04/2022:00:00:00'
        kdbegin = '01/04/2022:00:00:00'
        kdend = '12/31/2099:00:00:00'
        tran = "Deposit"
        quantity = 200000000
        total_amount = 200000000
        total_amount_base = 200000000
        location = "Goldman"
        strategy = "Growth"
        per_share = ''
        old_shares = ""
        new_shares = ""
        source = 'treasury'
        investment = 'USD'
        payment_currency = 'USD'
        allocation_entities = "",
        allocation_currencies ="",
        allocation_percents = "",
        financial_accounts = "",
        buy_currency = "",
        sell_currency = "",
        buy_amt = "",
        sell_amt = "",
        feeder = ""

    if action == "allocate":
        tran = 'Allocation'
        per_share = ''
        old_shares = ''
        new_shares = ''
        tradedate = '12/31/2022:23:59:59'
        settledate = '12/31/2022:23:59:59'
        kdbegin = '12/31/2022:23:59:59'
        kdend = '12/31/2099:00:00:00'
        total_amount_base = ""
        total_amount = ""
        quantity = ""
        location = ""
        strategy = ""
        source = "accounting"
        investment = ''
        payment_currency = ''
        allocation_entities = "ClassA_USD, ClassB, ClassC"
        allocation_percents = "33.333, 33.333, 33.334"
        financial_accounts = "",
        buy_currency = "",
        sell_currency = "",
        buy_amt = "",
        sell_amt = "",
        feeder = ""

    if action == "mark":
        tran = 'Mark-to-Market'
        per_share = ''
        old_shares = ''
        new_shares = ''
        tradedate = '12/31/2022:23:59:59'
        settledate = '12/31/2022:23:59:59'
        kdbegin = '12/31/2022:23:59:59'
        kdend = '12/31/2099:00:00:00'
        total_amount_base = ""
        total_amount = ""
        quantity = ""
        location = ""
        strategy = ""
        source = "accounting"
        investment = ''
        payment_currency = ''
        allocation_entities = ""
        allocation_percents = ""
        financial_accounts = "",
        buy_currency = "",
        sell_currency = "",
        buy_amt = "",
        sell_amt = "",
        feeder = ""

    action_transaction = {
        'portfolio': 'MyPortfolio',
        'method': action,
        'source': source,
        'tradedate': tradedate,
        'settledate': settledate,
        'kdbegin': kdbegin,
        'kdend': kdend,
        'investment':  investment,
        'payment_currency': payment_currency,
        'location': location,
        'strategy': strategy,
        'quantity': quantity,
        'total_amount': total_amount,
        'total_amount_base': total_amount_base,
        'tranid': len(transactions) + 1,
        'transaction': tran,
        'old_shares': old_shares,
        'new_shares': new_shares,
        'per_share': per_share,
        'legin': "",
        'legout': "",
        'allocation_entities': allocation_entities,
        'allocation_percents': allocation_percents,
        'financial_accounts' : "",
        'buy_currency' : "",
        'sell_currency' : "",
        'buy_amt' : "",
        'sell_amt' : "",
        'feeder' : ""

    }
    transactions.append(action_transaction)

# Create a DataFrame from the transactions list
df_transactions = pd.DataFrame(transactions)

# Save the DataFrame to an Excel file
output_file = 'C:/Users/hjmne/PycharmProjects/chest/refdata/portfolio1.xlsx'
df_transactions.to_excel(output_file, index=False)
#
# # Save the DataFrame with transactions to an Excel file
# 'C:/Users/hjmne/PycharmProjects/chest/refdata/portfolio1.xlsx'
# df_transactions.to_excel(output_file, index=False)
# print(f"Generated transactions saved to {output_file}")

# # Extract unique trade and settlement dates from the transactions DataFrame
# unique_trade_dates = df_transactions['tradedate'].unique()
# unique_settle_dates = df_transactions['settledate'].unique()
#
# # Combine trade and settle dates to get a unique set of dates
# all_unique_dates = np.unique(np.concatenate((unique_trade_dates, unique_settle_dates)))
#
# # Initialize lists to store data for the FX master DataFrame
# dates_list = []
# currencies_list = []
# prices_list = []
#
# # Populate the lists for the FX master DataFrame
# for date in all_unique_dates:
#     for currency in currencies:
#         dates_list.append(date)
#         currencies_list.append(currency)
#
#         # Define the price based on the currency
#         if currency == 'USD':
#             price = 1
#         elif currency == 'EUR':
#             price = random.uniform(0.888, 0.933)
#         elif currency == 'JPY':
#             price = random.uniform(138, 142)
#         elif currency == 'GBP':
#             price = random.uniform(0.73, 0.81)
#         elif currency == 'AUD':
#             price = random.uniform(1.45, 1.55)
#         prices_list.append(price)
#
# # Create the FX master DataFrame
# df_fx_master = pd.DataFrame({
#     'date': dates_list,
#     'currency': currencies_list,
#     'price': prices_list
# })
#
# # Strip the trailing time details from the date strings
# df_fx_master['date'] = df_fx_master['date'].str.split(":").str[0]
#
# # Now, convert the 'date' column to datetime
# df_fx_master['date'] = pd.to_datetime(df_fx_master['date'])
#
# # Format the date column to the desired format without leading zeros
# df_fx_master['date'] = df_fx_master['date'].apply(lambda x: f"{x.month}/{x.day}/{x.year}")
#
#
#
# #df_fx_master['date'] = df_fx_master['date'].dt.strftime('%-m/%-d/%Y')
# fx_output_file_csv = 'C:/Users/hjmne/PycharmProjects/chest/fx_master.csv'
# df_fx_master.to_csv(fx_output_file_csv, index=False)
#
# # fx_output_file_csv = 'C:/Users/hjmne/PycharmProjects/chest/fx_master.csv'
# # df_fx_master.to_csv(fx_output_file_csv, index=False)
#
#
# print(f"FX rates saved to {fx_output_file_csv}")
# import pandas as pd
# import numpy as np
# from datetime import datetime, timedelta
#
# # Defining the data structure
# ticker_currency_pairs = {
#     'ABC': 'USD', 'ABC1': 'USD', 'ABC2': 'USD', 'ABC3': 'USD', 'ABC4': 'USD', 'ABC5': 'USD',
#     'RR1': 'GBP', 'RR2': 'GBP', 'RR3': 'GBP', 'RR4': 'GBP', 'RR5': 'GBP',
#     'TTT1': 'AUD', 'TTT2': 'AUD', 'TTT3': 'AUD', 'TTT4': 'AUD', 'TTT5': 'AUD',
#     'UUU1': 'JPY', 'UUU2': 'JPY', 'UUU3': 'JPY', 'UUU4': 'JPY', 'UUU5': 'JPY',
#     'XYZ1': 'EUR', 'XYZ2': 'EUR', 'XYZ3': 'EUR', 'XYZ4': 'EUR', 'XYZ5': 'EUR',
#     'USD': 'USD', 'JPY': 'JPY', 'AUD': 'AUD', 'GBP': 'GBP', 'EUR': 'EUR',
# }
#
# # Your base data
# data = {
#     'date': ['12/31/2021']*len(ticker_currency_pairs),
#     'ticker': list(ticker_currency_pairs.keys()),
#     'currency': list(ticker_currency_pairs.values()),
#     'price': [100]*len(ticker_currency_pairs)  # Assuming a starting price of 100 for illustration
# }
# df = pd.DataFrame(data)
# df['date'] = pd.to_datetime(df['date'])
#
# # List of business days from Jan 4, 2021 to Dec 31, 2024
# business_days = pd.bdate_range(start='2021-01-04', end='2024-12-31')
#
# # Simulate prices
# simulated_prices = []
#
# for day in business_days:
#     prev_day_prices = df if day == business_days[0] else simulated_prices[-1]
#     new_prices = []
#     for index, row in prev_day_prices.iterrows():
#         if row['ticker'] in ['USD', 'AUD', 'GBP', 'JPY', 'EUR']:
#             new_price = 1
#         else:
#             random_factor = np.random.uniform(0.9, 1.1)
#             new_price = row['price'] * random_factor
#         new_prices.append(new_price)
#     df_day = prev_day_prices.copy()
#     df_day['price'] = new_prices
#     df_day['date'] = day
#     simulated_prices.append(df_day)
#
# # Combine all the simulated data
# simulated_df = pd.concat(simulated_prices)
# simulated_df.to_csv('C:/Users/hjmne/PycharmProjects/Chest/refdata/pricenew.csv', index=False)
#
# # Displaying a sample for illustration purposes
# print(simulated_df.head())
