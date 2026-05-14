from typing import List, Tuple, Generator

import main
import global_domain
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

from typing import List, Tuple
import datetime

from typing import List, Tuple
import datetime
from typing import List, Tuple
import datetime
#from kivygui import ld

from typing import List, Tuple
import datetime

def close_equity_lots(investment: str, location: str, quantity: float, local: float, book: float, closing_method: str,
                      tax_date: datetime.datetime, journal_entries, sub_ledger, ls: str, tranid) -> List[
    Tuple[str, str, int, float, float, float, float]]:

    bs_entries = sub_ledger.asset_liability_repository.get_position_entries(investment)

    # Extract investment lots including lotid and location
    investment_lots = [
        (k[0], k[1], k[2], k[3], k[4], k[5], v[0], v[1], v[2])
        for k, v in bs_entries.items()
        if k[1] == investment and k[5] == location and ((v[0] < 0 and k[4] == "s") or (v[0] > 0 and k[4] == "l")) and k[6] == "Cost"
    ]

    if not investment_lots:
        raise ValueError(f"No investment lots found for the specified criteria. TranID-{tranid}-{investment}")

    if closing_method == 'LIFO':
        investment_lots.sort(key=lambda x: x[3], reverse=True)  # Sort by tax_date (x[3]) first, then lotid (x[2])
    elif closing_method == 'FIFO':
        investment_lots.sort(key=lambda x: x[3]) # Sort by tax_date (x[3]) first, then lotid (x[2])

    closed_lots = []

    remaining_quantity = quantity
    remaining_sell_proceeds = local
    remaining_sell_proceeds_book = remaining_sell_proceeds / (local / book) if local != 0 else 0
    total_purchase_cost = 0
    total_shares = 0

    lots_left = len(investment_lots)

    for lot in investment_lots:
        portfolio, investment, lotid, tax_date, ls, location, lot_quantity, local, book = lot

        if remaining_quantity == 0:
            break

        closed_qty = min(lot_quantity, remaining_quantity)

        if closed_qty == 0:
            continue

        closed_proceeds = 0

        if lot_quantity == closed_qty:
            # Close the entire lot
            closed_proceeds = remaining_sell_proceeds * closed_qty / remaining_quantity if remaining_quantity != 0 else 0
            remaining_quantity -= closed_qty
            remaining_sell_proceeds -= closed_proceeds
        else:
            # Close a partial lot
            total_purchase_cost += closed_qty * local / lot_quantity
            total_shares += closed_qty
            closed_proceeds = remaining_sell_proceeds * closed_qty / remaining_quantity if remaining_quantity != 0 else 0
            remaining_quantity -= closed_qty
            remaining_shares = lot_quantity - closed_qty
            remaining_book_cost = book * remaining_shares / lot_quantity
            remaining_sell_proceeds -= closed_proceeds
            local = total_purchase_cost
            book = book - remaining_book_cost

        closed_lots.append((portfolio, investment, lotid, tax_date, closed_qty, local, book, closed_proceeds))
        lots_left -= 1

        # Create a new lot for the remaining quantity if it exceeds zero
        if remaining_quantity != 0 and lots_left == 0:
            raise ValueError(f"Not enough inventory to close or cover for transaction ID: {tranid}")
            new_lotid = max([0] + [k[2] for k in bs_entries.keys() if k[1] == investment]) + 1
            book = 0  # fill out in calling program
            bs_entries[(portfolio, investment, new_lotid, tax_date, ls, location, "Cost")] = (remaining_quantity, local, book)
            closed_lots.append((portfolio, investment, new_lotid, tax_date, remaining_quantity, remaining_sell_proceeds, 0, 0))

    return closed_lots


from datetime import datetime

def remove_options_exer_assign(investment: str, location: str, quantity: float, local: float, book: float,
                               closing_method: str,
                               tax_date: datetime, journal_entries, sub_ledger, ls: str, tranid) -> List[
    Tuple[str, str, str, int, float, float, float, float]]:
    # Retrieve entries from the repository
    bs_entries = sub_ledger.asset_liability_repository.get_position_entries(investment)

    # Define indices for readability
    portfoliox = 0
    investmentx = 1
    tax_datex = 2
    lsx = 3
    locationx = 4
    financial_accountx = 5
    qtyx = 6
    localx = 7
    bookx = 8
    notionalx = 9
    original_facex = 10

    # List to store matching investment lots
    investment_lots = []

    # Iterate through each key-value pair in bs_entries
    for k, v in bs_entries.items():
        # Check if investment and location match
        if k[investmentx] == investment and k[locationx] == location and k[financial_accountx] == "Cost":
            # Check if long/short condition matches
            if (v[0] < 0 and ls == "s") or (v[0] > 0 and ls == "l"):
                # Create new tuple and append to investment_lots
                new_tuple = k[:portfoliox + 4] + (lsx,) + k[locationx:] + v
                investment_lots.append(new_tuple)

    # Sort investment lots based on closing method
    if closing_method == 'LIFO':
        investment_lots.sort(key=lambda x: x[tax_datex])
    elif closing_method == 'FIFO':
        investment_lots.sort(key=lambda x: x[tax_datex], reverse=True)

    # List to store closed lots
    closed_lots = []

    # Iterate through investment lots to calculate closed lots
    for lot in investment_lots:
        # Check if quantity is equal to the lot quantity
        if v[0] == quantity:
            closed_qty = v[0]
            local_cost = v[1]
            book_cost = v[2]
        else:
            # Calculate closed quantity based on the proportion of the lot quantity to the given quantity
            lot_quantity = float(v[0])
            if lot_quantity < 0:
                closed_qty = max(lot_quantity, float(quantity))
            else:
                closed_qty = min(lot_quantity, float(quantity))
            local_cost = (closed_qty / lot_quantity) * v[1]
            book_cost = (closed_qty / lot_quantity) * v[2]

        # Append closed lot to closed_lots
        closed_lots.append((lot[portfoliox], lot[investmentx], lot[tax_datex], lot[lsx],
                            closed_qty, local_cost, book_cost, local_cost))

        # Update remaining quantity
        quantity -= closed_qty

        # Exit loop if all quantity is closed
        if quantity == 0:
            break

    return closed_lots


def lot_iterator(investment, sub_ledger):
    # Get the entries from the investment subspace
    investment_space = sub_ledger.get_position_space(investment)

    if investment_space:
        bs_entries = investment_space.entries  # Assuming 'entries' is a dictionary

        # Filter the entries based on the investment
        matching_lots = [entry for entry in bs_entries.items() if entry[0][1] == investment]

        # Extract relevant lot information (account key, lot quantity, local, and book values)
        # Assuming entry[1][0] is the lot quantity, entry[1][1] is local, and entry[1][2] is book
        return [(entry[0], entry[1][0], entry[1][1], entry[1][2]) for entry in matching_lots]
    else:
        return []

def lot_iterator_by_location(investment, sub_ledger):
    # Filter the lots based on the given investment
    bs_entries = sub_ledger.asset_liability_repository.get_position_entries(investment)

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



def buy_equity(portfolio, investment, location, quantity, local, book, journal_entries, sub_ledger, tranid, transaction,
               tradedate, settledate, kdbegin, kdend, payment_currency, tdate_fx):
    # Create a new je Open IBM
    if tranid == 8999:
        print("Here")
    ls = "l"
    financial_account = "Cost"
    ibor_date = tradedate
    tax_date = tradedate
    je = Journals(portfolio, investment, tranid, tax_date, ls, location, financial_account, quantity, local, book, None, None, tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    sub_ledger.post_journal_entry(je)


    ls = "s"
    financial_account = "Payable" # use tranid for payable receivable to close
    je = Journals( portfolio, payment_currency, tranid, tax_date, ls, location, financial_account, -local, -local, -book, None, None, tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    sub_ledger.post_journal_entry(je)

    return


def sell_equity(portfolio, investment, location, quantity, local, book, closing_method, journal_entries,
                sub_ledger, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                tdate_fx):
    ls = "l"
    financial_account = "Receivable"
    ibor_date = tradedate
    tax_date = tradedate


    if tranid == 99:
        print("Here")
    # Post receivable entry
    je = Journals(
        portfolio, payment_currency, tranid, tax_date, ls, location, financial_account,
        local, local, book, None, None,
        tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability"
    )
    sub_ledger.post_journal_entry(je)

    # Close the lots for the given investment and quantity using the specified closing method
    lots_returned = close_equity_lots(investment, location, quantity, local, book, closing_method, tax_date,
                                      journal_entries, sub_ledger, ls, tranid)

    # Initialize aggregate variables for gains/losses
    total_pgain_local = 0
    total_pgain_book = 0
    total_fxgain_book = 0

    # Loop over the closed lots and post the corresponding journal entries
    for lotinfo in lots_returned:
        portfolio, investment, lotid, tax_date, closed_qty, closed_local, closed_book, closed_proceeds = lotinfo

        # Calculate the realized gain/loss on investment
        fxrate = book / local
        pgain_local = closed_proceeds - closed_local
        pgain_book = pgain_local * fxrate
        fxgain_book = closed_proceeds * fxrate - closed_book - pgain_book

        # Aggregate gains/losses for bulk posting later
        total_pgain_local += pgain_local
        total_pgain_book += pgain_book
        total_fxgain_book += fxgain_book

        # Post the individual lot entries
        invclose = Journals(
            portfolio, investment, lotid, tax_date, ls, location, "Cost",
            -closed_qty, -closed_local, -closed_book, None, None,
            tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability"
        )
        sub_ledger.post_journal_entry(invclose)

        if pgain_local != 0:
            pgclose = Journals(
                portfolio, investment, lotid, tax_date, ls, location, "PriceGainInvestment", 0, -pgain_local,
                -pgain_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                ibor_date, "Revenue/Expense/Capital"
            )
            sub_ledger.post_journal_entry(pgclose)



        if fxgain_book != 0:
            fxclose = Journals(
                portfolio, investment, lotid, tax_date, ls, location, "FXGainInvestment", 0, 0, -fxgain_book, None,
                None,
                tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital"
            )
            sub_ledger.post_journal_entry(fxclose)


    #
    # # After processing all lots, post the aggregated gains to UnrealPriceGL, UnrealFXGL, and offset to UnearnedIncome
    # post_aggregated_gains(portfolio, investment, location, ls, tranid, transaction, tradedate, settledate, kdbegin,
    #                       kdend,
    #                       total_pgain_local, total_pgain_book, total_fxgain_book, sub_ledger)


def post_aggregated_gains(portfolio, investment, location, ls, tranid, transaction, tradedate, settledate, kdbegin,
                          kdend,
                          total_pgain_local, total_pgain_book, total_fxgain_book, sub_ledger):
    # Determine the offset amounts to Unearned Income
    unearned_income_local = total_pgain_local
    unearned_income_book = total_pgain_book - total_fxgain_book

    # Post UnrealPriceGL (local and book)
    unreal_price_gl = Journals(
        portfolio, investment, 0, 0, ls, location, 'UnrealPriceGL',
        None, total_pgain_local, total_pgain_book, None, None,
        0, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
        "Revenue/Expense/Capital"
    )
    sub_ledger.post_journal_entry(unreal_price_gl)

    # Post UnrealFXGL (book)
    unreal_fx_gl = Journals(
        portfolio, investment, 0, 0, ls, location, 'UnrealFXGL',
        None, 0, total_fxgain_book, None, None,
        0, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
        "Revenue/Expense/Capital"
    )
    sub_ledger.post_journal_entry(unreal_fx_gl)
    #
    # # Post offset to Unearned Income (local and book)
    # unearned_income = Journals(
    #     portfolio, investment, 0, 0, ls, location, 'UnearnedIncome',
    #     None, unearned_income_local, unearned_income_book, None, None,
    #     0, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
    #     "Revenue/Expense/Capital"
    # )
    # sub_ledger.post_journal_entry(unearned_income)
    #

def short_equity(portfolio, investment, location, quantity, local, book, journal_entries, sub_ledger, tranid, transaction,
               tradedate, settledate, kdbegin, kdend, payment_currency,  tdate_fx):
    # Create a new je Open IBM
    from currency_domain import open_close_cash
    ls = "s"
    financial_account = "Cost"
    ibor_date = tradedate
    tax_date = tradedate
    je = Journals(portfolio, investment, tranid, tax_date, ls,  location, financial_account, -quantity, -local, -book, None, None, tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    sub_ledger.post_journal_entry(je)
    

    ls = "l"
    financial_account = "Receivable"
    je = Journals(portfolio, payment_currency, tranid, tax_date,"l", location, financial_account, local, local, book, None, None,
                      tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    sub_ledger.post_journal_entry(je)
    
   
    return
def cover_equity(portfolio, investment, location, quantity, local, book, closing_method, journal_entries, sub_ledger, tranid,
                transaction, tradedate, settledate, kdbegin, kdend, payment_currency, tdate_fx):
    ls = "s"
    financial_account = "Payable"
    ibor_date = tradedate
    tax_date = tradedate
    je = Journals(portfolio, payment_currency, tranid, tax_date, ls, location, financial_account, -local, -local, -book, None, None,
                      tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    sub_ledger.post_journal_entry(je)
    

    # pass 'ls' flag into closelots - determine if l or is is being closed
    # Close the lots for the given investment and quantity using the specified closing method
    lots_returned = close_equity_lots(investment, location, -quantity, -local, -book, closing_method, tax_date,
                                      journal_entries, sub_ledger, 's', tranid)

    # Loop over the closed lots and post the corresponding journal entries
    for lotinfo in lots_returned:
        portfolio, investment, lotid, tax_date, closed_qty, closed_local, closed_book, closed_proceeds = lotinfo

        # Calculate the realized gain/loss on investment

        fxrate = book / local
        pgain_local = closed_proceeds - closed_local
        pgain_book = pgain_local * fxrate
        glbook = closed_proceeds * fxrate - closed_book - pgain_book
        realized_gl = (closed_proceeds - closed_local) * fxrate * -1

        if closed_book == 0:  # method passes back 0 for book as we need to convert it to trade fx equivalent
            closed_book = closed_local * fxrate

        # Post journal entries to update the bookkeeping space for investment
        invclose = Journals(portfolio, investment,lotid, tax_date, ls, location, "Cost", -closed_qty, -closed_local,
                        -closed_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(invclose)

        if pgain_local != 0:
            pgclose = Journals(portfolio, investment, lotid, tax_date, ls, location, "PriceGainInvestment", 0, -pgain_local,
                         -pgain_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
            sub_ledger.post_journal_entry(pgclose)



        if glbook != 0:
            glclose = Journals(portfolio, investment, lotid, tax_date, ls, location, "FXGainInvestment", 0, 0, -glbook, None, None,
                                   tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
            sub_ledger.post_journal_entry(glclose)

    return

def dividend_equity(portfolio, investment, journal_entries, sub_ledger, tranid,
                transaction, tradedate, settledate, kdbegin, kdend, payment_currency, per_share, period_start):
    ibor_date = tradedate

    # Call lot_iterator_by_location - it should return lots by location, total quantity, and lots
    #For loc, total_quantity, lots in lot_iterator_by_location(investment, bs.asset_liability_entries):
    for location, total_quantity in lot_iterator_by_location(investment, sub_ledger):

        divloc = total_quantity * per_share
     #   div_book = divloc * get_fx_rate()

        # Check dividend sign and set financial accounts accordingly
        if divloc > 0:
            faal = "DividendsReceivable"
            faie = "DividendReceipt"
            ls= "l"
        else:
            faal = "DividendsPayable"
            faie = "DividendExpense"
            ls = "s"
        # Post aggregate div for location/ls hitting financial accounts (faal faie) based on prior
        stkdiv = Journals(portfolio, payment_currency, tranid, tradedate, ls, location, faal, 0, divloc, divloc,None, None, tranid, transaction, tradedate,
                              settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(stkdiv)

        stkinc = Journals(portfolio, investment, tranid, tradedate, ls, location, faie, 0, -divloc, -divloc, None, None, tranid, transaction, tradedate,
                              settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
        sub_ledger.post_journal_entry(stkinc)

    return

def split_equity(portfolio, investment, journal_entries, sub_ledger, tranid, transaction, tradedate, settledate,
                 kdbegin, kdend, new_shares, old_shares):

    financial_account = "Cost"
    ibor_date = tradedate
    tax_date = tradedate
    # Fetch all lots for the given investment using the lot_iterator
    lots_returned = lot_iterator(investment, sub_ledger)

    # Loop over the lots and post the corresponding journal entries
    for lot_info in lots_returned:
        account_key, lot_qty = lot_info
        # Calculate the new lot quantity after the split
        split_qty = lot_qty * new_shares / old_shares - lot_qty

        # Create a new entry for the split result
        split_entry = Journals(portfolio, investment, account_key[2], account_key[3], account_key[4], account_key[5],
                                   financial_account, split_qty, 0, 0,None, None, tranid, transaction, tradedate, settledate,
                                   kdbegin, kdend, ibor_date, "Asset/Liability")

        # Post the split entry
        sub_ledger.post_journal_entry(split_entry)
    return
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
                sub_ledger, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                 put_call, strike, underlying, tdate_fx):

    ls= "l"

    # pass 'ls' flag into closelots - determine if l or is is being closed
    # Close the lots for the given investment and quantity using the specified closing method

# set underlying to empty else you will use underlying qty which is wrong and likely leads to oversold
    lots_returned =  remove_options_exer_assign(investment, location, quantity, local, book, closing_method, "", journal_entries,
                                      sub_ledger, ls, tranid)

    premium_local = 0
    premium_book = 0
    # Loop over the closed lots and accumulate the premium paid
    for lotinfo in lots_returned:
        portfolio, investment, lotid,  tax_date, ls, closed_qty, closed_local, closed_book= lotinfo[:7]

        # Accumulate premium paid
        premium_local += closed_local
        premium_book += closed_book

        invclose = Journals(portfolio, investment, lotid, tax_date, ls, location, "Cost", -closed_qty, -closed_local,
                            -closed_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
                            "Asset/Liability")
        sub_ledger.post_journal_entry(invclose)


    # calulate the strike price local and book

    formatted_date = "{}/{}/{}".format(tradedate.month, tradedate.day, tradedate.year)

    fx_rate = get_fx_rate(payment_currency, formatted_date, fx_data)

    # this is pure amt paid/received
    u_quantity = quantity * 100 # get this from AIF
    local_cost = u_quantity  * strike
    book_cost = local_cost * fx_rate
    ibor_date = tradedate

    #book the payment/receipt of currency for the exercise
    if put_call=="call": # Open Long
        je = Journals(portfolio, payment_currency, tranid, tradedate, "s", location, "Payable",
                      -local_cost, -local_cost, -book_cost,
                      None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                      "Asset/Liability")
        sub_ledger.post_journal_entry(je)

        je = Journals(portfolio, underlying, tranid, tradedate, "l", location, "Cost", u_quantity, local_cost+ premium_local,
                      book_cost+ premium_book, None, None, tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(je)

    if put_call=="put": #Sell Short
        je = Journals(portfolio, payment_currency, tranid, tradedate,"l", location, "Receivable",
                      local_cost, local_cost, book_cost, None, None, tranid, transaction,
                      tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(je)

        je = Journals(portfolio, underlying, tranid, tradedate,"s", location, "Cost", -u_quantity,
                      -local_cost + premium_local, -book_cost + premium_book, None, None,
                      tranid,  transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(je)


    return
# long put/call cover long/cover short underlying
def exercise_option_close(portfolio, investment, location, quantity, local, book, closing_method, journal_entries,
                sub_ledger, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                put_call, strike, underlying, tdate_fx):

    # pass 'ls' flag into closelots - determine if l or is is being closed
    # Close the lots for the given investment and quantity using the specified closing method

    lots_returned = remove_options_exer_assign(investment, location, quantity, local, book, closing_method, "", journal_entries,
                                      sub_ledger, "l", tranid)


    premium_local = 0
    premium_book = 0
    # Loop over the closed lots and accumulate the premium paid
    for lotinfo in lots_returned:
        portfolio, investment, lotid, tax_date, ls, closed_qty, closed_local, closed_book= lotinfo[:7]

        # Accumulate premium paid
        premium_local += closed_local
        premium_book += closed_book

        invclose = Journals(portfolio, investment, lotid, tax_date, ls, location, "Cost", -closed_qty, -closed_local,
                            -closed_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
                            "Asset/Liability")
        sub_ledger.post_journal_entry(invclose)

    income = Journals(portfolio, investment, ld,ld, "n", location, "OptionExpense", premium_local, premium_local,
                      premium_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
                      "Revenue/Expense/Capital")
    sub_ledger.post_journal_entry(income)
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
        je = Journals(portfolio, payment_currency, tranid, tradedate, "s", location,
                      "Payable", -local, -local, -book, None, None,
                      tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(je)

        lots_returned = close_equity_lots(underlying, location, -quantity, -local, -book, closing_method, "", journal_entries,
                                          sub_ledger, "s", tranid)

        # Loop over the closed lots and post the corresponding journal entries
        for lotinfo in lots_returned:
            portfolio, underlying, lotid, tax_date, closed_qty, closed_local, closed_book, closed_proceeds = lotinfo
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
            invclose = Journals(portfolio, underlying, lotid, tax_date, ls, location, "Cost", -closed_qty, -closed_local,
                                -closed_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                "Asset/Liability")
            sub_ledger.post_journal_entry(invclose)

            if pgain_local != 0:
                pgclose = Journals(portfolio, underlying, lotid, tax_date, ls, location, "PriceGainInvestment", 0, -pgain_local,
                                   -pgain_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                   ibor_date, "Revenue/Expense/Capital")
                sub_ledger.post_journal_entry(pgclose)

            if glbook != 0:
                glclose = Journals(portfolio, underlying, lotid, tax_date, ls, location, "FXGainInvestment", 0, 0, -glbook, None, None,
                                   tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                   "Revenue/Expense/Capital")
                sub_ledger.post_journal_entry(glclose)

    if put_call=="put": # Sell Long
        je = Journals(portfolio, payment_currency, tranid, tradedate,"l", location, "Receivable", local, local, book, None, None,
                      tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(je)

        lots_returned = close_equity_lots(underlying, location, quantity, local, book, closing_method, "",
                                          journal_entries,
                                          sub_ledger, "l", tranid)

        # Loop over the closed lots and post the corresponding journal entries
        for lotinfo in lots_returned:
            portfolio, underlying, lotid, tax_date, closed_qty, closed_local, closed_book, closed_proceeds = lotinfo
            # Calculate the realized gain/loss on investment

            fxrate = 1 # add fx
            pgain_local = closed_proceeds - closed_local
            pgain_book = pgain_local * fxrate
            glbook = closed_proceeds * fxrate - closed_book - pgain_book
            realized_gl = (closed_proceeds - closed_local) * fxrate * -1

            if closed_book == 0:  # method passes back 0 for book as we need to convert it to trade fx equivalent
                closed_book = closed_local * fxrate

                # Post journal entries to update the bookkeeping space for underlying
            invclose = Journals(portfolio, underlying, lotid, tax_date, "l", location, "Cost", -closed_qty, -closed_local,
                                -closed_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                "Asset/Liability")
            sub_ledger.post_journal_entry(invclose)

            if pgain_local != 0:
                pgclose = Journals(portfolio, underlying, lotid, tax_date, "l", location, "PriceGainInvestment", 0, -pgain_local,
                                   -pgain_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                   ibor_date, "Revenue/Expense/Capital")
                sub_ledger.post_journal_entry(pgclose)

            if glbook != 0:
                glclose = Journals(portfolio, underlying, lotid, tax_date, "l", location, "FXGainInvestment", 0, 0, -glbook, None, None,
                                   tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                   "Revenue/Expense/Capital")
                sub_ledger.post_journal_entry(glclose)

    return
def assign_option_open(portfolio, investment, location, quantity, local, book, closing_method, journal_entries,
                         sub_ledger, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                         payment_currency,
                         put_call, strike, underlying, tdate_fx):
    ls = "s"

    # pass 'ls' flag into closelots - determine if l or is is being closed
    # Close the lots for the given investment and quantity using the specified closing method

    # set underlying to empty else you will use underlying qty which is wrong and likely leads to oversold
    lots_returned = remove_options_exer_assign(investment, location, quantity, local, book, closing_method, "",
                                               journal_entries,
                                               sub_ledger, ls, tranid)

    premium_local = 0
    premium_book = 0
    # Loop over the closed lots and accumulate the premium paid
    for lotinfo in lots_returned:
        portfolio, investment, lotid, tax_date, ls, closed_qty, closed_local, closed_book = lotinfo[:7]

        # Accumulate premium paid
        premium_local += closed_local
        premium_book += closed_book
        # close option lots
        invclose = Journals(portfolio, investment, lotid, tax_date, "s", location, "Cost", -closed_qty, -closed_local,
                            -closed_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
                            "Asset/Liability")
        sub_ledger.post_journal_entry(invclose)

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
        je = Journals(portfolio, payment_currency, tranid, tradedate,"l", location, "Receivable", local_cost, local_cost,
                      book_cost,None, None, tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(je)

        # book a long position
        je = Journals(portfolio, underlying, tranid, tradedate, "l", location, "Cost", -u_quantity, -local_cost + premium_local,
                      -book_cost + premium_book, None, None, tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(je)

    if put_call == "put": #Buy Long
        je = Journals(portfolio, payment_currency, tranid, tradedate,"s", location, "Payable",
                      -local_cost, -local_cost, -book_cost, None, None,
                      tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(je)

        je = Journals(portfolio, underlying, tranid, tradedate, "l", location, "Cost", u_quantity, local_cost + premium_local,
                      book_cost + premium_book, None, None,
                      tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(je)

    return


# long put/call cover long/cover short underlying
def assign_option_close(portfolio, investment, location, quantity, local, book, closing_method, journal_entries,
                          sub_ledger, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                          payment_currency,
                          put_call, strike, underlying, tdate_fx):
    # pass 'ls' flag into closelots - determine if l or is is being closed
    # Close the lots for the given investment and quantity using the specified closing method

    lots_returned = remove_options_exer_assign(investment, location, -quantity, -local, -book, closing_method, "",
                                               journal_entries,
                                               sub_ledger, "s", tranid)

    premium_local = 0
    premium_book = 0
    # Loop over the closed lots and accumulate the premium paid
    for lotinfo in lots_returned:
        portfolio, investment, lotid, tax_date, ls, closed_qty, closed_local, closed_book = lotinfo[:7]

        # Accumulate premium paid
        premium_local += closed_local
        premium_book += closed_book

        invclose = Journals(portfolio, investment, lotid, tax_date, ls, location, "Cost", -closed_qty, -closed_local,
                            -closed_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
                            "Asset/Liability")
        sub_ledger.post_journal_entry(invclose)

    income = Journals(portfolio, investment, ld, ld,"n", location, "OptionExpense", premium_local, premium_local,
                      premium_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
                      "Revenue/Expense/Capital")
    sub_ledger.post_journal_entry(income)
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
        je = Journals(portfolio, payment_currency, tranid, tradedate,"l", location, "Receivable", local, local, book, None, None,
                      tranid,
                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(je)

        lots_returned = close_equity_lots(underlying, location, quantity, local, book, closing_method, "",
                                          journal_entries,
                                          sub_ledger, "l", tranid)

        # Loop over the closed lots and post the corresponding journal entries
        for lotinfo in lots_returned:
            portfolio, underlying, lotid, tax_date, closed_qty, closed_local, closed_book, closed_proceeds = lotinfo
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
            invclose = Journals(portfolio, underlying, lotid, tax_date, "l", location, "Cost", -closed_qty, -closed_local,
                                -closed_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                "Asset/Liability")
            sub_ledger.post_journal_entry(invclose)

            if pgain_local != 0:
                pgclose = Journals(portfolio, underlying, lotid, tax_date, ls, location, "PriceGainInvestment", 0,
                                   -pgain_local,
                                   -pgain_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                   ibor_date, "Revenue/Expense/Capital")
                sub_ledger.post_journal_entry(pgclose)

            if glbook != 0:
                glclose = Journals(portfolio, underlying, lotid, tax_date, ls, location, "FXGainInvestment", 0, 0, -glbook, None, None,
                                   tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                   "Revenue/Expense/Capital")
                sub_ledger.post_journal_entry(glclose)

    if put_call == "put": #Cover Short
        je = Journals(portfolio, payment_currency, tranid, tradedate,"s", location, "Payable", -local, -local, -book, None, None,
                      tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(je)

        lots_returned = close_equity_lots(underlying, location, -quantity, -local, -book, closing_method, "",
                                          journal_entries,
                                          sub_ledger, "s", tranid)

        # Loop over the closed lots and post the corresponding journal entries
        for lotinfo in lots_returned:
            portfolio, underlying, lotid, tax_date, closed_qty, closed_local, closed_book, closed_proceeds = lotinfo
            # Calculate the realized gain/loss on investment

            fxrate = 1  # add fx
            pgain_local = closed_proceeds - closed_local
            pgain_book = pgain_local * fxrate
            glbook = closed_proceeds * fxrate - closed_book - pgain_book
            realized_gl = (closed_proceeds - closed_local) * fxrate * -1

            if closed_book == 0:  # method passes back 0 for book as we need to convert it to trade fx equivalent
                closed_book = closed_local * fxrate

                # Post journal entries to update the bookkeeping space for underlying
            invclose = Journals(portfolio, underlying, lotid,  tax_date, "s", location, "Cost", -closed_qty, -closed_local,
                                -closed_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                "Asset/Liability")
            sub_ledger.post_journal_entry(invclose)

            if pgain_local != 0:
                pgclose = Journals(portfolio, underlying, lotid, tax_date, "s", location, "PriceGainInvestment", 0,
                                   -pgain_local,
                                   -pgain_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                                   ibor_date, "Revenue/Expense/Capital")
                sub_ledger.post_journal_entry(pgclose)

            if glbook != 0:
                glclose = Journals(portfolio, underlying, lotid, tax_date, "s", location, "FXGainInvestment", 0, 0, -glbook, None, None,
                                   tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                   "Revenue/Expense/Capital")
                sub_ledger.post_journal_entry(glclose)

    return

