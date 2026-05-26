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


# from kivygui import ld # lump data


def schedule_update_smf_record_status(smf, tranid, new_status, portfolio):
    """Function to schedule the update of SMF record status."""
    smf.update_record_status(tranid, new_status, portfolio)


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


def buy_bond(portfolio, investment, location, quantity, local, book, space, tranid, transaction,
             tradedate, settledate, kdbegin, kdend, payment_currency, smf,
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
    smf.add_record(tranid=tranid, portfolio=portfolio, investment=investment, position='long', position_effect='open',
                   location=location,
                   currency=payment_currency, qty=quantity, currency_amount=local, status='Unsettled')

    return


def sell_bond(portfolio, investment, location, quantity, local, book, closing_method,
              space, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
              smf, accrued_local, accrued_book):
    ibor_date = tradedate
    ls = "l"

    # ── SOLD INTEREST — accrued interest sold to buyer ──────────
    if accrued_local is not None and accrued_local != 0:
        je = Journals(portfolio, investment, tranid,tradedate, "s", location, "SoldInterest",
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
    smf.add_record(tranid=tranid, portfolio=portfolio, investment=investment,
                   position='long', position_effect='close', location=location,
                   currency=payment_currency, qty=quantity, currency_amount=local,
                   status='Unsettled')

    return


def short_bond(portfolio, investment, location, quantity, local, book, space, tranid,
               transaction, tradedate, settledate, kdbegin, kdend, payment_currency, smf,
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
    smf.add_record(tranid=tranid, portfolio=portfolio, investment=investment,
                   position='short', position_effect='open', location=location,
                   currency=payment_currency, qty=quantity, currency_amount=local,
                   status='Unsettled')

    return


def cover_bond(portfolio, investment, location, quantity, local, book, closing_method,
               space, tranid, transaction, tradedate, settledate, kdbegin, kdend,
               payment_currency, smf, accrued_local, accrued_book):
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
    smf.add_record(tranid=tranid, portfolio=portfolio, investment=investment,
                   position='short', position_effect='close', location=location,
                   currency=payment_currency, qty=quantity, currency_amount=local,
                   status='Unsettled')

    return

def bond_coupon(portfolio, investment, space, tranid,
                transaction, tradedate, settledate, kdbegin, kdend, payment_currency, per_share, smf):
    ibor_date = tradedate

    net_positions = smf.calculate_net_positions(portfolio=portfolio, investment=investment, date=tradedate,
                                                status="Settled")

    for location, positions in net_positions.items():
        for position_type, qty in positions.items():
            # Determine if the position is long or short for financial accounting
            ls = 'l' if 'long' in position_type else 's'

            if ls == 's':
                qty = -qty

            coupon = qty * per_share /100

            # Set financial account based on the type of position
            if coupon > 0:
                faal = "InterestReceivable"
                faie = "InterestReceipt"
            else:
                faal = "InterestPayable"
                faie = "InterestExpense"

            # Post journal entries for the coupon
            bcoup = Journals(portfolio, payment_currency, tranid, tradedate, ls, location, faal, coupon, coupon, coupon,
                             None, None, tranid,
                             transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
            space.post_journal_entry(bcoup)

            bcoupRE = Journals(portfolio, investment, 0,0, ls, location, faie, 0, -coupon, -coupon,
                               None, None, tranid,
                               transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                               "Revenue/Expense/Capital")
            space.post_journal_entry(bcoupRE)

    return
