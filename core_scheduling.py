import utilities

import equity_domain
import bond_domain
import futures_domain
import global_domain
import schedule_activities
from global_domain import mark_prices, mark_bond_accruals, bond_coupon

from bookkeeping import EventScheduler, Event
import currency_domain

event = Event()

on = 0
tranid = 0
import validate

journal_entries = []
events = []

# ── TRANID NUMBER SERIES ──────────────────────────────────────────────
# Regular trades:       1         →  99,999,999
# Marks:                100,000,000 → 199,999,999
# Dependent events:     200,000,000 → 299,999,999
MARK_TRANID_START = 100_000_000
DEPENDENT_TRANID_START = 200_000_000

def normalize_numeric(value):
    """
    Normalize a value to a float, handling strings with commas, integers, and floats.
    """
    if isinstance(value, str):  # If it's a string, remove commas and convert
        value = value.replace(",", "").strip()
        return float(value) if value else 0.0
    elif isinstance(value, (int, float)):  # If it's already a number, return it as float
        return float(value)
    else:  # Default fallback
        return 0.0

# =======================================================================
# 🔹 BUILD BOND CANDIDATES
# =======================================================================

# ── BUILD BOND CANDIDATES ─────────────────────────────────────────────
def build_bond_candidates(retrieved_events_records, period_end, space):
    """
    Build mapping of (portfolio, investment) → first tradedate
    filtered to BOND investments only.
    Uses repo.investment_attributes — authoritative AIF source.
    """
    candidates = {}
    repo = space.asset_liability_repository

    for er in retrieved_events_records:
        tradedate = er["tradedate"]
        if tradedate > period_end:
            continue

        inv = er["investment"]
        port = er["portfolio"]

        sub = repo.investment_attributes.get(inv)
        if not sub:
            continue

        attributes = sub.investment_attributes.get("AIF", {})
        if attributes.get("investment_type") == "BOND":
            key = (port, inv)
            if key not in candidates:
                candidates[key] = tradedate

    return candidates


# ── GENERATE COUPON DATES — exact month arithmetic ────────────────────
def generate_coupon_dates(first_coupon_date, maturity_date, payment_frequency,
                          period_start, period_end):
    """
    Generate coupon dates within period using exact month arithmetic.
    Uses relativedelta — no timedelta approximation.
    """
    from dateutil.relativedelta import relativedelta

    freq_months = {
        "annual": 12,
        "semi-annual": 6,
        "quarterly": 3,
        "monthly": 1,
        "ANNUAL": 12,
        "SEMI_ANNUAL": 6,
        "QUARTERLY": 3,
        "MONTHLY": 1,
    }

    months = freq_months.get(payment_frequency)
    if months is None:
        raise ValueError(f"Unknown payment frequency: {payment_frequency}")

    cur = first_coupon_date
    cds = []

    while cur <= maturity_date and cur <= period_end:
        if cur >= period_start:
            cds.append(cur)
        cur += relativedelta(months=months)

    return cds

def core_schedule_events(
    interpretation_ctx,
    qualifying_events,
    space,
    scheduler,
    af
):
    """
    Mechanical wrapper around existing scheduling logic.
    NO behavioral changes.
    """

    # ------------------------------------------------------------
    # BEGIN: ORIGINAL CODE (UNCHANGED)
    # ------------------------------------------------------------

    fx_data = utilities.load_fx_data_as_rows(
        "C:/Users/hjmne/PycharmProjects/chest/refdata/fx_master.csv"
    )
    import time

    _t0 = time.perf_counter()
    last_report = _t0
    REPORT_EVERY = 10000  # adjust if needed

    # ── RE-OFFER events deferred from prior periods ──────────────
    # Carried-forward out-of-window events (settles spanning a period
    # boundary) re-enter through the SAME schedule_event intake as
    # native events, so sort_events interleaves them by date. Sentinels
    # are rebound to THIS period's live af / space / fx_data -- never a
    # stale snapshot copy.

    scheduler.reoffer_deferred_events(
        cutoff=interpretation_ctx["trade_window_cutoff"],
        af=af, space=space, fx_data=fx_data,
    )

    total = len(qualifying_events)

  #  for event_record_args in events_for_scheduler:
    for i, event_record_args in enumerate(qualifying_events, 1):
        # --- progress probe ---
        if i % REPORT_EVERY == 0:
            now = time.perf_counter()
            print(
                f"[PROCESS] {i:,}/{total:,} "
                f"({i / total:5.1%})  "
                f"elapsed={now - _t0:6.2f}s  "
                f"delta={now - last_report:5.2f}s"
            )
            last_report = now
        portfolio = event_record_args['portfolio']
        method = event_record_args['method']
        tradedate = event_record_args['tradedate']
        settledate = event_record_args['settledate']
        kdbegin = event_record_args['kdbegin']
        kdend = event_record_args['kdend']
        investment =   event_record_args['investment']
        payment_currency = event_record_args['payment_currency']
        tdate_fx_value = event_record_args.get('tdate_fx', "").strip() if isinstance(
            event_record_args.get('tdate_fx', ""), str) else event_record_args.get('tdate_fx', 0)
        tdate_fx = float(tdate_fx_value) if tdate_fx_value else 0

        location = event_record_args['location']
        strategy = event_record_args['strategy']
        # Updated field processing with normalize_numeric
        quantity = normalize_numeric(event_record_args['quantity'])
        price = normalize_numeric(event_record_args.get('price')) if 'price' in event_record_args else None
        notional = normalize_numeric(event_record_args['notional'])
        original_face = normalize_numeric(event_record_args['original_face']) or None
        local = normalize_numeric(event_record_args['total_amount'])
        book = normalize_numeric(event_record_args['total_amount_base'])
        tranid = int(normalize_numeric(event_record_args['tranid']))
        transaction = event_record_args['transaction']
        accrued_local = normalize_numeric(event_record_args['accrued_local'])
        accrued_book = normalize_numeric(event_record_args['accrued_book'])
        new_shares = normalize_numeric(event_record_args['new_shares'])
        old_shares = normalize_numeric(event_record_args['old_shares'])
        per_share = normalize_numeric(event_record_args['per_share'])
        legin = event_record_args['legin']
        legout = event_record_args['legout']
        allocation_entities = event_record_args['allocation_entities']
        allocation_percents = event_record_args['allocation_percents']
        financial_account = event_record_args['financial_account']
        buy_currency = event_record_args['buy_currency']
        sell_currency = event_record_args['sell_currency']
        buy_amt = normalize_numeric(event_record_args['buy_amt'])
        sell_amt = normalize_numeric(event_record_args['sell_amt'])
        mark_price = normalize_numeric(event_record_args.get('mark_price'))
        mark_fx = normalize_numeric(event_record_args.get('mark_fx'))
        per_100FV_accrue = normalize_numeric(event_record_args.get('per_100FV_accrue'))
        per_100FV_amort = normalize_numeric(event_record_args.get('per_100FV_amort'))

        # ------------------------------------------------------------------
        # EVENT QUALIFICATION — PURE VISIBILITY FILTER
        # (NO mutation, NO collection, NO parsing)
        # ------------------------------------------------------------------

        # Assumptions:
        # - tradedate, kdbegin, kdend are datetime (or NaT handled upstream)
        # - current_period_knowledge is frozen ONCE in PE
        # - current_period_cutoff and replay_start are normalized and trusted

        # Required fields must exist
        if tradedate is None or kdbegin is None or kdend is None:
            continue

        # REPLAY / PERIOD WINDOW
        if not (interpretation_ctx["replay_start"] <= tradedate <= interpretation_ctx["trade_window_cutoff"]):
            continue

        # KNOWLEDGE VALIDITY WINDOW (core invariant)
        if not (kdbegin <= interpretation_ctx["effective_knowledge_date"] <= kdend):
            continue

        # TRANSACTION ID GUARD
        if tranid == 0:
            continue

        if method == "buy_equity" or method == "buy_option":
            scheduler.schedule_event(
                tradedate,
                equity_domain.buy_equity,
                portfolio, investment,
                location, quantity, local, book, space,
                tranid, transaction, tradedate, settledate, kdbegin, kdend, "Asset/Liability"
            )

            if tradedate == settledate:
                # Same-day settle: cash directly, no Payable lifecycle.
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.cash_payment_same_day,
                    portfolio, payment_currency,
                    location, -local, -local, -book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend
                )
            else:
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.open_payable,
                    portfolio, payment_currency,
                    location, local, book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend,
                    "Payable"
                )

                if settledate <= interpretation_ctx["trade_window_cutoff"]:
                    scheduler.schedule_event(settledate, currency_domain.settle_single_flow_out, portfolio,
                                             payment_currency, location, quantity, local, book,
                                             space, tranid, "Settlement", tradedate, settledate,
                                             kdbegin, kdend, fx_data)

        elif method == "sell_equity" or method == "sell_option":
            closing_method = "FIFO"
            scheduler.schedule_event(tradedate, equity_domain.sell_equity, portfolio, investment,
                                     location, quantity, local, book, closing_method,
                                     space, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                     payment_currency, tdate_fx)

            if tradedate == settledate:
                # Same-day settle: cash directly, no Payable lifecycle.
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.cash_payment_same_day,
                    portfolio, payment_currency,
                    location, local, local, book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend
                )
            else:
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.open_receivable,
                    portfolio, payment_currency,
                    location, local, book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend,
                    "Receivable"
                )

                if settledate <= interpretation_ctx["trade_window_cutoff"]:
                    scheduler.schedule_event(settledate, currency_domain.settle_single_flow_in, portfolio,
                                             payment_currency, location, quantity, local, book,
                                             space, tranid, "Settlement", tradedate, settledate,
                                             kdbegin, kdend, fx_data)


        elif method == "short_equity" or method == "short_option" or method == "write_option":
            scheduler.schedule_event(
                tradedate,
                equity_domain.short_equity,
                portfolio, investment,
                location, quantity, local, book, space,
                tranid, transaction, tradedate, settledate, kdbegin, kdend, "Asset/Liability"
            )

            if tradedate == settledate:
                # Same-day settle: cash directly, no Payable lifecycle.
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.cash_payment_same_day,
                    portfolio, payment_currency,
                    location, local, local, book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend
                )
            else:
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.open_receivable,
                    portfolio, payment_currency,
                    location, local, book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend,
                    "Receivable"
                )

                if settledate <= interpretation_ctx["trade_window_cutoff"]:
                    scheduler.schedule_event(settledate, currency_domain.settle_single_flow_in, portfolio,
                                             payment_currency, location, quantity, local, book,
                                             space, tranid, "Settlement", tradedate, settledate,
                                             kdbegin, kdend, fx_data)

        elif method == "cover_equity" or method == "cover_option":
            closing_method = "FIFO"
            scheduler.schedule_event(tradedate, equity_domain.cover_equity, portfolio, investment,
                                     location, quantity, local, book, closing_method,
                                     space, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                     payment_currency, tdate_fx)

            if tradedate == settledate:
                # Same-day settle: cash directly, no Payable lifecycle.
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.cash_payment_same_day,
                    portfolio, payment_currency,
                    location, -local, -local, -book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend
                )
            else:
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.open_payable,
                    portfolio, payment_currency,
                    location, local, book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend,
                    "Payable"
                )

                if settledate <= interpretation_ctx["trade_window_cutoff"]:
                    scheduler.schedule_event(settledate, currency_domain.settle_single_flow_out, portfolio,
                                             payment_currency, location, quantity, local, book,
                                             space, tranid, "Settlement", tradedate, settledate,
                                             kdbegin, kdend, fx_data)

        elif method == "dividend_equity":
            scheduler.schedule_event(tradedate, equity_domain.dividend_equity, portfolio, investment,
                                     space, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                     payment_currency, per_share, fx_data)

            if tradedate != settledate and settledate <= interpretation_ctx["trade_window_cutoff"]:
                financial_account_in = "DividendsReceivable"
                financial_account_out = "DividendsPayable"
                scheduler.schedule_event(settledate, currency_domain.settle_multiple_flows_in_out, portfolio,
                                         payment_currency, investment, financial_account_in, financial_account_out,
                                         space, tranid, "Settlement", tradedate, settledate, kdbegin,
                                         kdend, af, fx_data)

        elif method == "buy_future":
            scheduler.schedule_event(tradedate, futures_domain.buy_future, portfolio, investment,
                                     location, quantity, local, book, space, tranid,
                                     transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                                     tdate_fx, notional)

            if local != 0:
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.open_payable,
                    portfolio, payment_currency,
                    location, local, book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend,
                    "Payable"
                )

            if tradedate != settledate and settledate < interpretation_ctx["trade_window_cutoff"] and local != 0:
                scheduler.schedule_event(settledate, currency_domain.settle_single_flow_out, portfolio,
                                         payment_currency, investment, location, quantity, local, book,
                                         space, tranid, "Settlement", tradedate, settledate, kdbegin,
                                         kdend, fx_data)
        elif method == "buy_bond":
            scheduler.schedule_event(tradedate, bond_domain.buy_bond, portfolio,
                                     investment,
                                     location, quantity, local, book, space, tranid,
                                     transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                                     af, accrued_local, accrued_book, "Asset/Liability")

            if tradedate == settledate:
                # Same-day settle: cash directly, no Payable lifecycle.
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.cash_payment_same_day,
                    portfolio, payment_currency,
                    location, -local + -accrued_local, -local + -accrued_local, -book + -accrued_book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend
                )

                # Same-day: AF record settles on trade date. Runs at
                # 1045, after accrual's 1040 -- buyer's entitlement
                # begins the day AFTER settle, so trade date posts
                # nothing for the buyer (seller's day, through-settle
                # inclusive). Same mechanism as the gapped case.
                scheduler.schedule_event(settledate, bond_domain.schedule_mark_settled,
                                         af, tranid, settledate)
            else:
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.open_payable,
                    portfolio, payment_currency,
                    location, local + accrued_local, book + accrued_book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend,
                    "Payable"
                )

                # Settlement posting and AF settled-marking are ONE act: the
                # books and the entitlement state move together or not at all.
                # Both are gated on the settle actually falling within the
                # processable window. Marking the AF settled while the
                # settlement JE is withheld would flip entitlement (starting
                # accrual) with no settlement on the books -- a state/ledger
                # divergence, and accrual before settledate.
                if settledate <= interpretation_ctx["trade_window_cutoff"]:
                    scheduler.schedule_event(settledate, currency_domain.settle_bond_flows_out,
                                             portfolio, payment_currency, investment, location, quantity, local, book,
                                             space, tranid, "Settlement", tradedate, settledate, kdbegin,
                                             kdend, af, accrued_local, accrued_book, fx_data, "l")

                    scheduler.schedule_event(settledate, bond_domain.schedule_mark_settled,
                                             af, tranid, settledate)
                else:
                    scheduler.defer_event(settledate, currency_domain.settle_bond_flows_out,
                                          portfolio, payment_currency, investment, location, quantity, local, book,
                                          space, tranid, "Settlement", tradedate, settledate, kdbegin,
                                          kdend, af, accrued_local, accrued_book, fx_data, "l")

                    scheduler.defer_event(settledate, bond_domain.schedule_mark_settled,
                                          af, tranid, settledate)

        elif method == "sell_bond":
            closing_method = "FIFO"
            scheduler.schedule_event(tradedate, bond_domain.sell_bond, portfolio, investment,
                                     location, quantity, local, book, closing_method,
                                     space, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                     payment_currency, af, accrued_local,
                                     accrued_book)

            if tradedate == settledate:
                # Same-day settle: cash directly, no Receivable lifecycle.
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.cash_payment_same_day,
                    portfolio, payment_currency,
                    location, local + accrued_local, local + accrued_local, book + accrued_book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend
                )

                # Same-day: disposition settles on trade date. Accrual
                # at 1040 still posts the final owned day (seller
                # through settle inclusive) before this flips the AF.
                scheduler.schedule_event(settledate, bond_domain.schedule_mark_settled,
                                         af, tranid, settledate)

                # Same-day close still relieves accrued -- without
                # this the receivable strands (Pillar 7 residual).
                scheduler.schedule_event(settledate, bond_domain.relieve_accrued_on_close_settle,
                                         tranid, portfolio, investment, location, "l",
                                         settledate, payment_currency, space, af)
            else:
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.open_receivable,
                    portfolio, payment_currency,
                    location, local + accrued_local, book + accrued_book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend,
                    "Payable"
                )

                if settledate <= interpretation_ctx["trade_window_cutoff"]:
                    scheduler.schedule_event(settledate, currency_domain.settle_bond_flows_in,
                                             portfolio, payment_currency, investment, location, quantity, local, book,
                                             space, tranid, "Settlement", tradedate, settledate, kdbegin,
                                             kdend, af, accrued_local, accrued_book, fx_data, "l")

                # Schedule another event to updateAF record status*
                scheduler.schedule_event(settledate, bond_domain.schedule_mark_settled,
                                         af, tranid, settledate)

                scheduler.schedule_event(settledate, bond_domain.relieve_accrued_on_close_settle,
                                         tranid, portfolio, investment, location, "l",
                                         settledate, payment_currency, space, af)

        elif method == "short_bond":
            scheduler.schedule_event(tradedate, bond_domain.short_bond, portfolio,
                                     investment,
                                     location, quantity, local, book, space, tranid,
                                     transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                                     af, accrued_local, accrued_book, "Asset/Liability")

            if tradedate == settledate:
                # Same-day settle: cash directly, no Receivable lifecycle.
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.cash_payment_same_day,
                    portfolio, payment_currency,
                    location, local + accrued_local, local + accrued_local, book + accrued_book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend
                )

                # Same-day: short's AF record settles on trade date --
                # entitlement (negative, payable side) begins next day.
                scheduler.schedule_event(settledate, bond_domain.schedule_mark_settled,
                                         af, tranid, settledate)
            else:
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.open_receivable,
                    portfolio, payment_currency,
                    location, local + accrued_local, book + accrued_book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend,
                    "Receivable"
                )

                if settledate <= interpretation_ctx["trade_window_cutoff"]:
                    scheduler.schedule_event(settledate, currency_domain.settle_bond_flows_in,
                                             portfolio, payment_currency, investment, location, quantity, local, book,
                                             space, tranid, "Settlement", tradedate, settledate, kdbegin,
                                             kdend, af, accrued_local, accrued_book, fx_data, "s")

                # Schedule another event to updateAF record status*
                scheduler.schedule_event(settledate, bond_domain.schedule_mark_settled,
                                         af, tranid, settledate)

        elif method == "cover_bond":
            closing_method = "FIFO"
            scheduler.schedule_event(tradedate, bond_domain.cover_bond, portfolio, investment,
                                     location, quantity, local, book, closing_method,
                                     space, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                     payment_currency, af, accrued_local,
                                     accrued_book)

            if tradedate == settledate:
                # Same-day settle: cash directly, no Payable lifecycle.
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.cash_payment_same_day,
                    portfolio, payment_currency,
                    location, -local + -accrued_local, -local + -accrued_local, -book + -accrued_book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend
                )

                # Same-day: cover's AF record settles on trade date --
                # short entitlement runs through settle inclusive,
                # then this flips it at 1045.
                scheduler.schedule_event(settledate, bond_domain.schedule_mark_settled,
                                         af, tranid, settledate)

                # Same-day close of the short still relieves accrued
                # payable -- strands otherwise (Pillar 7 residual).
                scheduler.schedule_event(settledate, bond_domain.relieve_accrued_on_close_settle,
                                         tranid, portfolio, investment, location, "s",
                                         settledate, payment_currency, space, af)
            else:
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.open_payable,
                    portfolio, payment_currency,
                    location, local + accrued_local, book + accrued_book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend,
                    "Payable"
                )

                if settledate <= interpretation_ctx["trade_window_cutoff"]:
                    scheduler.schedule_event(settledate, currency_domain.settle_bond_flows_out,
                                             portfolio, payment_currency, investment, location, quantity, local, book,
                                             space, tranid, "Settlement", tradedate, settledate, kdbegin,
                                             kdend, af, accrued_local, accrued_book, fx_data, "s")

                # Schedule another event to updateAF record status*
                scheduler.schedule_event(settledate, bond_domain.schedule_mark_settled,
                                         af, tranid, settledate)

                scheduler.schedule_event(settledate, bond_domain.relieve_accrued_on_close_settle,
                                         tranid, portfolio, investment, location, "s",
                                         settledate, payment_currency, space, af)

        if method == "short_future":
            scheduler.schedule_event(tradedate, futures_domain.short_future, portfolio, investment,
                                     location, quantity, local, book, space, tranid,
                                     transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                                     tdate_fx, notional, price)

            if local != 0:
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.open_payable,
                    portfolio, payment_currency,
                    location, local, book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend,
                    "Payable"
                )

            if tradedate != settledate and settledate <= interpretation_ctx["trade_window_cutoff"] and local != 0:
                scheduler.schedule_event(settledate, currency_domain.settle_pay_rec_by_tranid, portfolio,
                                         payment_currency, location, quantity, local, book,
                                         space, tranid, "FuturesSettlement", tradedate, settledate, kdbegin,
                                         kdend, payment_currency, af, fx_data)



        elif method == "cover_future":
            closing_method = "FIFO"
            scheduler.schedule_event(tradedate, futures_domain.cover_future, portfolio, investment,
                                     location, quantity, local, book, closing_method,
                                     space, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                     payment_currency, tdate_fx, notional, price, fx_data)

            if tradedate != settledate and settledate <= interpretation_ctx["trade_window_cutoff"]:
                # Schedule settlement event
                scheduler.schedule_event(
                    settledate, currency_domain.settle_pay_rec_by_tranid, portfolio, investment, location, quantity,
                    local, book,
                    space, tranid, "FutureSettlement", tradedate, settledate, kdbegin,
                    kdend, payment_currency, af, fx_data)


        elif method == "sell_future":
            closing_method = "FIFO"
            scheduler.schedule_event(tradedate, futures_domain.sell_future, portfolio, investment,
                                     location, quantity, local, book, closing_method,
                                     space, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                     payment_currency, tdate_fx, notional, price, fx_data)

            if local != 0:
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.open_payable,
                    portfolio, payment_currency,
                    location, local, book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend,
                    "Payable"
                )

            if tradedate != settledate and settledate <= interpretation_ctx["trade_window_cutoff"]:
                # Schedule settlement event
                scheduler.schedule_event(
                    settledate, currency_domain.settle_pay_rec_by_tranid, portfolio, investment, location, quantity,
                    local, book,
                    space, tranid, "FuturesSettlement", tradedate, settledate, kdbegin,
                    kdend, payment_currency, af, fx_data)

        elif method == "split_equity":
            scheduler.schedule_event(tradedate, equity_domain.split_equity, portfolio, investment,
                                     space, tranid, transaction, tradedate, settledate,
                                     kdbegin, kdend, new_shares, old_shares)



        elif method == "deposit_currency":
            scheduler.schedule_event(tradedate, currency_domain.deposit_currency, portfolio,
                                     payment_currency, location, quantity, local, book,
                                     space, tranid, transaction, tradedate, settledate, kdbegin, kdend, fx_data)

            if tradedate == settledate:
                # Same-day settle: cash directly, no Payable lifecycle.
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.cash_payment_same_day,
                    portfolio, payment_currency,
                    location, local, local, book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend
                )
            else:
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.open_receivable,
                    portfolio, payment_currency,
                    location, local, book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend,
                    "Receivable"
                )

                if settledate <= interpretation_ctx["trade_window_cutoff"]:
                    scheduler.schedule_event(settledate, currency_domain.settle_single_flow_in, portfolio,
                                             payment_currency, location, quantity, local, book,
                                             space, tranid, "Settlement", tradedate, settledate,
                                             kdbegin, kdend, fx_data)




        elif method == "withdraw_currency":
            scheduler.schedule_event(tradedate, currency_domain.withdraw_currency, portfolio,
                                     payment_currency, location, local, local, book,
                                     space, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                     fx_data)

            if tradedate == settledate:
                # Same-day settle: cash directly, no Payable lifecycle.
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.cash_payment_same_day,
                    portfolio, payment_currency,
                    location, -local, -local, -book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend
                )
            else:
                scheduler.schedule_event(
                    tradedate,
                    currency_domain.open_payable,
                    portfolio, payment_currency,
                    location, local, book, space,
                    tranid, transaction, tradedate, settledate, kdbegin, kdend,
                    "Payable"
                )

                if settledate <= interpretation_ctx["trade_window_cutoff"]:
                    scheduler.schedule_event(settledate, currency_domain.settle_single_flow_out, portfolio,
                                             payment_currency, location, quantity, local, book,
                                             space, tranid, "Settlement", tradedate, settledate,
                                             kdbegin, kdend, fx_data)


        elif method == "open_equity_swap_long":
            scheduler.schedule_event(tradedate, swaps_domain.open_equity_swap_long, portfolio, investment,
                                     location, quantity, local, book, notional, space,
                                     tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                     payment_currency, tdate_fx, af, legin, legout)

        # elif method == "open_equity_swap_short":
        #     scheduler.schedule_event(tradedate, swaps_domain.open_equity_swap_long, portfolio, investment,
        #                              location, quantity, local, book, notional,  space,
        #                              tranid, transaction, tradedate, settledate, kdbegin, kdend,
        #                              payment_currency, tdate_fx, af, legin, legout)
        #
        elif method == "allocate":
            scheduler.schedule_event(tradedate, global_domain.allocate, portfolio,
                                     investment, location, quantity, local, book,
                                     tranid, transaction, tradedate, settledate, kdbegin, kdend, current_period_start,
                                     interpretation_ctx["trade_window_cutoff"], af, allocation_entities, allocation_percents)

        elif method == "expense":
            scheduler.schedule_event(tradedate, currency_domain.expense, portfolio,
                                     payment_currency, location, quantity, local, book, financial_account,
                                     space, tranid, transaction, tradedate, settledate, kdbegin, kdend, current_period_start,
                                     investment_accounting_space)

        elif method == "spot_fx":

            scheduler.schedule_event(tradedate, currency_domain.spot_fx, portfolio, investment, location,
                                     buy_currency, buy_currency, book, space, tranid, transaction, tradedate,
                                     settledate, kdbegin, kdend, buy_currency, sell_currency, buy_amt,
                                     sell_amt)
            if tradedate != settledate and settledate <= interpretation_ctx["trade_window_cutoff"]:
                scheduler.schedule_event(settledate, currency_domain.settle_single_flow_out, portfolio,
                                         sell_currency, location, sell_amt, sell_amt, book,
                                         space, tranid, "SpotSettlement", tradedate, settledate, kdbegin,
                                         kdend, fx_data)

                scheduler.schedule_event(settledate, currency_domain.settle_single_flow_in, portfolio,
                                         buy_currency, location, buy_amt, buy_amt, book,
                                         space, tranid, "SpotSettlement", tradedate, settledate, kdbegin,
                                         kdend, fx_data)
        # Schedule based on the method type (assign/exercise and call/put long/short)
        elif method == "assign_call_long":
            closing_method = "FIFO"
            scheduler.schedule_event(tradedate, equity_domain.assign_call_long, portfolio, investment, location,
                                     quantity,
                                     local, book, closing_method, space, tranid, transaction,
                                     tradedate, settledate, kdbegin, kdend, payment_currency, tdate_fx)
            if tradedate != settledate and settledate <= interpretation_ctx["trade_window_cutoff"]:
                scheduler.schedule_event(settledate, currency_domain.settle_pay_rec_by_tranid, portfolio,
                                         payment_currency,
                                         location, quantity, local, book, space, tranid,
                                         "Settlement", tradedate, settledate, kdbegin, kdend, fx_data)

        elif method == "assign_put_long":
            closing_method = "FIFO"
            scheduler.schedule_event(tradedate, equity_domain.assign_put_long, portfolio, investment, location,
                                     quantity,
                                     local, book, closing_method, space, tranid, transaction,
                                     tradedate, settledate, kdbegin, kdend, payment_currency, tdate_fx)
            if tradedate != settledate and settledate <= interpretation_ctx["trade_window_cutoff"]:
                scheduler.schedule_event(settledate, currency_domain.settle_pay_rec_by_tranid, portfolio,
                                         payment_currency,
                                         location, quantity, local, book, space, tranid,
                                         "Settlement", tradedate, settledate, kdbegin, kdend, fx_data)

        elif method == "assign_call_short":
            closing_method = "FIFO"
            scheduler.schedule_event(tradedate, equity_domain.assign_call_short, portfolio, investment, location,
                                     quantity,
                                     local, book, closing_method, space, tranid, transaction,
                                     tradedate, settledate, kdbegin, kdend, payment_currency, tdate_fx)
            if tradedate != settledate and settledate <= interpretation_ctx["trade_window_cutoff"]:
                scheduler.schedule_event(settledate, currency_domain.settle_pay_rec_by_tranid, portfolio,
                                         payment_currency,
                                         location, quantity, local, book, space, tranid,
                                         "Settlement", tradedate, settledate, kdbegin, kdend, fx_data)

        elif method == "assign_put_short":
            closing_method = "FIFO"
            scheduler.schedule_event(tradedate, equity_domain.assign_put_short, portfolio, investment, location,
                                     quantity,
                                     local, book, closing_method, space, tranid, transaction,
                                     tradedate, settledate, kdbegin, kdend, payment_currency, tdate_fx)
            if tradedate != settledate and settledate <= interpretation_ctx["trade_window_cutoff"]:
                scheduler.schedule_event(settledate, currency_domain.settle_pay_rec_by_tranid, portfolio,
                                         payment_currency,
                                         location, quantity, local, book, space, tranid,
                                         "Settlement", tradedate, settledate, kdbegin, kdend, fx_data)

        elif method == "exercise_call_long":
            closing_method = "FIFO"
            scheduler.schedule_event(tradedate, equity_domain.exercise_call_long, portfolio, investment, location,
                                     quantity,
                                     local, book, closing_method, space, tranid, transaction,
                                     tradedate, settledate, kdbegin, kdend, payment_currency, tdate_fx)
            if tradedate != settledate and settledate <= interpretation_ctx["trade_window_cutoff"]:
                scheduler.schedule_event(settledate, currency_domain.settle_pay_rec_by_tranid, portfolio,
                                         payment_currency,
                                         location, quantity, local, book, space, tranid,
                                         "Settlement", tradedate, settledate, kdbegin, kdend, fx_data)

        elif method == "exercise_put_long":
            closing_method = "FIFO"
            scheduler.schedule_event(tradedate, equity_domain.exercise_put_long, portfolio, investment, location,
                                     quantity,
                                     local, book, closing_method, space, tranid, transaction,
                                     tradedate, settledate, kdbegin, kdend, payment_currency, tdate_fx)
            if tradedate != settledate and settledate <= interpretation_ctx["trade_window_cutoff"]:
                scheduler.schedule_event(settledate, currency_domain.settle_pay_rec_by_tranid, portfolio,
                                         payment_currency,
                                         location, quantity, local, book, space, tranid,
                                         "Settlement", tradedate, settledate, kdbegin, kdend, fx_data)

        elif method == "exercise_call_short":
            closing_method = "FIFO"
            scheduler.schedule_event(tradedate, equity_domain.exercise_call_short, portfolio, investment, location,
                                     quantity,
                                     local, book, closing_method, space, tranid, transaction,
                                     tradedate, settledate, kdbegin, kdend, payment_currency, tdate_fx)
            if tradedate != settledate and settledate <= interpretation_ctx["trade_window_cutoff"]:
                scheduler.schedule_event(settledate, currency_domain.settle_pay_rec_by_tranid, portfolio,
                                         payment_currency,
                                         location, quantity, local, book, space, tranid,
                                         "Settlement", tradedate, settledate, kdbegin, kdend, fx_data)

        elif method == "exercise_put_short":
            closing_method = "FIFO"
            scheduler.schedule_event(tradedate, equity_domain.exercise_put_short, portfolio, investment, location,
                                     quantity,
                                     local, book, closing_method, space, tranid, transaction,
                                     tradedate, settledate, kdbegin, kdend, payment_currency, tdate_fx)
            if tradedate != settledate and settledate <= interpretation_ctx["trade_window_cutoff"]:
                scheduler.schedule_event(settledate, currency_domain.settle_pay_rec_by_tranid, portfolio,
                                         payment_currency,
                                         location, quantity, local, book, space, tranid,
                                         "Settlement", tradedate, settledate, kdbegin, kdend, fx_data)

        elif method == "mark_prices":
                # ── PRICE MARKS — all investments ─────────────────────────
                scheduler.schedule_event(
                    tradedate,
                    mark_prices,
                    portfolio,
                    investment,
                    tradedate,
                    space,
                    tranid,
                    mark_price,
                    mark_fx,
                    per_100FV_accrue,
                    per_100FV_amort
                )


        elif method == "mark_bond_accruals":
                # ── BOND ACCRUALS — self-guards for non-BOND investments ──
                # mark_bond_accruals checks investment_type == BOND internally
                # returns immediately for equities, currencies, futures
                scheduler.schedule_event(
                    tradedate,
                    mark_bond_accruals,
                    portfolio,
                    investment,
                    tradedate,
                    space,
                    tranid,
                    mark_price,
                    mark_fx,
                    per_100FV_accrue,
                    per_100FV_amort,
                    af
                )

        elif method == "bond_coupon":
            # ── BOND COUPON — self-guards for non-BOND investments ──
            #  checks investment_type == BOND internally
            # returns immediately for equities, currencies, futures
                scheduler.schedule_event(
                    tradedate,
                    bond_coupon,
                    portfolio,
                    investment,
                    space,
                    tranid,
                    transaction,
                    tradedate,
                    settledate,
                    kdbegin,
                    kdend,
                    payment_currency,
                    per_share,
                    af,
                    mark_fx,
                )

    return scheduler
