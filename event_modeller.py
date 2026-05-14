import os
import csv
import random
from datetime import datetime, timedelta
from collections import defaultdict

# ============================================================
# PATHS — EXPLICIT
# ============================================================

IM_PATH    = "c:/Users/hjmne/pycharmprojects/chest/refdata/investment_master.csv"
PRICE_PATH = "c:/Users/hjmne/pycharmprojects/chest/refdata/price_master.csv"
FX_PATH    = "c:/Users/hjmne/pycharmprojects/chest/refdata/fx_master.csv"

# ============================================================
# VISIBILITY TEMPORAL CONSTANTS
# ============================================================

V_TS_FORMAT = "%m/%d/%Y:%H:%M:%S"
V_KDEND     = datetime.strptime("12/31/2099:00:00:00", V_TS_FORMAT)

def vdt(dt: datetime) -> str:
    return dt.strftime(V_TS_FORMAT)

# ============================================================
# CANONICAL EVENT SCHEMA (AUTHORITATIVE)
# ============================================================

CANONICAL_EVENT_FIELDS = [
    "last_updated",
    "portfolio",
    "method",
    "source",
    "tradedate",
    "settledate",
    "kdbegin",
    "kdend",
    "investment",
    "payment_currency",
    "tdate_fx",
    "location",
    "strategy",
    "quantity",
    "price",
    "notional",
    "original_face",
    "total_amount",
    "total_amount_base",
    "tranid",
    "transaction",
    "accrued_local",
    "accrued_book",
    "new_shares",
    "old_shares",
    "per_share",
    "legin",
    "legout",
    "allocation_entities",
    "allocation_percents",
    "financial_account",
    "buy_currency",
    "sell_currency",
    "buy_amt",
    "sell_amt",
    "feeder",
    "put_call",
    "mark_price",
    "mark_fx",
    "per_100FV_accrual",
    "per_100FV_amort",
]

CANONICAL_EVENT_TEMPLATE = {k: "" for k in CANONICAL_EVENT_FIELDS}

# ============================================================
# MODELLER PARAMETERS — TYPE 1
# ============================================================

START_DATE = datetime.strptime("01/02/2021:00:00:00", V_TS_FORMAT)
END_DATE   = datetime.strptime("12/31/2025:00:00:00", V_TS_FORMAT)

TRADES_PER_DAY = 60
SETTLEMENT_LAG = 2

MIN_SHARES = 500
MAX_SHARES = 5_000

PRICE_OFFSET_PCT = 0.005
BASE_RANDOM_SEED = 42

# ============================================================
# LOADERS — ROW FACTS
# ============================================================

def load_investment_master(path):
    im = {}
    with open(path, newline="", encoding="cp1252") as f:
        reader = csv.DictReader(f)
        assert "investment" in reader.fieldnames
        for r in reader:
            if r["investment"]:
                im[r["investment"]] = r
    print(f"✅ Loaded Investment Master: {len(im)} instruments")
    return im

def load_price_data_as_rows(path):
    rows = []
    with open(path, newline="", encoding="cp1252") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "date": datetime.strptime(r["date"], "%m/%d/%Y"),
                "ticker": r["ticker"],
                "currency": r["currency"],
                "price": float(r["price"]),
            })
    print(f"✅ Loaded Price Rows: {len(rows)}")
    return rows

def load_fx_data_as_rows(path):
    rows = []
    with open(path, newline="", encoding="cp1252") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "date": datetime.strptime(r["date"], "%m/%d/%Y"),
                "currency": r["currency"],
                "price": float(r["price"]),
            })
    print(f"✅ Loaded FX Rows: {len(rows)}")
    return rows

def build_business_days(start, end):
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    print(f"✅ Built Business Days: {len(days)}")
    return days

# ============================================================
# EVENT MODELLER — TYPE 1 (USD EQUITIES)
# ============================================================

class EventModellerType1:

    def __init__(self, portfolio, investment_master, price_rows, fx_rows, business_days):
        random.seed(BASE_RANDOM_SEED + abs(hash(portfolio)) % 10_000)

        self.portfolio = portfolio
        self.im = investment_master
        self.price_rows = price_rows
        self.fx_rows = fx_rows
        self.business_days = business_days

        self.tranid_counter = 1
        self.events = []

        self.equities = [
            inv for inv, r in self.im.items()
            if r.get("investment_type") == "EQUITY"
            and r.get("currency") == "USD"
        ]
        assert self.equities, "❌ No USD equities found"

        self.price_lookup = {
            (r["ticker"], r["date"].date()): r["price"]
            for r in self.price_rows
            if r["currency"] == "USD"
        }
        assert self.price_lookup, "❌ Price lookup empty"

        self.open_positions = defaultdict(int)

        print(f"▶️ {portfolio}: {len(self.equities)} USD equities")

    def _settle_date(self, trade_dt):
        idx = self.business_days.index(trade_dt)
        if idx + SETTLEMENT_LAG >= len(self.business_days):
            return None
        return self.business_days[idx + SETTLEMENT_LAG]

    def _price(self, ticker, trade_dt):
        base = self.price_lookup[(ticker, trade_dt.date())]
        return round(base * (1 + random.uniform(-PRICE_OFFSET_PCT, PRICE_OFFSET_PCT)), 6)

    def _event(self, method, ticker, qty, price, trade_dt, settle_dt):
        tranid = self.tranid_counter
        self.tranid_counter += 1

        def vdt(dt):
            return dt.strftime(V_TS_FORMAT)

        return {
            # --------------------------------------------------
            # Identity / lineage
            # --------------------------------------------------
            "last_updated": vdt(trade_dt),
            "portfolio": self.portfolio,
            "method": method,
            "source": "trading",

            # --------------------------------------------------
            # Temporal (Visibility canonical)
            # --------------------------------------------------
            "tradedate": vdt(trade_dt),
            "settledate": vdt(settle_dt),
            "kdbegin": vdt(trade_dt),
            "kdend": vdt(V_KDEND),

            # --------------------------------------------------
            # Instrument
            # --------------------------------------------------
            "investment": ticker,
            "payment_currency": "USD",
            "tdate_fx": 0,

            # --------------------------------------------------
            # Attribution (LOCKED)
            # --------------------------------------------------
            "location": "Goldman",
            "strategy": "Core",
            "financial_account": "",

            # --------------------------------------------------
            # Economics
            # --------------------------------------------------
            "quantity": qty,
            "price": price,
            "notional": 0,
            "original_face": 0,
            "total_amount": qty * price,
            "total_amount_base": qty * price,

            # --------------------------------------------------
            # Transaction identity
            # --------------------------------------------------
            "tranid": tranid,
            "transaction": (
                "EquityPurchase"
                if method == "buy_equity"
                else "EquitySale"
            ),

            # --------------------------------------------------
            # Accrual / position mechanics
            # --------------------------------------------------
            "accrued_local": 0,
            "accrued_book": 0,
            "new_shares": qty if method == "buy_equity" else 0,
            "old_shares": 0,
            "per_share": 0,

            # --------------------------------------------------
            # Structural placeholders (REQUIRED)
            # --------------------------------------------------
            "legin": "",
            "legout": "",
            "allocation_entities": "",
            "allocation_percents": "",
            "buy_currency": "",
            "sell_currency": "",
            "buy_amt": 0,
            "sell_amt": 0,
            "feeder": "",
            "put_call": "",
            "mark_price": 0,
            "mark_fx": 0,
            "per_100FV_accrual": 0,
            "per_100FV_amort": 0,
        }


    def run(self):
        for i, trade_dt in enumerate(self.business_days, 1):
            if i == 1 or i % 50 == 0:
                print(f"  ⏳ {self.portfolio}: day {i}/{len(self.business_days)}")

            for _ in range(TRADES_PER_DAY):
                ticker = random.choice(self.equities)
                open_qty = self.open_positions[ticker]

                method = (
                    "buy_equity"
                    if open_qty == 0 or random.random() > 0.4
                    else "sell_equity"
                )

                qty = random.randint(MIN_SHARES, MAX_SHARES)

                if method == "sell_equity":
                    if open_qty < qty:
                        continue
                    self.open_positions[ticker] -= qty
                else:
                    self.open_positions[ticker] += qty

                settle_dt = self._settle_date(trade_dt)
                if not settle_dt:
                    continue

                price = self._price(ticker, trade_dt)

                self.events.append(
                    self._event(method, ticker, qty, price, trade_dt, settle_dt)
                )

        print(f"✅ {self.portfolio}: {len(self.events):,} events")
        return self.events

# ============================================================
# OUTPUT
# ============================================================

def write_events(portfolio, events):
    out_dir = f"c:/Users/hjmne/pycharmprojects/chest/funds/{portfolio}/Events"
    os.makedirs(out_dir, exist_ok=True)
    path = f"{out_dir}/{portfolio}.csv"

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANONICAL_EVENT_FIELDS)
        writer.writeheader()
        writer.writerows(events)

    print(f"📄 Wrote {len(events):,} → {path}")

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("🚀 RUNNING TYPE 1 EVENT MODELLER")

    investment_master = load_investment_master(IM_PATH)
    price_rows = load_price_data_as_rows(PRICE_PATH)
    fx_rows = load_fx_data_as_rows(FX_PATH)
    business_days = build_business_days(START_DATE, END_DATE)

    modeller = EventModellerType1(
        "Portfolio1",
        investment_master,
        price_rows,
        fx_rows,
        business_days,
    )

    events = modeller.run()
    write_events("Portfolio1", events)
