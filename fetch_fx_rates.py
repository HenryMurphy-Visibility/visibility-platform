import yfinance as yf
import pandas as pd


def fetch_fx_rates(start_date, end_date, currencies):
    base_currency = "USD"
    fx_data = []

    for currency in currencies:
        if currency == base_currency:
            dates = pd.date_range(start=start_date, end=end_date, freq="B")
            rates = [1.0] * len(dates)
            fx_data.extend([{"date": date.strftime("%m/%d/%Y"), "currency": currency, "price": rate}
                            for date, rate in zip(dates, rates)])
        else:
            pair = f"{currency}=X"
            ticker = yf.Ticker(pair)
            hist = ticker.history(start=start_date, end=end_date)

            if not hist.empty:
                hist.reset_index(inplace=True)
                hist["date"] = hist["Date"].dt.strftime("%m/%d/%Y")
                hist["currency"] = currency
                hist["price"] = hist["Close"]
                fx_data.extend(hist[["date", "currency", "price"]].to_dict(orient="records"))

    return pd.DataFrame(fx_data)


# Fetch FX rates
currencies = ["AUD", "EUR", "GBP", "JPY", "USD"]
start_date = "2023-01-01"
end_date = "2024-12-12"

fx_rates_df = fetch_fx_rates(start_date, end_date, currencies)
fx_rates_df.to_csv("fx_master.csv", index=False)
print("FX rates saved to fx_master.csv")
