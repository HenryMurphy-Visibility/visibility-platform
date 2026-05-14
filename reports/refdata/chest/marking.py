import pandas as pd

def load_price_data(csv_file):
    df = pd.read_csv(csv_file)
    price_data = {}
    for index, row in df.iterrows():
        ticker = row['ticker']
        date = row['date']
        price = row['price']
        if ticker not in price_data:
            price_data[ticker] = {}
        price_data[ticker][date] = price
    return price_data

# Example usage
price_data = load_price_data("C:/users/hjmne/pycharmprojects/chest/refdata/price_master.csv")


from datetime import datetime

def format_date(date):
    if isinstance(date, str):
        date = datetime.strptime(date, '%m/%d/%Y')
    return f"{date.month}/{date.day}/{date.year}"

def get_price(ticker, date, price_data):
    formatted_date = format_date(date)
    print(f"Looking for price for {ticker} on {formatted_date}")

    if ticker not in price_data:
        raise ValueError(f"Ticker {ticker} not found in price_data")

    available_dates = price_data[ticker].keys()
    print(f"Available dates for {ticker}: {available_dates}")

    if formatted_date in price_data[ticker]:
        return price_data[ticker][formatted_date]
    else:
        previous_dates = [d for d in available_dates if d <= formatted_date]
        if previous_dates:
            closest_date = max(previous_dates, key=lambda d: datetime.strptime(d, '%m/%d/%Y'))
            print(f"Closest previous available date for {ticker} is {closest_date}")
            return price_data[ticker][closest_date]
        else:
            next_dates = [d for d in available_dates if d > formatted_date]
            if next_dates:
                closest_date = min(next_dates, key=lambda d: datetime.strptime(d, '%m/%d/%Y'))
                print(f"Closest next available date for {ticker} is {closest_date}")
                return price_data[ticker][closest_date]
            else:
                raise ValueError(f"Price for {ticker} on {formatted_date} not found and no previous or next prices available")

# Load price data from CSV
load_price_data("C:/users/hjmne/pycharmprojects/chest/refdata/price_master.csv")

# Fetch price for 'ABC' on '01/02/2023'
price = get_price('ABC1', '01/01/2023', price_data)
print(price)  # Output: 102

# Fetch price for 'XYZ' on '01/04/2023' (should fetch the closest previous date)
price = get_price('ABC4', '01/01/2022', price_data)
print(price)  # Output: 204
