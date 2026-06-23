from typing import List, Tuple, Generator
import currency_domain
import main
import utilities
from utilities import get_fx_rate
from bookkeeping import Journals, Event, RevenueExpenseCapitalRepository, load_coa_from_csv
#import currency_domain
import datetime
revenue_expense_repository = RevenueExpenseCapitalRepository()
coa = load_coa_from_csv()
je = Journals()
import heapq
journal_entries = []
event = Event()
events = []  # This is a heap-based priority queue
import cProfile

def get_futures_lots(investment: str, location: str, quantity: float, local: float, book: float, closing_method: str,
                      tax_date: datetime, journal_entries, space, ls: str, tranid) -> List[
    Tuple[str, str, int, float, float, float, float]]:

    bs_entries = space.asset_liability_repository.get_position_entries(investment)

    # investment_lots = [(k[0], k[1], k[2], k[3], v[0], v[1], v[2]) for k, v in bs.bs.items() if k[1] == investment and (v[0] < 0 and ls =="s" or v[0]> 0 and ls=="l")]

    # added ls to tuple
    investment_lots = [(k[:4] + v) for k, v in list(bs_entries.items()) if
                       k[1] == investment and k[4] == location and (v[0] < 0 and ls == "s" or v[0] > 0 and ls == "l")]

    return investment_lots


from typing import List, Tuple
import datetime

def close_futures_lots(investment: str, location: str, quantity: float, local: float, book: float,
                       proceeds_notional: float, closing_method: str,
                      tax_date: datetime.datetime, journal_entries, space, ls: str, tranid) -> List[
    Tuple[str, str, int, datetime.datetime, str, str, str,  float, float, float, float]]:

    bs_entries = space.asset_liability_repository.get_position_entries(investment)

    # Extract investment lots including lotid and location
    investment_lots = [
        (k[0], k[1], k[2], k[3], k[4], k[5], k[6], v[0], v[1], v[2], v[3] )
        for k, v in bs_entries.items()
        if k[1] == investment and k[5] == location and ((v[0] < 0 and k[4] == "s") or (v[0] > 0 and k[4] == "l")) and k[6] == "Cost"
    ]



    if not investment_lots:
        raise ValueError(f"No investment lots found for the specified criteria. TranID-{tranid}-{investment}")

    if closing_method == 'LIFO':
        investment_lots.sort(key=lambda x: (x[3], x[2]), reverse=True)  # Sort by tax_date (x[3]) first, then lotid (x[2])
    elif closing_method == 'FIFO':
        investment_lots.sort(key=lambda x: (x[3], x[2]))  # Sort by tax_date (x[3]) first, then lotid (x[2])

    closed_lots = []


    # Flip the sign of remaining_quantity if ls == "s"
    if investment_lots[0][4] == "s":
        remaining_quantity = -quantity
        remaining_sell_proceeds = -proceeds_notional
    else:
        remaining_quantity = quantity
        remaining_sell_proceeds = proceeds_notional



    total_purchase_cost = 0
    total_shares = 0

    lots_left = len(investment_lots)

    for lot in investment_lots:
        portfolio, investment, lotid, tax_date, ls, location, fa, lot_quantity, lot_local, lot_book, lot_notional = lot

        if remaining_quantity == 0:
            break

        if ls == "l":
            closed_qty = min(lot_quantity, remaining_quantity)
        else:
            closed_qty = max(lot_quantity, remaining_quantity)

        if closed_qty == 0:
            continue

        closed_proceeds = 0

        if lot_quantity == closed_qty:
            # Close the entire lot
            closed_notional = lot_notional
            closed_proceeds = remaining_sell_proceeds * closed_qty / remaining_quantity if remaining_quantity != 0 else 0
            remaining_quantity -= closed_qty
            remaining_sell_proceeds -= closed_proceeds
        else:
            # Close a partial lot
            closed_notional = closed_qty / lot_quantity * lot_notional
            total_shares += closed_qty
            closed_proceeds = remaining_sell_proceeds * closed_qty / remaining_quantity if remaining_quantity != 0 else 0
            remaining_quantity -= closed_qty
            remaining_shares = lot_quantity - closed_qty
            remaining_book_cost = book * remaining_shares / lot_quantity
         #   remaining_sell_proceeds -= closed_proceeds
            book = 0  # no need

        # Append to the closed lots list with 'closed_notional'
        closed_lots.append(
            (portfolio, investment, lotid, tax_date, ls, closed_qty, closed_notional, local, book, closed_proceeds))
        lots_left -= 1

        # Create a new lot for the remaining quantity if it exceeds zero
        if remaining_quantity != 0 and lots_left == 0:
            raise ValueError(f"Not enough inventory to close or cover for transaction ID: {tranid}")
            new_lotid = max([0] + [k[2] for k in bs_entries.keys() if k[1] == investment]) + 1
            book = 0  # fill out in calling program
            bs_entries[(portfolio, investment, new_lotid, tax_date, ls, location, "Cost")] = (remaining_quantity, local, book)
            closed_lots.append((portfolio, investment, new_lotid, tax_date, remaining_quantity, remaining_sell_proceeds, 0, 0))

    return closed_lots

def futures_iterator(investment, space):
    # Get the entries from the investment subspace
    investment_space = space.get_position_space(investment)

    if investment_space:
        bs_entries = investment_space.entries  # Assuming 'entries' is a dictionary

        # Filter the entries based on the investment
        matching_lots = [entry for entry in bs_entries.items() if entry[0][1] == investment]

        # Extract relevant lot information (account key, lot quantity, local, and book values)
        # Assuming entry[1][0] is the lot quantity, entry[1][1] is local, and entry[1][2] is book
        return [(entry[0], entry[1][0], entry[1][1], entry[1][2], entry[1][3], entry[1][4]) for entry in matching_lots]
    else:
        return []



def lot_iterator_by_location(investment, space):
    # Filter the lots based on the given investment
    bs_entries = space.asset_liability_repository.get_position_entries(investment)

    filtered_lots = [lot for lot in bs_entries.items() if lot[0][1] == investment]

    # Group the lots by location (custodian) and accumulate quantities
    lots_by_location = {}
    for lot in filtered_lots:
        location = lot[0][5]
        if location not in lots_by_location:
            lots_by_location[location] = 0
        lots_by_location[location] += lot[1][0]

    # Return the accumulated quantities for each location
    result = [(location, quantity) for location, quantity in lots_by_location.items()]
    return result

def buy_future(portfolio, investment, location, quantity, local, book, space, tranid, transaction,
               tradedate, settledate, kdbegin, kdend, payment_currency, tdate_fx, notional):
    # Create a new je Open IBM

    ls = "l"
    financial_account = "Cost"
    ibor_date = tradedate
    tax_date = tradedate
    je = Journals(portfolio, investment, tranid, tax_date, ls, location, financial_account, quantity, local, book, notional, 0, tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    space.post_journal_entry(je)



    return


def sell_future(portfolio, investment, location, quantity, local, book, closing_method, journal_entries,
                space, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                tdate_fx, proceeds_notional, price, fx_data
                ):
    # investment_type = subspace.get_attribute_field("AIF", "investment_type") if subspace else None
    # pricing_factor = subspace.get_attribute_field("AIF", "pricing_factor") if subspace else 1.0
    # # Calculate notional if not provided
    # if notional is None:
    #     notional = quantity * price * 500

    # Set local to notional as these are the proceeds (minus commissions fees)
    # local = proceeds_notional - local
    # book = local + proceeds_notional / tdate_fx if tdate_fx !=0 else 1  # keep book pristine to calc fx on book

    lots_returned = close_futures_lots(investment, location, quantity, local, book, proceeds_notional, closing_method,
                                       tradedate, journal_entries, space, "l", tranid)

    currency_local = 0
    currency_book = 0
    investment_space = space.get_position_space(investment)
    currency = space.get_attribute_field(investment, 'AIF', 'Currency')

    for lotinfo in lots_returned:
        portfolio, investment, lotid, tax_date,  ls, closed_qty, closed_notional, closed_local, closed_book, closed_proceeds = lotinfo

        # Calculate the realized gain/loss on investment
        fx_rate = get_fx_rate(currency,tradedate ,fx_data)
        pgain_local = closed_proceeds - closed_notional
        pgain_book = pgain_local * fx_rate
        glbook = 0

        if closed_book == 0:  # method passes back 0 for book as we need to convert it to trade fx equivalent
            closed_book = closed_local * fx_rate
        closed_local = 0
        closed_book = 0
        # Post journal entries to update the bookkeeping space for investment Cost
        invclose = Journals(portfolio, investment, lotid,  tax_date, "l", location, "Cost", -closed_qty,
                            0, 0,-closed_notional, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
                            "Asset/Liability")
        space.post_journal_entry(invclose)



        currency_local += pgain_local
        currency_book += pgain_book

        if pgain_local != 0:
            pgclose = Journals(portfolio, investment, lotid, tax_date, "l", location, "PriceGainInvestment", 0,
                               -pgain_local, -pgain_book, closed_local, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
                               "Revenue/Expense/Capital")
            space.post_journal_entry(pgclose)

        if glbook != 0:
            glclose = Journals(portfolio, investment, lotid, tax_date, "l", location, "FXGainInvestment",  0, 0,
                               -glbook, closed_local, 0,  tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
                               "Revenue/Expense/Capital")
            space.post_journal_entry(glclose)

    if currency_local == 0:
        return

    financial_account = "Receivable" if currency_local > 0 else "Payable"
    ls = "l" if currency_local > 0 else "s"
    je = Journals(portfolio, payment_currency, tranid, tradedate, ls, location, financial_account,
                  currency_local, currency_local, currency_book, 0, 0, tranid,
                  transaction, tradedate, settledate, kdbegin, kdend, tradedate, "Asset/Liability")
    space.post_journal_entry(je)

def short_future(portfolio, investment, location, quantity, local, book, journal_entries, space, tranid,
                   transaction,  tradedate, settledate, kdbegin, kdend, payment_currency,
                  tdate_fx, notional, price):
        # Create a new je Open IBM
        if tranid == 8999:
            print("Here")
        ls = "s"
        financial_account = "Cost"
        ibor_date = tradedate
        tax_date = tradedate
        je = Journals(portfolio, investment, tranid, tax_date, ls, location, financial_account, -quantity, -local, -book,
                      -notional, 0, tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

        return

def cover_future(portfolio, investment, location, quantity, local, book, closing_method, journal_entries,
                space, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                tdate_fx, proceeds_notional, price, fx_data ):
    # investment_type = subspace.get_attribute_field("AIF", "investment_type") if subspace else None
    # pricing_factor = subspace.get_attribute_field("AIF", "pricing_factor") if subspace else 1.0
    # # Calculate notional if not provided
    # if notional is None:
    #     notional = quantity * price * 500

    # Set local to notional as these are the proceeds (minus commissions fees)
    # local = proceeds_notional - local
    # book = local + proceeds_notional / tdate_fx if tdate_fx !=0 else 1  # keep book pristine to calc fx on book

    lots_returned = close_futures_lots(investment, location, quantity, local, book, proceeds_notional,
                                       closing_method,
                                       tradedate, journal_entries, space, "s", tranid)

    currency_local = 0
    currency_book = 0
    investment_space = space.get_position_space(investment)
    currency = space.get_attribute_field(investment, 'AIF', 'Currency')


    for lotinfo in lots_returned:
        portfolio, investment, lotid, tax_date, ls, closed_qty, closed_notional, closed_local, closed_book, closed_proceeds = lotinfo

        # Calculate the realized gain/loss on investment
        fx_rate = get_fx_rate(currency, tradedate, fx_data)
        pgain_local = float(closed_proceeds) - closed_notional
        pgain_book = pgain_local * fx_rate
        glbook = 0

        if closed_book == 0:  # method passes back 0 for book as we need to convert it to trade fx equivalent
            closed_book = closed_local * fx_rate
        closed_local = 0
        closed_book = 0
        # Post journal entries to update the bookkeeping space for investment Cost
        invclose = Journals(portfolio, investment, lotid, tax_date, "s", location, "Cost", -closed_qty,
                            0, 0, -closed_notional, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                            tradedate,
                            "Asset/Liability")
        space.post_journal_entry(invclose)

        currency_local += pgain_local
        currency_book += pgain_book

        if pgain_local != 0:
            pgclose = Journals(portfolio, investment, lotid, tax_date, "s", location, "PriceGainInvestment", 0,
                               -pgain_local, -pgain_book, 0, 0, tranid, transaction, tradedate,
                               settledate, kdbegin, kdend, tradedate,
                               "Revenue/Expense/Capital")
            space.post_journal_entry(pgclose)

        if glbook != 0:
            glclose = Journals(portfolio, investment, lotid, tax_date, "s", location, "FXGainInvestment", 0, 0,
                               -glbook, closed_local, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                               tradedate,
                               "Revenue/Expense/Capital")
            space.post_journal_entry(glclose)

    if currency_local == 0:
        return

    financial_account = "Receivable" if currency_local > 0 else "Payable"
    ls = "l" if currency_local > 0 else "s"
    je = Journals(portfolio, payment_currency, tranid, tradedate, ls, location, financial_account,
                  currency_local, currency_local, currency_book, 0, 0, tranid,
                  transaction, tradedate, settledate, kdbegin, kdend, tradedate, "Asset/Liability")
    space.post_journal_entry(je)
