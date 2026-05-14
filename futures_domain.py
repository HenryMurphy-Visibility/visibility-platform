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

def buy_future(portfolio, investment, location, quantity, local, book, journal_entries, space, tranid, transaction,
               tradedate, settledate, kdbegin, kdend, payment_currency, tdate_fx, notional, price):
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


"""
| Transaction          | Call Option                                      | Put Option                                       |
|----------------------|--------------------------------------------------|--------------------------------------------------|
| Option Exercise Open | - Buy the underlying asset                       | - Sell short the underlying asset                |
|                      | - Apply premium received to adjust basis         | - Apply premium received to adjust basis         |
|----------------------|--------------------------------------------------|--------------------------------------------------|
| Option Exercise Close| - Sell the underlying asset                      | - Cover the underlying asset                     |
|                      | - Book premium received as income                | - Book premium received as income                |
|----------------------|--------------------------------------------------|--------------------------------------------------|
| Option Assign Open   | - Short the underlying asset                     | - Buy the underlying asset                      |
|                      | - Apply premium received to adjust basis         | - Apply premium received to adjust basis         |
|----------------------|--------------------------------------------------|--------------------------------------------------|
| Option Assign Close  | - Cover short the underlying asset               | - Sell the underlying asset                     |
|                      | - Book premium received as income                | - Book premium received as income                |
"""

# long put/call open short/long underlying
def exercise_option_open(portfolio, investment, location, quantity, local, book, closing_method, journal_entries,
                space, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                 put_call, strike, underlying, tdate_fx):

    ls= "l"

    # pass 'ls' flag into closelots - determine if l or is is being closed
    # Close the lots for the given investment and quantity using the specified closing method

# set underlying to empty else you will use underlying qty which is wrong and likely leads to oversold
    lots_returned =  remove_options_exer_assign(investment, location, quantity, local, book, closing_method, "", journal_entries,
                                      space, ls, tranid)

    premium_local = 0
    premium_book = 0
    # Loop over the closed lots and accumulate the premium paid
    for lotinfo in lots_returned:
        portfolio, investment, tax_date, ls, closed_qty, closed_local, closed_book= lotinfo[:7]

        # Accumulate premium paid
        premium_local += closed_local
        premium_book += closed_book

        invclose = Journals(portfolio, investment, tax_date, ls, location, "Cost", -closed_qty, -closed_local,
                            -closed_book, tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
                            "Asset/Liability")
        space.post_journal_entry(invclose)


    # calulate the strike price local and book

    formatted_date = "{}/{}/{}".format(tradedate.month, tradedate.day, tradedate.year)

    fx_rate = get_fx_rate(payment_currency, formatted_date, main.fx_data)

    # this is pure amt paid/received
    u_quantity = quantity * 100 # get this from AIF
    local_cost = u_quantity  * strike
    book_cost = local_cost * fx_rate
    ibor_date = tradedate

    #book the payment/receipt of currency for the exercise
    if put_call=="call": # Open Long
        je = Journals(portfolio, payment_currency, tranid, "s", location, "Payable", -local_cost, -local_cost, -book_cost,
                      tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

        je = Journals(portfolio, underlying, tradedate, "l", location, "Cost", u_quantity, local_cost+ premium_local, book_cost+ premium_book,
                      tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

    if put_call=="put": #Sell Short
        je = Journals(portfolio, investment, tranid, "l", location, "Receivable", local_cost, local_cost, book_cost,
                      tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

        je = Journals(portfolio, underlying, tradedate, "s", location, "Cost", -u_quantity, -local_cost + premium_local, -book_cost + premium_book,
                      tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)


    return
# long put/call cover long/cover short underlying
def exercise_option_close(portfolio, investment, location, quantity, local, book, closing_method, journal_entries,
                space, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                put_call, strike, underlying, tdate_fx):

    # pass 'ls' flag into closelots - determine if l or is is being closed
    # Close the lots for the given investment and quantity using the specified closing method

    lots_returned = remove_options_exer_assign(investment, location, quantity, local, book, closing_method, "", journal_entries,
                                      space, "l", tranid)


    premium_local = 0
    premium_book = 0
    # Loop over the closed lots and accumulate the premium paid
    for lotinfo in lots_returned:
        portfolio, investment, tax_date, ls, closed_qty, closed_local, closed_book= lotinfo[:7]

        # Accumulate premium paid
        premium_local += closed_local
        premium_book += closed_book

        invclose = Journals(portfolio, investment, tax_date, ls, location, "Cost", -closed_qty, -closed_local,
                            -closed_book, tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
                            "Asset/Liability")
        space.post_journal_entry(invclose)

    income = Journals(portfolio, investment, 0, "n", location, "OptionExpense", premium_local, premium_local,
                      premium_book, tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
                      "Revenue/Expense/Capital")
    space.post_journal_entry(income)
    # calulate the strike price local and book

    formatted_date = "{}/{}/{}".format(tradedate.month, tradedate.day, tradedate.year)

    fx_rate = get_fx_rate(payment_currency, formatted_date, main.fx_data)

    # this is pure amt paid/received
    quantity = quantity * 100 # get this from AIF
    local = quantity  * strike
    book = local * fx_rate
    ibor_date = tradedate

    #book the payment/receipt of currency for the exercise
    if put_call=="call": # Cover Short
        je = Journals(portfolio, payment_currency, tranid, "s", location, "Payable", -local, -local, -book,
                      tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

        lots_returned = close_equity_lots(underlying, location, -quantity, -local, -book, closing_method, "", journal_entries,
                                          space, "s", tranid)

        # Loop over the closed lots and post the corresponding journal entries
        for lotinfo in lots_returned:
            portfolio, underlying, tax_date, closed_qty, closed_local, closed_book, closed_proceeds = lotinfo
            # Calculate the realized gain/loss on investment

            fxrate = 1 # add fx rate lookup
            pgain_local = closed_proceeds - closed_local
            pgain_book = pgain_local * fxrate
            glbook = closed_proceeds * fxrate - closed_book - pgain_book
            realized_gl = (closed_proceeds - closed_local) * fxrate * -1

            if closed_book == 0:  # method passes back 0 for book as we need to convert it to trade fx equivalent
                closed_book = closed_local * fxrate

            ls = "s"
                # Post journal entries to update the bookkeeping space for underlying
            invclose = Journals(portfolio, underlying, tax_date, ls, location, "Cost", -closed_qty, -closed_local,
                                -closed_book, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                "Asset/Liability")
            space.post_journal_entry(invclose)

            if pgain_local != 0:
                pgclose = Journals(portfolio, underlying, tax_date, ls, location, "PriceGainInvestment", 0, -pgain_local,
                                   -pgain_book, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                   ibor_date, "Revenue/Expense/Capital")
                space.post_journal_entry(pgclose)

            if glbook != 0:
                glclose = Journals(portfolio, underlying, tax_date, ls, location, "FXGainInvestment", 0, 0, -glbook,
                                   tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                   "Revenue/Expense/Capital")
                space.post_journal_entry(glclose)

    if put_call=="put": # Sell Long
        je = Journals(portfolio, payment_currency, tranid, "l", location, "Receivable", local, local, book,
                      tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

        lots_returned = close_equity_lots(underlying, location, quantity, local, book, closing_method, "",
                                          journal_entries,
                                          space, "l", tranid)

        # Loop over the closed lots and post the corresponding journal entries
        for lotinfo in lots_returned:
            portfolio, underlying, tax_date, closed_qty, closed_local, closed_book, closed_proceeds = lotinfo
            # Calculate the realized gain/loss on investment

            fxrate = 1 # add fx
            pgain_local = closed_proceeds - closed_local
            pgain_book = pgain_local * fxrate
            glbook = closed_proceeds * fxrate - closed_book - pgain_book
            realized_gl = (closed_proceeds - closed_local) * fxrate * -1

            if closed_book == 0:  # method passes back 0 for book as we need to convert it to trade fx equivalent
                closed_book = closed_local * fxrate

                # Post journal entries to update the bookkeeping space for underlying
            invclose = Journals(portfolio, underlying, tax_date, "l", location, "Cost", -closed_qty, -closed_local,
                                -closed_book, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                "Asset/Liability")
            space.post_journal_entry(invclose)

            if pgain_local != 0:
                pgclose = Journals(portfolio, underlying, tax_date, "l", location, "PriceGainInvestment", 0, -pgain_local,
                                   -pgain_book, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                   ibor_date, "Revenue/Expense/Capital")
                space.post_journal_entry(pgclose)

            if glbook != 0:
                glclose = Journals(portfolio, underlying, tax_date, "l", location, "FXGainInvestment", 0, 0, -glbook,
                                   tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                   "Revenue/Expense/Capital")
                space.post_journal_entry(glclose)

    return
def assign_option_open(portfolio, investment, location, quantity, local, book, closing_method, journal_entries,
                         space, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                         payment_currency,
                         put_call, strike, underlying, tdate_fx):
    ls = "s"

    # pass 'ls' flag into closelots - determine if l or is is being closed
    # Close the lots for the given investment and quantity using the specified closing method

    # set underlying to empty else you will use underlying qty which is wrong and likely leads to oversold
    lots_returned = remove_options_exer_assign(investment, location, quantity, local, book, closing_method, "",
                                               journal_entries,
                                               space, ls, tranid)

    premium_local = 0
    premium_book = 0
    # Loop over the closed lots and accumulate the premium paid
    for lotinfo in lots_returned:
        portfolio, investment, tax_date, ls, closed_qty, closed_local, closed_book = lotinfo[:7]

        # Accumulate premium paid
        premium_local += closed_local
        premium_book += closed_book

        invclose = Journals(portfolio, investment, tax_date, "s", location, "Cost", -closed_qty, -closed_local,
                            -closed_book, tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
                            "Asset/Liability")
        space.post_journal_entry(invclose)

    # calulate the strike price local and book

    formatted_date = "{}/{}/{}".format(tradedate.month, tradedate.day, tradedate.year)

    fx_rate = get_fx_rate(payment_currency, formatted_date, main.fx_data)

    # this is pure amt paid/received
    u_quantity = quantity * 100  # get this from AIF
    local_cost = u_quantity * strike
    book_cost = local_cost * fx_rate
    ibor_date = tradedate

    # book the payment/receipt of currency for the exercise
    if put_call == "call": # Sell Short
        je = Journals(portfolio, payment_currency, tranid, "s", location, "Receivable", local_cost, local_cost,
                      book_cost,
                      tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

        je = Journals(portfolio, underlying, tradedate, "l", location, "Cost", -u_quantity, -local_cost + premium_local,
                      -book_cost + premium_book,
                      tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

    if put_call == "put": #Buy Long
        je = Journals(portfolio, investment, tranid, "l", location, "Payable", -local_cost, -local_cost, -book_cost,
                      tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

        je = Journals(portfolio, underlying, tradedate, "s", location, "Cost", u_quantity, local_cost + premium_local,
                      book_cost + premium_book,
                      tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

    return


# long put/call cover long/cover short underlying
def assign_option_close(portfolio, investment, location, quantity, local, book, closing_method, journal_entries,
                          space, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                          payment_currency,
                          put_call, strike, underlying, tdate_fx):
    # pass 'ls' flag into closelots - determine if l or is is being closed
    # Close the lots for the given investment and quantity using the specified closing method

    lots_returned = remove_options_exer_assign(investment, location, -quantity, -local, -book, closing_method, "",
                                               journal_entries,
                                               space, "s", tranid)

    premium_local = 0
    premium_book = 0
    # Loop over the closed lots and accumulate the premium paid
    for lotinfo in lots_returned:
        portfolio, investment, tax_date, ls, closed_qty, closed_local, closed_book = lotinfo[:7]

        # Accumulate premium paid
        premium_local += closed_local
        premium_book += closed_book

        invclose = Journals(portfolio, investment, tax_date, ls, location, "Cost", -closed_qty, -closed_local,
                            -closed_book, tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
                            "Asset/Liability")
        space.post_journal_entry(invclose)

    income = Journals(portfolio, investment, 0, "n", location, "OptionExpense", premium_local, premium_local,
                      premium_book, tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
                      "Revenue/Expense/Capital")
    space.post_journal_entry(income)
    # calulate the strike price local and book

    formatted_date = "{}/{}/{}".format(tradedate.month, tradedate.day, tradedate.year)

    fx_rate = get_fx_rate(payment_currency, formatted_date, main.fx_data)

    # this is pure amt paid/received
    quantity = quantity * 100  # get this from AIF
    local = quantity * strike
    book = local * fx_rate
    ibor_date = tradedate

    # book the payment/receipt of currency for the assignment
    if put_call == "call": #Sell Long
        je = Journals(portfolio, payment_currency, tranid, "l", location, "Receivable", local, local, book,
                      tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

        lots_returned = close_equity_lots(underlying, location, quantity, local, book, closing_method, "",
                                          journal_entries,
                                          space, "l", tranid)

        # Loop over the closed lots and post the corresponding journal entries
        for lotinfo in lots_returned:
            portfolio, underlying, tax_date, closed_qty, closed_local, closed_book, closed_proceeds = lotinfo
            # Calculate the realized gain/loss on investment

            fxrate = 1  # add fx rate lookup
            pgain_local = closed_proceeds - closed_local
            pgain_book = pgain_local * fxrate
            glbook = closed_proceeds * fxrate - closed_book - pgain_book
            realized_gl = (closed_proceeds - closed_local) * fxrate * -1

            if closed_book == 0:  # method passes back 0 for book as we need to convert it to trade fx equivalent
                closed_book = closed_local * fxrate

            ls = "l"
            # Post journal entries to update the bookkeeping space for underlying
            invclose = Journals(portfolio, underlying, tax_date, "l", location, "Cost", -closed_qty, -closed_local,
                                -closed_book, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                "Asset/Liability")
            space.post_journal_entry(invclose)

            if pgain_local != 0:
                pgclose = Journals(portfolio, underlying, tax_date, ls, location, "PriceGainInvestment", 0,
                                   -pgain_local,
                                   -pgain_book, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                   ibor_date, "Revenue/Expense/Capital")
                space.post_journal_entry(pgclose)

            if glbook != 0:
                glclose = Journals(portfolio, underlying, tax_date, ls, location, "FXGainInvestment", 0, 0, -glbook,
                                   tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                   "Revenue/Expense/Capital")
                space.post_journal_entry(glclose)

    if put_call == "put": #Cover Short
        je = Journals(portfolio, payment_currency, tranid, "s", location, "Payable", -local, -local, -book,
                      tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

        lots_returned = close_equity_lots(underlying, location, -quantity, -local, -book, closing_method, "",
                                          journal_entries,
                                          space, "s", tranid)

        # Loop over the closed lots and post the corresponding journal entries
        for lotinfo in lots_returned:
            portfolio, underlying, tax_date, closed_qty, closed_local, closed_book, closed_proceeds = lotinfo
            # Calculate the realized gain/loss on investment

            fxrate = 1  # add fx
            pgain_local = closed_proceeds - closed_local
            pgain_book = pgain_local * fxrate
            glbook = closed_proceeds * fxrate - closed_book - pgain_book
            realized_gl = (closed_proceeds - closed_local) * fxrate * -1

            if closed_book == 0:  # method passes back 0 for book as we need to convert it to trade fx equivalent
                closed_book = closed_local * fxrate

                # Post journal entries to update the bookkeeping space for underlying
            invclose = Journals(portfolio, underlying, tax_date, "s", location, "Cost", -closed_qty, -closed_local,
                                -closed_book, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                "Asset/Liability")
            space.post_journal_entry(invclose)

            if pgain_local != 0:
                pgclose = Journals(portfolio, underlying, tax_date, "s", location, "PriceGainInvestment", 0,
                                   -pgain_local,
                                   -pgain_book, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                   ibor_date, "Revenue/Expense/Capital")
                space.post_journal_entry(pgclose)

            if glbook != 0:
                glclose = Journals(portfolio, underlying, tax_date, "s", location, "FXGainInvestment", 0, 0, -glbook,
                                   tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                   "Revenue/Expense/Capital")
                space.post_journal_entry(glclose)

    return

