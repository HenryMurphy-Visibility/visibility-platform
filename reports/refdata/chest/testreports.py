import closed_period
from bookkeeping import BookkeepingSpace
from utilities import convert_to_structure, flatten_nested_tuples
import report
import time

def prepare_gl_data_for_reporting(period_cutoff, fund):
    start_time = time.time()

    closed_period.combine_je_files(fund)
    journals = closed_period.combined_file_python() # Assuming this returns a list of Journals objects
    # Filter the journal entries to include on journals with current knowledge for the current period being closed
    journals = [entry for entry in journals if entry.ibor_date is not None and entry.ibor_date <= period_cutoff]
    for entry in journals:
        if entry.ibor_date is None:
            print(f"Missing ibor_date for tranid: {entry.tranid}")
            raise ValueError(f"Terminating program due to missing ibor_date for tranid: {entry.tranid}")

    repository = BookkeepingSpace.create_new_instance()
    space1 = repository.build_sub_ledger_from_journals(journals, period_cutoff)
    asset_liability_data = space1.combined_assets_liabilities()
    all_bookkeeping_data = space1.get_combined_space()
    ready_asset_liability_data = flatten_nested_tuples(asset_liability_data)
    ready_all_bookkeeping_data = flatten_nested_tuples(all_bookkeeping_data)
#    ready_asset_liability_data = convert_to_structure(asset_liability_data, 4)
    je_data = space1.journal_entries


    end_time = time.time()
    fetch_time = end_time - start_time

    print("\nElapsed time- build from data: {:.6f}".format(fetch_time))

    return space1, je_data, ready_asset_liability_data, ready_all_bookkeeping_data
