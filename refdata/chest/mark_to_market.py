import pandas as pd
import bookkeeping


import utilities
def get_data_and_format(date):
    price_file = "C:/Users/hjmne/PycharmProjects/chest/refdata/price_master.csv"
    fx_file = "C:/Users/hjmne/PycharmProjects/chest/refdata/fx_master.csv"
    price_data = bookkeeping.load_price_data(price_file)
    fx_data = bookkeeping.load_fx_data(fx_file)
    formatted_date = "{}/{}/{}".format(date.month, date.day, date.year)

    return price_data, fx_data, formatted_date

def reverse_old_marks(sub_ledger, date):
    processed_entries = []
    revexp_entries = sub_ledger.get_revenue_expense_entries()

    for journal in revexp_entries:
        # Directly access the properties of the 'Journals' object
        account_key = journal.account_key  # Assuming 'account_key' is a tuple as defined in the class
        account_values = (journal.quantity, journal.local, journal.book)  # Create a tuple or list of account values

        if journal.financial_account == "UnrealGLRevExp":
            # Negate the local and book values
            reversed_local = -journal.local
            reversed_book = -journal.book

            # Instead of appending the original 'entry', create a new representation if needed
            # Or modify the 'journal' object directly if that's appropriate
            processed_journal = journal  # Or create a new object or data structure as needed
            processed_entries.append(processed_journal)  # Add the processed journal to the list

        return processed_entries

from datetime import datetime

#import logging



import cProfile
import pstats
import io
import functools

# # Profiling decorator
# def profile_function(func):
#     @functools.wraps(func)
#     def wrapper_profile_function(*args, **kwargs):

#         result = func(*args, **kwargs)
#         pr.disable()
#         s = io.StringIO()
#         ps = pstats.Stats(pr, stream=s).sort_stats(pstats.SortKey.CUMULATIVE)
#         ps.print_stats()
#         print(s.getvalue())
#         return result
#     return wrapper_profile_function
# @profile_function
import cProfile
import pstats
import io
import pandas as pd
import logging


def mark_to_market(sub_ledger, current_date, fx_rates_df):

    print("mark_to_market called")
    marked_results = []
    priced_investments = []

    for investment, subspace in sub_ledger.asset_liability_repository.investment_spaces_library.items():
        price = subspace.retrieve_price()

        if price is None:
            price = subspace.fetch_and_store_price(investment)

        # Retrieve the currency from the AIF (Accounting Impact Field) of the investment
        currency = sub_ledger.get_investment_attribute('AIF', investment, 'Currency')
        # Get the FX rate for the investment's currency from the global AIF cache
        fx_rate = global_aif.get_fx_rate(currency)

        if price is not None:
            priced_investments.append(investment)
            for entry_key, entry_values in subspace.entries.items():
                portfolio, inv, lotid, tax_date, ls, location, financial_account = entry_key
                quantity, local, book, notional, oface = entry_values

                market_value_local = quantity * price - (notional if notional else 0)
                market_value_book = market_value_local * fx_rate if fx_rate else market_value_local
                price_gain_local = market_value_local - local
                price_gain_book = price_gain_local * fx_rate if fx_rate else price_gain_local
                fx_gain_book = market_value_book - book - price_gain_book

                record_to_add = (
                    entry_key,
                    (quantity, local, book, market_value_local, market_value_book,
                     price_gain_local, price_gain_book, fx_gain_book, price, fx_rate)  # 10 values
                )

                marked_results.append(record_to_add)

    print(f"mark_to_market returning {len(marked_results)} marked results")
    return marked_results, priced_investments

def post_accounting_marks(records_to_mark, date, sub_ledger, tpranid):
    from bookkeeping import Journals
    if isinstance(date, str):
        date = pd.to_datetime(date)
    formatted_date = date.strftime('%Y-%m-%d')

    processed_entries = reverse_old_marks(sub_ledger, date)

    if records_to_mark is None:
        return

    for record in records_to_mark:
        account_key, values_tuple = record

        quantity, local, book, mvlocal, mvbook, price_gain_local, price_gain_book, fx_gain_book, price, fx_rate = values_tuple

        gllocal = mvlocal - local
        glbook = mvbook - book
        totgain = glbook  # Example calculation, adjust as needed
        fxgain = fx_gain_book  # Example, adjust as needed
        investment_type = sub_ledger.get_investment_attribute('AIF', account_key[1], 'Investment_Type')

        fx = mvlocal / mvbook if mvbook != 0 and mvlocal != 0 else 1

        if account_key[-1] in ('Cost', 'Payable', 'Receivable', 'SpotFxReceivable', 'SpotFxPayable', 'ExpensesPayable'):
            derived_key = account_key[:-1] + ("UnrealGLRevExp",)
        else:
            derived_key = None

        if processed_entries is None:
            processed_entries = []

        matching_entry = next((entry for entry in processed_entries if
                               derived_key and entry and derived_key[:2] + derived_key[3:] == entry[0][:2] + entry[0][
                                                                                                             3:] and str(
                                   derived_key[2]) == str(entry[0][2])), None)

        if matching_entry:
            prev_local = matching_entry[1][1]
            prev_book = matching_entry[1][2]
        else:
            prev_local = 0
            prev_book = 0

        net_local = gllocal + prev_local
        net_book = net_local * fx + prev_book if investment_type == "FUTURE" else totgain + prev_book

        tdate = datetime.strptime(formatted_date, '%Y-%m-%d')

        if net_local or net_book:
            markA = Journals(account_key[0], account_key[1], account_key[2], account_key[3], account_key[4], account_key[5],
                             "UnrealGLAsset", quantity, net_local, net_book, None, None, 0, "AcctMark", tdate, tdate, tdate, tdate, tdate, "Asset/Liability")
            sub_ledger.post_journal_entry(markA)

            markB = Journals(account_key[0], account_key[1], account_key[2], account_key[3], account_key[4], account_key[5],
                             "UnrealGLRevExp", 0, -net_local, -net_book, None, None, 0, "AcctMark", tdate, tdate, tdate, tdate, tdate, "Revenue/Expense/Capital")
            sub_ledger.post_journal_entry(markB)

            markC = Journals(account_key[0], account_key[1], account_key[2], account_key[3], account_key[4], account_key[5],
                             "MarketVal", quantity, mvlocal, mvbook, None, None, 0, "ValuationMark", tdate, tdate, tdate, tdate, tdate, "Asset/Liability")
            sub_ledger.post_journal_entry(markC)

            markD = Journals(account_key[0], account_key[1], account_key[2], account_key[3], account_key[4], account_key[5],
                             "PriceGL", 0, gllocal, glbook, None, None, 0, "ValuationMark", tdate, tdate, tdate, tdate, tdate, "Asset/Liability")
            sub_ledger.post_journal_entry(markD)

            markE = Journals(account_key[0], account_key[1], account_key[2], account_key[3], account_key[4], account_key[5],
                             "FXGL", 0, 0, fxgain, None, None, 0, "ValuationMark", tdate, tdate, tdate, tdate, tdate, "Asset/Liability")
            sub_ledger.post_journal_entry(markE)


def reverse_old_marks(sub_ledger, date):
    processed_entries = []
    revexp_entries = sub_ledger.get_revenue_expense_entries()

    for journal in revexp_entries:
        account_key = journal.account_key  # Assuming 'account_key' is a tuple as defined in the class
        account_values = (journal.quantity, journal.local, journal.book)

        if journal.financial_account == "UnrealGLRevExp":
            reversed_local = -journal.local
            reversed_book = -journal.book
            processed_journal = journal
            processed_entries.append(processed_journal)

    return processed_entries

def calculate_marks(tax_lots, sub_ledger, price_data, fx_data, date):
    if isinstance(date, str):
        date = pd.to_datetime(date)
    formatted_date = date.strftime('%Y-%m-%d')

    if tax_lots.empty:
        logging.info("The input DataFrame is empty. No processing will be done.")
        return []

    # Cache the investment space to avoid repetitive lookups
    investment_space_cache = {}

    # Prepare data for vectorized operations
    tickers = tax_lots['investment'].unique()
    data_for_date = price_data.get(formatted_date, {})
    prices = {ticker: data_for_date.get(ticker, {'price': 6.78787, 'currency': 'USD'})['price'] for ticker in tickers}
    currencies = {ticker: data_for_date.get(ticker, {'price': 6.78787, 'currency': 'USD'})['currency'] for ticker in tickers}
    fx_rates = {currency: fx_data.get(formatted_date, {}).get(currency, 1) for currency in set(currencies.values())}

    # Vectorized operations for prices and fx rates
    tax_lots['price'] = tax_lots['investment'].map(prices)
    tax_lots['currency'] = tax_lots['investment'].map(currencies)
    tax_lots['fx_rate'] = tax_lots['currency'].map(fx_rates)

    mark_records = []

    for _, row in tax_lots.iterrows():
        current_investment = row['investment']
        if current_investment not in investment_space_cache:
            investment_space_cache[current_investment] = sub_ledger.asset_liability_repository.get_position_space(current_investment)
        subspace = investment_space_cache[current_investment]

        record_key = (row['portfolio'], row['investment'], row['lotid'], row['tax_date'], row['ls'], row['location'])
        investment_type = subspace.get_attribute_field("AIF", "Investment_Type") if subspace else None
        pricing_factor_str = subspace.get_information_field("AIF", "Pricing_Factor") if subspace else None

        try:
            pricing_factor = float(pricing_factor_str) if pricing_factor_str is not None else 1.0
        except ValueError:
            pricing_factor = 1.0

        ticker = row['investment']
        quantity = row['quantity']
        local = row['local']
        book = row['book']
        notional = row['notional'] if row['notional'] is not None else 0

        price = row['price'] * float(pricing_factor)
        fx_rate = row['fx_rate']

        mkt_val_local = float(price) * quantity - notional if notional != 0 else 0
        mkt_val_book = mkt_val_local * fx_rate
        pgain_local = mkt_val_local - local if investment_type != "FUTURE" else mkt_val_local
        pgain_book = pgain_local * fx_rate
        totgain_book = mkt_val_book - book if investment_type != "FUTURE" else 0

        record_to_add = (
            quantity, local, book, mkt_val_local, mkt_val_book, pgain_local, pgain_book, totgain_book,
            0, date, investment_type)
        mark_records.append((record_key, record_to_add))

    return mark_records

import pandas as pd
from datetime import datetime


def post_performance_marks(records_to_mark,  date, sub_ledger,  tranid):
    if not sub_ledger:
        return
    for record in records_to_mark:
        account_key, (quantity, local, book, calc1, calc2, calc3, calc4, calc5, calc6, formatted_date, investment_type) = record
        # Now continue with your existing code to calculate and post new values for UnrealGLAsset and UnrealGLRevExp
        # Access the individual values
        quantity_value = quantity
        local_value = local
        book_value = book
        mvlocal = calc1
        mvbook = calc2
        gllocal = calc3
        glbook = calc4
        totgain = calc5
        fxgain = calc6

        from datetime import datetime

        # date_str = date
        # format_str = '%m/%d/%y'
        # date_obj = datetime.strptime(date_str, format_str)


        val1 = mvlocal
        val2 = mvbook
        finA = "MktVal"
        finRE = "MktValRE"
        transaction = "PerfMark"


        print(date)
        print(formatted_date)  # Output: 2022-01-03 00:00:00
        formatted_date = datetime.strptime(date, '%m/%d/%Y')
        perf = True
        if quantity != 0:
            markA = bookkeeping.Journals(account_key[0], account_key[1], account_key[2], account_key[3], account_key[4],
                                         account_key[5], finA, 0, val1, val2, None, None,
                                         tranid, transaction, formatted_date, formatted_date,
                                         formatted_date, formatted_date, formatted_date, "Asset/Liability")
            #
            # # Post the journal entry to the bookkeeping space
            sub_ledger.post_journal_entry(markA)

            #  # Create a journal entry using the values

            markB = bookkeeping.Journals(account_key[0], account_key[1], account_key[2], account_key[3],
                                         account_key[4],
                                         account_key[5], finRE, 0, -val1, -val2, None, None,
                                         tranid, transaction, formatted_date, formatted_date,
                                         formatted_date, formatted_date, formatted_date, "Revenue/Expense/Capital")
            sub_ledger.post_journal_entry(markB)


def accounting_mark_logic(period_cutoff, sub_ledger, tranid):
    al = sub_ledger.get_all_asset_liability_bookkeeping_info()
    f1, f2, mark_date = get_data_and_format(period_cutoff)
    df = utilities.convert_to_structure(al, 3)
    marked_records = calculate_marks(df,sub_ledger, f1, f2, mark_date)
    post_accounting_marks(marked_records, mark_date, sub_ledger, tranid)
    pass

def performance_mark_logic(period_cutoff, sub_ledger, tranid):
    al = sub_ledger.get_all_asset_liability_bookkeeping_info()
    f1, f2, mark_date = get_data_and_format(period_cutoff)
    df = utilities.convert_to_structure(al, 3)
    marked_records = calculate_marks(df, sub_ledger, f1, f2, mark_date)
    post_performance_marks(marked_records, mark_date, sub_ledger, tranid)
