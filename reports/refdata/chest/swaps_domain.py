from bookkeeping import Journals, Bookkeeping, Event, RevenueExpenseCapitalRepository, append_if_valid_date
import currency_domain
import datetime
sub_ledger = Bookkeeping()
revenue_expense_repository = RevenueExpenseCapitalRepository()
bs = sub_ledger
je = Journals()
import heapq
journal_entries = []
def swap_open(portfolio, investment, location, quantity, local, book, journal_entries, sub_ledger, tranid, transaction,
               tradedate, settledate, kdbegin, kdend, payment_currency, period_start, leg1, leg2):

    ibor_date = tradedate
    tax_date = tradedate

    legs = [leg1, leg2]

    for leg in legs:
        if leg == leg1:
            ls = "l"
            leg_investment = leg1
            leg_quantity = quantity
            leg_local = local
            leg_book = book

        elif leg == leg2:
            leg_investment = leg2
            ls = "s"
            leg_quantity = -local
            leg_local = -local
            leg_book = -book



        je = Journals(portfolio, leg_investment, tax_date, ls, location, "Notional", leg_quantity, leg_local, leg_book, tranid,
                          transaction, tradedate, settledate, None, None, ibor_date, "Asset/Liability")
        investment_accounting_space.post_journal_entry(je)
        if ibor_date >= period_start:
            journal_entries.append(je)

    # XYZSwap Entry
    ls = "l"  # Assuming a long position for the swap contract itself
    je = Journals(portfolio, investment, tax_date, ls, location, "Cost", 1, 0, 0, tranid,
                      transaction, tradedate, settledate, None, None, ibor_date, "Asset/Liability")
    investment_accounting_space.post_journal_entry(je)
    

   
    return


