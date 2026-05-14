import csv
import datetime
import logging
import os
import psutil
from collections import defaultdict
import time
import bookkeeping
from bookkeeping import BookkeepingSpace
from tkcalendar import DateEntry
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
import multiprocessing
import main
import report
import closed_period
import performance
import newperformance
import pandas as pd
from bookkeeping import BookkeepingSpace, EventScheduler, StatisticalRepository, SpaceManager, SettlementChores
import utilities
smf =  SettlementChores()
import logging

logging.basicConfig(level=logging.CRITICAL)

# Define the lump date to replace '0' for tax dates
ld = datetime.datetime(1970, 1, 1, 0, 0)

stat_repo = StatisticalRepository()

# Instantiate SpaceManager
space_manager = SpaceManager()

# Register spaces
space_manager.register_space('sub_ledger', BookkeepingSpace())
space_manager.register_space('general_ledger', BookkeepingSpace())



# Initialize the bookkeeping space using the get_instance method
sub_ledger = BookkeepingSpace()
general_ledger = BookkeepingSpace()



# Initialize the scheduler with the bookkeeping repository
scheduler = EventScheduler(sub_ledger)

def read_and_format_csv(file_path, date_column):
    try:
        df = pd.read_csv(file_path, parse_dates=[date_column])
        print(f"Initial format of dates in {file_path}:\n{df[date_column].head()}")
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None

    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    return df

def format_dates_in_dataframe(df, date_column, target_format):
    try:
        df[date_column] = df[date_column].dt.strftime(target_format)
        print(f"Formatted dates in {date_column}:\n{df[date_column].head()}")
    except Exception as e:
        print(f"Error formatting dates in dataframe: {e}")
        return None
    return df

logging.basicConfig(level=logging.CRITICAL)

DEFAULT_PORTFOLIO = "MyPortfolio1"
PROCESS_DEFAULT_ONLY = False

def load_fx_data_from_csv(filepath):
    fx_data = defaultdict(dict)
    with open(filepath, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            currency = row['currency']
            date = row['date']
            rate = float(row['price'])
            fx_data[currency][date] = rate
    return fx_data

fx_data = load_fx_data_from_csv('C:/Users/hjmne/PycharmProjects/chest/refdata/fx_master.csv')
price_data = pd.read_csv('C:/Users/hjmne/PycharmProjects/chest/refdata/price_master.csv')

# def review_fx_data(fx_data):
#     for currency, rates in fx_data.items():
#         print(f"Currency: {currency}")
#         for date, rate in rates.items():
#             print(f"  Date: {date}, Rate: {rate}")
#
# review_fx_data(fx_data)

def setup_gui():
    root = tk.Tk()
    root.title("Processing GUI")

    window_width = 900
    window_height = 725

    def center_window():
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        position_top = int(screen_height / 2 - window_height / 2)
        position_right = int(screen_width / 2 - window_width / 2)
        root.geometry(f'{window_width}x{window_height}+{position_right}+{position_top}')

    root.geometry(f'{window_width}x{window_height}')
    center_window()
    root.bind('<Configure>', lambda event: center_window())
    root.configure(bg='#4B0082')

    main_frame = ttk.Frame(root, padding="10")
    main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    main_frame.configure(style="MainFrame.TFrame")

    param_frame = ttk.LabelFrame(main_frame, text="Parameter Inputs", padding="10")
    param_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    param_frame.configure(style="ParamFrame.TLabelframe")

    current_period_frame = ttk.LabelFrame(param_frame, text="Current Period", padding="10")
    current_period_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    current_period_frame.configure(style="ParamFrame.TLabelframe")

    prior_period_frame = ttk.LabelFrame(param_frame, text="Prior Period", padding="10")
    prior_period_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
    prior_period_frame.configure(style="ParamFrame.TLabelframe")

    current_labels = ["Current Period Start", "Current Period Cutoff", "Current Period Knowledge"]
    prior_labels = ["Prior Period Start", "Prior Period Cutoff", "Prior Period Knowledge"]
    default_dates = ["2022-01-01", "2022-01-31", "2022-01-31",
                     "2022-01-01", "2022-01-31", "2022-01-31"]
    default_times = ["00:00:00", "23:59:59", "23:59:59",
                     "00:00:00", "23:59:59", "23:59:59"]

    param_inputs = {}

    for idx, label in enumerate(current_labels):
        lbl = ttk.Label(current_period_frame, text=label, background='#4B0082', foreground='white')
        lbl.grid(row=idx, column=0, padx=5, pady=5, sticky=tk.W)

        date_frame = ttk.Frame(current_period_frame)
        date_frame.grid(row=idx, column=1, padx=5, pady=5, sticky=(tk.W, tk.E))

        date_entry = DateEntry(date_frame, width=12, date_pattern='yyyy-mm-dd')
        date_entry.set_date(default_dates[idx])
        date_entry.grid(row=0, column=0, padx=5, pady=5)

        time_entry = ttk.Entry(date_frame, width=10)
        time_entry.insert(0, default_times[idx])
        time_entry.grid(row=0, column=1, padx=5, pady=5)

        param_inputs[label] = (date_entry, time_entry)

    for idx, label in enumerate(prior_labels):
        lbl = ttk.Label(prior_period_frame, text=label, background='#4B0082', foreground='white')
        lbl.grid(row=idx, column=0, padx=5, pady=5, sticky=tk.W)

        date_frame = ttk.Frame(prior_period_frame)
        date_frame.grid(row=idx, column=1, padx=5, pady=5, sticky=(tk.W, tk.E))

        date_entry = DateEntry(date_frame, width=12, date_pattern='yyyy-mm-dd')
        date_entry.set_date(default_dates[idx + 3])
        date_entry.grid(row=0, column=0, padx=5, pady=5)

        time_entry = ttk.Entry(date_frame, width=10)
        time_entry.insert(0, default_times[idx + 3])
        time_entry.grid(row=0, column=1, padx=5, pady=5)

        param_inputs[label] = (date_entry, time_entry)

    picklist_frame = ttk.LabelFrame(main_frame, text="Processing Mode", padding="10")
    picklist_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    picklist_frame.configure(style="ParamFrame.TLabelframe")

    processing_modes = ["Pure Run-Time", "Comprehensive Accounting", "Closed Periods"]
    processing_mode_var = tk.StringVar(value="Pure Run-Time")
    processing_mode_menu = ttk.Combobox(picklist_frame, textvariable=processing_mode_var, values=processing_modes)
    processing_mode_menu.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)

    mark_daily_var = tk.BooleanVar(value=True)
    aggregate_marks_var = tk.BooleanVar(value=False)
    include_marks_var = tk.BooleanVar(value=True)

    mark_daily_checkbutton = ttk.Checkbutton(picklist_frame, text="Mark daily?", variable=mark_daily_var)
    aggregate_marks_checkbutton = ttk.Checkbutton(picklist_frame, text="Aggregate marks?", variable=aggregate_marks_var)
    include_marks_checkbutton = ttk.Checkbutton(picklist_frame, text="Include marks?", variable=include_marks_var)

    mark_daily_checkbutton.grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
    aggregate_marks_checkbutton.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
    include_marks_checkbutton.grid(row=1, column=2, padx=5, pady=5, sticky=tk.W)

    portfolio_frame = ttk.LabelFrame(main_frame, text="Portfolio List", padding="10")
    portfolio_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    portfolio_frame.configure(style="ParamFrame.TLabelframe")

    portfolio_lists = [ "mylistXYZMutualFund.csv", "mylist1.csv", "mylist2.csv", "ScaleTest.csv", "mylist100.csv", "mylist500.csv", "mylist1000.csv",
                       "manyportfolios20000.csv", "myListMyBondPortfolio.csv", "myListMyFuturesPortfolio.csv"]
    portfolio_list_var = tk.StringVar(value="mylist1.csv")
    portfolio_list_menu = ttk.Combobox(portfolio_frame, textvariable=portfolio_list_var, values=portfolio_lists)
    portfolio_list_menu.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)

    mode_frame = ttk.LabelFrame(main_frame, text="Execution Mode", padding="10")
    mode_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    mode_frame.configure(style="ParamFrame.TLabelframe")

    global mode_var
    mode_var = tk.StringVar(value="Single-threaded")
    single_threaded_radio = ttk.Radiobutton(mode_frame, text="Single-threaded", variable=mode_var, value="Single-threaded")
    multi_threaded_radio = ttk.Radiobutton(mode_frame, text="Multi-threaded", variable=mode_var, value="Multi-threaded")

    single_threaded_radio.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
    multi_threaded_radio.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)

    query_dir_frame = ttk.LabelFrame(main_frame, text="Query Directory", padding="10")
    query_dir_frame.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    query_dir_frame.configure(style="ParamFrame.TLabelframe")

    query_directory_var = tk.StringVar()
    query_dir_entry = ttk.Entry(query_dir_frame, width=50, textvariable=query_directory_var)
    query_dir_entry.grid(row=0, column=0, padx=5, pady=5, sticky=(tk.W, tk.E))

    query_dir_button = ttk.Button(query_dir_frame, text="Browse", command=lambda: browse_directory(query_directory_var))
    query_dir_button.grid(row=0, column=1, padx=5, pady=5)

    report_dir_frame = ttk.LabelFrame(main_frame, text="Report Directory", padding="10")
    report_dir_frame.grid(row=5, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    report_dir_frame.configure(style="ParamFrame.TLabelframe")

    report_directory_var = tk.StringVar()
    report_dir_entry = ttk.Entry(report_dir_frame, width=50, textvariable=report_directory_var)
    report_dir_entry.grid(row=0, column=0, padx=5, pady=5, sticky=(tk.W, tk.E))

    report_dir_button = ttk.Button(report_dir_frame, text="Browse", command=lambda: browse_directory(report_directory_var))
    report_dir_button.grid(row=0, column=1, padx=5, pady=5)

    log_frame = ttk.LabelFrame(main_frame, text="System Processing Log", padding="1")
    log_frame.grid(row=6, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    log_frame.configure(style="ParamFrame.TLabelframe")

    log_text = tk.Text(log_frame, wrap='word', height=1)
    log_text.grid(row=0, column=0, padx=2, pady=2, sticky=(tk.W, tk.E, tk.N, tk.S))

    log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=log_text.yview)
    log_scroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
    log_text.configure(yscrollcommand=log_scroll.set)

    progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="5")
    progress_frame.grid(row=7, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    progress_frame.configure(style="ParamFrame.TLabelframe")

    progress = ttk.Progressbar(progress_frame, orient="horizontal", length=400, mode="determinate")
    progress.grid(row=0, column=0, padx=5, pady=5, sticky=(tk.W, tk.E))

    run_button = ttk.Button(mode_frame, text='Run Processing', command=lambda: start_processing(param_inputs, mode_var,
                                                                                                processing_mode_var,
                                                                                                portfolio_list_var.get(),
                                                                                                query_directory_var.get(),
                                                                                                report_directory_var.get(),
                                                                                                log_text, progress,
                                                                                                mark_daily_var,
                                                                                                aggregate_marks_var,
                                                                                                include_marks_var))
    run_button.grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)

    style = ttk.Style()
    style.configure("MainFrame.TFrame", background='#4B0082')
    style.configure("ParamFrame.TLabelframe", background='#4B0082', foreground='white')
    style.configure("TLabel", background='#4B0082', foreground='white')

    root.mainloop()

def browse_directory(directory_var):
    directory = tk.filedialog.askdirectory()
    if directory:
        directory_var.set(directory)

def start_processing(param_inputs, mode_var, processing_mode_var, portfolio_list_file, query_directory, report_directory,
                     log_text, progress, mark_daily_var, aggregate_marks_var, include_marks_var):
    current_period_data = {
        "current_period_start": f"{param_inputs['Current Period Start'][0].get()} {param_inputs['Current Period Start'][1].get()}",
        "current_period_cutoff": f"{param_inputs['Current Period Cutoff'][0].get()} {param_inputs['Current Period Cutoff'][1].get()}",
        "current_period_knowledge": f"{param_inputs['Current Period Knowledge'][0].get()} {param_inputs['Current Period Knowledge'][1].get()}",
        "prior_period_start": f"{param_inputs['Prior Period Start'][0].get()} {param_inputs['Prior Period Start'][1].get()}",
        "prior_period_cutoff": f"{param_inputs['Prior Period Cutoff'][0].get()} {param_inputs['Prior Period Cutoff'][1].get()}",
        "prior_period_knowledge": f"{param_inputs['Prior Period Knowledge'][0].get()} {param_inputs['Prior Period Knowledge'][1].get()}",
        "compare_to_prior_period": False,
        "performance_checkbox_value": False,
        "mark_daily": mark_daily_var.get(),
        "aggregate_marks": aggregate_marks_var.get(),
        "include_marks": include_marks_var.get()
    }

    portfolio_list_file_path = f'C:/BASE_PATH/{portfolio_list_file}'
    mode = mode_var.get()
    processing_mode = processing_mode_var.get()
    mark_daily = mark_daily_var.get()
    aggregate_marks = aggregate_marks_var.get()
    include_marks = include_marks_var.get()

    start_system(current_period_data, portfolio_list_file_path, mode, processing_mode, query_directory,
                 report_directory, log_text, progress, mark_daily, aggregate_marks, include_marks)

def distribute_portfolios(shards, portfolio_list, base_path):
    portfolios_to_process = [os.path.join(base_path, f"{portfolio}.csv") for portfolio in portfolio_list]

    for i, portfolio in enumerate(portfolios_to_process):
        shard = shards[i % len(shards)]
        shard.add_portfolio(portfolio)

def prepare_parameters_and_process_events(sub_ledger, general_Ledger, current_period_data, portfolio_file,
                                           processing_mode, fx_data, price_data,
                                          mark_daily, aggregate_marks, include_marks):
    logging.info(f"Processing domain-specific events for portfolio file: {portfolio_file}")

    portfolio_name = os.path.splitext(os.path.basename(portfolio_file))[0]
    logging.info(f"Extracted portfolio name: {portfolio_name}")

    if PROCESS_DEFAULT_ONLY and portfolio_name != DEFAULT_PORTFOLIO:
        logging.info(f"Skipping portfolio: {portfolio_name}")
        return

    temp_file = portfolio_file + '.tmp'
    with open(portfolio_file, mode='r', encoding='utf-8') as infile, open(temp_file, mode='w', encoding='utf-8',
                                                                          newline='') as outfile:
        reader = csv.reader(infile)
        writer = csv.writer(outfile)
        header = next(reader)
        writer.writerow(header)
        for row in reader:
            row[0] = portfolio_name
            writer.writerow(row)

    os.replace(temp_file, portfolio_file)

    selected_report = current_period_data.get("selected_report", "Default Report Type")


    coa_path = "C:/Users/hjmne/PycharmProjects/chest/chart_of_accounts.csv"
    coa = bookkeeping.load_coa_from_csv()

    date_fields = ["current_period_start", "current_period_cutoff", "current_period_knowledge",
                   "prior_period_start", "prior_period_cutoff", "prior_period_knowledge"]

    for field in date_fields:
        if not current_period_data.get(field):
            logging.error(f"Error: {field} data not provided.")
            return

    current_period_start = datetime.datetime.strptime(current_period_data.get("current_period_start"), "%Y-%m-%d %H:%M:%S")
    current_period_cutoff = datetime.datetime.strptime(current_period_data.get("current_period_cutoff"), "%Y-%m-%d %H:%M:%S")
    current_period_knowledge = datetime.datetime.strptime(current_period_data.get("current_period_knowledge"), "%Y-%m-%d %H:%M:%S")
    prior_period_start = datetime.datetime.strptime(current_period_data.get("prior_period_start"), "%Y-%m-%d %H:%M:%S")
    prior_period_cutoff = datetime.datetime.strptime(current_period_data.get("prior_period_cutoff"), "%Y-%m-%d %H:%M:%S")
    prior_period_knowledge = datetime.datetime.strptime(current_period_data.get("prior_period_knowledge"), "%Y-%m-%d %H:%M:%S")

    process_current = "Yes"
    process_base = "Yes"

    close_period = False
    create_performance = False
    prior_period_name = "foo"
    events_sheet = ""
    tdate_fx = 1

    logging.info(f"Processing portfolio: {portfolio_name}")
    processing_start_time = time.time()

    if processing_mode == "Pure Run-Time":
        import bigaccounting
        process_start_date = current_period_start
        if not isinstance(sub_ledger, bookkeeping.BookkeepingSpace):
            raise TypeError("sub_ledger is not an instance of BookkeepingSpace")

        sub_ledger.reset_all()

        import cProfile
        import pstats
        import io
        #
        # pr = cProfile.Profile()
        # pr.enable()

        main.process_events(space_manager, events_sheet,  portfolio_name, process_start_date, current_period_start,
                            current_period_cutoff, current_period_knowledge,
                            sub_ledger.journal_entries, sub_ledger, general_ledger,
                             tdate_fx, scheduler, stat_repo, price_data, fx_data,
                            mark_daily, aggregate_marks, include_marks)

        asset_liability_accounts = sub_ledger.all_asset_liability_bookkeeping_accounts_info()
        filen = '--Tax Lot Appraisal pure run--' + portfolio_name
        report.tax_lot_appraisal(asset_liability_accounts, sub_ledger, stat_repo, current_period_cutoff,
                                 filen)

        output_file = "C:/Users/hjmne/pycharmprojects/chest/reports/comprehensive_accounting.xlsx"

        bigaccounting.generate_comprehensive_report_and_pivot(space_manager, sub_ledger.journal_entries,
                                                              sub_ledger, current_period_start,
                                                              current_period_cutoff, portfolio_name,
                                                              output_file, False, fx_data)

        filen = '--Sub Ledger Journals--' + portfolio_name
        report.journals_by_tranid(sub_ledger.journal_entries,
                                  current_period_start, current_period_cutoff, filen)

        print("processing completed for portfolio " +portfolio_name)
        # pr.disable()
        # s = io.StringIO()
        # ps = pstats.Stats(pr, stream=s).sort_stats(pstats.SortKey.CUMULATIVE)
        # ps.print_stats()
        # print(s.getvalue())

        size = len(sub_ledger.journal_entries)
        print("Size of file: " + str(size) + " entries")

    sub_ledger.reset_all()

    if processing_mode == "Comprehensive Accounting":
        process_start_date = current_period_start
        if not isinstance(sub_ledger, bookkeeping.BookkeepingSpace):
            raise TypeError("sub_ledger is not an instance of BookkeepingSpace")

        sub_ledger.reset_all()

        main.process_events(space_manager, events_sheet, portfolio_name, process_start_date, current_period_start,
                            current_period_cutoff, current_period_knowledge,
                            sub_ledger.journal_entries, sub_ledger, general_ledger,
                             tdate_fx, scheduler, stat_repo, price_data, fx_data,
                            mark_daily, aggregate_marks, include_marks)

        size = len(sub_ledger.journal_entries)
        print("Size of file: " + str(size) + " entries")
        print("portfolio"+portfolio_name)

        # filen = '--Managerial--'+portfolio_name
        # report.journals_by_tranid(sub_ledger.journal_entries,
        #                            sub_ledger, current_period_start, current_period_cutoff)

        # asset_liability_accounts = sub_ledger.all_asset_liability_bookkeeping_accounts_info()
        # filen = '--Tax Lot Appraisal--' + portfolio_name
        # report.tax_lot_appraisal(asset_liability_accounts, sub_ledger, stat_repo, current_period_cutoff,
        #                          filen)
        #
        # filen = 'Realized Gains/Losses' + portfolio_name
        # report.realized_gains_losses(sub_ledger.journal_entries, sub_ledger,
        #                              current_period_start, current_period_cutoff, filen, portfolio_name)

        # filen = f'--Managerial--'+fund
        # report.position_report_by_sector(asset_liability_accounts, current_period_cutoff,current_period_knowledge, filen)

        # filen = '--Managerial--'+portfolio_name
        # report.total_income_earned(sub_ledger.journal_entries,
        #                             sub_ledger, current_period_start, current_period_cutoff,
        #                             filen)

        import bigaccounting

        # Debugging: Print the current_period_cutoff value
        # print(f"current_period_cutoff before passing to generate_comprehensive_report_and_pivot: {current_period_cutoff}")
        filen = '--Managerial--' + portfolio_name
        output_file = "C:/Users/hjmne/pycharmprojects/chest/reports/comprehensive_accounting.xlsx"

        bigaccounting.generate_comprehensive_report_and_pivot(space_manager, sub_ledger.journal_entries,
                                                               sub_ledger, current_period_start,
                                                               current_period_cutoff, portfolio_name,
                                                               output_file, False, fx_data)

        performance.calculate_and_report_performance(portfolio_name,  sub_ledger.journal_entries, "sub_ledger")

        asset_liability_accounts = sub_ledger.all_asset_liability_bookkeeping_accounts_info()
        filen = '--Tax Lot Appraisal--' + portfolio_name
        report.tax_lot_appraisal(asset_liability_accounts, sub_ledger, stat_repo, current_period_cutoff,
                                 filen)



        # pr.disable()
        # s = io.StringIO()
        # ps = pstats.Stats(pr, stream=s).sort_stats(pstats.SortKey.CUMULATIVE)
        # ps.print_stats()
        # print(s.getvalue())

    elif processing_mode == "Compare two Accounting Periods":
        process_start_date = current_period_start
        if not isinstance(sub_ledger, bookkeeping.BookkeepingSpace):
            raise TypeError("sub_ledger is not an instance of BookkeepingSpace")

        sub_ledger.reset_all()

        main.process_events(space_manager, events_sheet,  portfolio_name, process_start_date, current_period_start,
                            current_period_cutoff, current_period_knowledge,
                            sub_ledger.journal_entries, sub_ledger, general_ledger,
                            coa, tdate_fx, scheduler, stat_repo, price_data, fx_data,
                            mark_daily, aggregate_marks, include_marks)

        asset_liability_accounts = sub_ledger.all_asset_liability_bookkeeping_accounts_info()
        filen = '--Tax Lot Appraisal--' + portfolio_name
        report.tax_lot_appraisal(asset_liability_accounts, sub_ledger, current_period_cutoff, filen)

        sub_ledger.reset_all()

    elif processing_mode == "Closed Periods":
        process_start_date = current_period_start
        closed_period.process_closed_periods_mode(space_manager, portfolio_name, process_start_date, smf, scheduler, stat_repo, price_data, fx_data,
                                                  mark_daily, aggregate_marks, include_marks, tdate_fx)

    elif processing_mode == "Calculate and Report Performance":
        sub_ledger.reset_all()
        sub_ledger.reset_investment_subspaces()
        create_performance = False
        process_start_date = current_period_start
        main.process_events(space_manager, events_sheet, portfolio_name, process_start_date, current_period_start,
                            current_period_cutoff, current_period_knowledge,
                            sub_ledger.journal_entries, sub_ledger, general_ledger,
                            coa, tdate_fx, scheduler, stat_repo, price_data, fx_data,
                            mark_daily, aggregate_marks, include_marks)



        performance.calculate_and_report_performance(portfolio_name, sub_ledger.journal_entries)

def start_system(current_period_data, portfolio_list_file_path, mode, processing_mode, query_directory,
                 report_directory, log_text, progress, mark_daily, aggregate_marks, include_marks):
    logging.info("Starting system with data: %s", current_period_data)
    logging.info("Processing Mode: %s", processing_mode)

    manager = bookkeeping.SpaceManager()
    sub_ledger = manager.get_space('sub_ledger')
    journal_entries = []
    fund_structures_space_journal_entries = []

    shards = []
    logging.info("Adding shards")
    num_cores = psutil.cpu_count(logical=False)
    for i in range(num_cores):
        add_shard(shards, name=f"pool{i + 1}", current_period_data=current_period_data,
                  process_domain_events=prepare_parameters_and_process_events, cpu_core=i)

    portfolio_list = []
    with open(portfolio_list_file_path, mode='r', encoding='utf-8') as file:
        reader = csv.reader(file)
        portfolio_list = [row[0] for row in reader if row[0] != 'PortfolioName']
        portfolio_list = [portfolio for portfolio in portfolio_list if portfolio.strip()]
    base_path = 'C:/BASE_PATH/refdata/pooltest'

    distribute_portfolios(shards, portfolio_list, base_path)

    logging.info("Starting shard processes")
    total_portfolios = len(portfolio_list)
    progress["maximum"] = total_portfolios

    if mode == "Single-threaded":
        for shard in shards:
            for portfolio_file in shard.portfolios:
                sub_ledger.reset_all()
                prepare_parameters_and_process_events(sub_ledger, general_ledger, current_period_data, portfolio_file,
                                                      processing_mode, fx_data, price_data,
                                                      mark_daily, aggregate_marks, include_marks)
                log_text.insert(tk.END, f"Processed portfolio: {portfolio_file}\n")
                progress["value"] += 1
                log_text.update()
                progress.update()
    else:
        processes = []
        for shard in shards:
            p = multiprocessing.Process(target=process_shard, args=(shard, current_period_data, sub_ledger, general_ledger,
                                                                    processing_mode, query_directory, report_directory,
                                                                    mark_daily, aggregate_marks, include_marks))
            p.start()
            processes.append(p)

        for p in processes:
            p.join()

    logging.info("System processing completed.")
    log_text.insert(tk.END, "System processing completed.\n")
    log_text.update()

    for shard in shards:
        for i, processing_time in enumerate(shard.processing_times):
            logging.info(f"Shard {shard.name} processed portfolio {i + 1} in {processing_time} seconds")
            log_text.insert(tk.END, f"Shard {shard.name} processed portfolio {i + 1} in {processing_time} seconds\n")
            log_text.update()

    progress["value"] = 0

def process_shard(shard, current_period_data, sub_ledger, general_ledger,
                  processing_mode, query_directory, report_directory, mark_daily, aggregate_marks, include_marks):
    for portfolio_file in shard.portfolios:
        sub_ledger.reset_all()
        prepare_parameters_and_process_events(sub_ledger, general_ledger, current_period_data, portfolio_file,
                                              processing_mode, fx_data, price_data,
                                              mark_daily, aggregate_marks, include_marks)

if __name__ == '__main__':
    setup_gui()
