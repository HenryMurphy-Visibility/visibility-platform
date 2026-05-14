import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = r"C:/Users/hjmne/PycharmProjects/chest"
REFDATA = os.path.join(BASE_DIR, "refdata")
POOLTEST = os.path.join(REFDATA, "pooltest")

IM_FILE = os.path.join(REFDATA, "investment_master.csv")
PRICE_FILE = os.path.join(REFDATA, "price_master.csv")
FX_FILE = os.path.join(REFDATA, "fx_master.csv")
HOLIDAYS_FILE = os.path.join(REFDATA, "holidays.csv")

OUT_FILE = os.path.join(POOLTEST, "Portfolio1.csv")

START_DATE = datetime(2021, 1, 1)
END_DATE = datetime(2025, 12, 9)

TRADES_PER_DAY_MIN = 20
TRADES_PER_DAY_MAX = 50

QTY_MIN = 500
QTY_MAX = 5000

KD_END = "12/31/2099:00:00:00"


# ============================================================
# BUSINESS DAY CALENDAR
# ============================================================

def load_holidays(path):
    if not os.path.exists(path):
        print("⚠ No holiday file found. Only weekends removed.")
        return set()
    df = pd.read_csv(path)
    return set(pd.to_datetime(df["date"]).dt.date)


def generate_business_days(start, end, holidays):
    cur = start
    out = []
    while cur <= end:
        if cur.weekday() < 5 and cur.date() not in holidays:
            out.append(cur)
        cur += timedelta(days=1)
    return out


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def fmt_date(dt):
    return dt.strftime("%m/%d/%Y") + ":00:00:00"


def t_plus_2(date, business_days):
    idx = business_days.index(date)
    j = min(idx + 2, len(business_days) - 1)
    return business_days[j]


# ============================================================
# MAIN LOADING
# ============================================================

def load_equity_universe():
    im = pd.read_csv(IM_FILE)
    im = im[im["investment_type"].str.upper() == "EQUITY"]
    return sorted(im["investment"].unique())


def load_price_fx():
    px = pd.read_csv(PRICE_FILE)
    fx = pd.read_csv(FX_FILE)
    return px, fx


# ============================================================
# TICKER → LOCATION ASSIGNMENT (DETERMINISTIC)
# ============================================================

def assign_locations(tickers):
    locs = ["Goldman", "Morgan"]
    mapping = {}
    for i, t in enumerate(tickers):
        mapping[t] = locs[i % 2]
    return mapping


# ============================================================
# POSITION ENGINE
# ============================================================

class PositionTracker:
    """
    Tracks (ticker, location) positions so SELLs never exceed available quantity.
    """

    def __init__(self):
        self.pos = {}  # key: (ticker, location)

    def get(self, ticker, loc):
        return self.pos.get((ticker, loc), 0)

    def apply_buy(self, ticker, loc, qty):
        self.pos[(ticker, loc)] = self.get(ticker, loc) + qty
        return "buy_equity", "EquityPurchase", qty

    def apply_sell(self, ticker, loc, qty):
        available = self.get(ticker, loc)
        if available <= 0:
            # Must buy instead
            return self.apply_buy(ticker, loc, qty)

        qsell = min(qty, available)
        self.pos[(ticker, loc)] = available - qsell
        return "sell_equity", "EquitySale", qsell


# ============================================================
# TRADE GENERATOR
# ============================================================

def generate_trades():
    holidays = load_holidays(HOLIDAYS_FILE)
    business_days = generate_business_days(START_DATE, END_DATE, holidays)

    tickers = load_equity_universe()
    ticker_to_loc = assign_locations(tickers)

    price_df, fx_df = load_price_fx()

    # Quick index optimizations
    price_index = price_df.set_index(["date", "ticker", "currency"])
    fx_index = fx_df.set_index(["date", "currency"])

    price_index = price_index.sort_index()
    fx_index = fx_index.sort_index()

    pos = PositionTracker()

    rows = []
    tranid_counter = 1

    rng = np.random.default_rng(12345)

    for day in business_days:
        nd = rng.integers(TRADES_PER_DAY_MIN, TRADES_PER_DAY_MAX + 1)
        tdate_str = day.strftime("%Y-%m-%d")

        for _ in range(nd):
            # Select ticker
            tkr = tickers[rng.integers(0, len(tickers))]
            loc = ticker_to_loc[tkr]

            # Price (base daily)
            try:
                # ALWAYS use USD price for equities (your entire universe is currently USD)
                lookup_key = (tdate_str, tkr, "USD")

                try:
                    px = price_index.loc[lookup_key, "price"]
                except KeyError:
                    # No USD listing for this date/ticker -> skip trade
                    continue

                # If duplicate rows still exist, px may be a Series
                if isinstance(px, pd.Series):
                    px = px.iloc[0]

                base_price = float(px)
            except KeyError:
                # No price for this date/ticker → skip
                continue

            # Trade price with ±0.25% variation
            shock = rng.uniform(-0.0025, 0.0025)
            trade_price = base_price * (1 + shock)

            # Quantity
            qty = int(rng.integers(QTY_MIN, QTY_MAX + 1))

            # FX
            currency = "USD"
            try:
                fx_rate = float(fx_index.loc[(tdate_str, currency), "price"])
            except KeyError:
                fx_rate = 1.0

            # BUY or SELL logic
            if rng.random() < 0.5:
                method, trx, q_final = pos.apply_buy(tkr, loc, qty)
            else:
                method, trx, q_final = pos.apply_sell(tkr, loc, qty)

            # Local & Book
            local_amt = q_final * trade_price
            book_amt = local_amt * fx_rate

            # Dates
            tradedate = fmt_date(day)
            settledate = fmt_date(t_plus_2(day, business_days))
            last_updated = tradedate
            kdbegin = tradedate



            # Append row
            rows.append([
                last_updated,
                "Portfolio1",
                method,
                "trading",
                tradedate,
                settledate,
                kdbegin,
                KD_END,
                tkr,
                currency,       # payment_currency
                f"{fx_rate:.8f}" if currency != "USD" else "",  # tdate_fx
                loc,
                "",             # strategy (blank)
                q_final,
                round(trade_price, 6),
                "",             # notional (blank)
                "",             # original_face
                round(local_amt, 6),
                round(book_amt, 6),
                tranid_counter,
                trx,
                "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""
            ])

            tranid_counter += 1

    return rows


# ============================================================
# MAIN
# ============================================================

def main():
    rows = generate_trades()

    columns = [
        "last_updated","portfolio","method","source","tradedate","settledate",
        "kdbegin","kdend","investment","payment_currency","tdate_fx","location",
        "strategy","quantity","price","notional","original_face","total_amount",
        "total_amount_base","tranid","transaction","accrued_local","accrued_book",
        "new_shares","old_shares","per_share","legin","legout",
        "allocation_entities","allocation_percents","financial_account",
        "buy_currency","sell_currency","buy_amt","sell_amt","feeder","put_call"
    ]

    df = pd.DataFrame(rows, columns=columns)
    df.to_csv(OUT_FILE, index=False)
    print(f"✨ Portfolio1.csv generated successfully!\n → {OUT_FILE}")


if __name__ == "__main__":
    main()
