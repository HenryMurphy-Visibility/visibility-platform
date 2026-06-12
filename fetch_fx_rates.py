# # """
# # fetch_us_prices_2026.py  —  ONE-TIME staging fetch (run locally)
# #
# # Fetches real, UNADJUSTED daily closing prices (USD) for the ~500 US names
# # below, Jan 2 – May 31 2026, and writes them to a STANDALONE staging file:
# #
# #     chest/refdata/new_prices.csv      (date, ticker, currency, price)
# #
# # It does NOT touch price_master.csv. Inspect new_prices.csv, read the coverage
# # report, then merge into price_master by hand once satisfied.
# #
# # Unadjusted = actual traded price on each date (splits are events in V, so
# # prices must not be back-adjusted). Same handling as the intl fetcher.
# #
# # Run:  python fetch_us_prices_2026.py
# # Requires:  pip install yfinance pandas
# # """
# #
# # import sys
# # import time
# # from pathlib import Path
# #
# # import pandas as pd
# # import yfinance as yf
# #
# # # ── EDIT if refdata lives elsewhere ────────────────────────────────────────
# # REFDATA = Path(r"C:/Users/hjmne/PycharmProjects/chest/refdata")
# # OUT_FILE = REFDATA / "new_prices.csv"
# #
# # START = "2026-01-02"
# # END   = "2026-05-31"
# #
# # # stored_ticker -> yahoo_fetch_symbol  (only the two that differ are remapped;
# # # everything else fetches under its own name). Class-B share quirk.
# # FETCH_OVERRIDE = {"BRKB": "BRK-B", "BFB": "BF-B"}
# #
# # TICKERS = [
# #     "AAPL","MSFT","AMZN","NVDA","GOOGL","GOOG","META","BRKB","TSLA","UNH","LLY",
# #     "JPM","XOM","JNJ","V","PG","AVGO","MA","HD","CVX","MRK","ABBV","PEP","COST",
# #     "ADBE","KO","CSCO","WMT","TMO","MCD","PFE","CRM","BAC","ACN","CMCSA","LIN",
# #     "NFLX","ABT","ORCL","DHR","AMD","WFC","DIS","TXN","PM","VZ","INTU","COP",
# #     "CAT","AMGN","NEE","INTC","UNP","LOW","IBM","BMY","SPGI","RTX","HON","BA",
# #     "UPS","GE","QCOM","AMAT","NKE","PLD","NOW","BKNG","SBUX","MS","ELV","MDT",
# #     "GS","DE","ADP","LMT","TJX","T","BLK","ISRG","MDLZ","GILD","MMC","AXP","SYK",
# #     "REGN","VRTX","ETN","LRCX","ADI","SCHW","CVS","ZTS","CI","CB","AMT","SLB","C",
# #     "BDX","MO","PGR","TMUS","FI","SO","EOG","BSX","CME","EQIX","MU","DUK","PANW",
# #     "PYPL","AON","SNPS","ITW","KLAC","HUBB","ICE","APD","SHW","CDNS","CSX","NOC",
# #     "CL","MPC","HUM","FDX","WM","MCK","TGT","ORLY","HCA","FCX","EMR","PXD","MMM",
# #     "MCO","ROP","CMG","PSX","MAR","PH","APH","GD","USB","NXPI","AJG","NSC","PNC",
# #     "VLO","F","MSI","GM","TT","EW","CARR","AZO","ADSK","TDG","ANET","SRE","ECL",
# #     "OXY","PCAR","ADM","MNST","KMB","PSA","CCI","CHTR","MCHP","MSCI","CTAS","WMB",
# #     "AIG","STZ","HES","NUE","ROST","AFL","KVUE","AEP","IDXX","D","TEL","JCI","MET",
# #     "GIS","IQV","EXC","WELL","DXCM","HLT","ON","COF","PAYX","TFC","BIIB","O","FTNT",
# #     "DOW","TRV","DLR","MRNA","CPRT","ODFL","DHI","YUM","SPG","CTSH","AME","BKR",
# #     "SYY","A","CTVA","CNC","EL","AMP","CEG","HAL","OTIS","ROK","PRU","DD","KMI",
# #     "VRSK","LHX","DG","FIS","CMI","CSGP","FAST","PPG","GPN","GWW","HSY","BK","XEL",
# #     "DVN","EA","NEM","ED","URI","VICI","PEG","KR","RSG","LEN","PWR","WST","COR",
# #     "OKE","VMC","KDP","WBD","ACGL","ALL","IR","CDW","FANG","MLM","PCG","DAL","EXR",
# #     "FTV","AWK","IT","KHC","GEHC","WEC","HPQ","EIX","CBRE","APTV","ANSS","MTD",
# #     "DLTR","AVB","GDDY","ALGN","LYB","TROW","GLW","EFX","WY","ZBH","XYL","SBAC",
# #     "RMD","TSCO","EBAY","KEYS","CHD","STT","DFS","HIG","ALB","STE","ES","TTWO",
# #     "MPWR","CAH","EQR","RCL","WTW","HPE","DTE","GPC","BR","ULTA","FICO","CTRA",
# #     "BAX","AEE","MTB","MKC","ETR","WAB","DOV","FE","RJF","INVH","FLT","CLX","TDY",
# #     "TRGP","DRI","LH","HOLX","VRSN","MOH","LUV","PPL","ARE","NVR","COO","WBA","PHM",
# #     "NDAQ","HWM","RF","CNP","IRM","LVS","FITB","EXPD","VTR","FSLR","PFG","BRO",
# #     "WDAY","IEX","BG","ATO","FDS","ENPH","MAA","CMS","IFF","BALL","SWKS","CINF",
# #     "NTAP","STLD","UAL","WAT","OMC","TER","CCL","JBHT","TPL","TYL","HBAN","K",
# #     "GRMN","CBOE","NTRS","TSN","AKAM","EG","ESS","EQT","TXT","EXPE","SJM","PTC",
# #     "DGX","AVY","RVTY","BBY","CF","CAG","EPAM","AMCR","LW","PAYC","SNA","AXON",
# #     "POOL","SYF","SWK","ZBRA","DPZ","PKG","CFG","LDOS","VTRS","PODD","LKQ","MOS",
# #     "APA","EVRG","TRMB","MGM","NDSN","WDC","MAS","LNT","IPG","MTCH","STX","KMX",
# #     "TECH","WRB","BFB","LYV","IP","UDR","AES","CE","INCY","L","TAP","GEN","CPT",
# #     "KIM","JKHY","HRL","HST","FMC","CZR","PEAK","CDAY","PNR","NI","CHRW","HSIC",
# #     "CRL","REG","APO","TFX","KEY","GL","EMN","WYNN","ALLE","PLTR","FFIV","BWA",
# #     "BXP","MKTX","ROL","JNPR","PNW","DELL","BLDR","FOXA","AOS","HAS","HII","NRG",
# #     "CPB","UHS","ERIE","WRK","KKR","LII","GEV","BBWI","NWSA","TPR","PARA","SMCI",
# #     "BEN","AIZ","NCLH","GNRC","FRT","IVZ","SOLV","CRWD","DVA","JBL","LULU","DECK",
# #     "UBER","MHK","RL","VLTO","FOX","BX","ABNB","NWS",
# # ]
# #
# #
# # def _mdy(ts) -> str:
# #     ts = pd.Timestamp(ts)
# #     return f"{ts.month}/{ts.day}/{ts.year}"
# #
# #
# # def _raw_close(fetch_symbol: str) -> pd.Series:
# #     """Unadjusted close, split back-adjustment reversed to recover traded prices."""
# #     t = yf.Ticker(fetch_symbol)
# #     h = t.history(start=START, end="2026-06-01", auto_adjust=False, actions=True)
# #     if h is None or h.empty:
# #         return pd.Series(dtype=float)
# #     close = h["Close"].copy()
# #     if "Stock Splits" in h.columns:
# #         sp = h["Stock Splits"].replace(0, 1.0)
# #         if (sp != 1.0).any():
# #             factor = sp.replace(0, 1.0)[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
# #             close = close * factor
# #     close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
# #     return close.dropna()
# #
# #
# # def main():
# #     if not REFDATA.exists():
# #         print(f"FAILED: refdata not found at {REFDATA}", file=sys.stderr); sys.exit(1)
# #
# #     rows = []
# #     failed, short = [], []
# #     spine = set()  # union of all dates seen — the trading-day reference
# #
# #     total = len(TICKERS)
# #     for i, stored in enumerate(TICKERS, 1):
# #         fetch_sym = FETCH_OVERRIDE.get(stored, stored)
# #         try:
# #             s = _raw_close(fetch_sym)
# #         except Exception as e:
# #             print(f"  [{i}/{total}] {stored}: ERROR {e}")
# #             failed.append(stored); continue
# #
# #         if s.empty:
# #             print(f"  [{i}/{total}] {stored} ({fetch_sym}): NO DATA")
# #             failed.append(stored); continue
# #
# #         for dt, px in s.items():
# #             d = _mdy(dt)
# #             spine.add(d)
# #             rows.append({"date": d, "ticker": stored, "currency": "USD",
# #                          "price": round(float(px), 6)})
# #         if i % 25 == 0 or i == total:
# #             print(f"  [{i}/{total}] ... {stored}: {len(s)} days")
# #         time.sleep(0.15)  # be polite to Yahoo
# #
# #     df = pd.DataFrame(rows)
# #     df.to_csv(OUT_FILE, index=False)
# #     print(f"\n>>> WROTE {OUT_FILE} | {len(df)} rows | {df['ticker'].nunique()} tickers")
# #
# #     # ---------- COVERAGE REPORT ----------
# #     n_days = len(spine)
# #     print(f"\n=== COVERAGE (trading days seen: {n_days}) ===")
# #     counts = df.groupby("ticker")["date"].nunique()
# #     median = int(counts.median()) if len(counts) else 0
# #     for stored in TICKERS:
# #         if stored in failed:
# #             continue
# #         c = int(counts.get(stored, 0))
# #         if c < median - 3:        # noticeably short of the typical day count
# #             short.append((stored, c))
# #
# #     if failed:
# #         print(f"\nNO DATA ({len(failed)}) — these returned nothing, handle by hand:")
# #         print("  " + ", ".join(failed))
# #     if short:
# #         print(f"\nSHORT COVERAGE ({len(short)}) — fewer days than typical ({median}):")
# #         for t, c in short:
# #             print(f"  {t}: {c} days")
# #     if not failed and not short:
# #         print("All tickers returned full coverage.")
# #
# #     print("\nReview new_prices.csv, then merge into price_master.csv by hand.")
# #     print("Known 2026-risk names to check in the NO DATA list: PXD, WRK, PEAK, "
# #           "CDAY, FLT (renamed/acquired — may need the new symbol or removal).")
# #
# #
# # if __name__ == "__main__":
# #     try:
# #         main()
# #     except Exception as e:
# #         import traceback; traceback.print_exc()
# #         print(f"FAILED: {e}", file=sys.stderr); sys.exit(1)
#
# # test_fx_lookup.py — run from the chest root to verify the FX lookup
# import csv
# from pathlib import Path
# from v_config import REFDATA_PATH
#
# def _normalize_fx_date(val):
#     if not val: return ""
#     val = str(val).strip()
#     if "/" in val:
#         p = val.split("/")
#         if len(p) >= 3:
#             return f"{p[2].split(':')[0].split('T')[0].strip()}-{p[0].zfill(2)}-{p[1].zfill(2)}"
#     if len(val) >= 10 and val[4] == "-":
#         return val[:10]
#     return val
#
# def lookup(currency, trade_date):
#     if currency.upper() == "USD":
#         return {"rate": 1.0, "found": True, "source": "passthrough"}
#     td = _normalize_fx_date(trade_date)
#     path = Path(REFDATA_PATH) / "fx_master.csv"
#     with open(path, newline="", encoding="utf-8-sig") as f:
#         for row in csv.DictReader(f):
#             ccy  = str(row.get("currency") or row.get("ticker") or "").strip()
#             date = str(row.get("date") or row.get("fx_date") or "").strip()
#             rate = row.get("price") or row.get("rate") or row.get("close") or ""
#             if ccy.upper() == currency.upper() and _normalize_fx_date(date) == td:
#                 try: return {"rate": float(rate), "found": True, "source": "fx_master"}
#                 except: pass
#     return {"rate": None, "found": False, "source": "not_found"}
#
# # the exact case that corrupted tran 95
# print("JPY 2026-01-02:", lookup("JPY", "2026-01-02"))
# print("JPY ISO form :", lookup("JPY", "2026-01-02T00:00:00"))
# print("USD passthru :", lookup("USD", "2026-01-02"))
# # expected JPY ~0.00638

import pickle, glob

def g(je, f):
    return je.get(f) if isinstance(je, dict) else getattr(je, f, None)

for p in sorted(glob.glob('funds/B/Calendars/Monthly/Journals/*regular.pkl')):
    d = pickle.load(open(p, 'rb'))
    for je in d.get('journals', []):
        fa = str(g(je, 'financial_account') or '')
        if fa != 'AccruedInterestReceivable':
            continue
        td = str(g(je, 'tradedate'))[:10]
        ib = str(g(je, 'ibor_date'))[:10]
        if ib == '2026-01-20' or td in ('2026-01-17', '2026-01-18',
                                        '2026-01-19', '2026-01-20'):
            print(d.get('period_name'), '| txn=', g(je, 'transaction'),
                  '| trade=', td, '| ibor=', ib,
                  '| local=', g(je, 'local'))