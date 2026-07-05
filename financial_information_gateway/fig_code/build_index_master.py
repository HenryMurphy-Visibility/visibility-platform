"""
build_index_master.py  —  ONE-TIME prep script (run locally, not part of compute)

Fetches four benchmark series, rebases each to 1.0 at the base date, and writes
chest/refdata/index_master.csv.  Performance reads that file forever after; this
script never runs at compute time.

Why levels, not returns:
    We store the rebased LEVEL path (base = 1.0), never the daily returns.
    A return over any window — daily, monthly, since-inception — is derived from
    two levels (level_end / level_start - 1).  Returns cannot be re-aggregated
    back into a clean level path (gaps corrupt the chain).  Levels are the
    lossless, frequency-agnostic primitive; returns are a view computed on demand.

Why adjusted close:
    IEF is a bond ETF — its PRICE return omits coupon income, understating total
    return.  Adjusted close folds distributions back in, so all four series are
    TOTAL-return levels, not price-only.

Run:  python build_index_master.py
Requires:  pip install yfinance pandas
"""

import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

# ── EDIT THIS if your refdata lives elsewhere ──────────────────────────────
REFDATA_PATH = r"C:/Users/hjmne/PycharmProjects/chest/refdata"

# Canonical key -> Yahoo ticker.  Keys are what the loader and portfolio.json use.
TICKERS = {
    "SPX":  "^GSPC",   # S&P 500
    "IXIC": "^IXIC",   # NASDAQ Composite
    "RUT":  "^RUT",    # Russell 2000
    "IEF":  "IEF",     # iShares 7-10yr Treasury (total return via adj close)
}

START = "2020-12-31"   # base date — every series rebased to 1.0 here
END   = "2025-12-31"


def _adjusted_close(ticker: str) -> pd.Series:
    """
    Download one ticker and return its adjusted-close series.
    Handles both old and new yfinance defaults (Adj Close vs auto-adjusted Close).
    """
    df = yf.download(ticker, start=START, end=END, auto_adjust=False, progress=False)
    if df is None or df.empty:
        raise RuntimeError(f"No data returned for {ticker}")

    # New yfinance can return a column MultiIndex even for a single ticker.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if "Adj Close" in df.columns:
        s = df["Adj Close"]
    elif "Close" in df.columns:
        s = df["Close"]
    else:
        raise RuntimeError(f"{ticker}: no Adj Close or Close column found")

    s = s.dropna()
    s.index = pd.to_datetime(s.index).normalize()
    return s


def build():
    series_by_key = {}
    for key, ticker in TICKERS.items():
        print(f">>> fetching {key} ({ticker}) ...")
        raw = _adjusted_close(ticker)
        # Rebase to 1.0 at the first available value (the base date).
        rebased = raw / raw.iloc[0]
        series_by_key[key] = rebased
        print(f"    {len(rebased)} rows | {rebased.index.min().date()} "
              f"-> {rebased.index.max().date()} | base={rebased.iloc[0]:.4f}")

    # Join all four on common trading dates (all US-listed, calendars align).
    out = pd.DataFrame(series_by_key)
    out = out.dropna(how="any")          # keep dates every index has
    out.index.name = "date"
    out = out.sort_index()

    dest = Path(REFDATA_PATH) / "index_master.csv"
    out.to_csv(dest, date_format="%Y-%m-%d")
    print(f"\n>>> WROTE {dest}")
    print(f"    {len(out)} rows | columns: {list(out.columns)}")
    print(f"    first row (should be ~1.0 each):\n{out.iloc[0]}")


if __name__ == "__main__":
    try:
        build()
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)