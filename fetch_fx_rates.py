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
#
# import pickle, glob
#
# def g(je, f):
#     return je.get(f) if isinstance(je, dict) else getattr(je, f, None)
#
# for p in sorted(glob.glob('funds/B/Calendars/Monthly/Journals/*regular.pkl')):
#     d = pickle.load(open(p, 'rb'))
#     for je in d.get('journals', []):
#         fa = str(g(je, 'financial_account') or '')
#         if fa != 'AccruedInterestReceivable':
#             continue
#         td = str(g(je, 'tradedate'))[:10]
#         ib = str(g(je, 'ibor_date'))[:10]
#         if ib == '2026-01-20' or td in ('2026-01-17', '2026-01-18',
#                                         '2026-01-19', '2026-01-20'):
#             print(d.get('period_name'), '| txn=', g(je, 'transaction'),
#                   '| trade=', td, '| ibor=', ib,
#                   '| local=', g(je, 'local'))from proof_engine import load_jes_from_journals, _je_val
#
# jes_by_period, _ = load_jes_from_journals("Portfolio1", "Monthly", "<your funds path>")
# all_jan4 = []
# for period_name, jes in jes_by_period.items():
#     for je in jes:
#         if str(_je_val(je, "investment")) == "USD" and "2021-01-04" in str(_je_val(je, "ibor_date")):
#             all_jan4.append((period_name, je))
#
# print(f"Total USD lines on 2021-01-04 across all periods: {len(all_jan4)}")
# for period_name, je in all_jan4:
#     print(period_name, {f: _je_val(je, f) for f in
#           ["investment","ibor_date","tradedate","transaction","financial_account",
#            "quantity","local","book","tax_date"]})
#
# from proof_engine import load_jes_from_journals, _je_val
#
# jes_by_period, _ = load_jes_from_journals("Portfolio1", "Monthly", "<your funds path>")
# all_jan4 = []
# for period_name, jes in jes_by_period.items():
#     for je in jes:
#         if str(_je_val(je, "investment")) == "USD" and "2021-01-04" in str(_je_val(je, "ibor_date")):
#             all_jan4.append((period_name, je))
#
# print(f"Total USD lines on 2021-01-04 across all periods: {len(all_jan4)}")
# for period_name, je in all_jan4:
#     print(period_name, {f: _je_val(je, f) for f in
#           ["investment","ibor_date","tradedate","transaction","financial_account",
#            "quantity","local","book","tax_date"]})
#
# """
# test_cash_ledgers_real.py
# Quick manual test of compute_cash_trade_date / compute_cash_settle_date
# against REAL Portfolio1 data. Run from wherever you normally run other
# FIG scripts (so the financial_information_gateway.* imports resolve).
#
# Adjust portfolio / calendar / period below if needed, then:
#
#     python test_cash_ledgers_real.py
#
# What to look for, in order:
#   1. Does it run without errors at all? (import paths, IM bridge path)
#   2. metadata['investment_master_source'] should say
#      'TEMPORARY_BRIDGE_disk_csv' -- confirms it's reading the IM.
#   3. Row count > 0. If 0, the IM bridge probably isn't finding
#      investment_master.csv -- check the funds_path print message.
#   4. Spot-check a few rows: are the investments shown actually
#      currencies (USD, EUR, etc.), not equities/bonds?
#   5. Trade-date ledger: does running_local look sane (a plausible
#      cash commitment number, not way off)?
#   6. Settle-date ledger: does running_book reconcile sensibly --
#      i.e. does it look like a real cash balance, not wildly
#      different from running_local?
#   7. The open question from the build: trade-date ledger currently
#      shows BOTH the trade-date Payable posting AND its settle-date
#      relief entry for the same tranid. Look at a real multi-leg
#      trade and tell me whether that's the picture you want, or
#      whether it should be trade-date-only.
# """
# #
# # from financial_information_gateway.fig_code.compute_cash_trade_date import compute_cash_trade_date
# # from financial_information_gateway.fig_code.compute_cash_settle_date import compute_cash_settle_date
# #
# # PORTFOLIO = "Portfolio1"
# # CALENDAR = "Monthly"
# # PERIOD_START = "2021-01"
# # PERIOD_END = "2021-01"   # start small -- one month -- before running full history
# #
# # print("=" * 70)
# # print("TRADE DATE CASH LEDGER")
# # print("=" * 70)
# # result = compute_cash_trade_date(PORTFOLIO, CALENDAR, PERIOD_START, PERIOD_END)
# # print(f"\nrows: {len(result.data)}")
# # print(f"metadata: {result.metadata}")
# # if not result.data.empty:
# #     print("\nFirst 20 rows:")
# #     print(result.data.head(20).to_string(index=False))
# # else:
# #     print("\n*** ZERO ROWS -- check the funds_path / IM bridge message above ***")
# #
# # print()
# # print("=" * 70)
# # print("SETTLE DATE CASH LEDGER")
# # print("=" * 70)
# # result2 = compute_cash_settle_date(PORTFOLIO, CALENDAR, PERIOD_START, PERIOD_END)
# # print(f"\nrows: {len(result2.data)}")
# # print(f"metadata: {result2.metadata}")
# # if not result2.data.empty:
# #     print("\nFirst 20 rows:")
# #     print(result2.data.head(20).to_string(index=False))
# # else:
# #     print("\n*** ZERO ROWS -- check the funds_path / IM bridge message above ***")
# #
# # from financial_information_gateway.fig_code.fig_core import prep_state_cached as prep_state
# #
# # prep = prep_state("Portfolio1", "Monthly", "2021-01", "2021-01")
# # settle_by_tranid = {}
# # for je in prep["journal_entries"]:
# #     tranid = getattr(je, "tranid", None)
# #     if tranid is not None:
# #         settle_by_tranid[tranid] = getattr(je, "settledate", None)
# #
# # # Sample a few early-month tranids vs late-month ones
# # sample = list(settle_by_tranid.items())[:10]
# # for tranid, sd in sample:
# #     print(tranid, sd)
# from financial_information_gateway.fig_code.compute_accounting_ledger import compute_accounting_ledger
# from financial_information_gateway.fig_code.compute_accounting_ledger import compute_accounting_ledger
#
# ledger = compute_accounting_ledger("Portfolio1", "Monthly", "2021-01", "2021-01")
# df = ledger.data
#
# print("Step 0 -- ALL rows in ledger.data:", len(df))
#
# step1 = df[df["financial_account"] == "Payable"]
# print("Step 1 -- financial_account == 'Payable' (ANY investment, ANY event_type):", len(step1))
#
# step2 = step1[step1["investment"] == "USD"]
# print("Step 2 -- + investment == 'USD':", len(step2))
#
# step3 = step2[step2["event_type"] == "ACTIVITY"]
# print("Step 3 -- + event_type == 'ACTIVITY':", len(step3))
#
# step4 = step3[step3["transaction"] != "Settlement"]
# print("Step 4 -- + transaction != 'Settlement':", len(step4))
#
# print()
# print("All distinct investments with financial_account == 'Payable':")
# print(step1["investment"].value_counts())
#
# from proof_engine import run_proof
# results = run_proof(
#     portfolio="Portfolio1",
#     calendar="Monthly",
#     period="2025-12",
#     verbose=False,
# )
# print(results)
#
#
# #!/usr/bin/env python3
# """
# ACN Daily-calendar divergence locator.
#
# True trade-date net position of ACN at each year-end, computed from the
# full 167-event history. Compare these to the ACN qty shown in the DAILY
# appraisal at each corresponding year-end to find the FIRST year the Daily
# build diverges from truth. That narrows ~1,254 daily periods to one year.
#
# Usage:
#   1. Pull the Daily appraisal for ACN at each year-end (2021-12-31,
#      2022-12-31, 2023-12-31, 2024-12-31, 2025-12-31).
#   2. Enter the ACN qty each one shows in DAILY_OBSERVED below.
#   3. Run: python3 acn_daily_divergence.py
# """
#
# # ── True net from all 167 trade-date events (buy +, sell -) ──────────────
# EVENTS = [
# ("buy",724,"2021-01-06"),("buy",1302,"2021-01-07"),("buy",2252,"2021-02-10"),("buy",2922,"2021-02-10"),
# ("buy",3175,"2021-03-01"),("sell",3412,"2021-03-08"),("buy",2985,"2021-03-17"),("buy",2178,"2021-03-22"),
# ("sell",554,"2021-03-23"),("buy",3344,"2021-03-26"),("buy",2685,"2021-04-01"),("sell",4412,"2021-04-16"),
# ("buy",1575,"2021-04-16"),("sell",3037,"2021-04-22"),("buy",1179,"2021-05-03"),("sell",3889,"2021-05-06"),
# ("buy",3400,"2021-06-02"),("buy",3222,"2021-06-04"),("buy",702,"2021-06-08"),("sell",1140,"2021-06-28"),
# ("buy",2540,"2021-06-29"),("sell",1938,"2021-07-26"),("buy",3043,"2021-08-11"),("sell",4403,"2021-08-23"),
# ("buy",1112,"2021-08-24"),("sell",3834,"2021-08-30"),("buy",4283,"2021-09-07"),("sell",820,"2021-09-08"),
# ("buy",915,"2021-09-10"),("buy",974,"2021-09-28"),("buy",3881,"2021-10-01"),("buy",1278,"2021-10-18"),
# ("sell",4287,"2021-10-27"),("buy",3538,"2021-11-05"),("sell",2586,"2021-11-16"),("buy",3221,"2021-11-26"),
# ("buy",2963,"2021-11-26"),("buy",1051,"2021-11-29"),("buy",4405,"2021-12-06"),("buy",4731,"2021-12-09"),
# ("buy",4209,"2021-12-16"),("sell",4679,"2022-01-11"),("buy",3654,"2022-01-18"),("sell",3728,"2022-01-31"),
# ("buy",1292,"2022-01-31"),("buy",2988,"2022-02-03"),("buy",4859,"2022-02-08"),("buy",3709,"2022-02-23"),
# ("buy",1704,"2022-03-14"),("sell",4324,"2022-03-15"),("buy",4613,"2022-03-22"),("buy",3397,"2022-03-28"),
# ("sell",3949,"2022-04-11"),("buy",4148,"2022-04-22"),("buy",3966,"2022-05-09"),("buy",2947,"2022-05-10"),
# ("sell",3284,"2022-05-20"),("buy",1372,"2022-06-13"),("buy",1551,"2022-07-01"),("sell",2335,"2022-07-05"),
# ("buy",3377,"2022-07-13"),("buy",646,"2022-07-20"),("sell",4857,"2022-09-01"),("buy",1696,"2022-09-21"),
# ("buy",4973,"2022-09-22"),("sell",4147,"2022-09-30"),("buy",3584,"2022-10-07"),("buy",2375,"2022-10-18"),
# ("sell",1039,"2022-10-19"),("sell",2716,"2022-11-07"),("buy",539,"2022-11-15"),("buy",3668,"2022-12-08"),
# ("buy",1511,"2022-12-21"),("sell",832,"2023-01-12"),("buy",4204,"2023-01-17"),("sell",3625,"2023-02-01"),
# ("sell",2307,"2023-02-17"),("sell",2183,"2023-02-28"),("buy",1546,"2023-02-28"),("buy",2723,"2023-03-07"),
# ("buy",4328,"2023-03-09"),("buy",4863,"2023-03-22"),("sell",4398,"2023-03-23"),("buy",4695,"2023-03-27"),
# ("sell",3696,"2023-03-29"),("sell",4438,"2023-03-29"),("buy",4675,"2023-04-04"),("buy",2959,"2023-05-04"),
# ("sell",3854,"2023-05-10"),("buy",3561,"2023-05-12"),("buy",4874,"2023-05-15"),("buy",3935,"2023-05-30"),
# ("buy",1896,"2023-06-23"),("sell",813,"2023-06-23"),("buy",4873,"2023-07-12"),("buy",4580,"2023-07-14"),
# ("buy",2561,"2023-07-24"),("sell",935,"2023-07-31"),("sell",518,"2023-07-31"),("buy",3529,"2023-08-01"),
# ("sell",2130,"2023-08-14"),("buy",2740,"2023-09-06"),("sell",598,"2023-10-06"),("buy",953,"2023-12-11"),
# ("sell",2650,"2023-12-18"),("buy",752,"2023-12-26"),("sell",2715,"2024-01-04"),("sell",2843,"2024-01-17"),
# ("sell",1099,"2024-01-23"),("sell",3642,"2024-01-24"),("sell",4214,"2024-01-29"),("buy",2774,"2024-01-30"),
# ("buy",4427,"2024-02-15"),("sell",2654,"2024-03-13"),("buy",4221,"2024-03-14"),("sell",2705,"2024-03-27"),
# ("buy",3821,"2024-04-01"),("buy",4362,"2024-04-15"),("sell",3344,"2024-04-22"),("sell",2684,"2024-04-26"),
# ("buy",1943,"2024-05-13"),("sell",3306,"2024-07-05"),("buy",4695,"2024-07-05"),("buy",1268,"2024-07-10"),
# ("sell",2810,"2024-08-07"),("buy",2542,"2024-08-09"),("buy",4803,"2024-08-28"),("buy",540,"2024-09-09"),
# ("buy",2846,"2024-09-09"),("sell",1056,"2024-09-18"),("sell",4658,"2024-11-20"),("sell",3477,"2024-12-02"),
# ("sell",916,"2024-12-06"),("sell",883,"2024-12-11"),("buy",3826,"2024-12-16"),("sell",1270,"2025-01-03"),
# ("buy",2251,"2025-02-18"),("sell",1548,"2025-03-10"),("sell",4113,"2025-03-17"),("sell",1376,"2025-03-26"),
# ("buy",823,"2025-04-04"),("buy",4385,"2025-04-08"),("sell",4371,"2025-04-11"),("buy",2827,"2025-05-08"),
# ("buy",1742,"2025-05-27"),("buy",1783,"2025-05-28"),("sell",3020,"2025-06-06"),("buy",1340,"2025-06-11"),
# ("sell",1318,"2025-06-20"),("buy",2375,"2025-06-20"),("sell",928,"2025-07-01"),("buy",3596,"2025-07-16"),
# ("sell",3662,"2025-07-23"),("buy",3497,"2025-08-04"),("buy",2604,"2025-08-05"),("buy",3508,"2025-08-08"),
# ("sell",4666,"2025-08-22"),("sell",2925,"2025-09-10"),("sell",3231,"2025-09-12"),("buy",3716,"2025-09-24"),
# ("sell",841,"2025-10-01"),("sell",4797,"2025-10-07"),("buy",2634,"2025-10-28"),("buy",4125,"2025-11-04"),
# ("buy",3816,"2025-11-21"),("buy",1768,"2025-12-10"),("buy",1982,"2025-12-22"),
# ]
#
# YEAR_ENDS = ["2021-12-31","2022-12-31","2023-12-31","2024-12-31","2025-12-31"]
#
# def true_net_asof(date_iso):
#     n=0
#     for side,qty,d in EVENTS:
#         if d <= date_iso:
#             n += qty if side=="buy" else -qty
#     return n
#
# # ── PASTE the ACN qty the DAILY appraisal shows at each year-end here ──────
# # Leave as None until you pull it; 2025-12-31 is already known (103,422).
# DAILY_OBSERVED = {
#     "2021-12-31": None,
#     "2022-12-31": None,
#     "2023-12-31": None,
#     "2024-12-31": None,
#     "2025-12-31": 103422,
# }
#
# print("ACN — Daily calendar divergence check")
# print("="*64)
# print(f"{'year-end':<12}{'true net':>12}{'daily obs':>12}{'diff':>10}  verdict")
# print("-"*64)
# first_bad=None
# for ye in YEAR_ENDS:
#     tn = true_net_asof(ye)
#     obs = DAILY_OBSERVED.get(ye)
#     if obs is None:
#         print(f"{ye:<12}{tn:>12,}{'—':>12}{'—':>10}  (pull Daily appraisal)")
#         continue


"""
test_perf_persist.py
--------------------
Proves whether a computed performance object can be dropped to disk "as is"
and reloaded identical -- the foundation stone for stored performance results.

It does NOT modify the engine. It:
  1. runs compute_performance for a SMALL range (structure is identical at any
     size, so a couple of months is enough and fast),
  2. reaches into the performance cache and grabs the exact cached object,
  3. pickles it to disk,
  4. reloads it,
  5. diffs reload vs original and prints MATCH / MISMATCH + on-disk size.

Adjust the three CONFIG values and the two import lines marked TODO to match
your module paths, then run:  python test_perf_persist.py
"""

import pickle
import time
from pathlib import Path

import pandas as pd

# ── TODO: point these at your actual modules ─────────────────────────────────
# compute_performance and prep_state, plus the cache object that
# _get_cached_daily_state reads/writes. The cache is almost certainly a
# module-level dict in compute_performance.py — import it directly so we can
# inspect what was actually stored.
from financial_information_gateway.fig_code.compute_performance import compute_performance
from financial_information_gateway.fig_code.fig_core import prep_state_cached as prep_state
# The daily-state cache dict. If it has a different name, fix this import.
# Common names: _DAILY_STATE_CACHE, _CACHE, _daily_state_cache.
try:
    from financial_information_gateway.fig_code.compute_performance import _DAILY_STATE_CACHE as PERF_CACHE
    _CACHE_IMPORTED = True
except Exception:
    PERF_CACHE = None
    _CACHE_IMPORTED = False

# ── CONFIG: a small, fast range ──────────────────────────────────────────────
PORTFOLIO    = "Portfolio1"
CALENDAR     = "Monthly"
PERIOD_START = "2021-01"
PERIOD_END   = "2021-03"     # small on purpose; structure is size-independent
OUT_PATH     = Path("perf_persist_test.pkl")


def _summarize(obj, label):
    print(f"\n--- {label} ---")
    print(f"type: {type(obj)}")
    if isinstance(obj, pd.DataFrame):
        print(f"shape: {obj.shape}")
        print(f"columns: {list(obj.columns)[:12]}{' ...' if len(obj.columns) > 12 else ''}")
    elif isinstance(obj, (tuple, list)):
        print(f"len: {len(obj)}")
        for i, part in enumerate(obj):
            print(f"  [{i}] type={type(part)}"
                  + (f" shape={part.shape}" if isinstance(part, pd.DataFrame) else ""))
    elif isinstance(obj, dict):
        print(f"keys: {list(obj.keys())[:12]}")


def _equal(a, b):
    """Structural equality for the kinds of objects the cache might hold."""
    if isinstance(a, pd.DataFrame) and isinstance(b, pd.DataFrame):
        try:
            pd.testing.assert_frame_equal(a, b, check_like=False)
            return True
        except AssertionError as e:
            print(f"  DataFrame diff: {str(e)[:300]}")
            return False
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        if len(a) != len(b):
            return False
        return all(_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return False
        return all(_equal(a[k], b[k]) for k in a)
    return a == b


def main():
    print("=" * 64)
    print("PERFORMANCE PERSIST TEST")
    print("=" * 64)

    # 1. prep + run performance for the small range (builds + caches)
    prep = prep_state(PORTFOLIO, CALENDAR, PERIOD_START, PERIOD_END)
    t0 = time.perf_counter()
    result = compute_performance(
        portfolio=PORTFOLIO, calendar=CALENDAR,
        period_start=PERIOD_START, period_end=PERIOD_END,
        level="investment", cadence=None, prep=prep,
    )
    print(f"\ncompute_performance ran in {(time.perf_counter()-t0)*1000:.0f}ms, "
          f"valid={result.valid}, output_rows={len(result.data)}")

    # 2. grab the cached object
    if not _CACHE_IMPORTED or PERF_CACHE is None:
        print("\n!! Could not import the perf cache dict. Fix the import named "
              "PERF_CACHE at the top (find the module-level cache that "
              "_get_cached_daily_state uses). Falling back to testing "
              "result.data (the output DataFrame) instead, which still proves "
              "DataFrame pickling works but is NOT the cached chained state.")
        cached_obj = result.data
        cache_desc = "result.data (FALLBACK — not the cache)"
    else:
        # inception is available_periods[0]; the cache key uses it. We don't
        # know inception here, so just grab whatever single entry the run
        # just created (small cache in a fresh process).
        if len(PERF_CACHE) == 1:
            key = next(iter(PERF_CACHE))
            cached_obj = PERF_CACHE[key]
            cache_desc = f"PERF_CACHE[{key}]"
        else:
            # multiple entries — pick the one matching our portfolio/calendar/end
            match = [k for k in PERF_CACHE
                     if isinstance(k, tuple) and PORTFOLIO in k and CALENDAR in k
                     and PERIOD_END in k]
            if match:
                key = match[0]
                cached_obj = PERF_CACHE[key]
                cache_desc = f"PERF_CACHE[{key}]"
            else:
                key = next(iter(PERF_CACHE))
                cached_obj = PERF_CACHE[key]
                cache_desc = f"PERF_CACHE[{key}] (first of {len(PERF_CACHE)})"

    _summarize(cached_obj, f"CACHED OBJECT: {cache_desc}")

    # 3. pickle to disk
    t1 = time.perf_counter()
    try:
        with open(OUT_PATH, "wb") as f:
            pickle.dump(cached_obj, f)
    except Exception as e:
        print(f"\n!! PICKLE FAILED: {e}")
        print("   -> the cached object holds something that won't serialize "
              "(likely a live reference). This is the 'big job in disguise' "
              "signal. Stop here.")
        return
    size_mb = OUT_PATH.stat().st_size / (1024 * 1024)
    print(f"\npickled OK in {(time.perf_counter()-t1)*1000:.0f}ms "
          f"-> {OUT_PATH} ({size_mb:.2f} MB)")

    # 4. reload
    with open(OUT_PATH, "rb") as f:
        reloaded = pickle.load(f)
    _summarize(reloaded, "RELOADED OBJECT")

    # 5. diff
    print("\n--- DIFF ---")
    if _equal(cached_obj, reloaded):
        print("RESULT: MATCH  — object round-trips identically as-is.")
        print("=> 'drop it in as-is' is viable. This is the cheap foundation "
              "stone for stored performance results.")
    else:
        print("RESULT: MISMATCH — reload differs from original. Inspect the "
              "diff above before relying on persistence.")
    print("=" * 64)


if __name__ == "__main__":
    main()

#     diff = obs - tn
#     verdict = "OK" if diff==0 else f"OFF by {diff:+,}"
#     if diff!=0 and first_bad is None: first_bad=ye
#     print(f"{ye:<12}{tn:>12,}{obs:>12,}{diff:>10,}  {verdict}")
# print("-"*64)
# if first_bad:
#     print(f"\nFIRST year Daily diverges: {first_bad}")
#     print("→ Next: pull MONTHLY ACN qty for the same year-ends to confirm Monthly")
#     print("  stays correct, then drill that year's daily periods month by month.")
# else:
#     print("\nFill in DAILY_OBSERVED to locate the divergence year.")