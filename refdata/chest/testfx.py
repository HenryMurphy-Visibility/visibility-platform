import csv
from collections import defaultdict
from datetime import datetime

def load_fx_data_from_csv(filepath):
    fx_data = defaultdict(dict)  # Nested dictionary
    with open(filepath, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            currency = row['currency']
            date = row['date']
            rate = float(row['price'])
            fx_data[currency][date] = rate
    return fx_data

def format_date(date):
    # Convert the date to a datetime object if it is a string
    if isinstance(date, str):
        date = datetime.strptime(date, '%m/%d/%Y')
    # Manually format the date without leading zeros for month and day
    return f"{date.month}/{date.day}/{date.year}"

def get_fx_rate(currency, date, fx_data):
    # Ensure the date is in the correct format (MM/DD/YYYY without leading zeros)
    formatted_date = format_date(date)
    print(f"Looking for FX rate for {currency} on {formatted_date}")

    if currency in fx_data:
        available_dates = list(fx_data[currency].keys())
        print(f"Available dates for {currency}: {available_dates}")

        if formatted_date in fx_data[currency]:
            return fx_data[currency][formatted_date]
        else:
            # If the exact date is not found, find the closest earlier date
            previous_dates = [d for d in available_dates if d <= formatted_date]
            if previous_dates:
                closest_date = max(previous_dates, key=lambda d: datetime.strptime(d, '%m/%d/%Y'))
                print(f"Closest available date for {currency} is {closest_date}")
                return fx_data[currency][closest_date]
            else:
                raise ValueError(f"FX rate for {currency} on {formatted_date} not found and no previous rates available")
    else:
        raise ValueError(f"Currency {currency} not found in fx_data")

# Example usage
fx_file_path = 'C:/Users/hjmne/PycharmProjects/chest/refdata/fx_master.csv'
fx_data = load_fx_data_from_csv(fx_file_path)

# Test scenarios
test_cases = [
    ('USD', '1/1/2022'),
    ('EUR', '1/2/2022'),
    ('JPY', '1/3/2022'),
    ('GBP', '1/1/2022'),  # Should find the closest previous date
    ('GBP', '1/2/2022'),
    ('EUR', '1/4/2022')  # Should find the closest previous date
]

for currency, date in test_cases:
    try:
        fx_rate = get_fx_rate(currency, date, fx_data)
        print(f"FX rate for {currency} on {date}: {fx_rate}")
    except ValueError as e:
        print(e)
