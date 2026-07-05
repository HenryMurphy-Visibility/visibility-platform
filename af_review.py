#!/usr/bin/env python3
"""
afreview -- Administrative Facility inspection utility.

Read-only lookthrough into the AF as persisted in a period-end snapshot.
Loads a snapshot from disk, pulls out the admin_facility, and displays
record status, settlement state, and entitled-position rollups.

Does NOT mutate anything. Does NOT touch the UI. Standalone shell tool;
the eventual "admin facility console" can wrap these same queries.

Usage:
    python afreview.py <portfolio> <calendar> [--investment BND000]
                       [--snapshot latest|<YYYY-MM-DDTHH-MM-SS>]

Examples:
    python afreview.py C Monthly
    python afreview.py C Monthly --investment BND000
    python afreview.py C Monthly --snapshot 2026-01-31T23-59-59
"""

import sys
import argparse
import pickle
from pathlib import Path
from datetime import datetime

CHEST_ROOT = "C:/Users/hjmne/PycharmProjects/chest"


def snapshots_dir(portfolio, calendar):
    return (
        Path(CHEST_ROOT)
        / "funds" / portfolio
        / "Calendars" / calendar
        / "Snapshots"
    )


def list_snapshots(portfolio, calendar):
    """Return [(kd_datetime, path), ...] sorted oldest-first."""
    d = snapshots_dir(portfolio, calendar)
    out = []
    if not d.exists():
        return out
    for fn in d.iterdir():
        if fn.suffix != ".pkl":
            continue
        try:
            kd = datetime.strptime(fn.stem, "%Y-%m-%dT%H-%M-%S")
        except ValueError:
            continue
        out.append((kd, fn))
    out.sort(key=lambda x: x[0])
    return out


def resolve_snapshot(portfolio, calendar, which):
    snaps = list_snapshots(portfolio, calendar)
    if not snaps:
        print(f"No snapshots found in {snapshots_dir(portfolio, calendar)}")
        sys.exit(1)
    if which == "latest":
        return snaps[-1]
    # else a named stem
    for kd, path in snaps:
        if path.stem == which:
            return (kd, path)
    print(f"Snapshot '{which}' not found. Available:")
    for kd, path in snaps:
        print(f"    {path.stem}")
    sys.exit(1)


def load_af(snapshot_path):
    with open(snapshot_path, "rb") as f:
        snap = pickle.load(f)
    state = snap.get("state", {})
    af = state.get("admin_facility")
    return af, snap


def fmt_date(v):
    if v is None:
        return "-"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    return str(v)[:10]


def main():
    ap = argparse.ArgumentParser(description="Inspect Administrative Facility state from a snapshot.")
    ap.add_argument("portfolio")
    ap.add_argument("calendar")
    ap.add_argument("--investment", default=None,
                    help="Filter to a single investment (e.g. BND000)")
    ap.add_argument("--snapshot", default="latest",
                    help="'latest' (default) or a snapshot stem YYYY-MM-DDTHH-MM-SS")
    args = ap.parse_args()

    kd, path = resolve_snapshot(args.portfolio, args.calendar, args.snapshot)
    af, snap = load_af(path)

    print("=" * 78)
    print(f"ADMIN FACILITY REVIEW")
    print(f"  portfolio : {args.portfolio}")
    print(f"  calendar  : {args.calendar}")
    print(f"  snapshot  : {path.stem}   (kd={fmt_date(kd)})")
    print(f"  period    : {snap.get('period_name', '?')}")
    if args.investment:
        print(f"  filter    : investment = {args.investment}")
    print("=" * 78)

    if af is None:
        print("\n  Snapshot carried NO admin_facility (None).")
        print("  (Either a pre-AF snapshot, or AF was not persisted.)")
        return

    records = getattr(af, "records", {})
    if not records:
        print("\n  Admin facility is EMPTY (no records).")
        return

    # ---- Per-record table ----
    rows = []
    for tranid, r in records.items():
        if args.investment and r.get("investment") != args.investment:
            continue
        rows.append(r)

    if not rows:
        print(f"\n  No records match investment={args.investment}.")
        return

    # sort by investment, then tranid
    rows.sort(key=lambda r: (str(r.get("investment")), r.get("tranid")))

    print(f"\n  RECORDS ({len(rows)})")
    print(f"  {'tranid':>10} {'inv':<8} {'ls':<3} {'effect':<7} "
          f"{'status':<16} {'settled/trade':>22} {'exp_settle':<12} {'trade':<12}")
    print("  " + "-" * 96)
    for r in rows:
        settled = r.get("settled_qty", 0.0)
        trade = r.get("trade_qty", 0.0)
        sq = f"{settled:,.2f}/{trade:,.2f}"
        print(f"  {r.get('tranid'):>10} {str(r.get('investment')):<8} "
              f"{str(r.get('ls')):<3} {str(r.get('position_effect')):<7} "
              f"{str(r.get('status')):<16} {sq:>22} "
              f"{fmt_date(r.get('expected_settle_date')):<12} "
              f"{fmt_date(r.get('trade_date')):<12}")

    # ---- Entitled-position rollup ----
    # Group the matching investments and ask the AF for entitled position.
    print(f"\n  ENTITLED POSITION (by location, ls)")
    invs = sorted({r.get("investment") for r in rows})
    portfolios = sorted({r.get("portfolio") for r in rows})
    any_printed = False
    for pf in portfolios:
        for inv in invs:
            try:
                pos = af.entitled_position(pf, inv)
            except Exception as e:
                print(f"    {pf}/{inv}: entitled_position raised {type(e).__name__}: {e}")
                continue
            for (loc, side), qty in sorted(pos.items()):
                print(f"    {pf}/{inv}  loc={loc:<10} ls={side}  -> {qty:,.2f}")
                any_printed = True
            try:
                total = af.entitled_position_total(pf, inv)
                print(f"    {pf}/{inv}  TOTAL (signed)        -> {total:,.2f}")
                any_printed = True
            except Exception as e:
                print(f"    {pf}/{inv}: entitled_position_total raised {type(e).__name__}: {e}")
    if not any_printed:
        print("    (none)")

    # ---- Exceptions / pending ----
    for pf in portfolios:
        try:
            exc = af.exceptions(pf)
        except Exception as e:
            exc = None
            print(f"\n  exceptions({pf}) raised {type(e).__name__}: {e}")
        if exc:
            print(f"\n  EXCEPTIONS ({pf}): {len(exc)}")
            for r in exc:
                print(f"    tranid={r.get('tranid')} status={r.get('status')} "
                      f"inv={r.get('investment')} notes={r.get('notes')}")

    print()


if __name__ == "__main__":
    main()