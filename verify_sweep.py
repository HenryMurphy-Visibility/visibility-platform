"""
verify_sweep.py — Visibility pre-freeze verification sweep (READ-ONLY).

Hits the running server's HTTP endpoints and prints a PASS/FAIL board:
  - Master recon all_clear across Monthly / Quarterly / Yearly / Daily
  - Appraisal valid across all four calendars at year-end 2025
  - CROSS-CALENDAR PENNY CHECK: appraisal grand totals equal across calendars
  - Cash trade-date and settle-date recon (Monthly, 2025-12 and 2023-06)
  - Position ledger (Monthly, 2025-12)
  - Performance detail + summary (Monthly, full range)

Usage:  python verify_sweep.py                                  (127.0.0.1:8000, no auth)
        python verify_sweep.py http://host:port YOUR_API_KEY    (authenticated)

The API key is sent as X-API-Key on every request (matches auth_middleware).
Exits 0 on ALL CLEAR, 1 on any failure. Makes no writes of any kind.
"""

import json
import sys
import time
import urllib.request
import urllib.error

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"
API_KEY = sys.argv[2] if len(sys.argv) > 2 else None

PORTFOLIO = "Portfolio1"

YEAR_END = {
    "Monthly":   "2025-12",
    "Quarterly": "2025-Q4",
    "Yearly":    "2025",
    "Daily":     "2025-12-31",
}
MID_MONTH = "2023-06"

results = []          # (check, calendar, rng, ok, detail, ms)
grand_totals = {}     # calendar -> {"market_value_book": x, "book_cost": y}


def fetch(path, params):
    qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    url = f"{BASE}{path}?{qs}"
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url)
        if API_KEY:
            if API_KEY.startswith("session="):
                req.add_header("Cookie", "visibility_session=" + API_KEY[8:])
            else:
                req.add_header("X-API-Key", API_KEY)
        with urllib.request.urlopen(req, timeout=600) as r:
            body = json.loads(r.read().decode("utf-8"))
            return r.status, body, (time.perf_counter() - t0) * 1000, url
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = {"detail": str(e)}
        return e.code, body, (time.perf_counter() - t0) * 1000, url
    except Exception as e:
        return 0, {"detail": str(e)}, (time.perf_counter() - t0) * 1000, url


def discover_endpoints():
    status, spec, _, _ = fetch("/api/v1/openapi.json", {})
    if status != 200 or "paths" not in (spec if isinstance(spec, dict) else {}):
        status, spec, _, _ = fetch("/openapi.json", {})
    if status != 200 or "paths" not in (spec if isinstance(spec, dict) else {}):
        detail = spec.get("detail") if isinstance(spec, dict) else spec
        print(f"!! could not read openapi spec (status {status}): {detail}")
        print("!! status 0 = no HTTP response at all (server down / wrong URL / firewall)")
        return {}
    paths = list(spec.get("paths", {}).keys())

    def find(*must, exclude=("csv",)):
        for p in paths:
            lp = p.lower()
            if all(m in lp for m in must) and not any(x in lp for x in exclude):
                return p
        return None

    found = {
        "recon":        find("recon"),
        "appraisal":    find("appraisal"),
        "cash_trade":   find("cash", "trade"),
        "cash_settle":  find("cash", "settle"),
        "position":     find("position"),
        "perf":         find("performance", exclude=("csv", "summary", "clear")),
        "perf_summary": find("performance", "summary"),
    }
    for k, v in found.items():
        print(f"   endpoint {k:13s} -> {v or 'NOT FOUND'}")
    return found


def to_num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace("$", "").strip()
    if s in ("", "—"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def get_rows(body):
    if isinstance(body, dict):
        d = body.get("data")
        if isinstance(d, list):
            return d
    return []


def get_meta(body):
    if not isinstance(body, dict):
        return {}
    for key in ("metadata", "performance", "meta"):
        m = body.get(key)
        if isinstance(m, dict):
            return m
    return {}


def find_all_clear(body):
    """Look for all_clear in metadata, then in a cross_view data row."""
    meta = get_meta(body)
    if "all_clear" in meta:
        return bool(meta["all_clear"]), "metadata.all_clear"
    inner = meta.get("metadata")
    if isinstance(inner, dict) and "all_clear" in inner:
        return bool(inner["all_clear"]), "metadata.metadata.all_clear"
    for row in get_rows(body):
        if row.get("view") == "cross_view":
            if row.get("all_three_agree") is True or row.get("v1_v2_ties") is True:
                return True, "cross_view row"
            return False, "cross_view row"
    errs = body.get("errors") if isinstance(body, dict) else None
    if isinstance(errs, list):
        return len(errs) == 0, "errors list"
    return None, "not found"


def record(check, calendar, rng, ok, detail, ms):
    results.append((check, calendar, rng, ok, detail, ms))
    mark = "PASS" if ok else "FAIL" if ok is False else "????"
    print(f"   [{mark}] {check:22s} {calendar:9s} {rng:22s} {detail}  ({ms:.0f}ms)")


def run_recon(ep):
    for cal, pe in YEAR_END.items():
        status, body, ms, url = fetch(ep, {
            "portfolio": PORTFOLIO, "calendar": cal,
            "period_start": pe, "period_end": pe, "page_size": 5000,
        })
        if status != 200:
            record("master_recon", cal, pe, False,
                   f"HTTP {status}: {str(body.get('detail'))[:80]}", ms)
            continue
        clear, how = find_all_clear(body)
        if clear is None:
            record("master_recon", cal, pe, None,
                   f"could not locate all_clear — keys: {list(body.keys())[:8]}", ms)
        else:
            record("master_recon", cal, pe, clear, f"all_clear={clear} via {how}", ms)


def run_appraisal(ep):
    for cal, pe in YEAR_END.items():
        status, body, ms, url = fetch(ep, {
            "portfolio": PORTFOLIO, "calendar": cal,
            "period_start": pe, "period_end": pe,
            "summary_only": "true", "page_size": 5000,
        })
        if status != 200:
            record("appraisal", cal, pe, False,
                   f"HTTP {status}: {str(body.get('detail'))[:80]}", ms)
            continue
        rows = get_rows(body)
        gt = next((r for r in rows if r.get("row_type") == "grand_total"), None)
        if gt is None:
            record("appraisal", cal, pe, False,
                   f"{len(rows)} rows, no grand_total row (pagination?)", ms)
            continue
        mvb = to_num(gt.get("market_value_book"))
        bkc = to_num(gt.get("book_cost"))
        grand_totals[cal] = {"market_value_book": mvb, "book_cost": bkc}
        record("appraisal", cal, pe, True,
               f"{len(rows)} rows | grand MV={mvb:,.2f} cost={bkc:,.2f}"
               if mvb is not None else f"{len(rows)} rows | grand total unparsed",
               ms)


def run_cross_calendar():
    if len(grand_totals) < 2:
        record("cross_calendar_penny", "ALL", "12/31/2025", None,
               "insufficient appraisal totals collected", 0)
        return
    for field in ("market_value_book", "book_cost"):
        vals = {c: g.get(field) for c, g in grand_totals.items() if g.get(field) is not None}
        if len(vals) < 2:
            record("cross_calendar_penny", "ALL", field, None, "values unparsed", 0)
            continue
        lo, hi = min(vals.values()), max(vals.values())
        spread = hi - lo
        ok = spread <= 0.01
        detail = f"{field} spread={spread:.4f} across {len(vals)} calendars"
        if not ok:
            detail += " | " + "; ".join(f"{c}={v:,.2f}" for c, v in vals.items())
        record("cross_calendar_penny", "ALL", field, ok, detail, 0)


def run_cash(ep, name):
    for pe in ("2025-12", MID_MONTH):
        status, body, ms, url = fetch(ep, {
            "portfolio": PORTFOLIO, "calendar": "Monthly",
            "period_start": pe, "period_end": pe, "page_size": 5000,
        })
        if status != 200:
            record(name, "Monthly", pe, False,
                   f"HTTP {status}: {str(body.get('detail'))[:80]}", ms)
            continue
        meta = get_meta(body)
        rf = meta.get("recon_failures")
        if rf is None:
            inner = meta.get("metadata")
            if isinstance(inner, dict):
                rf = inner.get("recon_failures")
        rows = len(get_rows(body))
        if rf is not None:
            record(name, "Monthly", pe, rf == 0,
                   f"recon_failures={rf} | {rows} rows", ms)
        else:
            errs = body.get("errors") or []
            record(name, "Monthly", pe, len(errs) == 0 and rows > 0,
                   f"{rows} rows | errors={len(errs)} (recon_failures not in payload)", ms)


def run_position(ep):
    pe = "2025-12"
    status, body, ms, url = fetch(ep, {
        "portfolio": PORTFOLIO, "calendar": "Monthly",
        "period_start": pe, "period_end": pe, "page_size": 5000,
    })
    if status != 200:
        record("position_ledger", "Monthly", pe, False,
               f"HTTP {status}: {str(body.get('detail'))[:80]}", ms)
        return
    rows = len(get_rows(body))
    errs = body.get("errors") or []
    record("position_ledger", "Monthly", pe, rows > 0 and len(errs) == 0,
           f"{rows} rows | errors={len(errs)}", ms)


def run_performance(ep, ep_summary):
    ps, pe = "2021-01", "2025-12"
    status, body, ms, url = fetch(ep, {
        "portfolio": PORTFOLIO, "calendar": "Monthly",
        "period_start": ps, "period_end": pe,
        "level": "portfolio", "page_size": 5000,
    })
    rows = len(get_rows(body))
    record("performance_detail", "Monthly", f"{ps}->{pe}",
           status == 200 and rows > 0, f"HTTP {status} | {rows} rows", ms)

    if ep_summary:
        status, body, ms, url = fetch(ep_summary, {
            "portfolio": PORTFOLIO, "calendar": "Monthly",
            "period_start": ps, "period_end": pe,
            "level": "portfolio", "page_size": 5000,
        })
        rows = len(get_rows(body))
        record("performance_summary", "Monthly", f"{ps}->{pe}",
               status == 200 and rows > 0, f"HTTP {status} | {rows} rows", ms)


def main():
    print(f"\nVISIBILITY VERIFICATION SWEEP (read-only) | {BASE}")
    print("=" * 78)
    print(">> discovering endpoints from /openapi.json ...")
    ep = discover_endpoints()
    print("-" * 78)

    if ep.get("recon"):
        run_recon(ep["recon"])
    if ep.get("appraisal"):
        run_appraisal(ep["appraisal"])
        run_cross_calendar()
    if ep.get("cash_trade"):
        run_cash(ep["cash_trade"], "cash_trade_date")
    if ep.get("cash_settle"):
        run_cash(ep["cash_settle"], "cash_settle_date")
    if ep.get("position"):
        run_position(ep["position"])
    if ep.get("perf"):
        run_performance(ep["perf"], ep.get("perf_summary"))

    print("-" * 78)
    fails   = [r for r in results if r[3] is False]
    unknown = [r for r in results if r[3] is None]
    passes  = [r for r in results if r[3] is True]
    print(f"RESULT: {len(passes)} pass | {len(fails)} fail | {len(unknown)} undetermined")
    if not results:
        print("NO CHECKS RAN — endpoint discovery failed. This is NOT a pass.")
        print("Check: server running? correct base URL? valid API key?")
        sys.exit(1)
    if not fails and not unknown:
        print("ALL CLEAR — safe to commit and tag.")
        sys.exit(0)
    if fails:
        print("FAILURES:")
        for c, cal, rng, ok, d, ms in fails:
            print(f"  ✗ {c} {cal} {rng}: {d}")
    if unknown:
        print("UNDETERMINED (script could not judge — paste these back for calibration):")
        for c, cal, rng, ok, d, ms in unknown:
            print(f"  ? {c} {cal} {rng}: {d}")
    sys.exit(1)


if __name__ == "__main__":
    main()