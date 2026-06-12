#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
correct_equity_events.py
========================

Two jobs, in order:

(1) DROP late-issue (spinoff/IPO) securities entirely.
    A security is dropped if it has ANY event dated BEFORE its first price in
    price_master -- the pre-issue signature. These names have synthetic trades
    predating their existence (CEG, KVUE, VLTO, GEV, SOLV, ...). In a clean
    model they shouldn't have manual trades at all -- they're born from a
    spinoff corporate action off the parent. ALL events for such a security
    (every method) are removed. Discovered data-driven, not from a hardcoded
    list. price_master is NEVER written -- the prices are kept for when the
    spinoff transactions are introduced later.

(2) Re-sync prices on the SURVIVING buy_equity / sell_equity events.
      quantity           : UNCHANGED
      price              : price_master price for (ticker, tradedate),
                           offset by a random +/- 0.25% (SEEDED off
                           (tradedate, tranid) so re-runs are stable)
      total_amount       : quantity * offset_price                 (LOCAL)
      total_amount_base  : local * fx(payment_currency, tradedate) (BOOK; USD x1)
      notional           : local                                   (= LOCAL)
    Everything else (split_equity, dividends, other methods/columns) untouched.

After (1), no surviving security has a pre-issue trade, so price lookups hit
exact; a mid-history gap (holiday) falls back to the most-recent prior price.

Idempotent on the price source; writes a NEW file (original left untouched).
"""

import sys
import bisect
import random
from datetime import datetime
from collections import Counter

import pandas as pd

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

EVENTS_PATH       = r"C:\Users\hjmne\PycharmProjects\chest\funds\Portfolio1\Events\Portfolio1.csv"
OUTPUT_PATH       = r"C:\Users\hjmne\PycharmProjects\chest\funds\Portfolio1\Events\Portfolio1_corrected.csv"
PRICE_MASTER_PATH = r"C:\Users\hjmne\PycharmProjects\chest\refdata\price_master.csv"
FX_PATH           = r"C:\Users\hjmne\PycharmProjects\chest\refdata\fx_master.csv"   # <-- set to your FX file

DROP_PRE_ISSUE_SECURITIES = True   # drop all events for names with pre-issue trades
FILL_GAPS_FROM_PRIOR      = True   # fill holiday/gap misses from most-recent prior price

# price_master columns (date, ticker, currency, price)
PM_SEP        = ","
PM_DATE_COL   = "date"
PM_TICKER_COL = "ticker"
PM_PRICE_COL  = "price"

# fx table columns (date, currency, price=rate)
FX_SEP      = ","
FX_DATE_COL = "date"
FX_CCY_COL  = "currency"
FX_RATE_COL = "price"

# events
EVENTS_SEP       = ","
EVENTS_ENCODINGS = ("utf-8-sig", "cp1252")
PM_ENCODINGS     = ("utf-8-sig", "cp1252")
FX_ENCODINGS     = ("utf-8-sig", "cp1252")

# correction parameters
METHODS_TO_FIX  = {"buy_equity", "sell_equity"}
OFFSET_PCT      = 0.0025
PRICE_DECIMALS  = 6
AMOUNT_DECIMALS = 4

# event column names
EV_METHOD     = "method"
EV_INVESTMENT = "investment"
EV_PAYCCY     = "payment_currency"
EV_TRADEDATE  = "tradedate"
EV_TRANID     = "tranid"
EV_QUANTITY   = "quantity"
EV_PRICE      = "price"
EV_NOTIONAL   = "notional"
EV_TOTAL      = "total_amount"
EV_TOTAL_BASE = "total_amount_base"

EVENT_TRADEDATE_FMT = "%m/%d/%Y:%H:%M:%S"   # e.g. 01/04/2021:00:00:00


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _read_text_csv(path, sep, encodings):
    last = None
    for enc in encodings:
        try:
            return pd.read_csv(path, sep=sep, encoding=enc,
                               dtype=str, keep_default_na=False)
        except (UnicodeDecodeError, UnicodeError) as e:
            last = e
    raise last


def _read_typed_csv(path, sep, encodings):
    last = None
    for enc in encodings:
        try:
            return pd.read_csv(path, sep=sep, encoding=enc)
        except (UnicodeDecodeError, UnicodeError) as e:
            last = e
    raise last


def _parse_trade_date(raw):
    return datetime.strptime(raw.strip(), EVENT_TRADEDATE_FMT).date()


def _offset_factor(tradedate_raw, tranid_raw):
    rng = random.Random(f"{tradedate_raw}|{tranid_raw}")
    return 1.0 + rng.uniform(-OFFSET_PCT, OFFSET_PCT)


def _build_asof(df, key_col, date_col, val_col):
    out = {}
    tmp = df.copy()
    tmp["_d"] = pd.to_datetime(tmp[date_col]).dt.date
    tmp["_k"] = tmp[key_col].astype(str).str.strip()
    for k, g in tmp.groupby("_k"):
        g = g.sort_values("_d")
        out[k] = (list(g["_d"]), [float(v) for v in g[val_col]])
    return out


def _asof(table, key, d):
    entry = table.get(key)
    if not entry:
        return None
    dates, vals = entry
    i = bisect.bisect_right(dates, d) - 1
    return vals[i] if i >= 0 else None


def _resolve_price(inv, d, price_lookup, price_asof):
    exact = price_lookup.get((inv, d))
    if exact is not None:
        return exact, "exact"
    if FILL_GAPS_FROM_PRIOR:
        prior = _asof(price_asof, inv, d)
        if prior is not None:
            return prior, "prior"      # mid-history gap (holiday/etc.)
    return None, None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    print("Reading events:", EVENTS_PATH)
    ev = _read_text_csv(EVENTS_PATH, EVENTS_SEP, EVENTS_ENCODINGS)
    print(f"  {len(ev):,} event rows, {len(ev.columns)} columns")

    required = [EV_METHOD, EV_INVESTMENT, EV_PAYCCY, EV_TRADEDATE, EV_TRANID,
                EV_QUANTITY, EV_PRICE, EV_NOTIONAL, EV_TOTAL, EV_TOTAL_BASE]
    miss_cols = [c for c in required if c not in ev.columns]
    if miss_cols:
        sys.exit(f"ERROR: events file missing expected columns: {miss_cols}")

    print("Reading price_master:", PRICE_MASTER_PATH)
    pm = _read_typed_csv(PRICE_MASTER_PATH, PM_SEP, PM_ENCODINGS)
    for c in (PM_DATE_COL, PM_TICKER_COL, PM_PRICE_COL):
        if c not in pm.columns:
            sys.exit(f"ERROR: price_master missing '{c}'. Found {list(pm.columns)}.")
    pm = pm.copy()
    pm["_d"] = pd.to_datetime(pm[PM_DATE_COL]).dt.date
    pm["_t"] = pm[PM_TICKER_COL].astype(str).str.strip()
    price_lookup = {(t, d): float(p)
                    for t, d, p in zip(pm["_t"], pm["_d"], pm[PM_PRICE_COL])}
    price_asof = _build_asof(pm, PM_TICKER_COL, PM_DATE_COL, PM_PRICE_COL)
    price_first = {t: pd.Timestamp(dts[0]) for t, (dts, _v) in price_asof.items()}
    print(f"  {len(price_lookup):,} (ticker, date) prices; {len(price_asof):,} tickers")

    print("Reading fx:", FX_PATH)
    fx = _read_typed_csv(FX_PATH, FX_SEP, FX_ENCODINGS)
    for c in (FX_DATE_COL, FX_CCY_COL, FX_RATE_COL):
        if c not in fx.columns:
            sys.exit(f"ERROR: fx file missing '{c}'. Found {list(fx.columns)}.")
    fx_asof = _build_asof(fx, FX_CCY_COL, FX_DATE_COL, FX_RATE_COL)
    print(f"  fx currencies: {sorted(fx_asof.keys())}")

    # --- (1) identify late-issue (pre-issue) securities ----------------------
    inv_norm = ev[EV_INVESTMENT].astype(str).str.strip()
    td_parsed = pd.to_datetime(ev[EV_TRADEDATE].str.strip(),
                               format=EVENT_TRADEDATE_FMT, errors="coerce")
    min_event = td_parsed.groupby(inv_norm).min()   # earliest trade per security

    drop_set, absent_set = set(), set()
    for inv, mn in min_event.items():
        if pd.isna(mn):
            continue
        fp = price_first.get(inv)
        if fp is None:
            absent_set.add(inv)          # security with NO prices at all
            continue
        if mn < fp:                      # earliest trade precedes first price
            drop_set.add(inv)

    if DROP_PRE_ISSUE_SECURITIES and drop_set:
        keep_mask = ~inv_norm.isin(drop_set)
    else:
        keep_mask = pd.Series(True, index=ev.index)

    removed_counts = Counter(inv_norm[~keep_mask])
    ev_keep = ev[keep_mask].copy()

    # --- (2) correct surviving buy/sell events -------------------------------
    corrected = {"buy_equity": 0, "sell_equity": 0}
    src_counts = Counter()
    gap_examples = []
    price_misses, fx_misses = [], []

    keep_inv = ev_keep[EV_INVESTMENT].astype(str).str.strip()
    for idx in ev_keep.index:
        method = ev_keep.at[idx, EV_METHOD].strip()
        if method not in METHODS_TO_FIX:
            continue

        investment = keep_inv.at[idx]
        ccy        = ev_keep.at[idx, EV_PAYCCY].strip()
        td_raw     = ev_keep.at[idx, EV_TRADEDATE]
        tran_raw   = ev_keep.at[idx, EV_TRANID]

        try:
            tdate = _parse_trade_date(td_raw)
        except ValueError:
            price_misses.append((tran_raw, investment, td_raw, "bad date"))
            continue

        base_price, source = _resolve_price(investment, tdate, price_lookup, price_asof)
        if base_price is None:
            price_misses.append((tran_raw, investment, td_raw, "no price"))
            continue
        src_counts[source] += 1
        if source == "prior" and len(gap_examples) < 20:
            gap_examples.append((tran_raw, investment, td_raw))

        rate = _asof(fx_asof, ccy, tdate)
        if rate is None:
            fx_misses.append((tran_raw, ccy, td_raw))
            continue

        qty          = float(ev_keep.at[idx, EV_QUANTITY])
        offset_price = base_price * _offset_factor(td_raw, tran_raw)
        local        = qty * offset_price
        book         = local * rate

        ev_keep.at[idx, EV_PRICE]      = f"{offset_price:.{PRICE_DECIMALS}f}"
        ev_keep.at[idx, EV_TOTAL]      = f"{local:.{AMOUNT_DECIMALS}f}"
        ev_keep.at[idx, EV_TOTAL_BASE] = f"{book:.{AMOUNT_DECIMALS}f}"
        ev_keep.at[idx, EV_NOTIONAL]   = f"{local:.{AMOUNT_DECIMALS}f}"
        corrected[method] += 1

    ev_keep.to_csv(OUTPUT_PATH, sep=EVENTS_SEP, index=False)

    # --- report --------------------------------------------------------------
    print("\n" + "=" * 64)
    print("SUMMARY")
    print("=" * 64)
    print(f"  securities dropped (pre-issue): {len(removed_counts):,}")
    print(f"  events dropped (all methods)  : {sum(removed_counts.values()):,}")
    print(f"  events remaining              : {len(ev_keep):,}")
    print(f"  buy_equity  corrected         : {corrected['buy_equity']:,}")
    print(f"  sell_equity corrected         : {corrected['sell_equity']:,}")
    print(f"  total corrected               : {sum(corrected.values()):,}")
    print(f"  price source - exact          : {src_counts['exact']:,}")
    print(f"  price source - prior(gap)     : {src_counts['prior']:,}")
    print(f"  price misses (unfixable)      : {len(price_misses):,}")
    print(f"  fx misses                     : {len(fx_misses):,}")

    if removed_counts:
        print("\n  DROPPED securities (ticker : events removed):")
        for inv, n in sorted(removed_counts.items(), key=lambda kv: -kv[1]):
            print(f"    {inv:<8} {n:>5}")
    if absent_set:
        print("\n  WARNING - traded but NO prices in price_master (NOT dropped):")
        print("    " + ", ".join(sorted(absent_set)))
        print("    These can't be valued. Decide separately whether to drop them.")
    if src_counts["prior"]:
        print("\n  GAP fills (most-recent prior price) -- confirm these are holidays:")
        for tran, inv, td in gap_examples:
            print(f"    tran {tran:>6}  {inv:<6} {td}")
    if price_misses:
        print("\n  TRUE price misses (investigate before rebuild):")
        for m in price_misses[:15]:
            print("   ", m)
        if len(price_misses) > 15:
            print(f"    ... and {len(price_misses) - 15:,} more")
    if fx_misses:
        print("\n  fx misses:")
        for m in fx_misses[:15]:
            print("   ", m)

    print(f"\n  Output written: {OUTPUT_PATH}")
    print("  Original + price_master left untouched (prices kept for future spinoffs).")
    print("  Review, then swap in when satisfied.")


if __name__ == "__main__":
    main()