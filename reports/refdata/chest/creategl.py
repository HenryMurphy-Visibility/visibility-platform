
import json
import os
from bookkeeping import SpaceManager, Journals
import bookkeeping
from closed_period import fetch_all_files
import datetime

# Define your base directory for fund-related data
BASE_DIR = 'C:/Users/hjmne/PycharmProjects/chest/funds/{fund}/periods'

def load_journals_from_json(filepath):
    """
    Load journal entries from a JSON file and convert them into journal format.
    :param filepath: The path to the JSON file.
    :return: List of journal entries loaded from the JSON file.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            journals = json.load(file)
            return [Journals.from_dict(entry) for entry in journals]
    except Exception as e:
        print(f"Error reading data from JSON file {filepath}: {e}")
        return None

def combine_journals_from_json(fund):
    """
    Combine journal entries from all JSON files for a given fund and track their source files.
    :param fund: Fund name.
    :return: Combined list of journal entries along with their source files.
    """
    period_directory = BASE_DIR.format(fund=fund)
    print(f"Combining journals for fund: {fund}")

    files_to_combine = fetch_all_files(period_directory, extensions=('.json',))
    combined_journals = []

    for file_path in files_to_combine:
        journals = load_journals_from_json(file_path)
        if journals:
            for journal in journals:
                combined_journals.append((journal, file_path))  # Append journal and its source file

    # Ensure that all elements are sortable by converting to strings if necessary
    combined_journals.sort(key=lambda x: (
        str(x[0].ibor_date),
        str(x[0].portfolio),
        str(x[0].investment),
        str(x[0].lotid)
    ))
    return combined_journals

def print_all_journals(journals_with_sources):
    """
    Print all journal entries along with their source files.
    :param journals_with_sources: List of tuples containing journal entries and their source files.
    """
    for je, source_file in journals_with_sources:
        print(f"Journal Entry: {je}, Source File: {source_file}")

def standalone_post_journals_to_gl(fund, cutoff_date):
    """
    Standalone function to load, combine, and post journals to the general ledger space.
    :param fund: Fund name.
    :param cutoff_date: Cutoff date to filter journal entries.
    """
    space_manager = SpaceManager()
    general_ledger = space_manager.get_space('general_ledger')

    # Combine journal entries from JSON files
    combined_journals_with_sources = combine_journals_from_json(fund)
    print(f"Total combined journals: {len(combined_journals_with_sources)}")

    # Print all combined journals along with their source files
    print_all_journals(combined_journals_with_sources)

    # Post each journal entry to the general ledger space
    for je, source_file in combined_journals_with_sources:
        if je.ibor_date <= cutoff_date:
            general_ledger.post_journal_entry(je, target_space='general_ledger')

    print("Completed posting journals to general ledger space.")

if __name__ == "__main__":
    import datetime
    fund_name = "XYZMutualFund"
    cutoff_date = datetime.datetime(2022, 12, 31)  # Example cutoff date

    standalone_post_journals_to_gl(fund_name, cutoff_date)