from typing import List, Tuple, Generator
from bookkeeping import Journals, Event, RevenueExpenseCapitalRepository, load_coa_from_csv
# import currency_domain
import datetime


revenue_expense_repository = RevenueExpenseCapitalRepository()
coa = load_coa_from_csv()
je = Journals()
import heapq

journal_entries = []
event = Event()
events = []  # This is a heap-based priority queue
import cProfile


def close_bond_lots(investment: str, location: str, quantity: float, local: float, book: float, closing_method: str,
                    tax_date: datetime, space, ls: str, tranid) -> List[
    Tuple[str, str, int, datetime.datetime, float, float, float, float]]:
    bs_entries = space.asset_liability_repository.get_position_entries(investment)

    # investment_lots = [(k[0], k[1], k[2], k[3], v[0], v[1], v[2]) for k, v in bs.bs.items() if k[1] == investment and (v[0] < 0 and ls =="s" or v[0]> 0 and ls=="l")]

    # added ls to tuple
    investment_lots = [(k[:5] + v) for k, v in list(bs_entries.items()) if
                       k[1] == investment and k[5] == location and (
                                   v[0] < 0 and k[4] == ls or v[0] > 0 and k[4] == ls) and k[6] == "Cost"]

    closing_method = "FIFO"
    # Additional print statements to inspect k[0], k[1], etc.

    if not investment_lots:
        return []

    if closing_method == 'LIFO':
        investment_lots.sort(key=lambda x: (x[3], x[2]),
                             reverse=True)  # Sort by tax_date (x[3]) first, then lotid (x[2])
    elif closing_method == 'FIFO':
        investment_lots.sort(key=lambda x: (x[3], x[2]))  # Sort by tax_date (x[3]) first, then lotid (x[2])

    closed_lots = []

    remaining_quantity = quantity
    remaining_sell_proceeds = local
    remaining_sell_proceeds_book = remaining_sell_proceeds / (local / book)
    total_purchase_Cost = 0
    total_shares = 0

    # Initialize an empty set for locations
    locations = set()

    # Populate the set with locations from investment_lots
    for lot in investment_lots:
        locations.add(lot[0])

    # Now, iterate over the unique locations
    for location in locations:
        lots_in_location = [(k[0], k[1], k[2], k[3], v[0], v[1], v[2]) for k, v in bs_entries.items() if
                            k[1] == investment and (v[0] < 0 and ls == "s" or v[0] > 0 and ls == "l") and k[
                                6] == "Cost"]
        lots_left = len(lots_in_location)

        if closing_method == 'FIFO':
            lots_in_location.sort(key=lambda x: x[2])
        elif closing_method == 'LIFO':
            lots_in_location.sort(key=lambda x: x[2], reverse=True)

        # Reset remaining quantities for each new sale transaction
        remaining_quantity = quantity
        remaining_sell_proceeds = local
        remaining_sell_proceeds_book = remaining_sell_proceeds / (local / book)

        for lot in lots_in_location:
            portfolio, investment, lotid, tax_date, lot_quantity, local, book = lot

            if remaining_quantity == 0:
                break
            closed_qty = min(lot_quantity, remaining_quantity)
            if ls == "s":
                closed_qty = max(lot_quantity, remaining_quantity)

            if closed_qty == 0:
                break

            closed_proceeds = 0

            if (lot_quantity == closed_qty):
                # Close the entire lot
                closed_proceeds = remaining_sell_proceeds * closed_qty / remaining_quantity
                remaining_quantity -= closed_qty
                remaining_shares = lot_quantity - closed_qty
                remaining_sell_proceeds -= closed_proceeds
            else:
                # Close a partial lot
                remaining_quantity -= closed_qty  # sb be no qty left after execution
                remaining_shares = lot_quantity - closed_qty  # sb remaining shares in lot not disposed
                remaining_book_Cost = book * remaining_shares / lot_quantity
                total_purchase_Cost += closed_qty * local / lot_quantity
                total_shares += closed_qty
                closed_proceeds = remaining_sell_proceeds  # partial lot
                remaining_sell_proceeds -= closed_proceeds
                local = total_purchase_Cost
                book = book - remaining_book_Cost
                # lot_id = 0

            closed_lots.append((portfolio, investment, lotid, tax_date, closed_qty, local, book, closed_proceeds))
            lots_left -= 1

            # Create a new lot for the remaining quantity if it exceeds zero
            if remaining_quantity != 0 and lots_left == 0:
                raise ValueError(f"Not enough inventory to close or cover for transaction ID: {tranid}")
                lot_id = max([0] + [k[2] for k in bs.bs.keys() if k[1] == investment]) + 1
                #    local = remaining_quantity * sell_proceeds / remaining_quantity
                book = 0  # fill out in calling program
                bs.bs[(portfolio, investment, lot_id)] = (remaining_quantity, local, book)
                closed_lots.append(
                    (portfolio, investment, tax_date, remaining_quantity, remaining_sell_proceeds, 0, 0))
    return closed_lots


def bond_lot_iterator(investment, space):
    # Filter the entries based on the investment
    bs_entries = space.asset_liability_repository.get_position_entries(investment)
    matching_lots = [entry for entry in bs_entries.items() if entry[0][1] == investment]

    # Extract relevant lot information (account key and lot quantity)
    return [(entry[0], entry[1][0]) for entry in matching_lots]


def bond_lot_iterator_by_location(investment, space):
    # Filter the lots based on the given investment
    bs_entries = space.asset_liability_repository.get_position_entries(investment)

    filtered_lots = [lot for lot in bs_entries.items() if lot[0][1] == investment]

    # Group the lots by location (custodian) and accumulate quantities
    lots_by_location = {}
    for lot in filtered_lots:
        location = lot[0][4]
        if location not in lots_by_location:
            lots_by_location[location] = 0
        lots_by_location[location] += lot[1][0]

    # Return the accumulated quantities for each location
    result = [(location, quantity) for location, quantity in lots_by_location.items()]
    return result

# In bond_domain.py (or wherever schedule_update_smf_record_status used to live):

def schedule_mark_settled(af, tranid, settle_date):
    """
    Scheduler-compatible wrapper: marks a tranid as settled in the AF.
    Mirrors the shape of the old schedule_update_smf_record_status,
    so the scheduler's event-function registry just sees a regular
    module function.
    """
    af.mark_settled(tranid, settle_date)


def relieve_accrued_on_close_settle(tranid, portfolio, investment, location, ls,
                                    settle_date, payment_currency, space, af):
    """
    Fires after a close-side settlement (sell of long, cover of short).
    Reads current AccruedInterestReceivable/Payable balance for the
    bond at (location, ls). Reads the AF for what actually settled
    for this tranid. Computes proportional relief.

    Per locked Bond Accrual FX Model:
      - Partial close: proportional reduction only, no FX G/L
        crystallization (diff washes through at next coupon)
      - Full close: proportional reduction PLUS FX G/L crystallization
        here, since no future coupon will absorb the diff
    """
    from bookkeeping import Journals

    # Read what actually settled for this tranid from the AF
    record = af.lifecycle(tranid)
    if record is None:
        return  # no record, nothing to do
    settling_qty = record["settled_qty"]
    if settling_qty == 0:
        return  # nothing settled, nothing to relieve

    # Read current AccruedInterestReceivable/Payable balance
    repo = space.asset_liability_repository
    subspace = repo.get_position_space(investment)
    if subspace is None:
        return

    state_by_account = subspace.get_position_state_by_account()

    accrual_account = ("AccruedInterestReceivable" if ls == "l"
                       else "AccruedInterestPayable")
    accrued_key = (location, ls, accrual_account)

    if accrued_key not in state_by_account:
        return
    current = state_by_account[accrued_key]
    accrued_local_balance = current["local_cost"]
    accrued_book_balance = current["book_cost"]
    if accrued_local_balance == 0 and accrued_book_balance == 0:
        return

    # Query AF for net entitled position AFTER this settlement.
    # The settle event ran at precedence 1045 (mark_settled) and the
    # bond settlement flow at 1050/1053. This function runs at 1058,
    # so the AF reflects the post-settlement state.
    net_after = af.entitled_position_total(
        portfolio=portfolio, investment=investment, location=location
    )

    # Held before this close = net_after + settling_qty (since the
    # close just reduced entitled by settling_qty)
    qty_held_before = abs(net_after) + settling_qty
    if qty_held_before == 0:
        return  # defensive

    relief_fraction = settling_qty / qty_held_before
    is_full_close = abs(net_after) < 1e-9

    relief_local = accrued_local_balance * relief_fraction
    relief_book = accrued_book_balance * relief_fraction

    # ─── COMPOSE RELIEF JEs HERE ──────────────────────────────────
    # 1. Reduce AccruedInterestReceivable/Payable by
    #    (relief_local, relief_book), targeting investment=
    #    payment_currency, ls=ls, location=location
    #
    # 2. If is_full_close: post FX G/L plug for diff between
    #    relief_local × current_fx and relief_book. Crystallizes
    #    here per locked FX model.
    #
    # 3. If NOT is_full_close: no FX G/L plug. Diff washes through
    #    at next coupon.
    #
    # JE composition is your domain decision.
    # ──────────────────────────────────────────────────────────────

    print(f"AccruedInterest relief: tranid {tranid} relieved "
          f"{relief_local:.2f} local / {relief_book:.2f} book "
          f"(fraction={relief_fraction:.4f}, full_close={is_full_close})")


def buy_bond(portfolio, investment, location, quantity, local, book, space, tranid, transaction,
             tradedate, settledate, kdbegin, kdend, payment_currency, af,
             accrued_local, accrued_book, entry_type):
    # Create a new je Open IBM

    ls = "l"
    financial_account = "Cost"
    ibor_date = tradedate

    je = Journals(portfolio, investment, tranid, tradedate, ls, location, financial_account, quantity, local, book,
                  None, None, tranid,
                  transaction, tradedate, settledate, kdbegin, kdend, ibor_date, entry_type)
    space.post_journal_entry(je)

    if accrued_local is not None and accrued_local != 0:
        financial_account = "PurchasedInterest"  # use tranid for payable receivable to close
        je = Journals(portfolio, investment, tranid, tradedate, "l", location, financial_account, accrued_local,
                      accrued_local, accrued_book, None, None, tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

    # Record the settlement information to SMF
    af.add_record(
        tranid=tranid,
        portfolio=portfolio,
        investment=investment,
        location=location,
        ls="l",
        position_effect="open",
        qty=quantity,
        currency_amount=local,
        trade_date=tradedate,
        expected_settle_date=settledate,
        currency=payment_currency,
    )

    return


def sell_bond(portfolio, investment, location, quantity, local, book, closing_method,
              space, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
              af, accrued_local, accrued_book):
    ibor_date = tradedate
    ls = "l"

    # ── SOLD INTEREST — accrued interest sold to buyer *LS tied to long for all fin accts ──────────
    if accrued_local is not None and accrued_local != 0:
        je = Journals(portfolio, investment, tranid,tradedate, ls, location, "SoldInterest",
                      -accrued_local, -accrued_local, -accrued_book,
                      None, None, tranid, transaction,
                      tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

    # ── CLOSE COST LOTS ──────────────────────────────────────────
    lots_returned = close_bond_lots(investment, location, quantity, local, book,
                                    closing_method, "", space, "l", tranid)

    for lot in lots_returned:
        portfolio, investment, lotid, tax_date, closed_qty, closed_local, closed_book, closed_proceeds = lot

        fxrate = book / local if local != 0 else 0
        pgain_local = closed_proceeds - closed_local
        pgain_book = pgain_local * fxrate
        glbook = closed_proceeds * fxrate - closed_book - pgain_book
        realized_gl = (closed_proceeds - closed_local) * fxrate * -1

        # Cost lot closure
        space.post_journal_entry(Journals(
            portfolio=portfolio, investment=investment,
            lotid=lotid, tax_date=tax_date, ls="l", location=location,
            financial_account="Cost",
            quantity=-closed_qty, local=-closed_local, book=-closed_book,
            notional=None, oface=None, tranid=tranid, transaction=transaction,
            tradedate=tradedate, settledate=settledate,
            kdbegin=kdbegin, kdend=kdend, ibor_date=ibor_date,
            entry_type="Asset/Liability"
        ))

        # Price gain/loss
        if pgain_local != 0:
            space.post_journal_entry(Journals(
                portfolio=portfolio, investment=investment,
                lotid=lotid, tax_date=tax_date, ls=ls, location=location,
                financial_account="PriceGainInvestment",
                quantity=0, local=-pgain_local, book=-pgain_book,
                notional=None, oface=None, tranid=tranid, transaction=transaction,
                tradedate=tradedate, settledate=settledate,
                kdbegin=kdbegin, kdend=kdend, ibor_date=ibor_date,
                entry_type="Revenue/Expense/Capital"
            ))

        # FX gain/loss
        if realized_gl != 0:
            space.post_journal_entry(Journals(
                portfolio=portfolio, investment=investment,
                lotid=lotid, tax_date=tax_date, ls=ls, location=location,
                financial_account="FXGainInvestment",
                quantity=0, local=0, book=-glbook,
                notional=None, oface=None, tranid=tranid, transaction=transaction,
                tradedate=tradedate, settledate=settledate,
                kdbegin=kdbegin, kdend=kdend, ibor_date=ibor_date,
                entry_type="Revenue/Expense/Capital"
            ))

    # ── SMF — one record per trade, outside lot loop ─────────────
    af.add_record(
        tranid=tranid,
        portfolio=portfolio,
        investment=investment,
        location=location,
        ls="l",
        position_effect="close",
        qty=quantity,
        currency_amount=local,
        trade_date=tradedate,
        expected_settle_date=settledate,
        currency=payment_currency,
    )

    return


def short_bond(portfolio, investment, location, quantity, local, book, space, tranid,
               transaction, tradedate, settledate, kdbegin, kdend, payment_currency, af,
               accrued_local, accrued_book, entry_type="Asset/Liability"):
    ls = "s"
    ibor_date = tradedate

    # ── SHORT COST — opens short position ────────────────────
    je = Journals(portfolio, investment, tranid, tradedate, ls, location, "Cost",
                  -quantity, -local, -book,
                  None, None, tranid, transaction,
                  tradedate, settledate, kdbegin, kdend, ibor_date, entry_type)
    space.post_journal_entry(je)

    # ── SOLD INTEREST — accrued interest on short side ───────
    if accrued_local is not None and accrued_local != 0:
        je = Journals(portfolio, investment, tranid, tranid, ls, location, "SoldInterest",
                      -accrued_local, -accrued_local, -accrued_book,
                      None, None, tranid, transaction,
                      tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

    # ── SMF — one record per trade ────────────────────────────
    af.add_record(tranid=tranid, portfolio=portfolio, investment=investment,
                   position='short', position_effect='open', location=location,
                   currency=payment_currency, qty=quantity, currency_amount=local,
                   status='Unsettled')

    return


def cover_bond(portfolio, investment, location, quantity, local, book, closing_method,
               space, tranid, transaction, tradedate, settledate, kdbegin, kdend,
               payment_currency, af, accrued_local, accrued_book):
    ibor_date = tradedate
    ls = "s"

    # ── PURCHASED INTEREST — accrued interest on cover side ──
    if accrued_local is not None and accrued_local != 0:
        je = Journals(portfolio, investment, tranid, tradedate, "l", location, "PurchasedInterest",
                      accrued_local, accrued_local, accrued_book,
                      None, None, tranid, transaction,
                      tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

    # ── CLOSE SHORT COST LOTS ─────────────────────────────────
    lots_returned = close_bond_lots(investment, location, quantity, local, book,
                                    closing_method, "", space, "s", tranid)

    for lot in lots_returned:
        portfolio, investment, lotid, tax_date, closed_qty, closed_local, closed_book, closed_proceeds = lot

        fxrate = book / local if local != 0 else 0
        pgain_local = closed_local - closed_proceeds  # reversed — gain when price falls
        pgain_book = pgain_local * fxrate
        glbook = closed_proceeds * fxrate - closed_book - pgain_book
        realized_gl = (closed_local - closed_proceeds) * fxrate

        # Cost lot closure
        space.post_journal_entry(Journals(
            portfolio=portfolio, investment=investment,
            lotid=lotid, tax_date=tax_date, ls="s", location=location,
            financial_account="Cost",
            quantity=closed_qty, local=closed_local, book=closed_book,
            notional=None, oface=None, tranid=tranid, transaction=transaction,
            tradedate=tradedate, settledate=settledate,
            kdbegin=kdbegin, kdend=kdend, ibor_date=ibor_date,
            entry_type="Asset/Liability"
        ))

        # Price gain/loss
        if pgain_local != 0:
            space.post_journal_entry(Journals(
                portfolio=portfolio, investment=investment,
                lotid=lotid, tax_date=tax_date, ls=ls, location=location,
                financial_account="PriceGainInvestment",
                quantity=0, local=-pgain_local, book=-pgain_book,
                notional=None, oface=None, tranid=tranid, transaction=transaction,
                tradedate=tradedate, settledate=settledate,
                kdbegin=kdbegin, kdend=kdend, ibor_date=ibor_date,
                entry_type="Revenue/Expense/Capital"
            ))

        # FX gain/loss
        if realized_gl != 0:
            space.post_journal_entry(Journals(
                portfolio=portfolio, investment=investment,
                lotid=lotid, tax_date=tax_date, ls=ls, location=location,
                financial_account="FXGainInvestment",
                quantity=0, local=0, book=-glbook,
                notional=None, oface=None, tranid=tranid, transaction=transaction,
                tradedate=tradedate, settledate=settledate,
                kdbegin=kdbegin, kdend=kdend, ibor_date=ibor_date,
                entry_type="Revenue/Expense/Capital"
            ))

    # ── SMF — one record per trade, outside lot loop ──────────
    af.add_record(tranid=tranid, portfolio=portfolio, investment=investment,
                   position='short', position_effect='close', location=location,
                   currency=payment_currency, qty=quantity, currency_amount=local,
                   status='Unsettled')

    return


def bond_coupon(portfolio, investment, space, tranid,
                transaction, tradedate, settledate, kdbegin, kdend,
                payment_currency, per_share, af):
    ibor_date = tradedate

    # AF returns dict[(location, ls)] -> signed net entitled qty
    # (settled qty only, opens minus closes)
    positions = af.entitled_position(portfolio=portfolio,
                                     investment=investment)

    for (location, ls), entitled_qty in positions.items():
        # Skip zero-net buckets (e.g. fully netted location)
        if entitled_qty == 0:
            continue

        # Coupon magnitude and direction.
        # entitled_qty is already signed (long positive, short negative),
        # so coupon naturally carries the right sign.
        coupon = entitled_qty * per_share / 100

        # Set financial account based on direction of the cash flow.
        # > 0: you're receiving coupon  -> Receivable + Income
        # < 0: you're paying coupon     -> Payable + Expense
        # Same economic-direction rule as mark_bond_accruals.
        if coupon > 0:
            faal = "InterestReceivable"
            faie = "InterestIncome"
        else:
            faal = "InterestPayable"
            faie = "InterestExpense"

        # Post journal entries for the coupon
        bcoup = Journals(portfolio, payment_currency, tranid, tradedate,
                         ls, location, faal, coupon, coupon, coupon,
                         None, None, tranid,
                         transaction, tradedate, settledate,
                         kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(bcoup)

        bcoupRE = Journals(portfolio, investment, 0, 0,
                           ls, location, faie, 0, -coupon, -coupon,
                           None, None, tranid,
                           transaction, tradedate, settledate,
                           kdbegin, kdend, ibor_date,
                           "Revenue/Expense/Capital")
        space.post_journal_entry(bcoupRE)

    return
