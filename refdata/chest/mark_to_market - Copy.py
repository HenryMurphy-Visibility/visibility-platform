import pandas as pd
import bookkeeping
import utilities
import logging
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

import cProfile
import pstats
import io
import datetime


pr = cProfile.Profile()
pr.enable()


def calculate_marks(tax_lots,sub_ledger, price_data, fx_data, date):
#    mark_date = parse_datetime(date)
    if tax_lots.empty:
        logging.info("The input DataFrame is empty. No processing will be done.")
        return []

    required_columns = {'portfolio', 'investment', 'lotid', 'tax_date', 'ls', 'location', 'quantity', 'local', 'book'}
    if not required_columns.issubset(tax_lots.columns):
        raise KeyError(f"DataFrame is missing one or more required columns: {required_columns - set(tax_lots.columns)}")

    mark_records = []
    current_investment = None
    subspace = None



    for _, row in tax_lots.iterrows():
        if row['investment'] != current_investment:
            current_investment = row['investment']
            subspace = sub_ledger.get_position_space(row['investment'])

        record_key = (row['portfolio'], row['investment'], row['lotid'], row['tax_date'], row['ls'], row['location'])
        investment_type = subspace.get_attribute_field("AIF", "Investment_Type") if subspace else None
        pricing_factor = subspace.get_attribute_field("AIF", "Pricing_Factor") if subspace else 1.0
        pricing_factor = float(pricing_factor) if pricing_factor is not None else 1.0

        ticker = row['investment']
        quantity = row['quantity']
        local = row['local']
        book = row['book']
        notional = row['notional'] if row['notional'] is not None else 0.0

        # if isinstance(mark_date, datetime):
        #     formatted_date = f"{mark_date.month}/{mark_date.day}/{mark_date.year}"
        # else:
      #  formatted_date = date.strftime('%Y-%m-%d')

        if not pricing_factor:
            pricing_factor = 1

        data_for_date = price_data.get(date, {})
        price_data_filtered = data_for_date.get(ticker, {})
        price = price_data_filtered.get('price', 6.78787) * float(pricing_factor)  # Set price to default if None
        currency = price_data_filtered.get('currency', "USD")  # Set currency to "USD" if None

        fx_rate = fx_data.get(date, {}).get(currency, 1)

        logging.debug(
            f"Date: {date}, Investment: {row['investment']}, Price: {price}, Currency: {currency}, FX Rate: {fx_rate}")

        # Ensure all values are floats before performing arithmetic operations
        mkt_val_local = float(price) * float(quantity) - float(notional)
     #   mkt_val_local = price * row['quantity'] - row['notional']
        mkt_val_book = mkt_val_local * fx_rate
        pgain_local = mkt_val_local - row['local'] if investment_type != "FUTURE" else mkt_val_local
        pgain_book = pgain_local * fx_rate
        totgain_book = mkt_val_book - row['book'] if investment_type != "FUTURE" else 0

        record_to_add = (
            row['quantity'], row['local'], row['book'], mkt_val_local, mkt_val_book, pgain_local, pgain_book,
            totgain_book,
            0, date, investment_type)  # fx_gain is set to 0 and not calculated here
        mark_records.append((record_key, record_to_add))



    return mark_records
pr.disable()
s = io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats(pstats.SortKey.CUMULATIVE)
ps.print_stats()
print(s.getvalue())

def post_accounting_marks(records_to_mark, date, sub_ledger):
    # 1. Reverse previous unrealized GL assets
    processed_entries = reverse_old_marks(sub_ledger, date)

    # # 2. Get new mark data
    # price_file = "C:/Users/hjmne/PycharmProjects/chest/refdata/price_master.csv"
    # fx_file = "C:/Users/hjmne/PycharmProjects/chest/refdata/fx_master.csv"
    # price_data = bookkeeping.load_price_data(price_file)
    # fx_data = bookkeeping.load_fx_data(fx_file)
    # formatted_date = "{}/{}/{}".format(date.month, date.day, date.year)

    if records_to_mark is None:
        return  # Exit the function early since there are no records to mark

    # 3. Apply the new marks and net them with the reversed marks if they exist
    for record in records_to_mark:
        account_key, (quantity, local, book, *additional_data) = record
        quantity_value = quantity
        local_value = local
        book_value = book

        # Additional data is now stored in a list named 'additional_data'.
        # You can access individual elements using indexing.
        mvlocal = additional_data[0]
        mvbook = additional_data[1]
        gllocal = additional_data[2]
        glbook = additional_data[3]
        totgain = additional_data[4]
        fxgain = additional_data[5]

        # Take the first 5 or 6 elements of account_key, based on your requirement
        first_six_of_account_key = account_key[:7]

        if account_key[-1] in ('Cost'or 'Payable'or 'Receivable'or 'SpotFxReceivable'or 'SpotFxPayable'or 'ExpensesPayable'):
            derived_key = account_key[:-1] + ("UnrealGLRevExp",)
        else:
            derived_key = None  # This ensures derived_key is defined even if the condition isn't met

        # Attempt to find a matching entry in processed_entries
        # Ensure processed_entries is not None
        if processed_entries is None:
            processed_entries = []
        matching_entry = next((entry for entry in processed_entries if
                               derived_key and entry and derived_key[:2] + derived_key[3:] == entry[0][:2] + entry[0][
                                                                                                             3:] and str(
                                   derived_key[2]) == str(entry[0][2])), None)
        # Check if a matching entry was found
        if matching_entry:
            prev_local = matching_entry[1][1]
            prev_book = matching_entry[1][2]
        else:
            prev_local = 0
            prev_book = 0

        net_local = gllocal + prev_local
        net_book = glbook
        fx_book = totgain - net_book
        from datetime import datetime
        date_str = date  # Example date string
        date_format = '%m/%d/%Y'  # Date format: month/day/year

        # Parse the date string into a datetime object
        tdate = datetime.strptime(date_str, date_format)

        # Only post the entry if net values are different from zero
        if net_local or net_book:
            markA = bookkeeping.Journals(account_key[0], account_key[1], account_key[2], account_key[3], account_key[4],
                                         account_key[5],"UnrealPriceGL", 0, net_local, net_book,
                                         None,None, 0, "AcctMark", tdate, tdate, tdate, tdate, tdate, "Asset/Liability")
            sub_ledger.post_journal_entry(markA)

            markA = bookkeeping.Journals(account_key[0], account_key[1], account_key[2], account_key[3], account_key[4],
                                         account_key[5], "UnrealFXGL", 0, 0, fx_book,
                                         None, None, 0, "AcctMark", tdate,
                                         tdate, tdate, tdate, tdate, "Asset/Liability")
            sub_ledger.post_journal_entry(markA)

            markB = bookkeeping.Journals(account_key[0], account_key[1], account_key[2], account_key[3], account_key[4],
                                         account_key[5],"UnrealGLRevExp", 0, -net_local,
                                         -net_book - fx_book, None, None, 0,"AcctMark",
                                         tdate, tdate, tdate, tdate, tdate, "Revenue/Expense/Capital")
            sub_ledger.post_journal_entry(markB)

def post_performance_marks(records_to_mark,  date, sub_ledger,  tranid):
    if not sub_ledger:
        return
    for record in records_to_mark:
        account_key, (quantity, local, book, calc1, calc2, calc3, calc4, calc5, calc6, formatted_date) = record
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

        if quantity != 0:
            markA = bookkeeping.Journals(account_key[0], account_key[1], account_key[2], account_key[3], account_key[4],
                                         account_key[5],  finA, 0, val1, val2,None,None,
                                         tranid, transaction, formatted_date, formatted_date,
                                         formatted_date, formatted_date, formatted_date, "Asset/Liability")
            #
            # # Post the journal entry to the bookkeeping space
            sub_ledger.post_journal_entry(markA)

            #  # Create a journal entry using the values

            markB = bookkeeping.Journals(account_key[0], account_key[1], account_key[2], account_key[3],
                                         account_key[4],   account_key[5],
                             finRE, 0,
                             -val1, -val2, None, None, tranid, transaction, formatted_date, formatted_date,
                                                                    formatted_date, formatted_date, formatted_date,
                             "Revenue/Expense/Capital")
            #
            sub_ledger.post_journal_entry(markB)

#
# import cProfile
# import pstats
# import io
#
# def profile_function(func, *args, **kwargs):
#     pr = cProfile.Profile()
#     pr.enable()
#     result = func(*args, **kwargs)
#     pr.disable()
#     s = io.StringIO()
#     ps = pstats.Stats(pr, stream=s).sort_stats(pstats.SortKey.CUMULATIVE)
#     ps.print_stats()
#     print(s.getvalue())
#     return result
#
# def accounting_mark_logic(period_cutoff, sub_ledger, tranid):
#     al = profile_function(sub_ledger.all_asset_liability_bookkeeping_accounts_info)
#     f1, f2, mark_date = profile_function(get_data_and_format, period_cutoff)
#     df = profile_function(utilities.convert_to_structure, al, 3)
#     marked_records = profile_function(calculate_marks, df, sub_ledger, f1, f2, mark_date)
#     profile_function(post_accounting_marks, marked_records, mark_date, sub_ledger, tranid)
#     pass
def accounting_mark_logic(period_cutoff, sub_ledger):
    al = sub_ledger.all_asset_liability_bookkeeping_accounts_info()
    f1, f2, mark_date = get_data_and_format(period_cutoff)
    df = utilities.convert_to_structure(al, 3)
    marked_records = calculate_marks(df,sub_ledger, f1, f2, mark_date)
    post_accounting_marks(marked_records, mark_date, sub_ledger)
    pass


def performance_mark_logic(period_cutoff, sub_ledger, tranid):
    al = sub_ledger.all_asset_liability_bookkeeping_accounts_info()
    f1, f2, mark_date = get_data_and_format(period_cutoff)
    df = utilities.convert_to_structure(al, 3)
    marked_records = calculate_marks(df, al, f1, f2, mark_date)
    post_performance_marks(marked_records, mark_date, sub_ledger, tranid)
