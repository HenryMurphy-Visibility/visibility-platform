from typing import List, Tuple, Generator
from bookkeeping import Journals, Bookkeeping, Event
import currency_domain
sub_ledger = Bookkeeping()
bs = sub_ledger
je = Journals()
import heapq
journal_entries = []
event = Event()
events = []  # This is a heap-based priority queue
import cProfile


def close_equity_lots(investment: str, location: str, quantity: float, local: float, book: float, closing_method: str,
                      journal_entries, asset_liability_entries, ls: str) -> List[
    Tuple[str, str, int, float, float, float, float]]:
    # investment_lots = [(k[0], k[1], k[2], k[3], v[0], v[1], v[2]) for k, v in bs.bs.items() if k[1] == investment and (v[0] < 0 and ls =="s" or v[0]> 0 and ls=="l")]

    # added ls to tuple
    investment_lots = [(k[:4] + v) for k, v in list(asset_liability_entries) if
                       k[1] == investment and k[4] == location and (v[0] < 0 and ls == "s" or v[0] > 0 and ls == "l")]

    closing_method = "FIFO"
    # Additional print statements to inspect k[0], k[1], etc.

    if not investment_lots:
        return []

    if closing_method == 'LIFO':
        investment_lots.sort(key=lambda x: x[2])
    elif closing_method == 'FIFO':
        investment_lots.sort(key=lambda x: x[2], reverse=True)

    closed_lots = []

    remaining_quantity = quantity
    remaining_sell_proceeds = local
    remaining_sell_proceeds_book = remaining_sell_proceeds / (local / book)
    total_purchase_Cost = 0
    total_shares = 0

    # Iterate over lots by location
    for location in set(lot[0] for lot in investment_lots):
        lots_in_location = [(k[0], k[1], k[2], v[0], v[1], v[2]) for k, v in asset_liability_entries if
                            k[1] == investment and (v[0] < 0 and ls == "s" or v[0] > 0 and ls == "l")]
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
            portfolio, investment, lot_id, lot_quantity, local, book = lot

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
                # Close a partial lot0
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

            closed_lots.append((portfolio, investment, lot_id, closed_qty, local, book, closed_proceeds))
            lots_left -= 1

            # Create a new lot for the remaining quantity if it exceeds zero
            if remaining_quantity != 0 and lots_left == 0:
                continue
            #    raise ValueError("Not enough inventory to close or cover")
                lot_id = max([0] + [k[2] for k in bs.bs.keys() if k[1] == investment]) + 1
                #    local = remaining_quantity * sell_proceeds / remaining_quantity
                book = 0  # fill out in calling program
                bs.bs[(portfolio, investment, lot_id)] = (remaining_quantity, local, book)
                closed_lots.append(
                    (portfolio, investment, lot_id, remaining_quantity, remaining_sell_proceeds, 0, 0))
    return closed_lots


def buy_equity(portfolio, investment, location, quantity, local, book, journal_entries, sub_ledger, tranid, transaction,
               tradedate, settledate, kdbegin, kdend, payment_currency):
    # Create a new je Open IBM
    ls = "l"
    financial_account = "Cost"
    ibor_date = tradedate
    je = Journals(portfolio, investment, tranid, ls, location, financial_account, quantity, local, book, tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    investment_accounting_space.post_journal_entry(je)
    journal_entries.append(je)

    ls = "s"
    financial_account = "Payable"
    je = Journals( portfolio, payment_currency, tranid, ls, location, financial_account, -local, -local, -book, tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    investment_accounting_space.post_journal_entry(je)
    journal_entries.append(je)

   
    return
def sell_equity(portfolio, investment, location, quantity, local, book, closing_method, journal_entries,
                sub_ledger, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency):
    if tranid == 387:
        print("here")
    ls = "l"
    financial_account = "Receivable"
    ibor_date = tradedate
    je = Journals( portfolio, payment_currency, tranid, ls, location, financial_account, local, local, book,
                      tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    investment_accounting_space.post_journal_entry(je)
    journal_entries.append(je)

    # pass 'ls' flag into closelots - determine if l or is is being closed
    # Close the lots for the given investment and quantity using the specified closing method

    lots_returned = close_equity_lots(investment, location, quantity, local, book, closing_method, journal_entries,
                                      sub_ledger.asset_liability_entries, ls)

    # Loop over the closed lots and post the corresponding journal entries
    for lotinfo in lots_returned:
        portfolio, investment, lot_id, closed_qty, closed_local, closed_book, closed_proceeds = lotinfo
        # Calculate the realized gain/loss on investment

        fxrate = book / local
        pgain_local = closed_proceeds - closed_local
        pgain_book = pgain_local * fxrate
        glbook = closed_proceeds * fxrate - closed_book - pgain_book
        realized_gl = (closed_proceeds - closed_local) * fxrate * -1

        if closed_book == 0:  # method passes back 0 for book as we need to convert it to trade fx equivalent
            closed_book = closed_local * fxrate

        # Post journal entries to update the bookkeeping space for investment
        invclose = Journals(portfolio, investment, lot_id, ls, location, "Cost", -closed_qty, -closed_local,
                -closed_book, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,"Asset/Liability")
        investment_accounting_space.post_journal_entry(invclose)
        journal_entries.append(invclose)

        if pgain_local != 0:
            pgclose = Journals( portfolio, investment, lot_id, ls, location, "PriceGainInvestment", 0, -pgain_local,
                                   -pgain_book, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                    ibor_date, "Revenue/Expense/Capital")
            investment_accounting_space.post_journal_entry(pgclose)
            journal_entries.append(pgclose)

        if glbook != 0:
            glclose = Journals(portfolio, investment, lot_id, ls, location, "FXGainInvestment", 0, 0, -glbook,
                                   tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
            investment_accounting_space.post_journal_entry(glclose)
            journal_entries.append(glclose)
       
    return


def short_equity(portfolio, investment, location, quantity, local, book, journal_entries, sub_ledger, tranid, transaction,
               tradedate, settledate, kdbegin, kdend, payment_currency):
    # Create a new je Open IBM
    from currency_domain import open_close_cash
    ls = "s"
    financial_account = "Cost"
    ibor_date = tradedate
    je = Journals(portfolio, investment, tranid, ls, location, financial_account, -quantity, -local, -book, tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    investment_accounting_space.post_journal_entry(je)
    journal_entries.append(je)

    ls = "l"
    financial_account = "Receivable"
    je = Journals(portfolio, payment_currency, tranid, ls, location, financial_account, local, local, book,
                      tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    investment_accounting_space.post_journal_entry(je)
    journal_entries.append(je)
   
    return
def cover_equity(portfolio, investment, location, quantity, local, book, closing_method, journal_entries, sub_ledger, tranid,
                transaction, tradedate, settledate, kdbegin, kdend, payment_currency):
    if tranid == 399:
        print("here")
    ls = "s"
    financial_account = "Payable"
    ibor_date = tradedate
    je = Journals(portfolio, payment_currency, tranid, ls, location, financial_account, -local, -local, -book,
                      tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    investment_accounting_space.post_journal_entry(je)
    journal_entries.append(je)

    # pass 'ls' flag into closelots - determine if l or is is being closed
    # Close the lots for the given investment and quantity using the specified closing method
    lots_returned = close_equity_lots(investment, location, -quantity, -local, -book, closing_method,
                                      journal_entries, sub_ledger.asset_liability_entries, ls)

    # Loop over the closed lots and post the corresponding journal entries
    for lotinfo in lots_returned:
        portfolio, investment, lot_id, closed_qty, closed_local, closed_book, closed_proceeds = lotinfo

        # Calculate the realized gain/loss on investment

        fxrate = book / local
        pgain_local = closed_proceeds - closed_local
        pgain_book = pgain_local * fxrate
        glbook = closed_proceeds * fxrate - closed_book - pgain_book
        realized_gl = (closed_proceeds - closed_local) * fxrate * -1

        if closed_book == 0:  # method passes back 0 for book as we need to convert it to trade fx equivalent
            closed_book = closed_local * fxrate

        # Post journal entries to update the bookkeeping space for investment
        invclose = Journals(portfolio, investment, lot_id, ls, location, "Cost", -closed_qty, -closed_local,
                        -closed_book, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        investment_accounting_space.post_journal_entry(invclose)
        journal_entries.append(invclose)

        if pgain_local != 0:
            pgclose = Journals(portfolio, investment, lot_id, ls, location, "PriceGainInvestment", 0, -pgain_local,
                         -pgain_book, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
            investment_accounting_space.post_journal_entry(pgclose)
            journal_entries.append(pgclose)

        if glbook != 0:
            glclose = Journals(portfolio, investment, lot_id, ls, location, "FXGainInvestment", 0, 0, -glbook,
                                   tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
            investment_accounting_space.post_journal_entry(glclose)
            journal_entries.append(glclose)
       
    return

def dividend_equity(portfolio, investment, location, quantity, local, book, closing_method, journal_entries, bs, tranid,
                transaction, tradedate, settledate, kdbegin, kdend, payment_currency, per_share):
    ibor_date = tradedate
    divloc = 0
    new_shares_ratio = per_share
    pos_type = "l"
    for lot_id, new_quantity, location in bs.lot_iterator_by_custodian(investment,'dividends', new_shares_ratio):
        # Find index of tuple in bs.bs
        for pos_type in ['l', 's']:  # Iterate over both long and short positions
            index = next((i for i, v in enumerate(bs.bs) if v[0] == (portfolio, investment, lot_id, pos_type, location, 'Cost')), -1)
            if index >= 0:
                _, (quantity, local, book) = bs.bs[index]
                bs.bs[index] = ((portfolio, investment, lot_id, pos_type, location, 'Cost'), (quantity + new_quantity, local, book))
        divloc += new_quantity * 1
        print("After calling post_journal_entry, ibor_date: ", ibor_date)
    if divloc>0:
        faal = "Dividends Receivable"
        faie = "Dividend Receipt"
    else:
        faal = "Dividends Payable"
        faie = "Dividend Expense"

    stkdiv = Journals(portfolio, investment, 0, pos_type, location, faal, 0,
                 divloc, divloc, tranid, transaction, tradedate, kdbegin, kdend, ibor_date, "Asset/Liability")

    stkinc = Journals(portfolio, investment, 0, pos_type, location, faie, 0,
                     -divloc, -divloc, tranid, transaction, tradedate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")

    journal_entries.append(stkdiv)
    journal_entries.append(stkinc)
    investment_accounting_space.post_journal_entry(stkdiv)
    investment_accounting_space.post_journal_entry(stkinc)

def split_equity(portfolio, investment, journal_entries, bs, tranid, transaction, tradedate, settledate, kdbegin,
                 kdend,
                 new_shares, old_shares):
    new_shares_ratio = new_shares / old_shares
    ibor_date = tradedate
    for pos_type in ['l', 's']:  # Iterate over both long and short positions
        # Find index of tuples in bs.asset_liability_entries
        matching_lots = [(i, v) for i, v in enumerate(bs.asset_liability_entries) if
                         v[0][:2] == (portfolio, investment) and v[0][3] == pos_type and v[0][5] == 'Cost']

        for index, (key, value) in matching_lots:
            quantity, local, book = value  # Unpack the value tuple correctly
            new_quantity = quantity * new_shares_ratio
            bs.asset_liability_entries[index] = (key, (quantity + new_quantity, local, book))

            # Perform the split operation here
            # Add the relevant Journals to journal_entries
            location = key[4]  #
            stkdiv = Journals(portfolio, investment, 0, pos_type, location, 'Cost', new_quantity,
                                  0, 0, tranid, transaction, tradedate, kdbegin, kdend, ibor_date,
                                  "Asset/Liability")
            journal_entries.append(stkdiv)
            investment_accounting_space.post_journal_entry(stkdiv)
