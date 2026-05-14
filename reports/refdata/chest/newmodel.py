import pandas as pd
import random
import numpy as np

# Initialize an empty list to store transactions
transactions = []

# Initialize buys and sells per quarter
buys_per_quarter = [1000, 8000, 10000, 13000]  # Example: Buys ramp down each quarter
sells_per_quarter = [10, 3000, 4000, 6000]  # Example: Sells ramp up each quarter

# Define equity positions for buys
equity_positions_for_buys = ['ABC', 'XYZ', 'UUU', 'RRR', 'TTT', 'DBA', 'ZLU', 'MAR', 'POP', 'MJH', 'OOJ', 'IKI', 'KLM', 'MKL', 'PPL', 'NNN', 'NPM', 'ZAS', 'XXD', 'DED', 'DDD', 'EEE', 'FFF', 'GGG', 'HHH', 'III', 'JJJ', 'KKK', 'LLL', 'MMM', 'NNN', 'OOO', 'PPP', 'QQQ', 'RRR', 'SSS', 'TTT', 'UUU', 'VVV', 'WWW', 'ABCX', 'XYZXx', 'UUUX', 'RRRX', 'TTTX', 'DBAX', 'ZLUX', 'MARX', 'POPX', 'MJHX', 'OOJX', 'IKIX', 'KLMX', 'MKLX', 'PPLX', 'NNNX', 'NPMX', 'ZASX', 'XXDX', 'DEDX', 'DDDX', 'EEEX', 'FFFX', 'GGGX', 'HHHX', 'IIIX', 'JJJX', 'KKKX', 'LLLX', 'MMMX', 'NNNX', 'OOOX', 'PPPX', 'QQQX', 'RRRX', 'SSSX', 'TTTX', 'UUUX', 'VVVX', 'WWWX']

# Define equity positions for sells
equity_positions_for_sales = ['ABC', 'XYZ', 'UUU', 'RRR', 'TTT', 'DBA', 'ZLU', 'MAR', 'POP', 'MJH', 'OOJ', 'IKI', 'KLM', 'MKL', 'PPL', 'NNN', 'NPM', 'ZAS', 'XXD', 'DED', 'DDD', 'EEE', 'FFF', 'GGG', 'HHH', 'III', 'JJJ', 'KKK', 'LLL', 'MMM', 'NNN', 'OOO', 'PPP', 'QQQ', 'RRR', 'SSS', 'TTT', 'UUU', 'VVV', 'WWW']

# Initialize a dictionary to track purchased quantities for each equity position
purchased_quantities = {equity_position: 0 for equity_position in equity_positions_for_buys}

# Loop through each quarter
for quarter in range(4):
    # Adjust buys and sells for the quarter
    buys = buys_per_quarter[quarter]
    sells = sells_per_quarter[quarter]

    # Loop through equity positions for buys
    for equity_position in equity_positions_for_buys:
        num_lots_per_buy = buys // len(equity_positions_for_buys)  # Distribute buys evenly across positions
        dates = pd.date_range(start='2022-01-01', end='2022-12-31', freq='B')

        for _ in range(num_lots_per_buy):
            # Generate buy transactions for this quarter
            # Adjust quantities, prices, and dates accordingly
            # Generate a year's worth of business days

            # Example: Assuming buys evenly spread across the quarter
            buy_tradedate = random.choice(dates[quarter * len(dates) // 4: (quarter + 1) * len(dates) // 4])
            buy_tradedate_str = buy_tradedate.strftime('%m/%d/%Y:%H:%M:%S')  # Format datetime string
            buy_quantity = np.random.randint(100, 1000) * 100  # Example: Random quantity
            buy_price = random.uniform(50, 100)  # Example: Random price
            buy_fx_rate = random.uniform(0.5, 1.5)  # Example: Random FX rate
            buy_total_amount = buy_quantity * buy_price
            buy_total_amount_base = buy_total_amount / buy_fx_rate

            # Append buy transaction to transactions list only if quantity is non-zero
            if buy_quantity > 0:
                buy_transaction = {
                    'portfolio': 'MyPortfolio',
                    'method': 'buy',
                    'source': 'trading',
                    'tradedate': buy_tradedate_str,
                    'settledate': (buy_tradedate + pd.Timedelta(days=random.randint(1, 3))).strftime(
                        '%m/%d/%Y:%H:%M:%S'),
                    'kdbegin': buy_tradedate_str,
                    'kdend': '12/31/2099:00:00:00',
                    'investment': equity_position,
                    'payment_currency': 'USD',  # Assuming USD as payment currency
                    'location': 'Goldman',
                    'strategy': 'Growth',
                    'quantity': buy_quantity,
                    'total_amount': buy_total_amount,
                    'total_amount_base': buy_total_amount_base,
                    'tranid': len(transactions) + 1,
                    'transaction': 'BuyLong',
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
                    'feeder': "",
                    'financial_accounts': ""
                    # Add other transaction details as needed
                }
                transactions.append(buy_transaction)

                # Update purchased quantity for the equity position
                purchased_quantities[equity_position] += buy_quantity

    # Loop through equity positions for sells
    for equity_position in equity_positions_for_sales:
        num_sells_per_position = sells // len(equity_positions_for_sales)  # Distribute sells evenly across positions
        for _ in range(num_sells_per_position):
            # Generate sell transactions for this quarter
            # Adjust quantities, prices, and dates accordingly

            # Example: Assuming sells evenly spread across the quarter
            sell_tradedate = random.choice(dates[quarter * len(dates) // 4: (quarter + 1) * len(dates) // 4])
            sell_tradedate_str = sell_tradedate.strftime('%m/%d/%Y:%H:%M:%S')  # Format datetime string
            sell_quantity = np.random.randint(100, 1000) * 50  # Example: Random quantity

            # Check available quantity for selling
            available_quantity = purchased_quantities.get(equity_position, 0)
            if sell_quantity == 0:
                print("Here")
            if available_quantity >= sell_quantity and sell_quantity > 0:  # Ensure sell quantity is non-zero
                # If available quantity is sufficient and sell quantity is non-zero, proceed with the sell transaction
                sell_price = random.uniform(50, 100)  # Example: Random price
                sell_fx_rate = random.uniform(0.5, 1.5)  # Example: Random FX rate
                sell_total_amount = sell_quantity * sell_price
                sell_total_amount_base = sell_total_amount / sell_fx_rate

                # Append sell transaction to transactions list
                sell_transaction = {
                    'portfolio': 'MyPortfolio',
                    'method': 'sell',
                    'source': 'trading',
                    'tradedate': sell_tradedate_str,
                    'settledate': (sell_tradedate + pd.Timedelta(days=random.randint(1, 3))).strftime(
                        '%m/%d/%Y:%H:%M:%S'),
                    'kdbegin': sell_tradedate_str,
                    'kdend': '12/31/2099:00:00:00',
                    'investment': equity_position,
                    'payment_currency': 'USD',  # Assuming USD as payment currency
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
                    'feeder': "",
                    'financial_accounts': ""
                    # Add other transaction details as needed
                }
                transactions.append(sell_transaction)

                # Update purchased quantity after selling
                purchased_quantities[equity_position] -= sell_quantity
            else:
                if sell_quantity <= 0:
                    print(f"Ignored sell transaction for {equity_position} due to zero or negative quantity.")
                elif available_quantity < sell_quantity:
                    print(f"Oversold condition detected for {equity_position}. Adjusting sell quantity.")
                    sell_quantity = available_quantity  # Adjust sell quantity to available quantity
                    # Proceed with the sell transaction with adjusted quantity
                    sell_price = random.uniform(50, 100)  # Example: Random price
                    sell_fx_rate = random.uniform(0.5, 1.5)  # Example: Random FX rate
                    sell_total_amount = sell_quantity * sell_price
                    sell_total_amount_base = sell_total_amount / sell_fx_rate


                    if sell_quantity ==0:
                        continue
                    # Append sell transaction to transactions list
                    sell_transaction = {

                        'portfolio': 'MyPortfolio',
                        'method': 'sell',
                        'source': 'trading',
                        'tradedate': sell_tradedate_str,
                        'settledate': (sell_tradedate + pd.Timedelta(days=random.randint(1, 3))).strftime(
                            '%m/%d/%Y:%H:%M:%S'),
                        'kdbegin': sell_tradedate_str,
                        'kdend': '12/31/2099:00:00:00',
                        'investment': equity_position,
                        'payment_currency': 'USD',  # Assuming USD as payment currency
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
                        'feeder': "",
                        'financial_accounts': ""
                        # Add other transaction details as needed
                    }
                    transactions.append(sell_transaction)
                    purchased_quantities[equity_position] -= sell_quantity
                    # Update purchased quantity after selling
                    #purchased_quantities[equity_position] = 0  # Reset purchased quantity to zero after adjusting sell quantity

df_transactions = pd.DataFrame(transactions)

# Save the DataFrame to an Excel file
output_file = 'C:/Users/hjmne/PycharmProjects/chest/refdata/ScaleTestRealTime.csv'
df_transactions.to_csv(output_file, index=False)
