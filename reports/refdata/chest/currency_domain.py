from typing import List, Tuple
import bookkeeping
from bookkeeping import BookkeepingSpace, Journals
from utilities import check_same_sign, get_fx_rate
#from main import get_fx_rate
import main
tranid =0
from kivygui import ld # lump data

# args
def open_close_cash(investment: str, qty: float, local: float, book: float, sub_ledger):
    # Query the currency positio

    bs_entries = sub_ledger.get_position_entries(investment)

    investment_lots = []
    for key, values in bs_entries.items():  # Correctly unpack key, values from the dictionary
        if key[1] == investment and key[6] == "Cost":
            # Logic assuming 'values' is a tuple like (quantity, local, book)
            investment_lots.append(
                (key[0], investment, key[2], key[3], key[4], "Cost", values[0], values[1], values[2]))


    # investment_lots = [(k[0], investment, k[2], k[3],k[4],"Cost", v[0], v[1], v[2]) for k, v in bs if
    #                        k[1] == investment and k[5] == "Cost"]


   #k[0] is the index of the account key tuble when thinking about k,v as in k,v context v are the three values

    existing_local = sum([lot[7] for lot in investment_lots])
    amount_to_close = 0
    amount_to_close_book = 0
    closed_proceeds_local = 0
    closed_proceeds_book = 0
    opened_local= 0
    opened_book =0
    # first section executes if there are lots, second simply moves away from zero
    # as if there are no lots test will fail and give index out of bounds error
    if book != 0:
        fxrate =float(local)/float(book)
    else:
        fxrate =1
    # move away from zero
    if check_same_sign(existing_local, local):
        amount_to_close = 0
        amount_to_close_book = 0
        closed_proceeds_local = 0
        closed_proceeds_book = 0
        opened_local = qty
        opened_book = book
    # partial or full close
    if not check_same_sign(existing_local, local) and abs(qty) <= abs(investment_lots[0][6]):
        amount_to_close = investment_lots[0][7] * abs(local) / abs(investment_lots[0][6])
        amount_to_close_book = investment_lots[0][8] * abs(local) / abs(investment_lots[0][7])
        closed_proceeds_local = amount_to_close
        closed_proceeds_book = closed_proceeds_local / fxrate
        opened_local = 0
        opened_book = 0
    # cross zero
    if not check_same_sign(local, existing_local) and abs(qty) > abs(investment_lots[0][6]):
        amount_to_close = investment_lots[0][7]
        amount_to_close_book = investment_lots[0][8]
        closed_proceeds_local = amount_to_close
        closed_proceeds_book = amount_to_close / fxrate
        opened_local = qty + amount_to_close
        opened_book = opened_local / fxrate

    # Return the amount to be closed in local and book, and the local and book balance to be opened
    # switch signs for atc,atcb,cpl,cpb to so that journal engine posts intuitively
    return amount_to_close, amount_to_close_book, closed_proceeds_local, closed_proceeds_book, opened_local, opened_book


def currency_iterator_by_location_and_flow(investment, sub_ledger,
                                           financial_account_in, financial_account_out, tranid):

    bs_entries = sub_ledger.asset_liability_repository.get_position_entries(investment)

    lots = []
    for entry in bs_entries.items():
        entry_data = entry[0]
        if entry_data[1] == investment and entry_data[5] in [financial_account_in, financial_account_out] and entry_data[2] == tranid:
            lots.append((entry_data[3], entry_data[5], entry_data[4], entry[1][1],
                         entry[1][2]))  # Append location,financial_account, LS, local, and book amounts
            # Append the location and LS values directly
    return lots
def settle_single_flow_out(portfolio, payment_currency, location, quantity, local,
                      book, journal_entries, sub_ledger, tranid, transaction, tradedate, settledate,
                           kdbegin, kdend, fx_data):

    if transaction == "SpotSettlement":
        fin_acct = "SpotFxPayable"
    else:
        fin_acct = "Payable"

    # close payable
    ibor_date = settledate
    je = Journals(portfolio, payment_currency, tranid, tradedate,"s", location, fin_acct, local, local,
                      book, None, None, tranid, transaction, tradedate, settledate, kdbegin,
                  kdend, ibor_date, "Asset/Liability")
    sub_ledger.post_journal_entry(je)
    formatted_date = "{}/{}/{}".format(settledate.month, settledate.day, settledate.year)
    fx_rate = get_fx_rate(payment_currency, formatted_date, fx_data)
    #fx_rate =1
    # calculate gl between trade and settle

    glts = book - local * fx_rate
    if glts != 0:
        currglx = Journals( portfolio, payment_currency, 0,ld, 'n', location, "FXGainTradeSettle", 0, 0, -glts, None, None, tranid,
                               transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
        sub_ledger.post_journal_entry(currglx)
        #


    lot_id = 0
    ls = "n"
    financial_account = "Cost"
    # Call open_close_cash
    bookflow = local * fx_rate


    closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(
        payment_currency, -local, -local, -bookflow, sub_ledger)


    if closed_local != 0:  # means there is a balance to close
        curclosebal = Journals(portfolio, payment_currency, 0, ld, 'n',
                                   location, financial_account, -closed_local, -closed_local, -closed_book, None, None,tranid,
                                   transaction, tradedate,
                                   settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(curclosebal)

    if opened_local != 0:  # means a balance must be opened
        curopenbal = Journals(portfolio, payment_currency, 0, ld, 'n', location,
                                  "Cost", opened_local, opened_local, opened_book, None, None, tranid,
                                  transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(curopenbal)


    gl = proceeds_book - closed_book
    if gl != 0:
        currglx = Journals( portfolio, payment_currency, 0, ld, 'n', location,
                               "FXGainCurrency", 0, 0, -gl, None, None, tranid, transaction,
                               tradedate, settledate, kdbegin, kdend,  ibor_date, "Revenue/Expense/Capital")
        sub_ledger.post_journal_entry(currglx)


    return



def settle_single_flow_in(portfolio, payment_currency, location, quantity, local,
                  book, journal_entries, sub_ledger, tranid, transaction, tradedate, settledate,
                       kdbegin, kdend, fx_data):
    if transaction == "SpotSettlement":
        fin_acct = "SpotFxReceivable"
    else:
        fin_acct = "Receivable"

    # close receivable
    ibor_date = settledate
    je = Journals( portfolio, payment_currency, tranid, tradedate, "l", location, fin_acct, -local, -local,
                        -book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend,  ibor_date, "Asset/Liability")
    sub_ledger.post_journal_entry(je)



    fx_rate = get_fx_rate(payment_currency, settledate, fx_data)
    #fx_rate =1
    # calculate gl between trade and settle

    glts = book - local * fx_rate
    if glts != 0:
        currglx = Journals( portfolio, payment_currency, 0, ld, 'n', location, "FXGainTradeSettle", 0, 0, glts,
                            None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,"Revenue/Expense/Capital")
        sub_ledger.post_journal_entry(currglx)



    lot_id = 0
    ls = "n"
    financial_account = "Cost"
    # Call open_close_cash
    bookflow = local * fx_rate



    closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(
        payment_currency, local, local, bookflow, sub_ledger)


    if closed_local != 0:  # means there is a balance to close
        curclosebal = Journals( portfolio, payment_currency, 0, ld,'n',
                                   location, financial_account, -closed_local, -closed_local, -closed_book, None, None, tranid,
                                   transaction, tradedate,
                                   settledate, kdbegin, kdend, ibor_date, "Asset/Liability")

        sub_ledger.post_journal_entry(curclosebal)

    if opened_local != 0:  # means a balance must be opened
        curopenbal = Journals(portfolio, payment_currency, 0, ld, 'n', location,
                                  "Cost", opened_local, opened_local, opened_book, None, None, tranid,
                                  transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(curopenbal)

    gl = proceeds_book - closed_book
    if gl != 0:
        currglx = Journals( portfolio, payment_currency, 0, ld,'n', location,
                               "FXGainCurrency", 0, 0, -gl, None, None, tranid, transaction,
                               tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
        sub_ledger.post_journal_entry(currglx)



    return


def settle_bond_flow_out(portfolio, payment_currency, investment, location, quantity, local,
                          book, journal_entries, sub_ledger, tranid, transaction, tradedate, settledate,
                          kdbegin, kdend, smf, accrued_local, accrued_book, fx_data):
    principal_flow_fa = "Payable"
    accrue_fa = "AccruedInterestPayable"
    asset_liability_fa = "PurchasedInterest"
    inc_exp_fa = "PurchasedInterestExpense"
    # close receivable
    ibor_date = settledate
    je = Journals(portfolio, payment_currency, tranid, tradedate,"l", location, principal_flow_fa, local, local,
                  book, None,None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    sub_ledger.post_journal_entry(je)

    je = Journals(portfolio, payment_currency, tranid, tradedate,"l", location, accrue_fa, accrued_local, accrued_local,
                  accrued_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    sub_ledger.post_journal_entry(je)

    je = Journals(portfolio, investment, tranid, tradedate,"l", location, asset_liability_fa, -accrued_local, -accrued_local,
                  -accrued_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    sub_ledger.post_journal_entry(je)

    je = Journals(portfolio, investment, settledate, tranid, "n", location,  inc_exp_fa, accrued_local, accrued_local,
                  accrued_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
    sub_ledger.post_journal_entry(je)

    fx_rate = get_fx_rate(payment_currency, settledate, fx_data)
    # fx_rate =1
    # calculate gl between trade and settle
    tot_book = book + accrued_book
    tot_local = local + accrued_local
    glts = tot_book - tot_local  * fx_rate
    if glts != 0:
        currglx = Journals(portfolio, payment_currency, 0,ld, 'n', location, "FXGainTradeSettle", 0, 0, glts,None, None, tranid,
                           transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
        sub_ledger.post_journal_entry(currglx)



    lot_id = 0
    ls = "n"
    financial_account = "Cost"
    # Call open_close_cash
    bookflow = (local + accrued_local) * fx_rate


    closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(
        payment_currency, -(local+accrued_local), -(local+accrued_local), -bookflow, sub_ledger)

    if closed_local != 0:  # means there is a balance to close
        curclosebal = Journals(portfolio, payment_currency, 0, ld,'n',
                               location, financial_account, -closed_local, -closed_local, -closed_book, None, None, tranid,
                               transaction, tradedate,
                               settledate, kdbegin, kdend, ibor_date, "Asset/Liability")

        sub_ledger.post_journal_entry(curclosebal)

    if opened_local != 0:  # means a balance must be opened
        curopenbal = Journals(portfolio, payment_currency, 0, ld,'n', location,
                              "Cost", opened_local, opened_local, opened_book, None, None, tranid,
                              transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(curopenbal)

    gl = proceeds_book - closed_book
    if gl != 0:
        currglx = Journals(portfolio, payment_currency, 0, ld, 'n', location,
                           "FXGainCurrency", 0, 0, -gl, None, None, tranid, transaction,
                           tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
        sub_ledger.post_journal_entry(currglx)



    return
def settle_bond_flow_in(portfolio, payment_currency, investment, location, quantity, local,
                          book, journal_entries, sub_ledger, tranid, transaction, tradedate, settledate,
                          kdbegin, kdend, smf, accrued_local, accrued_book, fx_data):
    principal_flow_fa = "Receivable"
    accrue_fa = "AccruedInterestReceivable"
    asset_liability_fa = "SoldInterest"
    inc_exp_fa = "PurchasedInterestIncome"
    # close receivable
    ibor_date = settledate
    je = Journals(portfolio, payment_currency, tranid, tradedate,"l", location, principal_flow_fa, -local, -local,
                  -book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    sub_ledger.post_journal_entry(je)

    je = Journals(portfolio, payment_currency, tranid, tradedate,"l", location, accrue_fa, -accrued_local, -accrued_local,
                  -accrued_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    sub_ledger.post_journal_entry(je)

    je = Journals(portfolio, investment, tranid, tradedate,"l", location, asset_liability_fa, accrued_local, accrued_local,
                  accrued_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    sub_ledger.post_journal_entry(je)

    je = Journals(portfolio, investment, tranid, settledate, "l", location, inc_exp_fa, -accrued_local, -accrued_local,
                  -accrued_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
    sub_ledger.post_journal_entry(je)

    fx_rate = get_fx_rate(payment_currency, settledate, fx_data)
    # fx_rate =1
    # calculate gl between trade and settle
    tot_book = -(book + accrued_book)
    tot_local = -(local + accrued_local)
    glts = tot_book - tot_local  * fx_rate
    if glts != 0:
        currglx = Journals(portfolio, payment_currency, 0, ld,'n', location, "FXGainTradeSettle", 0, 0, glts,None, None, tranid,
                           transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
        sub_ledger.post_journal_entry(currglx)




    lot_id = 0
    ls = "n"
    financial_account = "Cost"
    # Call open_close_cash
    bookflow = (local + accrued_local) * fx_rate

    closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(
        payment_currency, local+accrued_local, local+accrued_local, bookflow, sub_ledger)

    if closed_local != 0:  # means there is a balance to close
        curclosebal = Journals(portfolio, payment_currency, 0 ,ld, 'n',
                               location, financial_account, -closed_local, -closed_local, -closed_book, None, None, tranid,
                               transaction, tradedate,
                               settledate, kdbegin, kdend, ibor_date, "Asset/Liability")

        sub_ledger.post_journal_entry(curclosebal)

    if opened_local != 0:  # means a balance must be opened
        curopenbal = Journals(portfolio, payment_currency, 0, ld, 'n', location,
                              "Cost", opened_local, opened_local, opened_book, None, None, tranid,
                              transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(curopenbal)

    gl = proceeds_book - closed_book
    if gl != 0:
        currglx = Journals(portfolio, payment_currency, 0, ld, 'n', location,
                           "FXGainCurrency", 0, 0, -gl, None, None, tranid, transaction,
                           tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
        sub_ledger.post_journal_entry(currglx)





    return




def settle_multiple_flows_in_out(portfolio, payment_currency,investment, financial_account_in, financial_account_out,
                                 journal_entries, sub_ledger, tranid, transaction, tradedate, settledate,
                                 kdbegin, kdend, smf, fx_data):


    lots = currency_iterator_by_location_and_flow(payment_currency, sub_ledger,
                                                  financial_account_in, financial_account_out, tranid)

    for lot in lots:
        # Unpack the lot tuple
        LS, financial_account, location,  local, book = lot


        # Close receivable or payable account
        ibor_date = settledate
        je = Journals(portfolio, payment_currency, tranid, tradedate, LS, location, financial_account, -local, -local,
                          -book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                          "Asset/Liability")
        sub_ledger.post_journal_entry(je)


        fx_rate = get_fx_rate(payment_currency, settledate, fx_data)
        glts = book - local * fx_rate
        if glts != 0:
            currglx = Journals(portfolio, payment_currency, 0, ld,'n', location,
                                "FXGainTradeSettle", 0, 0, glts,
                                None, None,
                                   tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                   "Revenue/Expense/Capital")
            sub_ledger.post_journal_entry(currglx)



        # Call open_close_cash
        bookflow = local * fx_rate

        closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(
            payment_currency, local, local, bookflow, sub_ledger)

        financial_account = "Cost"
        if closed_local != 0:  # means there is a balance to close
            curclosebal = Journals(portfolio, payment_currency, 0,ld, 'n',
                                       location, financial_account, -closed_local, -closed_local, -closed_book, None, None,
                                       tranid, transaction, tradedate,
                                       settledate, kdbegin, kdend, ibor_date, "Asset/Liability")

            sub_ledger.post_journal_entry(curclosebal)


        if opened_local != 0:  # means a balance must be opened
            curopenbal = Journals(portfolio, payment_currency, 0,ld, 'n', location,
                                      financial_account, opened_local, opened_local, opened_book, None, None, tranid,
                                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
            sub_ledger.post_journal_entry(curopenbal)


        gl = proceeds_book - closed_book
        if gl != 0:
            currglx = Journals(portfolio, payment_currency,  0,ld, 'n', location,
                                   "FXGainCurrency", 0, 0, -gl, None, None, tranid, transaction,
                                   tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
            sub_ledger.post_journal_entry(currglx)



    return

def settle_pay_rec_by_tranid(portfolio, investment, location, quantity, local, book, journal_entries,
                             sub_ledger, tranid, transaction, tradedate, settledate, kdbegin,
                             kdend, payment_currency, smf, fx_data):
    print(f"Processing settlement event for transaction ID: {tranid}")

    # Query receivable balances for the transaction ID
    receivables = sub_ledger.query_balance_by_tranid(tranid, "Receivable", payment_currency)

    # If no receivables found, query payables
    if not receivables:
        payables = sub_ledger.query_balance_by_tranid(tranid, "Payable", payment_currency)
        entries = payables
        account_type = "Payable"
    else:
        entries = receivables
        account_type = "Receivable"

    # Process the balances
    for entry in entries:
        portfolio, investment, lotid, tax_date, ls, location, financial_account, quantity, local, book, notional, oface = entry

        # Close receivable or payable account
        ibor_date = settledate
        je = Journals(portfolio, payment_currency, lotid, tax_date, 'n', location, account_type, -local, -local, -book, None, None, tranid, transaction, tradedate,
                      settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        sub_ledger.post_journal_entry(je)

        # Calculate FX gain/loss
        fx_rate = get_fx_rate(payment_currency, settledate, fx_data)
        glts = book - local * fx_rate
        if glts != 0:
            currglx = Journals(portfolio, payment_currency, lotid, tax_date, 'n', location,
                               "FXGainTradeSettle", 0, 0, glts, None, None, tranid, transaction,
                               tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
            sub_ledger.post_journal_entry(currglx)



        # Call open_close_cash
        bookflow = local * fx_rate

        closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(payment_currency, local, local, bookflow, sub_ledger)

        financial_account = "Cost"
        if closed_local != 0:  # means there is a balance to close
            curclosebal = Journals(portfolio, payment_currency, lotid, tax_date, 'n', location, financial_account, -closed_local, -closed_local, -closed_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
            sub_ledger.post_journal_entry(curclosebal)

        if opened_local != 0:  # means a balance must be opened
            curopenbal = Journals(portfolio, payment_currency, lotid, tax_date, 'n', location, financial_account, opened_local, opened_local, opened_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
            sub_ledger.post_journal_entry(curopenbal)

        gl = proceeds_book - closed_book
        if gl != 0:
            currglx = Journals(portfolio, payment_currency, lotid, tax_date, 'n', location, "FXGainCurrency", 0, 0, -gl, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
            sub_ledger.post_journal_entry(currglx)



    # If no entries are found, handle it appropriately
    if not entries:
        print(f"No receivables or payables found for transaction ID: {tranid}")


def deposit_currency(portfolio, payment_currency, location, qty, local, book, journal_entries, bs, tranid, transaction,
            tradedate, settledate, kdbegin, kdend, fx_data):

    # Currency
    lot_id = 0
    ibor_date = tradedate

    # Call open_close_cash
    closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(payment_currency,
                                                                                             local,
                                                                                             local,
                                                                                             book,
                                                                                             bs)

    if closed_local != 0:  # means there is a balance to close
        curclosebal = Journals(portfolio, payment_currency, 0, ld, 'n', location, "Cost", -closed_local, -closed_local,
                            -closed_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        bs.post_journal_entry(curclosebal)


    if opened_local != 0:  # means a balance must be opened
        curopenbal = Journals( portfolio, payment_currency, 0, ld, 'n', location, "Cost", opened_local, opened_local,
                             opened_book, None, None, tranid, transaction,tradedate, settledate, kdbegin, kdend, ibor_date,"Asset/Liability")
        bs.post_journal_entry(curopenbal)


    gl = proceeds_book - closed_book
    if gl != 0:
        currglx = Journals( portfolio, payment_currency, 0, ld,'n', location,
                             "FXGainCurrency", 0, 0, -gl, None, None,
                             tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                            "Revenue/Expense/Capital")
        bs.post_journal_entry(currglx)



        #Capital

    je = Journals(portfolio, payment_currency, 0, ld, "n", location, "ContributedCost", -qty, -local,
                      -book, None, None, tranid,  transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
    bs.post_journal_entry(je)

def withdraw_currency(portfolio, payment_currency, location, qty, local, book, journal_entries, bs, tranid, transaction,
             tradedate, settledate, kdbegin, kdend, fx_data):
    # Create a new je Open IBM
    ls = "n"
    ibor_date = tradedate

    # Currency
    # Call open_close_cash

    closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(payment_currency,
                                                                                                    -local,
                                                                                                    -local,
                                                                                                    -book,
                                                                                                     bs)

    if closed_local != 0:  # means there is a balance to close
        curclosebal = Journals( portfolio, payment_currency, 0, ld, 'n', location, "Cost", -closed_local, -closed_local,
                             -closed_book, None, None, tranid, transaction, tradedate,settledate, kdbegin, kdend, ibor_date,"Asset/Liability")
        bs.post_journal_entry(curclosebal)

    if opened_local != 0:  # means a balance must be opened
        curopenbal = Journals(portfolio, payment_currency, 0, ld, 'n', location, "Cost", opened_local, opened_local,
                         opened_book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        bs.post_journal_entry(curopenbal)

    gl = proceeds_book - closed_book
    if gl != 0:
        currglx = Journals( portfolio, payment_currency, 0, ld, 'n', location, "FXGainCurrency", 0, 0, -gl,
                              None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
        bs.post_journal_entry(currglx)


        # Capital

    je = Journals( portfolio, payment_currency, 0,ld, "n", location, "ContributedCost", qty, local,
                      book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
    bs.post_journal_entry(je)

def expense(portfolio, payment_currency, location, qty, local, book, financial_account, journal_entries, bs, tranid, transaction,
            tradedate, settledate, kdbegin, kdend):
    # Currency
    lot_id = 0
    ibor_date = tradedate

    je = Journals(portfolio, payment_currency, 0, ld,"n", location, financial_account, 0, local,
                      book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                      "Revenue/Expense/Capital")
    bs.post_journal_entry(je)

    financial_account = "ExpensesPayable"
    je = Journals(portfolio, payment_currency, tranid, tradedate,"s", location, financial_account, -local, -local,
                          -book, None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                          "Asset/Liability")
    bs.post_journal_entry(je)

def spotfx(portfolio, investment, location, qty, local, book, journal_entries, sub_ledger, tranid,
               transaction, tradedate, settledate, kdbegin, kdend, buy_currency, sell_currency,
               buy_amt, sell_amt):

    # Case when portfolio currency matches the buy currency (X)
    if investment == buy_currency: #AIF will handle base curr of portolio overloading investment for now
        base_equivalent_buy = buy_amt
        base_equivalent_sell = buy_amt
    # Case when portfolio currency matches the sell currency (Y)
    elif investment == sell_currency:
        base_equivalent_sell = sell_amt
        base_equivalent_buy = sell_amt
    # Case when portfolio currency doesn't match either X or Y
    else:
        base_equivalent = buy_amt *  get_fx_rate(buy_currency, tradedate, main.fx_data)
        base_equivalent_buy = base_equivalent
        base_equivalent_sell = base_equivalent

    # Create receivable for the buy_currency
    ls = "l"
    financial_account = "SpotFxReceivable"
    ibor_date = tradedate
    tax_date = tradedate
    je = Journals(portfolio, buy_currency, tranid, tradedate, ls, location, financial_account, buy_amt, buy_amt,
                      base_equivalent_buy, None, None,tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                  "Asset/Liability")
    sub_ledger.post_journal_entry(je)

    ls = "s"
    financial_account = "SpotFxPayable"  # use tranid for payable receivable to close
    je = Journals(portfolio, sell_currency, tranid, tradedate, ls, location, financial_account,
                  -sell_amt, -sell_amt, -base_equivalent_sell, None, None,
                tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    sub_ledger.post_journal_entry(je)

    return
