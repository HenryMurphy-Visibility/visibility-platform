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

from typing import List, Tuple
import datetime


def close_equity_lots(investment: str, location: str, quantity: float, local: float, book: float, closing_method: str,
                      tax_date: datetime.datetime, space, ls: str, tranid) -> List[
    Tuple[str, str, int, float, float, float, float]]:
    bs_entries = space.asset_liability_repository.get_position_entries(investment)

    # Extract investment lots including lotid and location
    investment_lots = [
        (k[0], k[1], k[2], k[3], k[4], k[5], v[0], v[1], v[2])
        for k, v in bs_entries.items()
        if k[1] == investment and k[5] == location and ((v[0] < 0 and k[4] == ls) or (v[0] > 0 and k[4] == ls)) and k[
            6] == "Cost"
    ]

    if (tranid == 360):
        print("here")

    if not investment_lots:
        raise ValueError(f"No investment lots found for the specified criteria. TranID-{tranid}-{investment}")

    if closing_method == 'LIFO':
        investment_lots.sort(key=lambda x: x[3], reverse=True)  # Sort by tax_date (x[3]) first, then lotid (x[2])
    elif closing_method == 'FIFO':
        investment_lots.sort(key=lambda x: x[3])  # Sort by tax_date (x[3]) first, then lotid (x[2])

    closed_lots = []

    # Flip the sign of remaining_quantity if ls == "s"
    if investment_lots[0][4] == "s":
        remaining_quantity = -quantity
        remaining_sell_proceeds = -local
    else:
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

        if ls == "l":
            closed_qty = min(lot_quantity, remaining_quantity)
        else:
            closed_qty = max(lot_quantity, remaining_quantity)

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
            bs_entries[(portfolio, investment, new_lotid, tax_date, ls, location, "Cost")] = (
            remaining_quantity, local, book)
            closed_lots.append(
                (portfozlio, investment, new_lotid, tax_date, remaining_quantity, remaining_sell_proceeds, 0, 0))

    return closed_lots


from datetime import datetime

from datetime import datetime
from typing import List, Tuple


def remove_options_exer_assign(
        investment: str, location: str, quantity: float, local: float, book: float,
        closing_method: str, tax_date: datetime, journal_entries, space, ls: str, tranid
) -> List[Tuple[str, str, str, int, float, float, float, float]]:
    # Retrieve entries from the repository
    bs_entries = space.asset_liability_repository.get_position_entries(investment)

    # Define indices for readability
    portfoliox = 0
    investmentx = 1
    lotidx = 2
    tax_datex = 3
    lsx = 4
    locationx = 5
    financial_accountx = 6
    qtyx = 7
    localx = 8
    bookx = 9

    # List to store matching investment lots
    investment_lots = []

    # Iterate through each key-value pair in bs_entries
    for k, v in bs_entries.items():
        # Filter based on investment, location, and financial account
        if k[investmentx] == investment and k[locationx] == location and k[financial_accountx] == "Cost":
            # Check long/short condition based on the quantity and ls
            if (v[0] < 0 and ls == "s") or (v[0] > 0 and ls == "l"):
                investment_lots.append(
                    (k[portfoliox], k[investmentx], k[lotidx], k[tax_datex], k[lsx], v[0], v[1], v[2]))

    # Sort investment lots based on closing method
    if closing_method == 'LIFO':
        investment_lots.sort(key=lambda x: x[tax_datex], reverse=True)  # Latest first for LIFO
    elif closing_method == 'FIFO':
        investment_lots.sort(key=lambda x: x[tax_datex])  # Earliest first for FIFO

    # List to store closed lots
    closed_lots = []

    # Adjust quantities and calculate closed quantities
    for lot in investment_lots:
        lot_quantity = lot[5]  # Quantity from investment_lots

        if quantity == 0:
            break  # All quantities are closed

        if lot_quantity < 0:
            closed_qty = max(lot_quantity, quantity)
        else:
            closed_qty = min(lot_quantity, quantity)

        proportion = closed_qty / lot_quantity
        local_cost = proportion * lot[6]
        book_cost = proportion * lot[7]

        # Append closed lot to the result list
        closed_lots.append((
            lot[portfoliox], lot[investmentx], lot[lotidx], lot[tax_datex],
            lot[lsx], closed_qty, local_cost, book_cost
        ))

        # Reduce the remaining quantity
        quantity -= closed_qty

    return closed_lots


def lot_iterator(investment, space):
    # Get the entries from the investment subspace
    investment_space = space.get_position_space(investment)

    if investment_space:
        bs_entries = investment_space.entries  # Assuming 'entries' is a dictionary

        # Filter the entries based on the investment
        matching_lots = [entry for entry in bs_entries.items() if entry[0][1] == investment]

        # Extract relevant lot information (account key, lot quantity, local, and book values)
        # Assuming entry[1][0] is the lot quantity, entry[1][1] is local, and entry[1][2] is book
        return [(entry[0], entry[1][0], entry[1][1], entry[1][2], entry[1][3]) for entry in matching_lots]
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



def buy_equity(portfolio, investment, location, quantity, local, book, space, tranid, transaction,
               tradedate, settledate, kdbegin, kdend, entry_type):
    ls        = "l"
    ibor_date = tradedate
    tax_date  = tradedate

    je = Journals(portfolio, investment, tranid, tax_date, ls, location, "Cost",
                  quantity, local, book, 0, 0, tranid,
                  transaction, tradedate, settledate, kdbegin, kdend, ibor_date, entry_type)
    space.post_journal_entry(je)

    return


def sell_equity(portfolio, investment, location, quantity, local, book, closing_method,
                space, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                payment_currency, tdate_fx):
    ls        = "l"
    ibor_date = tradedate
    tax_date  = tradedate
    closing_method = "FIFO"

    # ── CLOSE COST LOTS ──────────────────────────────────────────
    lots_returned = close_equity_lots(investment, location, quantity, local, book,
                                      closing_method, tax_date, space, ls, tranid)

    for lotinfo in lots_returned:
        portfolio, investment, lotid, tax_date, closed_qty, closed_local, closed_book, closed_proceeds = lotinfo

        fxrate      = book / local if local != 0 else 0
        pgain_local = closed_proceeds - closed_local
        pgain_book  = pgain_local * fxrate
        fxgain_book = closed_proceeds * fxrate - closed_book - pgain_book

        # Cost lot closure
        space.post_journal_entry(Journals(
            portfolio, investment, lotid, tax_date, ls, location, "Cost",
            -closed_qty, -closed_local, -closed_book, 0, 0,
            tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
            "Asset/Liability"
        ))

        if pgain_local != 0:
            space.post_journal_entry(Journals(
                portfolio, investment, lotid, tax_date, ls, location, "PriceGainInvestment",
                0, -pgain_local, -pgain_book, 0, 0,
                tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                "Revenue/Expense/Capital"
            ))

        if fxgain_book != 0:
            space.post_journal_entry(Journals(
                portfolio, investment, lotid, tax_date, ls, location, "FXGainInvestment",
                0, 0, -fxgain_book, None, None,
                tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                "Revenue/Expense/Capital"
            ))

    return


def short_equity(portfolio, investment, location, quantity, local, book, space, tranid, transaction,
                 tradedate, settledate, kdbegin, kdend, payment_currency, tdate_fx, entry_type):
    ls        = "s"
    ibor_date = tradedate
    tax_date  = tradedate

    je = Journals(portfolio, investment, tranid, tax_date, ls, location, "Cost",
                  -quantity, -local, -book, 0, 0, tranid,
                  transaction, tradedate, settledate, kdbegin, kdend, ibor_date, entry_type)
    space.post_journal_entry(je)

    return


def cover_equity(portfolio, investment, location, quantity, local, book, closing_method,
                 space, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                 payment_currency, tdate_fx):
    ls        = "s"
    ibor_date = tradedate
    tax_date  = tradedate
    closing_method = "FIFO"

    # ── CLOSE SHORT COST LOTS ─────────────────────────────────
    # No negation — close_equity_lots handles direction via ls="s"
    lots_returned = close_equity_lots(investment, location, quantity, local, book,
                                      closing_method, tax_date, space, ls, tranid)

    for lotinfo in lots_returned:
        portfolio, investment, lotid, tax_date, closed_qty, closed_local, closed_book, closed_proceeds = lotinfo

        fxrate      = book / local if local != 0 else 0
        pgain_local = closed_local - closed_proceeds  # reversed — gain when price falls
        pgain_book  = pgain_local * fxrate
        glbook      = closed_proceeds * fxrate - closed_book - pgain_book

        if closed_book == 0:
            closed_book = closed_local * fxrate

        # Cost lot closure
        space.post_journal_entry(Journals(
            portfolio, investment, lotid, tax_date, ls, location, "Cost",
            closed_qty, closed_local, closed_book, 0, 0,
            tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
            "Asset/Liability"
        ))

        if pgain_local != 0:
            space.post_journal_entry(Journals(
                portfolio, investment, lotid, tax_date, ls, location, "PriceGainInvestment",
                0, -pgain_local, -pgain_book, 0, 0,
                tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                "Revenue/Expense/Capital"
            ))

        if glbook != 0:
            space.post_journal_entry(Journals(
                portfolio, investment, lotid, tax_date, ls, location, "FXGainInvestment",
                0, 0, -glbook, None, None,
                tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                "Revenue/Expense/Capital"
            ))

    return


def dividend_equity(portfolio, investment, space, tranid,
                    transaction, tradedate, settledate, kdbegin, kdend,
                    payment_currency, per_share):
    ibor_date = tradedate

    for location, total_quantity in lot_iterator_by_location(investment, space):

        divloc = total_quantity * per_share

        if divloc > 0:
            faal = "DividendsReceivable"
            faie = "DividendReceipt"
            ls   = "l"
        else:
            faal = "DividendsPayable"
            faie = "DividendExpense"
            ls   = "s"

        space.post_journal_entry(Journals(
            portfolio, payment_currency, tranid, tradedate, ls, location, faal,
            divloc, divloc, divloc, 0, 0, tranid, transaction,
            tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability"
        ))

        space.post_journal_entry(Journals(
            portfolio, investment, tranid, tradedate, ls, location, faie,
            0, -divloc, -divloc, 0, 0, tranid, transaction,
            tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital"
        ))

    return

def split_equity(portfolio, investment, space, tranid, transaction, tradedate, settledate,
                 kdbegin, kdend, new_shares, old_shares):
    financial_account = "Cost"
    ibor_date = tradedate
    tax_date = tradedate
    # Fetch all lots for the given investment using the lot_iterator
    lots_returned = lot_iterator(investment, space)

    # Loop over the lots and post the corresponding journal entries
    for lot_info in lots_returned:
        account_key, lot_qty = lot_info
        # Calculate the new lot quantity after the split
        split_qty = lot_qty * new_shares / old_shares - lot_qty

        # Create a new entry for the split result
        split_entry = Journals(portfolio, investment, account_key[2], account_key[3], account_key[4], account_key[5],
                               financial_account, split_qty, 0, 0, 0, 0, tranid, transaction, tradedate, settledate,
                               kdbegin, kdend, ibor_date, "Asset/Liability")

        # Post the split entry
        space.post_journal_entry(split_entry)
    return


"""
Transaction	                        Call Option	                                    Put Option
Option Exercise Open	- Buy the underlying asset (opens long position)	-   Sell short the underlying asset (opens short position)
- Use premium paid to adjust cost basis	- Use premium paid to adjust cost basis
-------------------------	------------------------------------------------------------	------------------------------------------------------------
Option Exercise Close	- Cover a short position (by buying shares)	-           Sell the underlying asset (closes long position)
- Book premium received as income	- Book premium received as income
-------------------------	------------------------------------------------------------	------------------------------------------------------------
Option Assignment Open	- Sell the underlying asset (if shares held)	-        Buy the underlying asset (if no shares are held)
- Sell short the underlying asset (if no shares held)	-                   -     Close short position (if already short)
-------------------------	------------------------------------------------------------	------------------------------------------------------------
Option Assignment Close	- Sell the underlying asset (if shares held)	-        Buy the underlying asset (if assigned)
- Book premium received as income	-                                            Book premium received as income
Key Details:
Exercise (action by the option holder):

Call Option:
Exercising opens a long position (buys the asset) or closes a short position (covers a short by buying shares).
Put Option:
Exercising opens a short position (sells short) or closes a long position (sells the asset).
Assignment (action forced on the option writer):

Call Option:
If the writer holds the shares, they must sell the shares.
If the writer doesn’t hold the shares, they must sell short.
Put Option:
If assigned, the writer must buy the asset (if no shares are held) or cover the short position if already short.
"""


# Assign Call (option short, underlying long)
def assign_call_long(portfolio, investment, location, quantity, local, book, closing_method,
                     space, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                     tdate_fx):
    """
    Handles the assignment of a short call option where the underlying investment is long.
    """
    handle_option_scenario('call', 's', 'l', 'assign', portfolio, investment, location, quantity, local, book,
                           closing_method, space, tranid, transaction, tradedate, settledate,
                           kdbegin, kdend, payment_currency, tdate_fx, "in")


# Assign Put (option short, underlying long)
def assign_put_long(portfolio, investment, location, quantity, local, book, closing_method,
                    space, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                    tdate_fx):
    """
    Handles the assignment of   a short put option where the underlying investment is long.
    """
    handle_option_scenario('put', 's', 'l', 'assign', portfolio, investment, location, quantity, local, book,
                           closing_method, space, tranid, transaction, tradedate, settledate,
                           kdbegin, kdend, payment_currency, tdate_fx, "out")


# Assign Call (option short, underlying short)
def assign_call_short(portfolio, investment, location, quantity, local, book, closing_method,
                      space, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                      tdate_fx):
    """
    Handles the assignment of a short call option where the underlying investment is short.
    """
    handle_option_scenario('call', 's', 's', 'assign', portfolio, investment, location, quantity, local, book,
                           closing_method, space, tranid, transaction, tradedate, settledate,
                           kdbegin, kdend, payment_currency, tdate_fx, "in")


# Assign Put (option short, underlying short)
def assign_put_short(portfolio, investment, location, quantity, local, book, closing_method,
                     space, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                     tdate_fx):
    """
    Handles the assignment of a short put option where the underlying investment is short.
    """
    handle_option_scenario('put', 's', 's', 'assign', portfolio, investment, location, quantity, local, book,
                           closing_method, space, tranid, transaction, tradedate, settledate,
                           kdbegin, kdend, payment_currency, tdate_fx, "out")


# Exercise Call (option long, underlying long)
def exercise_call_long(portfolio, investment, location, quantity, local, book, closing_method,
                       space, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                       tdate_fx):
    """
    Handles the exercise of a long call option where the underlying investment is long.
    """
    handle_option_scenario('call', 'l', 'l', 'exercise', portfolio, investment, location, quantity, local, book,
                           closing_method, space, tranid, transaction, tradedate, settledate,
                           kdbegin, kdend, payment_currency, tdate_fx, "out")


# Exercise Put (option long, underlying long)
def exercise_put_long(portfolio, investment, location, quantity, local, book, closing_method,
                      space, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                      tdate_fx):
    """
    Handles the exercise of a long put option where the underlying investment is long.
    """
    handle_option_scenario('put', 'l', 'l', 'exercise', portfolio, investment, location, quantity, local, book,
                           closing_method, space, tranid, transaction, tradedate, settledate,
                           kdbegin, kdend, payment_currency, tdate_fx, "in")


# Exercise Call (option long, underlying short)
def exercise_call_short(portfolio, investment, location, quantity, local, book, closing_method,
                        space, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                        tdate_fx):
    """
    Handles the exercise of a long call option where the underlying investment is short.
    """
    handle_option_scenario('call', 'l', 's', 'exercise', portfolio, investment, location, quantity, local, book,
                           closing_method, space, tranid, transaction, tradedate, settledate,
                           kdbegin, kdend, payment_currency, tdate_fx, "out")


# Exercise Put (option long, underlying short)
def exercise_put_short(portfolio, investment, location, quantity, local, book, closing_method,
                       space, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                       tdate_fx):
    """
    Handles the exercise of a long put option where the underlying investment is short.
    """
    handle_option_scenario('put', 'l', 's', 'exercise', portfolio, investment, location, quantity, local, book,
                           closing_method, space, tranid, transaction, tradedate, settledate,
                           kdbegin, kdend, payment_currency, tdate_fx, "in")


def handle_option_scenario(option_type, option_side, investment_side, method, portfolio, investment, location, quantity,
                           local, book, closing_method, space, tranid, transaction,
                           tradedate, settledate, kdbegin, kdend, payment_currency, tdate_fx, flow):
    # get the underlying qty, local and book

    # Fetch the subspace for the given investment
    investment_space = space.get_position_space(investment)
    strike = space.get_attribute_field(investment, 'AIF', 'Strike')
    underlying = space.get_attribute_field(investment, 'AIF', 'Underlying')
    contract_size = space.get_attribute_field(investment, 'AIF', 'Contract_Size')

    underlying_qty = quantity * float(contract_size)
    underlying_local = underlying_qty * float(strike)
    underlying_book = underlying_local
    """
    Main function to handle option scenarios: call/put (option_type), long/short option (option_side),
    long/short underlying (investment_side), assign/exercise.
    """

    if method == "assign":
        quantity * -1
    # Step 1: Close the option and accumulate the premium using the existing remove_options_exer_assign function
    lots_returned = remove_options_exer_assign(
        investment, location, quantity, local, book, closing_method, tradedate, space,
        option_side, tranid
    )

    premium_local = 0
    premium_book = 0

    # Loop over the closed lots and accumulate the premium paid
    for lotinfo in lots_returned:
        portfolio, investment, lotid, tax_date, ls, closed_qty, closed_local, closed_book = lotinfo[:8]

        # Accumulate premium paid
        premium_local += closed_local
        premium_book += closed_book

        invclose = Journals(portfolio, investment, lotid, tax_date, ls, location, "Cost", closed_qty, closed_local,
                            closed_book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate,
                            "Asset/Liability")
        space.post_journal_entry(invclose)

    # Step 2: Book income if assign
    book_premium_income(method, -premium_local, -premium_book, portfolio, investment, location, space, tranid,
                        transaction, tradedate, settledate, kdbegin, kdend, journal_entries)

    if method == "exercise":
        underlying_local = underlying_local - premium_local
        underlying_book = underlying_book - premium_book

    # Step 3: Handle the underlying asset transaction (buy/sell or cover)
    if option_type == 'call':
        if investment_side == 'l':
            # For a long underlying, assignment = sell, exercise = buy
            if method == 'assign':
                get_equity_lots(
                    underlying, location, underlying_qty, underlying_local, underlying_book, closing_method,
                    space,
                    "sell", tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                    tdate_fx, investment_side
                )
            else:  # Exercise the call = buy (cover)
                get_equity_lots(
                    underlying, location, -underlying_qty, -underlying_local, -underlying_book, closing_method,
                    space,
                    "buy", tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                    tdate_fx, investment_side
                )
        else:
            # Short underlying, assignment = cover the short
            get_equity_lots(
                underlying, location, underlying_qty, underlying_local, underlying_book, closing_method,
                space,
                "cover_short", tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                tdate_fx, investment_side
            )

    elif option_type == 'put':
        if investment_side == 'l':
            # For a long underlying, assignment = buy, exercise = sell
            if method == 'assign':
                get_equity_lots(
                    underlying, location, underlying_qty, underlying_local, underlying_book, closing_method,
                    space,
                    "buy", tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                    tdate_fx, investment_side
                )
            else:  # Exercise the put = sell
                get_equity_lots(
                    underlying, location, -underlying_qty, -underlying_local, -underlying_book, closing_method,
                    space,
                    "sell", tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                    tdate_fx, investment_side
                )
        else:
            # Short underlying, assignment = buy to cover short
            get_equity_lots(
                underlying, location, underlying_qty, underlying_local, underlying_book, closing_method,
                space,
                "cover_short", tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                tdate_fx, investment_side
            )

    # Now, the two conditions that **open** a new long or short position:
    elif method == 'exercise':
        # Condition 1: Exercise Call Long (open new long position)
        if option_type == 'call' and investment_side == 'l':
            invclose = Journals(
                portfolio, investment, tranid, tradedate, "l", location, "Cost",
                underlying_qty, underlying_local, underlying_book, 0, 0, tranid, transaction, tradedate, settledate,
                kdbegin, kdend, tradedate, "Asset/Liability"
            )
            space.post_journal_entry(invclose)

        # Condition 2: Exercise Put Short (open new short position)
        elif option_type == 'put' and investment_side == 's':
            invclose = Journals(
                portfolio, investment, tranid, tradedate, "s", location, "Cost",
                -underlying_qty, -underlying_local, -underlying_book, 0, 0, tranid, transaction, tradedate, settledate,
                kdbegin, kdend, tradedate, "Asset/Liability"
            )
            space.post_journal_entry(invclose)

    if flow == "in":
        # book receivable/payable
        ls = "l"
        financial_account = "Receivable"
    else:
        ls = "s"
        financial_account = "Payable"
        underlying_local = -underlying_local
        underlying_book = -underlying_book

    ibor_date = tradedate
    tax_date = tradedate

    # Post receivable entry
    je = Journals(
        portfolio, payment_currency, tranid, tax_date, ls, location, financial_account,
        underlying_local, underlying_local, underlying_book, 0, 0,
        tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability"
    )
    space.post_journal_entry(je)


def get_equity_lots(investment, location, quantity, local, book, closing_method, journal_entries, space,
                    transaction_type, tranid, transaction, tradedate, settledate, kdbegin, kdend, payment_currency,
                    tdate_fx, investment_side):
    """
    Closes the equity lots for the underlying asset, whether long or short, depending on the option type.
    """
    # Close the lots for the given investment and quantity using the specified closing method
    lots_returned = close_equity_lots(investment, location, quantity, local, book, closing_method, "",
                                      journal_entries, space, investment_side, tranid)

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
            portfolio, investment, lotid, tax_date, investment_side, location, "Cost",
            -closed_qty, -closed_local, -closed_book, 0, 0,
            tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate, "Asset/Liability"
        )
        space.post_journal_entry(invclose)

        if pgain_local != 0:
            pgclose = Journals(
                portfolio, investment, lotid, tax_date, investment_side, location, "PriceGainInvestment", 0,
                -pgain_local,
                -pgain_book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                tradedate, "Revenue/Expense/Capital"
            )
            space.post_journal_entry(pgclose)

        if fxgain_book != 0:
            fxclose = Journals(
                portfolio, investment, lotid, tax_date, investment_side, location, "FXGainInvestment", 0, 0,
                -fxgain_book, None,
                None,
                tranid, transaction, tradedate, settledate, kdbegin, kdend, tradedate, "Revenue/Expense/Capital"
            )
            space.post_journal_entry(fxclose)


def book_premium_income(method, premium_local, premium_book, portfolio, investment, location, space, tranid,
                        transaction,
                        tradedate, settledate, kdbegin, kdend, journal_entries):
    """
    Realizes or allocates the premium depending on whether the event is an assignment or exercise.
    """
    if method == 'assign':
        # Realize the premium for assignments
        journal = Journals(
            portfolio, investment, 0, 0, "n", location, "OptionIncome", 0, premium_local, premium_book, 0, 0, tranid,
            transaction, tradedate, settledate, kdbegin, kdend, tradedate, "Revenue/Expense/Capital"
        )
        space.post_journal_entry(journal)
