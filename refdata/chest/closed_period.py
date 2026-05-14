import pickle
import os
from datetime import datetime, timedelta
from bookkeeping import Journals, SpaceManager
import main
import copy
import time
import report
import bigaccounting
import performance

space_manager = SpaceManager()
BASE_DIR = "C:/Users/hjmne/PycharmProjects/chest/periods"

# Helper Functions
def store_journals_as_pickle(journals, file_path):
    """Store journals using pickle to maintain Python object structure."""
    with open(file_path, "wb") as file:
        pickle.dump(journals, file)

def load_journals_from_pickle(file_path):
    """Load journals using pickle."""
    if os.path.exists(file_path):
        with open(file_path, "rb") as file:
            return pickle.load(file)
    return []

import os
import json
from datetime import datetime

import os
import pickle

import os
import pickle
import os
import pickle

import os
import pickle
import os
import pickle

def combine_je_files(fund):
    """Combine journal entries from all pickle files (adjusting and current) for a given fund, sorted by journal type and sequence number."""
    base_directory = f'C:/Users/hjmne/PycharmProjects/chest/funds/{fund}/periods'

    # Get a list of period directories sorted by numerical order
    period_directories = sorted(
        [d for d in os.listdir(base_directory) if os.path.isdir(os.path.join(base_directory, d))],
        key=lambda x: int(x)  # Sort by directory name as integer
    )

    combined_journals = []

    # Read and combine the journals from each period directory
    for period_dir in period_directories:
        period_path = os.path.join(base_directory, period_dir)

        # Collect all pickle files in the directory, sorted to ensure adjusting journals come first
        all_files = sorted(
            [os.path.join(period_path, f) for f in os.listdir(period_path) if f.endswith('.pkl')],
            key=lambda x: 'adjusting' not in x  # False (adjusting) comes before True (current)
        )

        for path in all_files:
            try:
                with open(path, 'rb') as f:
                    journals = pickle.load(f)
                    combined_journals.extend(journals)
            except FileNotFoundError:
                print(f"File {path} not found, skipping.")
            except pickle.UnpicklingError:
                print(f"Error unpickling file {path}, skipping.")

    # Sort the combined journals by period, journal type, and by sequence number
    combined_journals.sort(key=lambda je: (int(je.period), je.journal_type == 'current'))

    # Assign sequence numbers in the exact order of the sorted list
    Journals.sequence_counter = 0  # Reset sequence counter for consistent ordering
    for je in combined_journals:
        je.sequence_number = Journals.sequence_counter
        Journals.sequence_counter += 1

    return combined_journals

def ensure_sequence_number(journals):
    """Ensure all Journals objects have a sequence_number."""
    for je in journals:
        if not hasattr(je, 'sequence_number'):
            je.sequence_number = Journals.sequence_counter
            Journals.sequence_counter += 1
    return journals

def create_adjustment_records(journals_A, journals_B):
    """Create adjustment records from two sets of journals."""
    adjustments = []
    dict_A = {
        (entry.portfolio, entry.investment, entry.tax_date, entry.ls, entry.location, entry.financial_account): entry
        for entry in journals_A}
    dict_B = {
        (entry.portfolio, entry.investment, entry.tax_date, entry.ls, entry.location, entry.financial_account): entry
        for entry in journals_B}

    keys_only_in_A = set(dict_A.keys()) - set(dict_B.keys())
    keys_only_in_B = set(dict_B.keys()) - set(dict_A.keys())
    common_keys = set(dict_A.keys()).intersection(set(dict_B.keys()))

    for key in keys_only_in_A:
        adjusted_entry = copy.copy(dict_A[key])
        adjusted_entry.quantity = -dict_A[key].quantity
        adjusted_entry.local = -dict_A[key].local
        adjusted_entry.book = -dict_A[key].book
        adjustments.append(adjusted_entry)

    for key in keys_only_in_B:
        adjustments.append(dict_B[key])

    for key in common_keys:
        entry_from = dict_A[key]
        entry_to = dict_B[key]
        if entry_from.quantity != entry_to.quantity or entry_from.local != entry_to.local or entry_from.book != entry_to.book:
            delta_record = copy.copy(entry_from)
            delta_record.quantity = (entry_to.quantity or 0) - (entry_from.quantity or 0)
            delta_record.local = entry_to.local - entry_from.local
            delta_record.book = entry_to.book - entry_from.book
            adjustments.append(delta_record)

    return adjustments

def process_closed_periods_mode(space_manager, portfolio_name, process_start_date, smf, scheduler, stat_repo, price_data, fx_data,
                                mark_daily, aggregate_marks, include_marks, tdate_fx):
    input_records_file_path = f'C:/Users/hjmne/PycharmProjects/chest/configs/inputs{portfolio_name}.txt'
    with open(input_records_file_path, 'r') as file:
        input_records = [json.loads(line) for line in file]

    for record in input_records:
        current_period_start = datetime.strptime(record["current_period_start"], "%Y-%m-%d:%H:%M:%S")
        current_period_cutoff = datetime.strptime(record["current_period_cutoff"], "%Y-%m-%d:%H:%M:%S")
        current_period_knowledge = datetime.strptime(record["current_period_knowledge"], "%Y-%m-%d:%H:%M:%S")
        prior_period_start = datetime.strptime(record["prior_period_start"], "%Y-%m-%d:%H:%M:%S")
        prior_period_cutoff = datetime.strptime(record["prior_period_cutoff"], "%Y-%m-%d:%H:%M:%S")
        prior_period_knowledge = datetime.strptime(record["prior_period_knowledge"], "%Y-%m-%d:%H:%M:%S")
        period_name = record["period_name"]
        fund = record["selected_fund"]

        # Process events with prior period knowledge
        sub_ledger = space_manager.get_space('sub_ledger')
        space_manager.clear_space('sub_ledger')
        main.process_events(space_manager, "", fund, process_start_date, prior_period_start, prior_period_cutoff,
                            prior_period_knowledge, sub_ledger.journal_entries, sub_ledger, "", tdate_fx, scheduler,
                            stat_repo, price_data, fx_data, mark_daily, aggregate_marks, include_marks)

        prior_period_journals_not_adjusted = sub_ledger.journal_entries
        filtered_journals = [entry for entry in prior_period_journals_not_adjusted if
                             entry.ibor_date <= prior_period_cutoff]
        store_journals_as_pickle(filtered_journals,
                                 f"C:/Users/hjmne/PycharmProjects/chest/funds/{fund}/periods/prior_period_journals_not_adjusted.pkl")

        # Process events with current period knowledge
        sub_ledger = space_manager.get_space('sub_ledger')
        space_manager.clear_space('sub_ledger')
        main.process_events(space_manager, "", fund, process_start_date, prior_period_start, prior_period_cutoff,
                            current_period_knowledge, sub_ledger.journal_entries, sub_ledger, "", tdate_fx, scheduler,
                            stat_repo, price_data, fx_data, mark_daily, aggregate_marks, include_marks)

        prior_period_journals_adjusted = sub_ledger.journal_entries
        filtered_journals = [entry for entry in prior_period_journals_adjusted if
                             entry.ibor_date <= prior_period_cutoff]
        store_journals_as_pickle(filtered_journals,
                                 f"C:/Users/hjmne/PycharmProjects/chest/funds/{fund}/periods/prior_period_journals_adjusted.pkl")

        # Load previous journals and create adjustments
        prior_period_journals_not_adjusted = load_journals_from_pickle(
            f"C:/Users/hjmne/PycharmProjects/chest/funds/{fund}/periods/prior_period_journals_not_adjusted.pkl")
        prior_period_journals_adjusted = load_journals_from_pickle(
            f"C:/Users/hjmne/PycharmProjects/chest/funds/{fund}/periods/prior_period_journals_adjusted.pkl")

        if prior_period_journals_not_adjusted:
            adjusting_journals = create_adjustment_records(prior_period_journals_not_adjusted,
                                                           prior_period_journals_adjusted)
            store_journals_as_pickle(adjusting_journals,
                                     f"C:/Users/hjmne/PycharmProjects/chest/funds/{fund}/periods/{period_name}/adjusting_journals.pkl")

        # Process current period journal entries
        sub_ledger = space_manager.get_space('sub_ledger')
        space_manager.clear_space('sub_ledger')
        main.process_events(space_manager, "", fund, process_start_date, current_period_start, current_period_cutoff,
                            current_period_knowledge, sub_ledger.journal_entries, sub_ledger, "", tdate_fx, scheduler,
                            stat_repo, price_data, fx_data, mark_daily, aggregate_marks, include_marks)

        period_journals = sub_ledger.journal_entries
        current_period_journals = [entry for entry in period_journals if
                                   current_period_start <= entry.ibor_date <= current_period_cutoff]
        store_journals_as_pickle(current_period_journals,
                                 f"C:/Users/hjmne/PycharmProjects/chest/funds/{fund}/periods/{period_name}/current_period_journals.pkl")

    # General Ledger Processing
    general_ledger = space_manager.get_space('general_ledger')
    space_manager.clear_space('general_ledger')
    combined_journals = combine_je_files(fund)
    gl_results = general_ledger.build_general_ledger_from_journals(combined_journals, current_period_cutoff)

    general_ledger_asset_liability_accounts = gl_results.all_asset_liability_bookkeeping_accounts_info()
    report.tax_lot_appraisal(general_ledger_asset_liability_accounts, gl_results, stat_repo, current_period_cutoff,
                             f'--Tax Lot Appraisal General Ledger--{portfolio_name}')

    combined_journals = load_journals_from_pickle("C:/Users/hjmne/PycharmProjects/chest/combined_journals.pkl")
    for entry in combined_journals:
        print(f"Type: {type(entry)}, Content: {entry}")
    gl_results = general_ledger.build_general_ledger_from_journals(combined_journals, current_period_cutoff)

    filen = '--General Ledger Journals--' + portfolio_name
    report.journals_by_tranid(gl_results.journal_entries,
                              current_period_start, current_period_cutoff, filen)

    output_file = "C:/Users/hjmne/pycharmprojects/chest/reports/comprehensive_accounting-GeneralLedger.xlsx"
    bigaccounting.generate_comprehensive_report_and_pivot(general_ledger, gl_results.journal_entries, general_ledger,
                                                          current_period_start, current_period_cutoff, portfolio_name,
                                                          output_file, False, fx_data)

    performance.calculate_and_report_performance(portfolio_name, gl_results.journal_entries, view_type="GeneralLedger")

def build_general_ledger_from_journals(self, journals, period_end):
    """Build general ledger from a list of journals."""
    import time
    bs_start_time = time.time()

    space_manager = SpaceManager()
    general_ledger = space_manager.get_space('general_ledger')

    space_manager.clear_space('general_ledger')
    for idx, je in enumerate(journals):
        if je.ibor_date <= period_end:
            general_ledger.post_journal_entry(je)

            if idx % 10 == 0:
                print(f"Processed {idx} journal entries for General Ledger...")
        else:
            break

    print("Finished processing all journal entries for General Ledger!")
    bs_end_time = time.time()
    fetch_time = bs_end_time - bs_start_time

    print("\nElapsed time - General Ledger build from data: {:.6f}".format(fetch_time))

    return general_ledger
import pickle
import json
import os
from datetime import datetime, timedelta
from bookkeeping import Journals, SpaceManager
import main
import copy
import time
import report
import bigaccounting
import performance

space_manager = SpaceManager()
BASE_DIR = "C:/Users/hjmne/PycharmProjects/chest/periods"

# Helper Functions
# def datetime_serializer(obj):
#     if isinstance(obj, datetime):
#         return obj.isoformat()
#     raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")
#
# def extended_serializer(obj):
#     if isinstance(obj, datetime):
#         return obj.isoformat()
#     elif isinstance(obj, Journals):
#         return {
#             "portfolio": obj.portfolio,
#             "investment": obj.investment,
#             "tax_date": obj.tax_date.isoformat() if isinstance(obj.tax_date, datetime) else obj.tax_date,
#             "ls": obj.ls,
#             "location": obj.location,
#             "financial_account": obj.financial_account,
#             "quantity": obj.quantity,
#             "local": obj.local,
#             "book": obj.book,
#             "tranid": obj.tranid,
#             "transaction": obj.transaction,
#             "tradedate": obj.tradedate.isoformat() if isinstance(obj.tradedate, datetime) else obj.tradedate,
#             "settledate": obj.settledate.isoformat() if isinstance(obj.settledate, datetime) else obj.settledate,
#             "kdbegin": obj.kdbegin.isoformat() if isinstance(obj.kdbegin, datetime) else obj.kdbegin,
#             "kdend": obj.kdend.isoformat() if isinstance(obj.kdend, datetime) else obj.kdend,
#             "ibor_date": obj.ibor_date.isoformat() if isinstance(obj.ibor_date, datetime) else obj.ibor_date,
#             "entry_type": obj.entry_type,
#             "feeder": obj.feeder,
#             "running_balances": obj.running_balances,
#             "split_ratio": obj.split_ratio,
#             "account_key": obj.account_key
#         }
#     raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

import pickle
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def store_journals_as_pickle(journals, file_path):
    """Store journals using pickle to maintain Python object structure."""
    try:
        # Verify that all journals have the required metadata
        for journal in journals:
            if not hasattr(journal, 'period') or not hasattr(journal, 'journal_type') or not hasattr(journal, 'sequence_number'):
                raise ValueError(f"Journal entry missing required metadata: {journal}")

        # Store journals to the pickle file
        with open(file_path, "wb") as file:
            pickle.dump(journals, file)
        logging.info(f"Successfully stored journals to {file_path}")

    except (pickle.PicklingError, IOError, ValueError) as e:
        logging.error(f"Failed to store journals to {file_path}: {e}")
        raise

# Example usage:
# store_journals_as_pickle(journals_list, 'path/to/journals.pkl')


def load_journals_from_pickle(file_path):
    if os.path.exists(file_path):
        with open(file_path, "rb") as file:
            return pickle.load(file)
    return []

# def store_journals_as_json(journals, file_path):
#     journal_entries = [entry.to_dict() for entry in journals]
#     json_data = json.dumps(journal_entries, default=datetime_serializer)
#     with open(file_path, 'w') as file:
#         file.write(json_data)
import pickle
import os
from datetime import timedelta

def store_adjusting_journals(new_ibor_date, adjusting_journals, fund, period, period_start):
    """Store adjusting journals for a closed period using pickle."""
    period_dir = f"C:/Users/hjmne/PycharmProjects/chest/funds/{fund}/periods/{period}/"
    os.makedirs(period_dir, exist_ok=True)

    for journal in adjusting_journals:
        journal.ibor_date = period_start
        journal.transaction = "PriorPeriodAdjustment"

    file_path = period_dir + "adjusting_journals.pkl"
    with open(file_path, 'wb') as f:
        pickle.dump(adjusting_journals, f)
import os

def fetch_all_files(directory):
    """
    Recursively fetch all pickle files in a given directory and its subdirectories.

    Parameters:
    - directory (str): The path to the directory where the files are to be fetched.

    Returns:
    - list: A list of file paths for all .pkl files in the given directory.
    """
    all_files = []
    for foldername, subfolders, filenames in os.walk(directory):
        for filename in filenames:
            if filename.endswith('.pkl') and 'bookkeeping' not in filename.lower():
                full_path = os.path.join(foldername, filename)
                all_files.append(full_path)
    return all_files

import pickle
import os
from datetime import datetime
from bookkeeping import Journals

import os
import pickle
import os
import pickle

import os
import pickle

import os
import pickle

import os
import pickle

import os
import pickle

def combine_je_files(fund):
    """
    Combine journal entries from all pickle files (adjusting and current) for a given fund,
    sorted by journal type and then by the order of processing.
    """
    base_directory = f'C:/Users/hjmne/PycharmProjects/chest/funds/{fund}/periods'

    # Get a list of period directories sorted by numerical order
    period_directories = sorted(
        [d for d in os.listdir(base_directory) if os.path.isdir(os.path.join(base_directory, d))],
        key=lambda x: int(x)  # Sort by directory name as an integer
    )

    combined_journals = []

    # Read and combine the journals from each period directory
    for period_dir in period_directories:
        period_path = os.path.join(base_directory, period_dir)

        # Collect all pickle files in the directory, sorted to ensure adjusting journals come first
        all_files = sorted(
            [os.path.join(period_path, f) for f in os.listdir(period_path) if f.endswith('.pkl')],
            key=lambda x: 'adjusting' not in x  # False (adjusting) comes before True (current)
        )

        for path in all_files:
            try:
                with open(path, 'rb') as f:
                    journals = pickle.load(f)
                    combined_journals.extend(journals)
            except FileNotFoundError:
                print(f"File {path} not found, skipping.")
            except pickle.UnpicklingError:
                print(f"Error unpickling file {path}, skipping.")

    # Sort the combined journals by journal type (adjusting first), and then assign sequence numbers
    combined_journals.sort(key=lambda je: (je.journal_type == 'current'))

    # Assign sequence numbers in the exact order of the sorted list
    Journals.sequence_counter = 0  # Reset sequence counter for consistent ordering
    for je in combined_journals:
        je.sequence_number = Journals.sequence_counter
        Journals.sequence_counter += 1


    return combined_journals

def ensure_sequence_number(journals):
    """Ensure all Journals objects have a sequence_number."""
    for je in journals:
        if not hasattr(je, 'sequence_number'):
            je.sequence_number = Journals.sequence_counter
            Journals.sequence_counter += 1
    return journals



def combined_file_python():
    """
    Load combined journals from a pickle file and return a list of Journals objects.

    Returns:
    - journal_entries (list): A list of Journals objects.
    """
    # Define the path to the combined pickle file
    combined_file_path = "C:/Users/hjmne/PycharmProjects/chest/combined_journals.pkl"

    # Load combined journals from the pickle file
    if os.path.exists(combined_file_path):
        journal_entries = load_journals_from_pickle(combined_file_path)
    else:
        journal_entries = []  # Return an empty list if the file doesn't exist

    return journal_entries


def create_adjustment_records(journals_A, journals_B):
    adjustments = []
    dict_A = {
        (entry.portfolio, entry.investment, entry.tax_date, entry.ls, entry.location, entry.financial_account): entry
        for entry in journals_A}
    dict_B = {
        (entry.portfolio, entry.investment, entry.tax_date, entry.ls, entry.location, entry.financial_account): entry
        for entry in journals_B}

    keys_only_in_A = set(dict_A.keys()) - set(dict_B.keys())
    keys_only_in_B = set(dict_B.keys()) - set(dict_A.keys())
    common_keys = set(dict_A.keys()).intersection(set(dict_B.keys()))

    for key in keys_only_in_A:
        adjusted_entry = copy.copy(dict_A[key])
        adjusted_entry.quantity = -dict_A[key].quantity
        adjusted_entry.local = -dict_A[key].local
        adjusted_entry.book = -dict_A[key].book
        adjustments.append(adjusted_entry)

    for key in keys_only_in_B:
        adjustments.append(dict_B[key])

    for key in common_keys:
        entry_from = dict_A[key]
        entry_to = dict_B[key]
        if entry_from.quantity != entry_to.quantity or entry_from.local != entry_to.local or entry_from.book != entry_to.book:
            delta_record = copy.copy(entry_from)
            delta_record.quantity = (entry_to.quantity or 0) - (entry_from.quantity or 0)
            delta_record.local = entry_to.local - entry_from.local
            delta_record.book = entry_to.book - entry_from.book
            adjustments.append(delta_record)

    return adjustments

def process_closed_periods_mode(space_manager, portfolio_name, process_start_date, smf, scheduler, stat_repo, price_data, fx_data,
                                mark_daily, aggregate_marks, include_marks, tdate_fx):
    input_records_file_path = f'C:/Users/hjmne/PycharmProjects/chest/configs/inputs{portfolio_name}.txt'
    with open(input_records_file_path, 'r') as file:
        input_records = [json.loads(line) for line in file]

    for record in input_records:
        current_period_start = datetime.strptime(record["current_period_start"], "%Y-%m-%d:%H:%M:%S")
        current_period_cutoff = datetime.strptime(record["current_period_cutoff"], "%Y-%m-%d:%H:%M:%S")
        current_period_knowledge = datetime.strptime(record["current_period_knowledge"], "%Y-%m-%d:%H:%M:%S")
        prior_period_start = datetime.strptime(record["prior_period_start"], "%Y-%m-%d:%H:%M:%S")
        prior_period_cutoff = datetime.strptime(record["prior_period_cutoff"], "%Y-%m-%d:%H:%M:%S")
        prior_period_knowledge = datetime.strptime(record["prior_period_knowledge"], "%Y-%m-%d:%H:%M:%S")
        period_name = record["period_name"]
        fund = record["selected_fund"]

        sub_ledger = space_manager.get_space('sub_ledger')
        space_manager.clear_space('sub_ledger')
        main.process_events(space_manager, "", fund, process_start_date, prior_period_start, prior_period_cutoff,
                            prior_period_knowledge, sub_ledger.journal_entries, sub_ledger, "", tdate_fx, scheduler,
                            stat_repo, price_data, fx_data, mark_daily, aggregate_marks, include_marks)

        prior_period_journals_not_adjusted = sub_ledger.journal_entries
        filtered_journals = [entry for entry in prior_period_journals_not_adjusted if
                             entry.ibor_date <= prior_period_cutoff]
        store_journals_as_pickle(filtered_journals,
                                 f"C:/Users/hjmne/PycharmProjects/chest/funds/{fund}/periods/prior_period_journals_not_adjusted.pkl")

        sub_ledger = space_manager.get_space('sub_ledger')
        space_manager.clear_space('sub_ledger')
        main.process_events(space_manager, "", fund, process_start_date, prior_period_start, prior_period_cutoff,
                            current_period_knowledge, sub_ledger.journal_entries, sub_ledger, "", tdate_fx, scheduler,
                            stat_repo, price_data, fx_data, mark_daily, aggregate_marks, include_marks)

        prior_period_journals_adjusted = sub_ledger.journal_entries
        filtered_journals = [entry for entry in prior_period_journals_adjusted if
                             entry.ibor_date <= prior_period_cutoff]
        store_journals_as_pickle(filtered_journals,
                                 f"C:/Users/hjmne/PycharmProjects/chest/funds/{fund}/periods/prior_period_journals_adjusted.pkl")

        prior_period_journals_not_adjusted = load_journals_from_pickle(
            f"C:/Users/hjmne/PycharmProjects/chest/funds/{fund}/periods/prior_period_journals_not_adjusted.pkl")
        prior_period_journals_adjusted = load_journals_from_pickle(
            f"C:/Users/hjmne/PycharmProjects/chest/funds/{fund}/periods/prior_period_journals_adjusted.pkl")

        if prior_period_journals_not_adjusted:
            adjusting_journals = create_adjustment_records(prior_period_journals_not_adjusted,
                                                           prior_period_journals_adjusted)
            store_adjusting_journals(current_period_start, adjusting_journals, fund, period_name,
                                     (prior_period_cutoff + timedelta(seconds=1)))

        sub_ledger = space_manager.get_space('sub_ledger')
        space_manager.clear_space('sub_ledger')
        main.process_events(space_manager, "", fund, process_start_date, current_period_start, current_period_cutoff,
                            current_period_knowledge, sub_ledger.journal_entries, sub_ledger, "", tdate_fx, scheduler,
                            stat_repo, price_data, fx_data, mark_daily, aggregate_marks, include_marks)

        period_journals = sub_ledger.journal_entries
        current_period_journals = [entry for entry in period_journals if
                                   current_period_start <= entry.ibor_date <= current_period_cutoff]
        store_journals_as_pickle(current_period_journals,
                               f"C:/Users/hjmne/PycharmProjects/chest/funds/{fund}/periods/{period_name}/journals.pkl")

    general_ledger = space_manager.get_space('general_ledger')
    space_manager.clear_space('general_ledger')
    combined_journals = combine_je_files(fund)
    gl_results = general_ledger.build_general_ledger_from_journals(combined_journals, current_period_cutoff)

    general_ledger_asset_liability_accounts = gl_results.all_asset_liability_bookkeeping_accounts_info()
    report.tax_lot_appraisal(general_ledger_asset_liability_accounts, gl_results, stat_repo, current_period_cutoff,
                             f'--Tax Lot Appraisal General Ledger--{portfolio_name}')

    filen = '--General Ledger Journals--' + portfolio_name
    report.journals_by_tranid(gl_results.journal_entries,
                              current_period_start, current_period_cutoff, filen)

    filen = '--General Ledger Journals By Sequence Number--' + portfolio_name
    report.journals_by_sequence_number(gl_results.journal_entries,
                              current_period_start, current_period_cutoff, filen)


    output_file = "C:/Users/hjmne/pycharmprojects/chest/reports/comprehensive_accounting-GeneralLedger.xlsx"
    bigaccounting.generate_comprehensive_report_and_pivot(general_ledger, gl_results.journal_entries, general_ledger,
                                                          current_period_start, current_period_cutoff, portfolio_name,
                                                          output_file, False, fx_data)

    performance.calculate_and_report_performance(portfolio_name, gl_results.journal_entries, view_type="GeneralLedger")

def build_general_ledger_from_journals(self, journals, period_end):
    import time
    bs_start_time = time.time()

    space_manager = SpaceManager()
    general_ledger = space_manager.get_space('general_ledger')

    space_manager.clear_space('general_ledger')
    for idx, je in enumerate(journals):
        if je.ibor_date <= period_end:
            general_ledger.post_journal_entry(je)

            if idx % 10 == 0:
                print(f"Processed {idx} journal entries for General Ledger...")
        else:
            break

    print("Finished processing all journal entries for General Ledger!")
    bs_end_time = time.time()
    fetch_time = bs_end_time - bs_start_time

    print("\nElapsed time - General Ledger build from data: {:.6f}".format(fetch_time))

    return general_ledger
