# ============================================================
# Visibility — Compute Cash Settle Date Ledger
# compute_cash_settle_date.py
#
# Custodian-recon cash ledger, SETTLE-DATE basis.
# "What's actually settled, actually sitting at the custodian" --
# the number that has to tie out against a custodian statement.
#
# Scope: currency investments only (is_currency=1 in the investment
# master), Cost account ONLY. No Receivable/Payable, no accruals --
# just the actual settled cash balance, in date order. This is
# deliberately blind to the trade-date ledger's commitment-side
# postings (see compute_cash_trade_date.py) -- the two ledgers stay
# non-overlapping by design.
#
# FX TRUE-UP (FXGainTradeSettle):
#   The settle-date Cost leg's LOCAL figure is the true currency-
#   native cash movement. Its BOOK figure reflects whatever FX rate
#   applied at settlement -- which can differ from the rate assumed
#   at trade date. FXGainTradeSettle is what reconciles that gap; it
#   is not itself a cash movement (no local-currency dimension --
#   confirmed local=0 on this account in the live JE example this
#   was built from), but it IS required for the running BOOK balance
#   to be correct. Per the confirmed design: included in the running
#   BOOK total, excluded from running LOCAL, shown as its own visible
#   row (not silently folded into the Cost row) so it stays auditable.
#   This presentation choice (visible row vs. folded) was explicitly
#   left open to revisit once real output is seen -- flagged here as
#   the one thing most likely to change after first real use.
#
# Thin filter over compute_accounting_ledger -- same foundation
# every other report derives from. No new materialization path.
# ============================================================

import pandas as pd
from datetime import datetime

from financial_information_gateway.fig_code.fig_core import prep_state_cached as prep_state
from financial_information_gateway.fig_code.compute_result import ComputeResult
from financial_information_gateway.fig_code.compute_accounting_ledger import (
    compute_accounting_ledger,
)
# Reused, not reimplemented: the same AL-repo position extraction
# compute_position_ledger.py already proved out for opening/closing
# balances. Pointed at SETTLE_DATE_CASH_ACCOUNTS (Cost) below.
from financial_information_gateway.fig_code.compute_position_ledger import (
    _extract_al_positions_keep_zeros,
)

# Reuse the IM bridge loader from the trade-date twin rather than
# duplicating it -- same TEMPORARY BRIDGE caveat applies here.
from financial_information_gateway.fig_code.compute_cash_trade_date import (
    _load_investment_master_for,
)


# ============================================================
# SETTLE-DATE CASH ACCOUNTS
# Confirmed mechanism: the Cost leg on a currency investment is what
# actually moves on settle date -- this IS the custodian-recon cash
# balance. FXGainTradeSettle is the true-up that makes the BOOK
# figure correct; included separately, not as a "cash account" itself.
# ============================================================

SETTLE_DATE_CASH_ACCOUNTS = frozenset({"Cost"})
FX_TRUE_UP_ACCOUNTS = frozenset({"FXGainTradeSettle"})


def _rollup_settle_date_cash(lot_rows, currency_invs):
    """
    Roll AL-repo lot-level rows up to a SINGLE settled-cash number per
    currency investment: sum of local/book across SETTLE_DATE_CASH_ACCOUNTS
    (Cost), currency investments only. This is the real point-in-time
    custodian-recon balance -- same mechanism compute_position_ledger.py
    already uses for Cost, just scoped to currency investments here.

    Returns {investment: {"local": x, "book": y}}.
    """
    acc = {}
    for r in lot_rows:
        inv = r.get("investment")
        if inv not in currency_invs:
            continue
        if r.get("financial_account") not in SETTLE_DATE_CASH_ACCOUNTS:
            continue
        if inv not in acc:
            acc[inv] = {"local": 0.0, "book": 0.0}
        acc[inv]["local"] += r.get("local_cost", 0.0) or 0.0
        acc[inv]["book"]  += r.get("book_cost", 0.0) or 0.0
    return acc


# ============================================================
# COMPUTE CASH SETTLE DATE — PUBLIC INTERFACE
# ============================================================

def compute_cash_settle_date(
        portfolio,
        calendar,
        period_start,
        period_end,
        uber_filter=None,
        prep=None,
        ppa_ibor_date=None,
):
    """
    Custodian-recon settle-date cash ledger for currency investments.

    OPENING / CLOSING are real point-in-time balances -- the AL-repo
    snapshot rolled up across SETTLE_DATE_CASH_ACCOUNTS (Cost) for
    currency investments, at prior_cutoff and current_cutoff. Same
    mechanism compute_position_ledger.py uses for Cost positions.

    RECON CONTRACT (this is the custodian-recon ledger, so unlike
    trade-date cash, this DOES need to tie): per currency investment,
        opening_local + activity_local == closing_local   (to tolerance)
    A tie failure sets valid=False and populates errors, the same
    contract compute_position_ledger.py enforces for Cost. This is the
    number that has to match a custodian statement -- if it doesn't
    tie internally, it's not safe to hand externally.

    FXGainTradeSettle is included in running BOOK only (no local-
    currency dimension), shown as its own visible row -- see module
    header for the full rationale. Excluded from the LOCAL recon check
    since the recon contract is about Cost, the real settled-cash
    account; the true-up is what makes BOOK match, not LOCAL.

    Does NOT include trade-side Receivable/Payable commitment
    postings -- see compute_cash_trade_date for that ledger.

    Returns
    -------
    ComputeResult with shape='cash_settle_date'
    """
    start_time = datetime.now()

    if prep is None:
        prep = prep_state(portfolio, calendar, period_start, period_end)

    ledger = compute_accounting_ledger(
        portfolio=portfolio, calendar=calendar,
        period_start=period_start, period_end=period_end,
        uber_filter=uber_filter, prep=prep,
        ppa_ibor_date=ppa_ibor_date,
    )

    df = ledger.data
    prior_cutoff = prep.get("prior_cutoff_datetime")
    current_cutoff = prep.get("current_cutoff_datetime")

    # -- OPENING boundary, display-only -- identical logic to
    # compute_cash_trade_date.py. prior_cutoff_datetime stays correctly
    # None at inception (prep_state untouched); start_period_boundary
    # from portfolio.json supplies a real display date for that one case.
    if prior_cutoff is not None:
        opening_boundary = prior_cutoff
    else:
        portfolio_config = prep.get("portfolio_config") or {}
        spb = portfolio_config.get("start_period_boundary")
        if not spb:
            inception = portfolio_config.get("inception_date")
            spb = f"{inception}T00:00:00" if inception else None
        opening_boundary = pd.to_datetime(spb) if spb else None

    im = _load_investment_master_for(portfolio, prep)
    currency_invs = {
        inv for inv, attrs in im.items()
        if str(attrs.get("is_currency", "")).strip() in ("1", "true", "True", "TRUE")
    }

    # -- OPENING / CLOSING: real point-in-time balances, AL-repo snapshot --
    open_lot_rows  = _extract_al_positions_keep_zeros(prep.get("prior_state"), im)
    close_lot_rows = _extract_al_positions_keep_zeros(prep.get("current_state"), im)
    opening_bal = _rollup_settle_date_cash(open_lot_rows, currency_invs)
    closing_bal = _rollup_settle_date_cash(close_lot_rows, currency_invs)

    rows_out = []
    for inv in sorted(set(opening_bal) | set(closing_bal)):
        ob = opening_bal.get(inv, {"local": 0.0, "book": 0.0})
        rows_out.append({
            "event_type": "OPENING", "row_role": "SETTLED_CASH", "investment": inv,
            "ibor_date": opening_boundary, "transaction": None, "financial_account": "",
            "local": ob["local"], "book": ob["book"],
            "running_local": ob["local"], "running_book": ob["book"],
            "tranid": None, "sequence": -1,
        })

    activity_local_by_inv = {}
    if df is not None and not df.empty:
        relevant_accounts = SETTLE_DATE_CASH_ACCOUNTS | FX_TRUE_UP_ACCOUNTS
        scoped = df[
            df["investment"].isin(currency_invs)
            & df["financial_account"].isin(relevant_accounts)
            & (df["event_type"] == "ACTIVITY")
        ].copy()

        if not scoped.empty:
            scoped["row_role"] = scoped["financial_account"].apply(
                lambda fa: "FX_TRUE_UP" if fa in FX_TRUE_UP_ACCOUNTS else "SETTLED_CASH"
            )
            scoped = scoped.sort_values(by=["investment", "ibor_date", "sequence"])
            scoped["event_type"] = "SETTLE_DATE_CASH"

            for inv, grp in scoped.groupby("investment"):
                activity_local_by_inv[inv] = grp.loc[
                    grp["row_role"] == "SETTLED_CASH", "local"
                ].sum()

            rows_out.extend(scoped.to_dict("records"))

    for inv in sorted(set(opening_bal) | set(closing_bal)):
        cb = closing_bal.get(inv, {"local": 0.0, "book": 0.0})
        rows_out.append({
            "event_type": "CLOSING", "row_role": "SETTLED_CASH", "investment": inv,
            "ibor_date": current_cutoff, "transaction": None, "financial_account": "",
            "local": cb["local"], "book": cb["book"],
            "running_local": cb["local"], "running_book": cb["book"],
            "tranid": None, "sequence": 999999,
        })

    out_df = pd.DataFrame(rows_out)

    # -- RECON CHECK: opening + activity == closing, per currency investment --
    # Same contract compute_position_ledger.py enforces for Cost. A tie
    # failure here is a real signal -- this is the custodian-recon number.
    recon_failures = []
    for inv in sorted(set(opening_bal) | set(closing_bal)):
        ob = opening_bal.get(inv, {}).get("local", 0.0)
        cb = closing_bal.get(inv, {}).get("local", 0.0)
        ab = activity_local_by_inv.get(inv, 0.0) or 0.0
        expected_closing = ob + ab
        if abs(expected_closing - cb) > 0.01:
            recon_failures.append(
                f"{inv}: opening {ob:,.2f} + activity {ab:,.2f} = "
                f"{expected_closing:,.2f} != closing {cb:,.2f} "
                f"(diff {expected_closing - cb:,.2f})"
            )

    if recon_failures:
        print(f">>> SETTLE DATE CASH RECON: {len(recon_failures)} "
              f"investment(s) do not tie:")
        for f in recon_failures[:5]:
            print(f"    {f}")
        if len(recon_failures) > 5:
            print(f"    ... and {len(recon_failures) - 5} more")

    if not out_df.empty:
        order_map = {"OPENING": 0, "SETTLE_DATE_CASH": 1, "CLOSING": 2}
        out_df["_order"] = out_df["event_type"].map(order_map).fillna(1)
        out_df = out_df.sort_values(
            by=["investment", "_order", "ibor_date", "sequence"]
        ).reset_index(drop=True)

        running_local, running_book = [], []
        carry = {}
        for _, row in out_df.iterrows():
            inv = row["investment"]
            if row["event_type"] == "OPENING":
                carry[inv] = {"local": row["local"], "book": row["book"]}
                running_local.append(carry[inv]["local"])
                running_book.append(carry[inv]["book"])
            elif row["event_type"] == "CLOSING":
                running_local.append(row["running_local"])
                running_book.append(row["running_book"])
            else:
                cur = carry.setdefault(inv, {"local": 0.0, "book": 0.0})
                if row["row_role"] == "SETTLED_CASH":
                    cur["local"] += row["local"] or 0.0
                cur["book"] += row["book"] or 0.0
                running_local.append(cur["local"])
                running_book.append(cur["book"])

        out_df["running_local"] = running_local
        out_df["running_book"] = running_book
        out_df = out_df.drop(columns=["_order"], errors="ignore")

    col_order = [
        "event_type", "row_role", "investment", "ibor_date",
        "transaction", "financial_account",
        "local", "book", "running_local", "running_book",
        "tranid", "sequence",
    ]
    if not out_df.empty:
        col_order = [c for c in col_order if c in out_df.columns]
        extras = [c for c in out_df.columns if c not in col_order]
        out_df = out_df[col_order + extras]
        out_df = out_df.fillna("")

    elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
    valid = ledger.valid and len(recon_failures) == 0
    metadata = {
        **ledger.metadata,
        "category": "Cash Ledger — Settle Date",
        "rows_after_filter": len(out_df) if out_df is not None else 0,
        "accounts_included": sorted(SETTLE_DATE_CASH_ACCOUNTS | FX_TRUE_UP_ACCOUNTS),
        "fx_true_up_presentation": "visible_row",  # flagged as revisit-after-output
        "elapsed_ms": round(elapsed_ms, 2),
        "investment_master_source": "TEMPORARY_BRIDGE_disk_csv",
        "recon_failures": len(recon_failures),
    }

    print(
        f">>> COMPUTE CASH SETTLE DATE COMPLETE "
        f"| {portfolio} | {calendar} | {period_start} -> {period_end} "
        f"| {metadata['rows_after_filter']} rows "
        f"| recon_fail={len(recon_failures)} "
        f"| {round(elapsed_ms, 1)}ms"
    )

    return ComputeResult(
        function="compute_cash_settle_date",
        portfolio=portfolio, calendar=calendar,
        period_start=period_start, period_end=period_end,
        shape="cash_settle_date",
        data=out_df, valid=valid,
        errors=list(ledger.errors) + recon_failures,
        metadata=metadata,
    )