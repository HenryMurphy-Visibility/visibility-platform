import time
import json
import main

def benchmark_load(period_start, period_cutoff):

    json_file_path = "C:/Users/hjmne/PycharmProjects/chest/refdata/ScaleTestJournals.json"

    # Open and read the JSON file
    # Load JSON file and convert each entry to a Python file

    start_time = time.time()


    with open(json_file_path, 'r') as file:
            prior_period_journals_not_adjusted_jsn = json.load(file)  # journals posted in prior period
            journals_not_adjusted_py = [Journals.from_json(entry) for entry in
                                        prior_period_journals_not_adjusted_jsn]

    je_load_time = time.time() - start_time
    print("\nElapsed time- JE Load: {:.6f}".format(je_load_time))


    space1 = BookkeepingSpace.build_sub_ledger_from_journals(journals_not_adjusted_py, period_start, period_cutoff)

    bookkeeping_load_time = time.time() - je_load_time
    print("\nElapsed time- JE Load: {:.6f}".format(bookkeeping_load_time))