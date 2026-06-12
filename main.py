print(">>> ENTER main.py")




import heapq


import pandas as pd

investment_master_path = 'c:/BASE_PATH/refdata/investment_master.csv'
bond_info_path = 'c:/BASE_PATH/refdata/bond_info.csv'

from utilities import load_price_data_as_rows, load_fx_data_as_rows


# if not space.asset_liability_repository.get_position_space:
#     utilities.load_investment_master_to_aif(space, investment_master_path)
#     utilities.load_bond_info_to_aif(space, investment_master_path)


schedule_begin_time = 0
schedule_end_time = 0



def process_events(
    fund,
    calendar,          # STRING: calendar name
    period_name,       # STRING
    period_start,      # ignored (calendar authoritative)
    period_cutoff,     # ignored
    knowledge_cutoff,  # ignored
    journal_entries,
    space,
    scheduler,
    price_data,
    fx_data,
    af,
    stat_repo,
    sir,
    rebuild_marks,
    snapshots=None     # OPTIONAL acceleration
):
    print("✅ entered process_events")

    import time
    from datetime import datetime

    schedule_start_time = time.time()


      # 🕒 Step 2: End scheduling time
    # 🧪 Step 3: Sort and prepare
    print(f"🧪 Pre-Sort: {len(scheduler.events)} events loaded into scheduler")
    scheduler.sort_events()  # if you uncomment it
    print(f"✅ Post-Sort: {len(scheduler.events)} events after sorting")

    # 🧰 Step 4: Process events with progress logging
    print("🔧 Starting to process events...")

    process_start_time = time.time()
    processed_count = 0
    progress_interval = 10000
    print(f"📋 Number of events in scheduler: {len(scheduler.events)}")

    processed_count = 0

    while scheduler.events:
        try:
            scheduler.run_next_event()
            processed_count += 1

            if processed_count % progress_interval == 0:
                print(f"⚙️ Processed {processed_count} events...")

        except KeyError as e:
            print(f"❌ KeyError: {e} — dropping event and continuing.")
            if scheduler.events:
                scheduler.events.popitem(last=False)

        except Exception as ex:
            print(f"❌ Unexpected error: {type(ex).__name__}: {ex} — dropping event and continuing.")
            import traceback
            traceback.print_exc()
            if scheduler.events:
                scheduler.events.popitem(last=False)

    # 8. CALENDAR UPDATE (mode-dependent — NEW)
    # ------------------------------------------------------------
    from datetime import datetime
    now_kd = datetime.now()


    # ------------------------------------------------------------
    # 10. PERFORMANCE SUMMARY
    # ------------------------------------------------------------
    process_end_time = time.time()
    processing_duration = process_end_time - process_start_time
    total_duration = process_end_time - schedule_start_time

    print("\n📊 Summary:")
    print(f"⚙️  Total processing time: {processing_duration:.2f} seconds")
    print(f"📈 Total time (overall):  {total_duration:.2f} seconds")
    print(f"📦 Events processed:      {processed_count}")
    if processing_duration > 0:
        print(f"🚀 Events per second:     {processed_count / processing_duration:.2f}")

    return space



    # ✅ Step 5: Final metrics
    print("\n📊 Summary:")
    #  print(f"🕒 Total scheduling time    : {schedule_duration:.2f} seconds")
    print(f"⚙️  Total processing time    : {processing_duration:.2f} seconds")
    print(f"📈 Total time (overall)     : {total_duration:.2f} seconds")
    print(f"📦 Events processed         : {processed_count}")
    if processing_duration > 0:
        print(f"🚀 Events per second        : {processed_count / processing_duration:.2f}")

    combined_asset_liability_entries_for_marking = space.combined_assets_liabilities()
    all_asset_liability_for_marking = []
    # Assuming combined_entries is structured correctly as expected
    for entry in combined_asset_liability_entries_for_marking:
        key, values = entry  # Unpack key and values
        # Unpack the key tuple
        portfolio, investment, lotid, tax_lot_num, ls, location, financial_account = key

        # Unpack the values tuple, now including notional, original_face, and settlement_status
        quantity, local, book, notional, oface = values

        # Prepare the row for output, including new fields
        booksp_row = [portfolio, investment, lotid, tax_lot_num, ls, location, financial_account,
                      quantity, local, book, notional, oface]

        all_asset_liability_for_marking.append(booksp_row)


    #  bookkeeping.store_journals(journal_entries)
    journal_entries_dict = {}

    for entry in space.journal_entries:
        key = (entry.portfolio, entry.investment, entry.lotid, entry.tax_date, entry.ls, entry.location,
               entry.financial_account)
        if key in journal_entries_dict:
            journal_entries_dict[key].append(entry)
        else:
            journal_entries_dict[key] = [entry]

    # print(isinstance(investment_accounting_space, Bookkeeping))
    # Example usage
    combined_space_custom = space.get_combined_space()
    # Assuming combined_entries is structured correctly as expected
    all_bookkeeping_accounts_list = []
    for entry in combined_space_custom:
        key, values = entry[0], entry[1]  # Extracting key and values from each entry
        # Unpacking key into individual variables
        portfolio, investment, lotid, tax_date, ls, location, financial_account = key

        # Using unpack_values to safely extract data from values
        quantity, local, book = utilities.unpack_values(values)

        # Create a bookkeeping row with all the data
        booksp_row = [
            portfolio, investment, lotid, tax_date, ls, location, financial_account,
            quantity, local, book
        ]

        # Append this row to the list of all bookkeeping accounts
        all_bookkeeping_accounts_list.append(booksp_row)

    combined_asset_liability_entries = []
    combined_asset_liability_entries = space.combined_assets_liabilities()
    all_asset_liability_accounts_list = []
    # Assuming combined_entries is structured correctly as expected
    for entry in combined_asset_liability_entries:
        key, values = entry[0], entry[1]  # If combined_entries contains entries as ((key), (values))
        # Or directly, if combined_entries is indeed structured as (key, values)
        portfolio, investment, lotid, tax_date, ls, location, financial_account = key
        # Using unpack_values to safely extract data from values
        quantity, local, book = utilities.unpack_values(values)

        booksp_row = [portfolio, investment, lotid, tax_date, ls, location, financial_account, quantity, local, book]
        all_asset_liability_accounts_list.append(booksp_row)
    #
    # # for key, v in combined_entries:
    #     portfolio, investment, tax_lot_num, ls, location, financial_account = key
    #     quantity, local, book = v[0], v[1], v[2]
    #     booksp_row = [portfolio, investment, tax_lot_num, ls, location, financial_account, quantity, local, book]
    #     space_list.append(booksp_row)
    #
    #  space.serialize_journal_entries(investment_accounting_space.journal_entries, fund)

    # VERIFY JOURNALS ARE BALANCED
    out_of_balance = check_journal_balances(space.journal_entries, threshold=0.01)
    print(out_of_balance)

    return


    # Verify that the bookkeeping space is balanced
    # total_bv = space.sum_bs_book()
    # print("\nBalance Check: {:.6f}".format(total_bv))
    #
    # if total_bv > -.01 and total_bv < .01:
    #     print("Bookkeeping space is balanced.")
    # else:
    #     print("Bookkeeping space is not balanced by ", total_bv)


   # prepare data for reporting

    # # Example of generating a report
    # asset_liability_repo = asset_liability_repository  # Assuming bookkeeping is your Bookkeeping instance
    # all_assets_and_liabilites = asset_liability_repo.aggregate_entries_for_reporting()
    # # space = BookkeepingSpace()
    # if timeset == "current" and create_performance and not close_period:
    #     filen = 'AccountingResultsCurrentPeriod'+fund
    #     fname = 'C:/Users/hjmne/PycharmProjects/chest/reports/PerformanceSummaries.xlsx'
    #     performance.create_performance_sheets(investment_accounting_space.journal_entries)
    #
    # if timeset == "current" and compare_to_prior_period:
    #     filen = 'AccountingResultsCurrentPeriod'+fund
    #     report.create_accounting_reports(investment_accounting_space.journal_entries, filen,
    #                                      all_asset_liability_accounts_list, period_cutoff)


print(">>> LEAVE main.py")

