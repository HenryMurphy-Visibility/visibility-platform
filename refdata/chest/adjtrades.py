import pandas as pd

# Define file paths
portfolio_path = 'C:/Users/hjmne/PycharmProjects/chest/refdata/portfolio1.xlsx'
price_path = 'C:/Users/hjmne/PycharmProjects/chest/refdata/price_master.csv'
fx_path = 'C:/Users/hjmne/PycharmProjects/chest/refdata/fx_master.csv'

# Load the data
portfolio_df = pd.read_excel(portfolio_path)
price_df = pd.read_csv(price_path)
fx_df = pd.read_csv(fx_path)

# Replace colon (:) with a space ( ) before converting to datetime
portfolio_df['tradedate'] = pd.to_datetime(portfolio_df['tradedate'], format='%m/%d/%Y:%H:%M:%S')





# Convert dates to datetime objects for better comparison
price_df['date'] = pd.to_datetime(price_df['date'])
fx_df['date'] = pd.to_datetime(fx_df['date'])

# Function to find the price for the given ticker and trade date
def fetch_price(ticker, tradedate):
    price = price_df[(price_df['ticker'] == ticker) & (price_df['date'] == tradedate)]['price']
    return price.iloc[0] if not price.empty else None

# Function to find the fx rate for the given currency and trade date
def fetch_fx_rate(currency, tradedate):
    fx_rate = fx_df[(fx_df['currency'] == currency) & (fx_df['date'] == tradedate)]['price']
    return fx_rate.iloc[0] if not fx_rate.empty else None

# Process each row in the portfolio
for index, row in portfolio_df.iterrows():
    if row['method'] in ['buy', 'sell']:
        # If payment_currency is JPY, multiply quantity by 10
        quantity = row['quantity'] * 10 if row['payment_currency'] == 'JPY' else row['quantity']

        # Fetch the price and fx rate
        price = fetch_price(row['investment'], row['tradedate'])
        fx_rate = fetch_fx_rate(row['payment_currency'], row['tradedate'])

        # Continue only if we found both price and fx rate
        if price is not None and fx_rate is not None:
            # Calculate new total_amount and total_amount_base
            portfolio_df.at[index, 'total_amount'] = quantity * price
            portfolio_df.at[index, 'total_amount_base'] = portfolio_df.at[index, 'total_amount'] * fx_rate

# Save the modified dataframe back to an xlsx file
output_path = 'C:/Users/hjmne/PycharmProjects/chest/refdata/portfolio1_modified.xlsx'
portfolio_df.to_excel(output_path, index=False)

print(f"Updated portfolio saved to {output_path}")
