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
       # print(f"[ITER CHECK] key={entry[0]} vals={entry[1]}")
        entry_data = entry[0]
        if entry_data[1] == investment and entry_data[5] in [financial_account_in, financial_account_out] and entry_data[2] == tranid:
            lots.append((entry_data[3], entry_data[5], entry_data[4], entry[1][1],
                         entry[1][2]))  # Append location,financial_account, LS, local, and book amounts
            # Append the location and LS values directly
    return lots

def bond_coupon_settle(portfolio, investment, space, tranid,
                       transaction, tradedate, settledate,
                       kdbegin, kdend, payment_currency, fx_pay):
    """
    Coupon pay-date settlement. Settles what was BOOKED: reads the
    InterestReceivable/Payable balance the ex-date posting created
    and washes it at its booked value. No recomputation -- the
    receivable is the fact; entitlement may have moved since ex
    date but the issuer pays the ex-date holders, and the booked
    claim carries that truth.

      wash claim at booked value (embodies the ex rate)
      cash at pay-date rate via open_close_cash
      FX G/L = local * fx_pay - booked book   (ex-to-pay lag)

    Same-day coupon: fx_pay equals the booking rate, G/L is zero
    by construction.
    """
    ibor_date = settledate
    repo = space.asset_liability_repository

    # ── READ the due balances created on ex date ──────────────────
    DUE_ACCOUNTS = ("InterestReceivable", "InterestPayable")
    due_bal = {}  # (location, ls, fa) -> [local, book]
    subspace = repo.get_position_space(payment_currency)
    if subspace is None:
        print(f"COUPON SETTLE: no subspace for {payment_currency}; "
              f"nothing to wash.")
        return
    for key, (qty, local, book, notional, oface) in subspace.entries.items():
        (_, inv, lotid, tax_date, ls_k, loc_k, fa) = key
        if fa in DUE_ACCOUNTS and (local != 0 or book != 0):
            k = (loc_k, ls_k, fa)
            if k not in due_bal:
                due_bal[k] = [0.0, 0.0]
            due_bal[k][0] += local
            due_bal[k][1] += book

    if not due_bal:
        print(f"COUPON SETTLE: {portfolio}/{payment_currency} "
              f"{settledate} -- no due interest balances to wash.")
        return

    for (location, ls, fa), (bal_local, bal_book) in due_bal.items():

        # 1. Wash the claim at its booked value.
        wash = Journals(portfolio, payment_currency, 0, 0,
                        ls, location, fa,
                        -bal_local, -bal_local, -bal_book,
                        None, None, tranid,
                        "Settlement", tradedate, settledate,
                        kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(wash)

        # 2. Cash at the pay-date rate (open_close_cash: caller-
        #    owned sign -- register note applies).
        cash_book = bal_local * fx_pay
        closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(
            payment_currency, bal_local, bal_local,
            cash_book, location, space)

        if closed_local != 0:
            curclosebal = Journals(portfolio, payment_currency, 0, 0, 'n', location,
                                   "Cost", -closed_local, -closed_local, -closed_book,
                                   0, 0, tranid, "Settlement", tradedate, settledate,
                                   kdbegin, kdend, ibor_date, "Asset/Liability")
            space.post_journal_entry(curclosebal)

        if opened_local != 0:
            curopenbal = Journals(portfolio, payment_currency, 0, 0, 'n', location,
                                  "Cost", opened_local, opened_local, opened_book,
                                  0, 0, tranid, "Settlement", tradedate, settledate,
                                  kdbegin, kdend, ibor_date, "Asset/Liability")
            space.post_journal_entry(curopenbal)

        glc = proceeds_book - closed_book
        if glc != 0:
            currglx = Journals(portfolio, payment_currency, 0, 0, 'n', location,
                               "FXGainCurrency", 0, 0, -glc, None, None,
                               tranid, "Settlement", tradedate, settledate,
                               kdbegin, kdend, ibor_date,
                               "Revenue/Expense/Capital")
            space.post_journal_entry(currglx)

        # 3. Ex-to-pay FX G/L: cash received vs claim's booked value.
        fxgl = cash_book - bal_book
        if fxgl != 0:
            couponfx = Journals(portfolio, payment_currency, 0, 0,
                                ls, location, "FXGainTradeSettle",
                                0, 0, -fxgl, None, None,
                                tranid, "Settlement", tradedate, settledate,
                                kdbegin, kdend, ibor_date,
                                "Revenue/Expense/Capital")
            space.post_journal_entry(couponfx)

    return


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
                          kdbegin, kdend, af, accrued_local, accrued_book, fx_data, ls="l"):
    # Resolve position-dependent account name once. l/s on the JEs carries the
    # position context; the COA does not distinguish direction (no account
    # proliferation -- lessons from Geneva). The only account that swaps is
    # the accrued-interest account, because asset-vs-liability is structural.
    if ls == "l":
        accrual_account = "AccruedInterestReceivable"
    else:
        accrual_account = "AccruedInterestPayable"

    ibor_date = settledate  # close total payable including accrued

    # Trade-pending obligation. ls on this JE is identity-keyed (tranid + ls)
    # so settlement can do a direct match without iteration.
    je = Journals(portfolio, payment_currency, tranid, tranid, ls, location, "Payable",
                  local + accrued_local, accrued_local + local,
                  accrued_book + book, 0, 0, tranid, transaction, tradedate, settledate,
                  kdbegin, kdend, ibor_date, "Asset/Liability")
    space.post_journal_entry(je)

    if accrued_local != 0:
        # Phase-1 -> Phase-3 reclass for the interest portion.
        # PurchasedInterest serves both buy-long and cover-short; ls carries
        # the position direction.
        je = Journals(portfolio, investment, tranid, tradedate, ls, location, "PurchasedInterest",
                      -accrued_local, -accrued_local,
                      -accrued_book, 0, 0, tranid, transaction, tradedate, settledate,
                      kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

        # Open the active accrual that will close at coupon.
        # Account swaps Receivable/Payable on ls (resolved above); ls on the JE
        # carries position direction.
        je = Journals(portfolio, investment, 0,None, ls, location, accrual_account,
                      accrued_local, accrued_local,
                      accrued_book, 0, 0, tranid, transaction, tradedate, settledate,
                      kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

    fx_rate = get_fx_rate(payment_currency, settledate, fx_data)
    # fx_rate = 1
    # calculate gl between trade and settle
    tot_book = book + accrued_book
    tot_local = local + accrued_local
    glts = tot_book - (tot_local * fx_rate)
    if glts != 0:
        currglx = Journals(portfolio, payment_currency, 0, 0, 'n', location, "FXGainTradeSettle",
                           0, 0, glts, None, None, tranid,
                           transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                           "Revenue/Expense/Capital")
        space.post_journal_entry(currglx)

    lot_id = 0
    financial_account = "Cost"
    # bookflow is a magnitude; sign is applied at the open_close_cash call.
    bookflow = (local + accrued_local) * fx_rate

    closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(
        payment_currency, -(local + accrued_local), -(local + accrued_local), -bookflow, location, space)

    if closed_local != 0:  # means there is a balance to close
        curclosebal = Journals(portfolio, payment_currency, 0, 0, 'n',
                               location, financial_account, -closed_local, -closed_local, -closed_book,
                               0, 0, tranid, transaction, tradedate,
                               settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(curclosebal)

    if opened_local != 0:  # means a balance must be opened
        curopenbal = Journals(portfolio, payment_currency, 0, 0, 'n', location,
                              "Cost", opened_local, opened_local, opened_book, 0, 0, tranid,
                              transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                              "Asset/Liability")
        space.post_journal_entry(curopenbal)

    gl = proceeds_book - closed_book
    if gl != 0:
        currglx = Journals(portfolio, payment_currency, 0, 0, 'n', location,
                           "FXGainCurrency", 0, 0, -gl, None, None, tranid, transaction,
                           tradedate, settledate, kdbegin, kdend, ibor_date,
                           "Revenue/Expense/Capital")
        space.post_journal_entry(currglx)

    # ------------------------------------------------------------------
    # FINAL STEP: Remove bond stats ONLY after settlement AND netting= legacy? statacct?
    # ------------------------------------------------------------------
    # if af.is_fully_settled_and_netted(tranid):
    #     space.statistical_repository.delete_investment(portfolio, investment)

    return


def settle_bond_flows_in(portfolio, payment_currency, investment, location, quantity, local,
                         book, space, tranid, transaction, tradedate, settledate,
                         kdbegin, kdend, af, accrued_local, accrued_book, fx_data, ls="l"):
    # Resolve position-dependent account name once. l/s on the JEs carries the
    # position context; the COA does not distinguish direction (no account
    # proliferation -- lessons from Geneva). The only account that swaps is
    # the accrued-interest account, because asset-vs-liability is structural.
    if ls == "l":
        accrual_account = "AccruedInterestReceivable"
    else:
        accrual_account = "AccruedInterestPayable"

    ibor_date = settledate

    # Trade-pending claim. ls on this JE is identity-keyed (tranid + ls)
    # so settlement can do a direct match without iteration.
    je = Journals(portfolio, payment_currency, tranid, tranid, ls, location, "Receivable",
                  -accrued_local + -local, -accrued_local + -local,
                  -accrued_book + -book, 0, 0, tranid, transaction, tradedate, settledate,
                  kdbegin, kdend, ibor_date, "Asset/Liability")
    space.post_journal_entry(je)

    if accrued_local != 0:
        # Phase-1 -> Phase-3 reclass for the interest portion.
        # SoldInterest serves both sell-long and short-open; ls carries
        # the position direction.
        je = Journals(portfolio, investment, tranid, tradedate, ls, location, "SoldInterest",
                      accrued_local, accrued_local,
                      accrued_book, 0, 0, tranid, transaction, tradedate, settledate,
                      kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

        # Reduce active accrual (long sell relieves receivable) or open one
        # on the payable side (short open). Account name resolved above;
        # ls on the JE carries position direction.
        je = Journals(portfolio, investment, 0, None, ls, location, accrual_account,
                      -accrued_local, -accrued_local,
                      -accrued_book, 0, 0, tranid, transaction, tradedate, settledate,
                      kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(je)

    fx_rate = get_fx_rate(payment_currency, settledate, fx_data)
    # fx_rate = 1
    # calculate gl between trade and settle
    tot_book = -(book + accrued_book)
    tot_local = -(local + accrued_local)
    glts = tot_book - (tot_local * fx_rate)
    if glts != 0:
        currglx = Journals(portfolio, payment_currency, 0, 0, 'n', location, "FXGainTradeSettle",
                           0, 0, glts, None, None, tranid,
                           transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                           "Revenue/Expense/Capital")
        space.post_journal_entry(currglx)

    lot_id = 0
    financial_account = "Cost"
    # bookflow is a magnitude; sign is applied at the open_close_cash call.
    bookflow = (local + accrued_local) * fx_rate

    closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(
        payment_currency, local + accrued_local, local + accrued_local, bookflow, location, space)

    if closed_local != 0:  # means there is a balance to close
        curclosebal = Journals(portfolio, payment_currency, 0, 0, 'n',
                               location, financial_account, -closed_local, -closed_local, -closed_book,
                               0, 0, tranid, transaction, tradedate,
                               settledate, kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(curclosebal)

    if opened_local != 0:  # means a balance must be opened
        curopenbal = Journals(portfolio, payment_currency, 0, 0, 'n', location,
                              "Cost", opened_local, opened_local, opened_book, 0, 0, tranid,
                              transaction, tradedate, settledate, kdbegin, kdend, ibor_date,
                              "Asset/Liability")
        space.post_journal_entry(curopenbal)

    gl = proceeds_book - closed_book
    if gl != 0:
        currglx = Journals(portfolio, payment_currency, 0, 0, 'n', location,
                           "FXGainCurrency", 0, 0, -gl, None, None, tranid, transaction,
                           tradedate, settledate, kdbegin, kdend, ibor_date,
                           "Revenue/Expense/Capital")
        space.post_journal_entry(currglx)

    # ------------------------------------------------------------------
    # FINAL STEP: Remove bond stats ONLY after settlement AND netting
    # ------------------------------------------------------------------
    # if af.is_fully_settled_and_netted(tranid):
    #     space.statistical_repository.delete_investment(portfolio, investment)

    return

def settle_multiple_flows_in_out(portfolio, payment_currency,investment, financial_account_in, financial_account_out,
                                  space, tranid, transaction, tradedate, settledate,
                                 kdbegin, kdend, af, fx_data):


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

def settle_pay_rec_by_tranid(portfolio, investment, location, quantity, local, book,
                             space, tranid, transaction, tradedate, settledate, kdbegin,
                             kdend, payment_currency, af, fx_data):
    print(f"Processing settlement event for transaction ID: {tranid}")

    # Query receivable balances for the transaction ID
    receivables = space.query_futures_balance(tranid, "Receivable", payment_currency)

    # If no receivables found, query payables
    if not receivables:
        payables = space.query_futures_balance(tranid, "Payable", payment_currency)
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

def cash_payment_same_day(portfolio, payment_currency, location,
                          quantity, local, book, space, tranid,
                          transaction, tradedate, settledate,
                          kdbegin, kdend):
    """
    Same-day-settling trade payment: cash pays directly on trade
    date. No Payable is opened and no settlement flow follows --
    the trade's cash lifecycle begins and ends here.

    Posting pattern is the standard currency open/close:
      - close existing cash balance (Cost on currency, ls 'n')
      - open the resulting balance if the payment overdraws
      - FXGainCurrency for the book difference on the closed
        balance (zero for base currency by construction; zero
        trade-to-settle FX component by construction, since trade
        FX and settle FX are the same rate on the same day --
        any G/L here is realized FX on the cash holding itself)

    Scheduled on tradedate (== settledate) by the hub when the two
    dates are equal. The multi-day path (open_payable +
    settle_single_flow_out) is unchanged for all later-settling
    trades.
    """
    from bookkeeping import Journals

    lot_id = 0
    ibor_date = tradedate
    bs = space

    closed_local, closed_book, proceeds, proceeds_book, opened_local, opened_book = open_close_cash(
        payment_currency, local, local, book, location, bs)

    if closed_local != 0:  # balance to close
        curclosebal = Journals(portfolio, payment_currency, 0, 0, 'n', location,
                               "Cost", -closed_local, -closed_local, -closed_book,
                               0, 0, tranid, transaction, tradedate, settledate,
                               kdbegin, kdend, ibor_date, "Asset/Liability")
        bs.post_journal_entry(curclosebal)

    if opened_local != 0:  # balance must be opened
        curopenbal = Journals(portfolio, payment_currency, 0, 0, 'n', location,
                              "Cost", opened_local, opened_local, opened_book,
                              0, 0, tranid, transaction, tradedate, settledate,
                              kdbegin, kdend, ibor_date, "Asset/Liability")
        bs.post_journal_entry(curopenbal)

    gl = proceeds_book - closed_book
    if gl != 0:
        currglx = Journals(portfolio, payment_currency, 0, 0, 'n', location,
                           "FXGainCurrency", 0, 0, -gl, None, None,
                           tranid, transaction, tradedate, settledate,
                           kdbegin, kdend, ibor_date,
                           "Revenue/Expense/Capital")
        bs.post_journal_entry(currglx)

def deposit_currency(portfolio, payment_currency, location, qty, local, book, bs, tranid, transaction,
            tradedate, settledate, kdbegin, kdend, fx_data):


        #Capital
    ibor_date = tradedate
    je = Journals(portfolio, payment_currency, tranid, 0, "n", location, "ContributedCost", -qty, -local,
                      -book, 0, 0, tranid,  transaction, tradedate, settledate, kdbegin, kdend, ibor_date, "Revenue/Expense/Capital")
    bs.post_journal_entry(je)



def withdraw_currency(portfolio, payment_currency, location, qty, local, book, bs, tranid, transaction,
             tradedate, settledate, kdbegin, kdend, fx_data):
    # Create a new je Open IBM

    ibor_date = tradedate
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
