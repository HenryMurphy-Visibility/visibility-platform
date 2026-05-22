from typing import List, Tuple
import bookkeeping
from bookkeeping import BookkeepingSpace, Journals
from utilities import check_same_sign, get_fx_rate
#from main import get_fx_rate
import main
tranid =0
# args
import time

# ------------------------------------------------------------
# Optimized open_close_cash using the single cash Cost bucket
# ------------------------------------------------------------
def open_close_cash(investment: str, qty: float, local: float, book: float, location, space):

    # access the AL subspace for this currency investment
    subspace = space.get_position_space(investment)
    entries = subspace.entries

    # canonical cash lot key
    # (portfolio, investment, lotid=0, tax_date=0, ls="n", location, "Cost")
    # portfolio is embedded in JE so we must derive the portfolio dynamically.
    # This function must receive it or use the JE object normally.
    # We assume CURRENT_EVENT.portfolio is globally available as in your domains.


    cash_key = ("p", investment, 0, 0, "n", location, "Cost")

    # Existing balance (qty, local, book)
    old_qty, old_local, old_book = (0, 0, 0)

    if cash_key in entries:
        vals = entries[cash_key]
        old_qty, old_local, old_book = vals[0], vals[1], vals[2]

    # Compute FX
    fxrate = (local / book) if book != 0 else 1

    # Output variables
    amount_to_close       = 0
    amount_to_close_book  = 0
    closed_proceeds_local = 0
    closed_proceeds_book  = 0
    opened_local          = 0
    opened_book           = 0

    # ------------------------------------------------------------
    # CASE A — SAME SIGN: open new cash
    # ------------------------------------------------------------
    if old_local == 0 or (old_local > 0 and local > 0) or (old_local < 0 and local < 0):
        opened_local = local
        opened_book  = book
        return amount_to_close, amount_to_close_book, closed_proceeds_local, closed_proceeds_book, opened_local, opened_book

    # ------------------------------------------------------------
    # CASE B — PARTIAL CLOSE
    # ------------------------------------------------------------
    if abs(local) <= abs(old_local):
        proportion = abs(local) / abs(old_local)
        amount_to_close       = old_local * proportion
        amount_to_close_book  = old_book  * proportion
        closed_proceeds_local = amount_to_close
        closed_proceeds_book  = amount_to_close / fxrate
        return amount_to_close, amount_to_close_book, closed_proceeds_local, closed_proceeds_book, opened_local, opened_book

    # ------------------------------------------------------------
    # CASE C — CROSS ZERO
    # ------------------------------------------------------------
    # Close entire old position
    amount_to_close       = old_local
    amount_to_close_book  = old_book
    closed_proceeds_local = old_local
    closed_proceeds_book  = old_local / fxrate

    # Remainder becomes new opening
    opened_local = local + old_local
    opened_book  = opened_local / fxrate

    return amount_to_close, amount_to_close_book, closed_proceeds_local, closed_proceeds_book, opened_local, opened_book

def currency_iterator_by_location_and_flow(investment, space,
                                           financial_account_in, financial_account_out, tranid):

    bs_entries = space.asset_liability_repository.get_position_entries(investment)

    lots = []
    for entry in bs_entries.items():
        entry_data = entry[0]
        if entry_data[1] == investment and entry_data[5] in [financial_account_in, financial_account_out] and entry_data[2] == tranid:
            lots.append((entry_data[3], entry_data[5], entry_data[4], entry[1][1],
                         entry[1][2]))  # Append location,financial_account, LS, local, and book amounts
            # Append the location and LS values directly
    return lots

def settle_single_flow_in(portfolio, payment_currency, location, quantity, local,
                  book, space, tranid, transaction, tradedate, settledate,
                       kdbegin, kdend, fx_data):
    if transaction == "SpotSettlement":
        fin_acct = "SpotFxReceivable"
    else:
        fin_acct = "Receivable"

    # close receivable
    ibor_date = settledate
    je = Journals( portfolio, payment_currency, tranid, tradedate, "l", location, fin_acct, -local, -local,
                        -book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend,  ibor_date, "Asset/Liability")
    space.post_journal_entry(je)



    fx_rate = get_fx_rate(payment_currency, settledate, fx_data)
    #fx_rate =1
    # calculate gl between trade and settle

    glts = book - local * fx_rate
    if glts != 0:
        currglx = Journals( portfolio, payment_currency, 0, 0, 'n', location, "FXGainTradeSettle", 0, 0, glts,
                            None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,"Revenue/Expense/Capital")
        space.post_journal_entry(currglx)

    lot_id = 0
    ls = "n"
    financial_account = "Cost"
    # Call open_close_cash
    bookflow = local * fx_rate



    closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(
        payment_currency, local, local, bookflow, location, space)


    if closed_local != 0:  # means there is a balance to close
        curclosebal = Journals( portfolio, payment_currency, 0, 0,'n',
                                   location, financial_account, -closed_local, -closed_local, -closed_book, 0, 0, tranid,
                                   transaction, tradedate,
                                   settledate, kdbegin, kdend, ibor_date, "Asset/Liability")

        space.post_journal_entry(curclosebal)

    if opened_local != 0:  # means a balance must be opened
        curopenbal = Journals(portfolio, payment_currency, 0, 0, 'n', location,
                                  "Cost", opened_local, opened_local, opened_book, 0, 0, tranid,
                                  transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(curopenbal)

    gl = proceeds_book - closed_book
    if gl != 0:
        currglx = Journals( portfolio, payment_currency, 0, 0,'n', location,
                               "FXGainCurrency", 0, 0, -gl, None, None, tranid, transaction,
                               tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
        space.post_journal_entry(currglx)



    return


def settle_single_flow_out(portfolio, payment_currency, location, quantity, local,
                      book, space, tranid, transaction, tradedate, settledate,
                           kdbegin, kdend, fx_data):

    if transaction == "SpotSettlement":
        fin_acct = "SpotFxPayable"
    else:
        fin_acct = "Payable"

    # close payable
    ibor_date = settledate
    je = Journals(portfolio, payment_currency, tranid, tradedate,"s", location, fin_acct, local, local,
                      book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin,
                  kdend, ibor_date, "Asset/Liability")
    space.post_journal_entry(je)
    formatted_date = "{}/{}/{}".format(settledate.month, settledate.day, settledate.year)
    fx_rate = get_fx_rate(payment_currency, formatted_date, fx_data)
    #fx_rate =1
    # calculate gl between trade and settle

    glts = book - local * fx_rate
    if glts != 0:
        currglx = Journals( portfolio, payment_currency, 0,0, 'n', location, "FXGainTradeSettle", 0, 0, -glts, None, None, tranid,
                               transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
        space.post_journal_entry(currglx)
        #


    lot_id = 0
    ls = "n"
    financial_account = "Cost"
    # Call open_close_cash
    bookflow = local * fx_rate


    closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(
        payment_currency, -local, -local, -bookflow, location, space)


    if closed_local != 0:  # means there is a balance to close
        curclosebal = Journals(portfolio, payment_currency, 0, 0, 'n',
                                   location, financial_account, -closed_local, -closed_local, -closed_book, 0, 0,tranid,
                                   transaction, tradedate,
                                   settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(curclosebal)

    if opened_local != 0:  # means a balance must be opened
        curopenbal = Journals(portfolio, payment_currency, 0, 0, 'n', location,
                                  "Cost", opened_local, opened_local, opened_book, 0, 0, tranid,
                                  transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(curopenbal)


    gl = proceeds_book - closed_book
    if gl != 0:
        currglx = Journals( portfolio, payment_currency, 0, 0, 'n', location,
                               "FXGainCurrency", 0, 0, -gl, None, None, tranid, transaction,
                               tradedate, settledate, kdbegin, kdend,  ibor_date, "Revenue/Expense/Capital")
        space.post_journal_entry(currglx)
    return



def settle_bond_flows_out(portfolio, payment_currency, investment, location, quantity, local,
                          book, space, tranid, transaction, tradedate, settledate,
                          kdbegin, kdend, smf, accrued_local, accrued_book, fx_data):

    ibor_date = settledate
    je = Journals(portfolio, payment_currency, tranid, tradedate, "s", location, "Payable", local, local,
                  book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    space.post_journal_entry(je)

    if accrued_local != 0:

        je = Journals(portfolio, payment_currency, tranid, tradedate, "s", location, "PurchasedInterestPayable",
                      accrued_local, accrued_local,
                      accrued_book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                      "Asset/Liability")
        space.post_journal_entry(je)

        je = Journals(portfolio, investment, tranid, None, "l", location, "PurchasedInterest", -accrued_local, -accrued_local,
                      -accrued_book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                      "Asset/Liability")
        space.post_journal_entry(je)

        je = Journals(portfolio, payment_currency, tranid, None, "n", location, "AccruedInterestReceivable", accrued_local,
                      accrued_local, accrued_book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                      "Revenue/Expense/Capital")
        space.post_journal_entry(je)

    fx_rate = get_fx_rate(payment_currency, settledate, fx_data)
    # fx_rate =1
    # calculate gl between trade and settle
    tot_book = book + accrued_book
    tot_local = local + accrued_local
    glts = tot_book - tot_local  * fx_rate
    if glts != 0:
        currglx = Journals(portfolio, payment_currency, 0,0, 'n', location, "FXGainTradeSettle", 0, 0, glts,None, None, tranid,
                           transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
        space.post_journal_entry(currglx)



    lot_id = 0
    ls = "n"
    financial_account = "Cost"
    # Call open_close_cash
    bookflow = (local + accrued_local) * fx_rate


    closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(
        payment_currency, -(local+accrued_local), -(local+accrued_local), -bookflow, location, space)

    if closed_local != 0:  # means there is a balance to close
        curclosebal = Journals(portfolio, payment_currency, 0, 0,'n',
                               location, financial_account, -closed_local, -closed_local, -closed_book, 0, 0, tranid,
                               transaction, tradedate,
                               settledate, kdbegin, kdend, ibor_date, "Asset/Liability")

        space.post_journal_entry(curclosebal)

    if opened_local != 0:  # means a balance must be opened
        curopenbal = Journals(portfolio, payment_currency, 0, 0,'n', location,
                              "Cost", opened_local, opened_local, opened_book, 0, 0, tranid,
                              transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(curopenbal)

    gl = proceeds_book - closed_book
    if gl != 0:
        currglx = Journals(portfolio, payment_currency, 0, 0, 'n', location,
                           "FXGainCurrency", 0, 0, -gl, None, None, tranid, transaction,
                           tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
        space.post_journal_entry(currglx)


    # ------------------------------------------------------------------
    # 🚩 FINAL STEP: Remove bond stats ONLY after settlement AND netting= legacy? statacct?
    # ------------------------------------------------------------------
    # if smf.is_fully_settled_and_netted(tranid):
    #     space.statistical_repository.delete_investment(portfolio, investment)


    return

def settle_bond_flows_in(portfolio, payment_currency, investment, location, quantity, local,
                          book,  space, tranid, transaction, tradedate, settledate,
                          kdbegin, kdend, smf, accrued_local, accrued_book, fx_data):

    # close receivable
    ibor_date = settledate
    je = Journals(portfolio, payment_currency, tranid, tradedate,"l", location,  "Receivable", -local, -local,
                  -book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    space.post_journal_entry(je)

    if accrued_local !=0:
        je = Journals(portfolio, payment_currency, tranid, tradedate,"l", location, "SoldInterestReceivable", -accrued_local, -accrued_local,
                      -accrued_book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

        je = Journals(portfolio, investment, tranid, tradedate,"s", location, "SoldInterest", accrued_local, accrued_local,
                      accrued_book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

        je = Journals(portfolio, investment, tranid, settledate, "n", location, "AccruedInterestReceivable", -accrued_local, -accrued_local,
                      -accrued_book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
        space.post_journal_entry(je)

    fx_rate = get_fx_rate(payment_currency, settledate, fx_data)
    # fx_rate =1
    # calculate gl between trade and settle
    tot_book = -(book + accrued_book)
    tot_local = -(local + accrued_local)
    glts = tot_book - tot_local  * fx_rate
    if glts != 0:
        currglx = Journals(portfolio, payment_currency, 0, 0,'n', location, "FXGainTradeSettle", 0, 0, glts,None, None, tranid,
                           transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
        space.post_journal_entry(currglx)

    lot_id = 0
    ls = "n"
    financial_account = "Cost"
    # Call open_close_cash
    bookflow = (local + accrued_local) * fx_rate

    closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(
        payment_currency, local+accrued_local, local+accrued_local, bookflow, location, space)

    if closed_local != 0:  # means there is a balance to close
        curclosebal = Journals(portfolio, payment_currency, 0 ,0, 'n',
                               location, financial_account, -closed_local, -closed_local, -closed_book, 0, 0, tranid,
                               transaction, tradedate,
                               settledate, kdbegin, kdend, ibor_date, "Asset/Liability")

        space.post_journal_entry(curclosebal)

    if opened_local != 0:  # means a balance must be opened
        curopenbal = Journals(portfolio, payment_currency, 0, 0, 'n', location,
                              "Cost", opened_local, opened_local, opened_book, 0, 0, tranid,
                              transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(curopenbal)

    gl = proceeds_book - closed_book
    if gl != 0:
        currglx = Journals(portfolio, payment_currency, 0, 0, 'n', location,
                           "FXGainCurrency", 0, 0, -gl, None, None, tranid, transaction,
                           tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
        space.post_journal_entry(currglx)

    # ------------------------------------------------------------------
    # 🚩 FINAL STEP: Remove bond stats ONLY after settlement AND netting
    # ------------------------------------------------------------------
    if smf.is_fully_settled_and_netted(tranid):
        space.statistical_repository.delete_investment(portfolio, investment)

    return




def settle_multiple_flows_in_out(portfolio, payment_currency,investment, financial_account_in, financial_account_out,
                                  space, tranid, transaction, tradedate, settledate,
                                 kdbegin, kdend, smf, fx_data):


    lots = currency_iterator_by_location_and_flow(payment_currency, space,
                                                  financial_account_in, financial_account_out, tranid)

    for lot in lots:
        # Unpack the lot tuple
        LS, financial_account, location,  local, book = lot


        # Close receivable or payable account
        ibor_date = settledate
        je = Journals(portfolio, payment_currency, tranid, tradedate, LS, location, financial_account, -local, -local,
                          -book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                          "Asset/Liability")
        space.post_journal_entry(je)


        fx_rate = get_fx_rate(payment_currency, settledate, fx_data)
        glts = book - local * fx_rate
        if glts != 0:
            currglx = Journals(portfolio, payment_currency, 0, 0,'n', location,
                                "FXGainTradeSettle", 0, 0, glts,
                                None, None,
                                   tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                                   "Revenue/Expense/Capital")
            space.post_journal_entry(currglx)



        # Call open_close_cash
        bookflow = local * fx_rate

        closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(
            payment_currency, local, local, bookflow, location, space)

        financial_account = "Cost"
        if closed_local != 0:  # means there is a balance to close
            curclosebal = Journals(portfolio, payment_currency, 0,0, 'n',
                                       location, financial_account, -closed_local, -closed_local, -closed_book, 0, 0,
                                       tranid, transaction, tradedate,
                                       settledate, kdbegin, kdend, ibor_date, "Asset/Liability")

            space.post_journal_entry(curclosebal)


        if opened_local != 0:  # means a balance must be opened
            curopenbal = Journals(portfolio, payment_currency, 0,0, 'n', location,
                                      financial_account, opened_local, opened_local, opened_book, 0, 0, tranid,
                                      transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
            space.post_journal_entry(curopenbal)


        gl = proceeds_book - closed_book
        if gl != 0:
            currglx = Journals(portfolio, payment_currency,  0,0, 'n', location,
                                   "FXGainCurrency", 0, 0, -gl, None, None, tranid, transaction,
                                   tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
            space.post_journal_entry(currglx)


    return

def settle_pay_rec_by_tranid(portfolio, investment, location, quantity, local, book, journal_entries,
                             space, tranid, transaction, tradedate, settledate, kdbegin,
                             kdend, payment_currency, smf, fx_data):
    print(f"Processing settlement event for transaction ID: {tranid}")

    # Query receivable balances for the transaction ID
    receivables = space.query_futures_balance(tranid, "Receivable", payment_currency, space)

    # If no receivables found, query payables
    if not receivables:
        payables = space.query_balance_by_tranid(tranid, "Payable", payment_currency)
        entries = payables
        account_type = "Payable"
        ls = "s"
    else:
        entries = receivables
        account_type = "Receivable"
        ls = "l"

    # If no entries are found, handle it appropriately
    if not entries:
        print(f"No receivables or payables found for transaction ID: {tranid}")
    else:
        # Process the balances
        for entry in entries:
            portfolio, investment, lotid, tax_date, ls, location, financial_account, quantity, local, book, notional, oface = entry

            # Close receivable or payable account
            ibor_date = settledate
            je = Journals(
                portfolio, payment_currency, lotid, tax_date, ls, location, account_type,
                -local, -local, -book, 0, 0, tranid, transaction, tradedate, settledate,
                kdbegin, kdend, ibor_date, "Asset/Liability"
            )
            space.post_journal_entry(je)

            # Calculate FX gain/loss
            fx_rate = get_fx_rate(payment_currency, settledate, fx_data)
            glts = book - local * fx_rate
            if glts != 0:
                currglx = Journals(
                    portfolio, payment_currency, lotid, tax_date, 'n', location,
                    "FXGainTradeSettle", 0, 0, glts, None, None, tranid, transaction,
                    tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital"
                )
                space.post_journal_entry(currglx)

            # Call open_close_cash
            bookflow = local * fx_rate
            closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(
                payment_currency, local, local, bookflow, location, space
            )

            # Post balance closure (if applicable)
            financial_account = "Cost"
            if closed_local != 0:  # means there is a balance to close
                curclosebal = Journals(
                    portfolio, payment_currency, 0,0, 'n', location, financial_account,
                    -closed_local, -closed_local, -closed_book, 0, 0, tranid, transaction,
                    tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability"
                )
                space.post_journal_entry(curclosebal)

            # Post balance opening (if applicable)
            if opened_local != 0:  # means a balance must be opened
                curopenbal = Journals(
                    portfolio, payment_currency, 0,0, 'n', location, financial_account,
                    opened_local, opened_local, opened_book, 0, 0, tranid, transaction,
                    tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability"
                )
                space.post_journal_entry(curopenbal)

            # Post FX gain/loss for currency (if applicable)
            gl = proceeds_book - closed_book
            if gl != 0:
                currglx = Journals(
                    portfolio, payment_currency, lotid, tax_date, 'n', location, "FXGainCurrency",
                    0, 0, -gl, None, None, tranid, transaction, tradedate, settledate, kdbegin,
                    kdend, ibor_date, "Revenue/Expense/Capital"
                )
                space.post_journal_entry(currglx)
#================================================
def open_payable(
    portfolio, payment_currency, location,
    local, book, space,
    tranid, transaction, tradedate, settledate,
    kdbegin, kdend,
    financial_account
):
    """Generic payable posting (uses payment_currency as the investment)."""
    investment = payment_currency  # currency is itself an investment

    je = Journals(
        portfolio, investment, tranid, tradedate,
        "s", location, financial_account,
        -local, -local, -book,
        None, None, tranid, transaction,
        tradedate, settledate, kdbegin, kdend, tradedate,
        "Asset/Liability"
    )

    space.post_journal_entry(je)


def open_receivable(
    portfolio, payment_currency, location,
    local, book, space,
    tranid, transaction, tradedate, settledate,
    kdbegin, kdend,
    financial_account
):
    """Generic receivable posting (uses payment_currency as the investment)."""
    investment = payment_currency  # currency is itself an investment

    je = Journals(
        portfolio, investment, tranid, tradedate,
        "l", location, financial_account,
        local, local, book,
        None, None, tranid, transaction,
        tradedate, settledate, kdbegin, kdend, tradedate,
        "Asset/Liability"
    )

    space.post_journal_entry(je)

def deposit_currency(portfolio, payment_currency, location, qty, local, book, bs, tranid, transaction,
            tradedate, settledate, kdbegin, kdend, fx_data):

    # Currency
    lot_id = 0
    ibor_date = tradedate

    # Call open_close_cash
    closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(payment_currency,
                                                                                             local,
                                                                                             local,
                                                                                             book,
                                                                                             location,
                                                                                              bs)

    if closed_local != 0:  # means there is a balance to close
        curclosebal = Journals(portfolio, payment_currency, 0, 0, 'n', location, "Cost", -closed_local, -closed_local,
                            -closed_book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        bs.post_journal_entry(curclosebal)


    if opened_local != 0:  # means a balance must be opened
        curopenbal = Journals( portfolio, payment_currency, 0, 0, 'n', location, "Cost", opened_local, opened_local,
                             opened_book, 0, 0, tranid, transaction,tradedate, settledate, kdbegin, kdend, ibor_date,"Asset/Liability")
        bs.post_journal_entry(curopenbal)


    gl = proceeds_book - closed_book
    if gl != 0:
        currglx = Journals( portfolio, payment_currency, 0, 0,'n', location,
                             "FXGainCurrency", 0, 0, -gl, None, None,
                             tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                            "Revenue/Expense/Capital")
        bs.post_journal_entry(currglx)



        #Capital

    je = Journals(portfolio, payment_currency, tranid, 0, "n", location, "ContributedCost", -qty, -local,
                      -book, 0, 0, tranid,  transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
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
                                                                                                    location,
                                                                                                     bs)

    if closed_local != 0:  # means there is a balance to close
        curclosebal = Journals( portfolio, payment_currency, 0, 0, 'n', location, "Cost", -closed_local, -closed_local,
                             -closed_book, 0, 0, tranid, transaction, tradedate,settledate, kdbegin, kdend, ibor_date,"Asset/Liability")
        bs.post_journal_entry(curclosebal)

    if opened_local != 0:  # means a balance must be opened
        curopenbal = Journals(portfolio, payment_currency, 0, 0, 'n', location, "Cost", opened_local, opened_local,
                         opened_book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        bs.post_journal_entry(curopenbal)

    gl = proceeds_book - closed_book
    if gl != 0:
        currglx = Journals( portfolio, payment_currency, 0, 0, 'n', location, "FXGainCurrency", 0, 0, -gl,
                              None, None, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
        bs.post_journal_entry(currglx)


        # Capital

    je = Journals( portfolio, payment_currency, tranid, 0, "n", location, "ContributedCost", qty, local,
                      book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
    bs.post_journal_entry(je)

def expense(portfolio, payment_currency, location, qty, local, book, financial_account, journal_entries, bs, tranid, transaction,
            tradedate, settledate, kdbegin, kdend):
    # Currency
    lot_id = 0
    ibor_date = tradedate

    je = Journals(portfolio, payment_currency, 0, 0,"n", location, financial_account, 0, local,
                      book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                      "Revenue/Expense/Capital")
    bs.post_journal_entry(je)

    financial_account = "ExpensesPayable"
    je = Journals(portfolio, payment_currency, tranid, tradedate,"s", location, financial_account, -local, -local,
                          -book, 0, 0, tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                          "Asset/Liability")
    bs.post_journal_entry(je)

def spot_fx(portfolio, investment, location, qty, local, book, journal_entries, space, tranid,
               transaction, tradedate, settledate, kdbegin, kdend, buy_currency, sell_currency,
               buy_amt, sell_amt):


    # Case when portfolio currency doesn't match either X or Y
    if buy_currency != "USD" and sell_currency != "USD":
        book = buy_amt *  get_fx_rate(buy_currency, tradedate, main.fx_data)


    # Create receivable for the buy_currency
    ls = "l"
    financial_account = "SpotFxReceivable"
    ibor_date = tradedate
    tax_date = tradedate
    je = Journals(portfolio, buy_currency, tranid, tradedate, ls, location, financial_account, buy_amt, buy_amt,
                      book, None, None,tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                  "Asset/Liability")
    space.post_journal_entry(je)

    ls = "s"
    financial_account = "SpotFxPayable"  # use tranid for payable receivable to close
    je = Journals(portfolio, sell_currency, tranid, tradedate, ls, location, financial_account,
                  -sell_amt, -sell_amt, -book, None, None,
                tranid, transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
    space.post_journal_entry(je)

    return
