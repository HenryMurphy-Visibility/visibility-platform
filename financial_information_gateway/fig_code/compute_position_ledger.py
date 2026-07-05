
# ============================================================
# Visibility — Compute Position Ledger
# compute_position_ledger.py
#
# Position-level AL ledger, grain = (investment, ls).
#
#   OPENING  = AL positions at prior cutoff, rolled to (investment, ls),
#              with calculated unrealized G/L at the prior cutoff.
#   ACTIVITY = Cost-account journal movement during the period
#              (detail + per-(investment, ls) subtotal).
#   CLOSING  = AL positions at current cutoff, rolled to (investment, ls),
#              with calculated unrealized G/L at the current cutoff.
#
# ROW UNIVERSE = union of (investment, ls) keys across opening, activity,
# and closing. Anything that opened OR moved OR closed appears in ALL
# THREE sections, zero-filled where a section is genuinely zero. Nothing
# that touched the period is hidden -- a position bought and fully sold
# shows opening (or 0) -> activity -> closing 0.
#
# RECONCILIATION CONTRACT:
#   COST ties through activity, per (investment, ls):
#       opening_cost + activity_cost_movement = closing_cost  (to the penny)
#   UNREALIZED does NOT tie through activity: it is a calculated MARK at
#   each boundary. The change in unrealized is a price effect, not a
#   movement -- deliberately not reconciled here.
#
# COLUMN ALIGNMENT: opening, activity, and closing rows all write their
# core figures into the SAME column names (qty / local_cost / book_cost)
# so the three row types stack vertically. Activity leaves the mark
# columns (market value, price gain, price, fx) blank; opening/closing
# fill them. A single explicit col_order fixes left-to-right placement.
#
# NOTE (deferred): _ensure_reference_data / _calculate_market_values and the
# reference-data globals live in compute_appraisal and are reached here
# cross-file via the module alias `appraisal`. Intentional for now; a shared
# helpers module is the proper home but must not be extracted under time
# pressure (it would break every importer until repointed).
# ============================================================

import pandas as pd
from datetime import datetime
from collections import defaultdict

# Import the appraisal module itself so we can read the reference-data
# globals from the namespace where _ensure_reference_data populates them.
# (Importing the names directly would capture None at import time.)
import financial_information_gateway.fig_code.compute_appraisal as appraisal
from financial_information_gateway.fig_code.compute_appraisal import (
    _ensure_reference_data,
    _calculate_market_values,
    UNREALIZED_ACCOUNTS,
)
from financial_information_gateway.fig_code.fig_core import prep_state
from financial_information_gateway.fig_code.compute_result import ComputeResult


# ============================================================
# AL-ONLY POSITION EXTRACTION (lot level, zeros kept)
# ============================================================

def _extract_al_positions_keep_zeros(state, investment_master):
    """
    AL-only position extraction at LOT level, KEEPING zero-qty lots.

    This is _extract_appraisal_rows minus the zero-qty skip: a ledger must
    show fully-closed positions (closing qty 0), so zeros are retained here.
    RevExp is excluded (AL repo only); UNREALIZED_ACCOUNTS excluded, exactly
    as appraisal does. Currency collapse is intentionally NOT applied -- the
    position ledger rolls by (investment, ls) uniformly below.

    Returns row dicts in the shape _calculate_market_values expects
    (qty / local_cost / book_cost / pricing_factor / currency / ...).
    """
    if not state:
        return []

    al_repo = state.get("asset_liability_repository")
    if not al_repo:
        return []

    rows = []
    for subspace in al_repo.investment_positions.values():
        for key, row in subspace.entries.items():
            (_, inv, lotid, tax_date, ls, loc, fa) = key

            # AL position rows only -- skip unrealized GL accounts, same as
            # appraisal. (Cost is the position-bearing account.)
            if fa in UNREALIZED_ACCOUNTS:
                continue

            qty   = row[0] if len(row) > 0 else 0.0
            local = row[1] if len(row) > 1 else 0.0
            book  = row[2] if len(row) > 2 else 0.0

            attrs = investment_master.get(inv, {})

            rows.append({
                "investment":        inv,
                "full_name":         attrs.get("full_name", ""),
                "lotid":             lotid,
                "tax_date":          tax_date,
                "location":          loc,
                "ls":                ls,
                "financial_account": fa,
                "currency":          attrs.get("currency", "USD"),
                "pricing_factor":    attrs.get("pricing_factor", 1.0),
                "investment_type":   attrs.get("investment_type", "EQUITY"),
                "sector":            attrs.get("sector", ""),
                "country":           attrs.get("country", ""),
                "analyst":           attrs.get("analyst", ""),
                "qty":               qty,
                "local_cost":        local,
                "book_cost":         book,
            })
    return rows


# ============================================================
# ROLL UP LOTS TO POSITION GRAIN (investment, ls)
# ============================================================

def _rollup_to_position(rows):
    """
    Roll lot-level AL rows up to position grain (investment, ls).
    Locations and lots collapse; long and short stay DISTINCT (they are
    different positions from a ledger standpoint).

    Sums qty / local_cost / book_cost. Carries first descriptive
    attributes. Returns {(investment, ls): rolled_row}.
    """
    acc = {}
    for r in rows:
        k = (r["investment"], r["ls"])
        if k not in acc:
            acc[k] = {
                "investment":      r["investment"],
                "ls":              r["ls"],
                "full_name":       r.get("full_name", ""),
                "currency":        r.get("currency", "USD"),
                "pricing_factor":  r.get("pricing_factor", 1.0),
                "investment_type": r.get("investment_type", "EQUITY"),
                "sector":          r.get("sector", ""),
                "country":         r.get("country", ""),
                "analyst":         r.get("analyst", ""),
                "qty":             0.0,
                "local_cost":      0.0,
                "book_cost":       0.0,
            }
        acc[k]["qty"]        += r.get("qty", 0.0) or 0.0
        acc[k]["local_cost"] += r.get("local_cost", 0.0) or 0.0
        acc[k]["book_cost"]  += r.get("book_cost", 0.0) or 0.0

    return acc


# ============================================================
# COMPUTE POSITION LEDGER — PUBLIC INTERFACE
# ============================================================

def compute_position_ledger(
        portfolio,
        calendar,
        period_start,
        period_end,
        uber_filter=None,
        prep=None,
        ppa_ibor_date=None
):
    """
    Position-level AL ledger, grain (investment, ls), with calculated
    unrealized at both boundaries. See module header for the contract.
    """
    start_time = datetime.now()

    # --------------------------------------------------
    # PREP + REFERENCE DATA
    # Reference globals live in compute_appraisal; _ensure_reference_data
    # populates THAT module's namespace, so read them via `appraisal.`
    # AFTER the load call (reading them at import time would capture None).
    # --------------------------------------------------
    if prep is None:
        prep = prep_state(portfolio, calendar, period_start, period_end)

    _ensure_reference_data()
    price_rows        = appraisal._PRICE_ROWS
    fx_rows           = appraisal._FX_ROWS
    investment_master = appraisal._INVESTMENT_MASTER

    prior_state    = prep["prior_state"]
    current_state  = prep["current_state"]
    prior_cutoff   = prep["prior_cutoff_datetime"]
    current_cutoff = prep["current_cutoff_datetime"]

    # --------------------------------------------------
    # OPENING / CLOSING — AL-only, zeros kept, rolled to (investment, ls),
    # unrealized calculated at each boundary date.
    # --------------------------------------------------
    open_lot_rows  = _extract_al_positions_keep_zeros(prior_state,   investment_master)
    close_lot_rows = _extract_al_positions_keep_zeros(current_state, investment_master)

    # Optional single-investment filter (applied at lot level, pre-rollup)
    if uber_filter and uber_filter.get("investment"):
        inv_f = uber_filter["investment"]
        open_lot_rows  = [r for r in open_lot_rows  if r["investment"] == inv_f]
        close_lot_rows = [r for r in close_lot_rows if r["investment"] == inv_f]

    opening_pos = _rollup_to_position(open_lot_rows)   # {(inv, ls): row}
    closing_pos = _rollup_to_position(close_lot_rows)

    # Calculate unrealized on the ROLLED-UP positions (one price per
    # investment applies to the summed qty -- roll first, then mark).
    # _calculate_market_values preserves input order, so zip back to keys.
    opening_keys = list(opening_pos.keys())
    closing_keys = list(closing_pos.keys())

    opening_marked = dict(zip(
        opening_keys,
        _calculate_market_values(list(opening_pos.values()), prior_cutoff,
                                 price_rows, fx_rows)
    ))
    closing_marked = dict(zip(
        closing_keys,
        _calculate_market_values(list(closing_pos.values()), current_cutoff,
                                 price_rows, fx_rows)
    ))

    # --------------------------------------------------
    # ACTIVITY — Cost JE movement during the period, by (investment, ls).
    # Core figures written as qty / local_cost / book_cost so activity rows
    # stack vertically under the opening/closing figures of the same name.
    # --------------------------------------------------
    activity_detail = []   # list of detail dicts
    activity_cost   = defaultdict(lambda: {"qty": 0.0, "local": 0.0, "book": 0.0})

    for je in prep["journal_entries"]:
        if getattr(je, "financial_account", None) != "Cost":
            continue
        inv = getattr(je, "investment", None)
        if uber_filter and uber_filter.get("investment") and inv != uber_filter["investment"]:
            continue
        ls = getattr(je, "ls", None)

        # Window: regular entries within (prior_cutoff, current_cutoff].
        is_adj = getattr(je, "is_adjustment", False)
        ibor   = getattr(je, "ibor_date", None)
        if not is_adj:
            if not ibor:
                continue
            if prior_cutoff is None:
                if ibor > current_cutoff:
                    continue
            else:
                if not (prior_cutoff < ibor <= current_cutoff):
                    continue

        qty   = getattr(je, "quantity", 0.0) or 0.0
        local = getattr(je, "local", 0.0) or 0.0
        book  = getattr(je, "book", 0.0) or 0.0

        k = (inv, ls)
        activity_cost[k]["qty"]   += qty
        activity_cost[k]["local"] += local
        activity_cost[k]["book"]  += book

        activity_detail.append({
            "event_type":        "ACTIVITY",
            "investment":        inv,
            "ls":                ls,
            "transaction":       getattr(je, "transaction", None),
            "ibor_date":         ibor,
            "financial_account": "Cost",
            "qty":               qty,
            "local_cost":        local,   # same column name as opening/closing
            "book_cost":         book,
            "sequence":          getattr(je, "sequence_number", 0),
        })

    # --------------------------------------------------
    # ROW UNIVERSE — union of (investment, ls) across all three sections.
    # --------------------------------------------------
    keys = set(opening_marked) | set(closing_marked) | set(activity_cost.keys())

    def _zero_pos(inv, ls):
        return {"investment": inv, "ls": ls, "qty": 0.0,
                "local_cost": 0.0, "book_cost": 0.0,
                "market_value_local": 0.0, "market_value_book": 0.0,
                "price_gain_local": 0.0, "price_gain_book": 0.0,
                "price": None, "fx_rate": None}

    # --------------------------------------------------
    # RECONCILIATION SELF-CHECK (cost ties through activity)
    # opening_cost + activity_cost = closing_cost, per (investment, ls).
    # Unrealized is NOT checked here -- it is a mark, not a movement.
    # --------------------------------------------------
    recon_failures = []
    for k in sorted(keys):
        inv, ls = k
        o = opening_marked.get(k) or _zero_pos(inv, ls)
        c = closing_marked.get(k) or _zero_pos(inv, ls)
        a = activity_cost.get(k, {"local": 0.0, "book": 0.0, "qty": 0.0})

        exp_close_local = (o.get("local_cost", 0.0) or 0.0) + (a["local"] or 0.0)
        act_close_local = c.get("local_cost", 0.0) or 0.0
        if abs(exp_close_local - act_close_local) > 0.01:
            recon_failures.append(
                f"{inv} ({ls}): opening_cost {o.get('local_cost', 0.0):,.2f} "
                f"+ activity {a['local']:,.2f} = {exp_close_local:,.2f} "
                f"!= closing_cost {act_close_local:,.2f} "
                f"(diff {exp_close_local - act_close_local:,.2f})")

    if recon_failures:
        print(f">>> POSITION LEDGER RECON: {len(recon_failures)} "
              f"(investment, ls) keys do not tie:")
        for f in recon_failures[:5]:
            print(f"    {f}")
        if len(recon_failures) > 5:
            print(f"    ... and {len(recon_failures) - 5} more")

    # --------------------------------------------------
    # BUILD OUTPUT ROWS — per key: OPENING, activity detail, ACTIVITY_TOTAL,
    # CLOSING. Long before short via ls sort, then by investment.
    # --------------------------------------------------
    LS_ORDER = {"l": 0, "s": 1}
    out = []

    for k in sorted(keys, key=lambda x: (x[0], LS_ORDER.get(x[1], 9))):
        inv, ls = k
        o = opening_marked.get(k) or _zero_pos(inv, ls)
        c = closing_marked.get(k) or _zero_pos(inv, ls)

        out.append({**o, "event_type": "OPENING", "transaction": None,
                    "ibor_date": prior_cutoff, "sequence": -1})

        det = [d for d in activity_detail if (d["investment"], d["ls"]) == k]
        det.sort(key=lambda d: (d["ibor_date"] or datetime.min, d["sequence"]))
        out.extend(det)

        a = activity_cost.get(k)
        if a:
            out.append({"event_type": "ACTIVITY_TOTAL", "investment": inv,
                        "ls": ls, "transaction": "TOTAL", "ibor_date": None,
                        "financial_account": "",
                        "qty": a["qty"], "local_cost": a["local"],
                        "book_cost": a["book"], "sequence": 999997})

        out.append({**c, "event_type": "CLOSING", "transaction": None,
                    "ibor_date": current_cutoff, "sequence": 999999})

    result_df = pd.DataFrame(out)

    # --------------------------------------------------
    # COLUMN ORDER — deliberate left-to-right so OPENING / ACTIVITY /
    # CLOSING align vertically. Identity columns first, then the core
    # qty/local_cost/book_cost figures (shared by all three row types),
    # then the boundary marks, then descriptive attributes.
    # --------------------------------------------------
    col_order = [
        "event_type",
        "investment",
        "ls",
        "ibor_date",
        "transaction",
        "qty",
        "local_cost",
        "book_cost",
        "market_value_local",
        "market_value_book",
        "price_gain_local",
        "price_gain_book",
        "price",
        "fx_rate",
        "cost_per_unit",
        "financial_account",
        "full_name",
        "currency",
        "pricing_factor",
        "investment_type",
        "sector",
        "country",
        "analyst",
        "sequence",
    ]
    if not result_df.empty:
        col_order = [c for c in col_order if c in result_df.columns]
        # keep any stray columns not in the canonical list, at the end
        extras = [c for c in result_df.columns if c not in col_order]
        result_df = result_df[col_order + extras]

    result_df = result_df.fillna("")

    elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
    metadata = {
        "row_count":      len(result_df),
        "positions":      len(keys),
        "recon_failures": len(recon_failures),
        "elapsed_ms":     round(elapsed_ms, 2),
        "uber_filter":    uber_filter,
    }

    print(
        f">>> COMPUTE POSITION LEDGER COMPLETE "
        f"| {portfolio} | {calendar} | {period_start} -> {period_end} "
        f"| {len(keys)} positions | {len(result_df)} rows "
        f"| recon_fail={len(recon_failures)} | {round(elapsed_ms, 1)}ms"
    )

    return ComputeResult(
        function="compute_position_ledger",
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        shape="position_ledger",
        data=result_df,
        valid=(len(recon_failures) == 0),
        errors=recon_failures,
        metadata=metadata,
    )