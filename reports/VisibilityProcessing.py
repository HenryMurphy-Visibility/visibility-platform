import csv
import datetime
import business_days
import logging
import pickle
import os
from business_days import US_HOLIDAYS
import psutil
from collections import defaultdict
import build_a_query_set
import query_builder
import time
import utilities
from report import prepare_data
from sharding import add_shard
import bookkeeping
from bookkeeping import BookkeepingSpace
from tkcalendar import DateEntry
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
import domain_language_model
import multiprocessing
import main
import report
import closed_period
import performance
import performance_old
import performance_attribution
import performance_detail
from utilities import load_fx_data, load_price_data
# ✅ Dictionary to store JEs per portfolio
MASTER_QUERY_SPACES = {}  # Global dictionary for optional storage


import pandas as pd
from bookkeeping import BookkeepingSpace, EventScheduler, StatisticalRepository, SpaceManager, SettlementChores
import utilities
smf =  SettlementChores()
import logging
import query_data


import warnings
warnings.filterwarnings("ignore")


logging.basicConfig(level=logging.CRITICAL)

BASE_PATH = "C:/users/hjmne/pycharmprojects/chest"

# Define the lump date to replace '0' for tax dates
#ld = datetime.datetime(1970, 1, 1, 0, 0)
ld = 0
stat_repo = StatisticalRepository()

# Instantiate SpaceManager
space_manager = SpaceManager()

# Register spaces
space_manager.register_space('sub_ledger', BookkeepingSpace())
space_manager.register_space('general_ledger', BookkeepingSpace())



# Retrieve the registered spaces from the space manager-
sub_ledger = space_manager.get_space('sub_ledger')
general_ledger = space_manager.get_space('general_ledger')

# Initialize the scheduler with the bookkeeping repository (sub_ledger from space_manager)
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

DEFAULT_PORTFOLIO = "XYZMutualFund1"
PROCESS_DEFAULT_ONLY = False

import csv
from collections import defaultdict
from datetime import datetime

import csv
from collections import defaultdict
from datetime import datetime
# remember csv file is custom format so convert to date
# that is the actual format in csv not the custom

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

DEFAULT_PORTFOLIO = "XYZMutualFund1"
PROCESS_DEFAULT_ONLY = False


fx_data = load_fx_data('C:/Users/hjmne/PycharmProjects/chest/refdata/fx_master.csv')
price_data = load_price_data('C:/Users/hjmne/PycharmProjects/chest/refdata/price_master.csv')
import os

def process_portfolio_list(portfolio_list_or_name, query_directory):
    """
    Returns a list of portfolios to process.
    Handles both single portfolio names and list files.
    """
    portfolios = []

    query_directory = "C:/Users/hjmne/PycharmProjects/chest/refdata/pooltest"
    if portfolio_list_or_name.lower().startswith("mylist"):
        portfolio_path = os.path.join(query_directory, f"{portfolio_list_or_name}.csv")

        if not os.path.exists(portfolio_path):
            print(f"Warning: Portfolio list file not found: {portfolio_path}")
            return []

        with open(portfolio_path, 'r') as f:
            portfolios = [line.strip() for line in f if line.strip()]

    else:
        # Assume it's a single portfolio name
        portfolio_path = os.path.join(query_directory, f"{portfolio_list_or_name}.csv")
        if os.path.exists(portfolio_path):
            portfolios = [portfolio_list_or_name]
        else:
            print(f"Warning: Portfolio file '{portfolio_list_or_name}.csv' not found in {query_directory}.")

    return portfolios



import os
import pickle
import datetime
import tkinter as tk
from tkinter import ttk, filedialog
from tkcalendar import DateEntry
import psutil

# ---- Themes ----
themes = {
    "default": {
        "background": "#191970",   # **Dark Blue** (to match GWI)
        "text": "white",           # White text
        "button_bg": "#4682B4",    # **Steel Blue** button background
        "button_text": "#FFFFFF",  # White button text
        "active_text": "#FF4500",  # **Orange-Red** active text
        "odd_row": "#D3D3D3",      # **Light Gray** for odd rows
        "even_row": "white",       # White for even rows
    }
}


import tkinter as tk
from tkinter import ttk


def apply_theme(root):
    """Applies the GWI theme to the Tkinter UI."""
    # 🎨 Set overall background color
    root.configure(bg="#191970")  # Deep Blue/Purple

    # 🎨 Style for Buttons
    button_style = ttk.Style()
    button_style.configure(
        "TButton",
        background="white",
        foreground="black",
        font=("Arial", 10),
        padding=5
    )

    # 🎨 Style for Labels
    label_style = ttk.Style()
    label_style.configure(
        "TLabel",
        background="#191970",
        foreground="white",
        font=("Arial", 14, "bold")
    )

    # 🎨 Style for Frames (Panel Sections)
    frame_style = ttk.Style()
    frame_style.configure("TFrame", background="#191970")

    # 🎨 Table Styles (Treeview)
    tree_style = ttk.Style()
    tree_style.configure("Treeview", background="white", foreground="black", fieldbackground="white")
    tree_style.configure("Treeview.Heading", background="#4682B4", foreground="white", font=("Arial", 10, "bold"))

    return button_style, label_style, frame_style, tree_style


# 🎨 Modify Setup UI Function
def setup_ui():
    root = tk.Tk()
    root.title("VisibilityProcessing - Themed Version")
    root.geometry("800x600")

    # ✅ Apply theme
    apply_theme(root)

    # 📌 Title Label
    title_label = ttk.Label(root, text="VisibilityProcessing - Graphical Workflow Interface (GWI)", style="TLabel")
    title_label.pack(pady=10)

    # 📌 Frame for Inputs
    frame = ttk.Frame(root, style="TFrame")
    frame.pack(pady=10, padx=20, fill="x")

    # 📌 Dropdown Example
    portfolio_label = ttk.Label(frame, text="Select Portfolio:", style="TLabel")
    portfolio_label.grid(row=0, column=0, padx=5, pady=5)

    portfolio_dropdown = ttk.Combobox(frame, values=["Portfolio 1", "Portfolio 2"])
    portfolio_dropdown.grid(row=0, column=1, padx=5, pady=5)

    # 📌 Process Button
    process_button = ttk.Button(root, text="Process Portfolio", style="TButton", command=lambda: print("Processing..."))
    process_button.pack(pady=10)

    # 📌 Table Example (Treeview)
    table = ttk.Treeview(root, columns=("Column 1", "Column 2"), show="headings", style="Treeview")
    table.heading("Column 1", text="Header 1")
    table.heading("Column 2", text="Header 2")
    table.pack(fill="both", expand=True, padx=10, pady=10)

    root.mainloop()


# ✅ Run the UI if script is executed directly
if __name__ == "__main__":
    setup_ui()


# ---- GUI Setup ----
def setup_gui():
    theme = themes["default"]

    root = tk.Tk()
    root.title("Processing GUI")
    root.configure(bg=theme["background"])

    window_width, window_height = 1000, 800
    center_window(root, window_width, window_height)

    main_frame = ttk.Frame(root, padding="10")
    main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    # ---- Parameter Inputs ----
    param_inputs = setup_parameter_inputs(main_frame, theme)


    # ---- Portfolio List Setup ----
    def setup_portfolio_list(main_frame, theme):
        portfolio_frame = ttk.LabelFrame(main_frame, text="Portfolio List", padding="10")
        portfolio_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        portfolio_lists = [
            "XYZMutualFund1", "myListMutualFunds", "XYZMutualFund2",
            "XYZMutualFund3","XYZMutualFund4","XYZMutualFund5","XYZMutualFund6",
            "XYZMutualFund7", "XYZMutualFund8", "XYZMutualFund9", "XYZMutualFund10",
            "manyportfolios20000", "myListMyBondPortfolio", "myListMyFuturesPortfolio",
            "A_Composite"
        ]

        portfolio_list_var = tk.StringVar(value="XYZMutualFund1")
        portfolio_list_menu = ttk.Combobox(portfolio_frame, textvariable=portfolio_list_var, values=portfolio_lists,
                                           state="readonly")
        portfolio_list_menu.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)

        # Allow multiple portfolio selection from a list
        portfolio_listbox = tk.Listbox(portfolio_frame, selectmode=tk.MULTIPLE, height=10)
        for item in portfolio_lists:
            portfolio_listbox.insert(tk.END, item)
        portfolio_listbox.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky=(tk.W, tk.E))

        # Browse button to select a file manually
        browse_button = ttk.Button(portfolio_frame, text="Browse", command=lambda: browse_file(portfolio_list_var))
        browse_button.grid(row=2, column=0, padx=5, pady=5)

        return portfolio_list_var, portfolio_listbox

    # ---- Helper Function to Get Selected Portfolios ----
    def get_selected_portfolios(listbox):
        selected_indices = listbox.curselection()
        selected_portfolios = [listbox.get(i) for i in selected_indices]
        return selected_portfolios

    # ---- Execution Mode Setup ----
    def setup_execution_mode(main_frame, theme):
        mode_frame = ttk.LabelFrame(main_frame, text="Execution Mode", padding="10")
        mode_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        mode_var = tk.StringVar(value="Single-threaded")
        ttk.Radiobutton(mode_frame, text="Single-threaded", variable=mode_var, value="Single-threaded").grid(row=0,
                                                                                                             column=0,
                                                                                                             padx=5,
                                                                                                             pady=5,
                                                                                                             sticky=tk.W)
        ttk.Radiobutton(mode_frame, text="Multi-threaded", variable=mode_var, value="Multi-threaded").grid(row=0,
                                                                                                           column=1,
                                                                                                           padx=5,
                                                                                                           pady=5,
                                                                                                           sticky=tk.W)

        return mode_var, mode_frame

    # ---- Directories Setup ----
    def setup_directories(main_frame):
        query_directory_var = setup_directory_frame(main_frame, "Query Directory", 4)
        report_directory_var = setup_directory_frame(main_frame, "Report Directory", 5)
        return query_directory_var, report_directory_var

    def setup_directory_frame(main_frame, text, row):
        frame = ttk.LabelFrame(main_frame, text=text, padding="10")
        frame.grid(row=row, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        directory_var = tk.StringVar()
        ttk.Entry(frame, width=50, textvariable=directory_var).grid(row=0, column=0, padx=5, pady=5,
                                                                    sticky=(tk.W, tk.E))
        ttk.Button(frame, text="Browse", command=lambda: browse_directory(directory_var)).grid(row=0, column=1, padx=5,
                                                                                               pady=5)

        return directory_var

    # ---- System Processing Log Setup ----
    def setup_log_frame(main_frame):
        log_frame = ttk.LabelFrame(main_frame, text="System Processing Log", padding="1")
        log_frame.grid(row=6, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        log_text = tk.Text(log_frame, wrap='word', height=1)
        log_text.grid(row=0, column=0, padx=2, pady=2, sticky=(tk.W, tk.E, tk.N, tk.S))

        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=log_text.yview)
        log_scroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
        log_text.configure(yscrollcommand=log_scroll.set)

        return log_text

    # ---- Progress Bar Setup ----
    def setup_progress_bar(main_frame):
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="5")
        progress_frame.grid(row=7, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        progress = ttk.Progressbar(progress_frame, orient="horizontal", length=400, mode="determinate")
        progress.grid(row=0, column=0, padx=5, pady=5, sticky=(tk.W, tk.E))

        return progress

    # ---- Directory Browsing ----
    def browse_directory(directory_var):
        directory = filedialog.askdirectory()
        if directory:
            directory_var.set(directory)

    # ---- File Browsing ----
    def browse_file(variable):
        file_path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if file_path:
            variable.set(file_path)

    # ---- Processing Mode Setup ----
    def setup_processing_mode(main_frame, theme):
        picklist_frame = ttk.LabelFrame(main_frame, text="Processing Mode", padding="10")
        picklist_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        processing_modes = [
            "Build Standard Accounting View",
            "Build Queries for GWI and Report Output",
            "Fetch Information from External Sources",
            "Close Periods",
            "Performance Only",
            "Ledger Only",
            "Positions Only",
            "Composite Performance"
        ]

        processing_mode_var = tk.StringVar(value="Build Standard Accounting View")
        processing_mode_menu = ttk.Combobox(
            picklist_frame,
            textvariable=processing_mode_var,
            values=processing_modes,
            state="readonly",
            width=35
        )
        processing_mode_menu.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)

        processing_mode_label = ttk.Label(
            picklist_frame,
            text="Select Processing Mode:",
            background=theme["background"],
            foreground=theme["text"]
        )
        processing_mode_label.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)

        mark_daily_var = tk.BooleanVar(value=True)
        closed_periods_var = tk.BooleanVar(value=False)
        include_marks_var = tk.BooleanVar(value=True)

        ttk.Checkbutton(
            picklist_frame, text="Mark daily?", variable=mark_daily_var
        ).grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)

        ttk.Checkbutton(
            picklist_frame, text="Close Periods?", variable=closed_periods_var
        ).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Checkbutton(
            picklist_frame, text="Include marks?", variable=include_marks_var
        ).grid(row=1, column=2, padx=5, pady=5, sticky=tk.W)

        return processing_mode_var, mark_daily_var, closed_periods_var, include_marks_var

    # ---- Setup Directories ----
    query_directory_var, report_directory_var = setup_directories(main_frame)

    # ---- Portfolio List Setup ----
    portfolio_list_var, portfolio_listbox = setup_portfolio_list(main_frame, theme)

    # ---- Processing Mode Setup ----
    processing_mode_var, mark_daily_var, closed_periods_var, include_marks_var = setup_processing_mode(main_frame,
                                                                                                        theme)

    # ---- Execution Mode Setup ----
    mode_var, mode_frame = setup_execution_mode(main_frame, theme)

    # ---- System Processing Log ----
    log_text = setup_log_frame(main_frame)

    progress = setup_progress_bar(main_frame)
    # ---- Run Button ----
    run_button = ttk.Button(
        mode_frame,
        text="Run Processing",
        command=lambda: route_mode(
            param_inputs, mode_var, processing_mode_var, portfolio_list_var.get(),
            query_directory_var, report_directory_var.get(), log_text, progress,
            mark_daily_var.get(), closed_periods_var.get(), include_marks_var.get(),
            fx_data, price_data
        )
    )
    run_button.grid(row=0, column=2, padx=10, pady=5, sticky=tk.E)

    # ---- Styles ----
    style = ttk.Style()
    style.configure("TFrame", background=theme["background"])
    style.configure("TLabelframe", background=theme["background"], foreground=theme["text"])
    style.configure("TLabel", background=theme["background"], foreground=theme["text"])
    style.configure("TButton", background=theme["button_bg"], foreground=theme["button_text"])
    style.map("TButton", background=[("active", theme["button_bg"])], foreground=[("active", theme["active_text"])])

    root.mainloop()

# ---- Center Window Function ----
def center_window(root, width, height):
    screen_width, screen_height = root.winfo_screenwidth(), root.winfo_screenheight()
    position_top = int(screen_height / 2 - height / 2)
    position_right = int(screen_width / 2 - width / 2)
    root.geometry(f'{width}x{height}+{position_right}+{position_top}')



# ---- Setup Parameter Inputs ----
def setup_parameter_inputs(main_frame, theme):
    param_frame = ttk.LabelFrame(main_frame, text="Parameter Inputs", padding="10")
    param_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    current_period_frame = ttk.LabelFrame(param_frame, text="Current Period", padding="10")
    current_period_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    prior_period_frame = ttk.LabelFrame(param_frame, text="Prior Period", padding="10")
    prior_period_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))

    param_inputs = {}

    setup_date_entries(current_period_frame, param_inputs, "Current", theme)
    setup_date_entries(prior_period_frame, param_inputs, "Prior", theme)

    return param_inputs

def setup_date_entries(frame, param_inputs, period, theme):
    labels = [f"{period} Period Start", f"{period} Period Cutoff", f"{period} Period Knowledge"]
    default_dates = ["2023-01-01", "2023-03-31", "2024-01-31"] if period == "Current" else ["2022-01-01", "2022-03-31", "2022-01-31"]

    for idx, label in enumerate(labels):
        lbl = ttk.Label(frame, text=label, background=theme["background"], foreground=theme["text"])
        lbl.grid(row=idx, column=0, padx=5, pady=5, sticky=tk.W)

        date_frame = ttk.Frame(frame)
        date_frame.grid(row=idx, column=1, padx=5, pady=5, sticky=(tk.W, tk.E))

        date_entry = DateEntry(date_frame, width=12, date_pattern='yyyy-mm-dd')
        date_entry.set_date(default_dates[idx])
        date_entry.grid(row=0, column=0, padx=5, pady=5)

        time_entry = ttk.Entry(date_frame, width=10)
        time_entry.insert(0, "00:00:00")
        time_entry.grid(row=0, column=1, padx=5, pady=5)

        param_inputs[label] = (date_entry, time_entry)

# ---- Route Mode Function ----
def route_mode(param_inputs, mode_var, processing_mode_var, portfolio_list, query_directory, report_directory,
               log_text, progress, mark_daily, closed_periods, include_marks, fx_data, price_data):
    processing_mode = processing_mode_var.get()
    import combineperf

    if processing_mode == "Build Standard Accounting View" or processing_mode == "Build Queries for GWI and Report Output":
        log_text.insert(tk.END, "Executing Begin Processing...\n")
        begin_processing(
            param_inputs, mode_var, processing_mode_var, portfolio_list, query_directory, report_directory,
            log_text, progress, mark_daily, closed_periods, include_marks, fx_data, price_data
        )
    else:
        log_text.insert(tk.END, f"Error: Unknown processing mode '{processing_mode}'.\n")
        log_text.update()

    log_text.update()

# ---- Begin Processing ----
def begin_processing(param_inputs, mode_var, processing_mode_var, portfolio_list, query_directory, report_directory,
                     log_text, progress, mark_daily, closed_periods, include_marks, fx_data, price_data):
    log_text.insert(tk.END, f"Query Directory: {query_directory}\n")
    log_text.insert(tk.END, "Preparing portfolio list...\n")

    portfolio_list = process_portfolio_list(portfolio_list, query_directory)

    if not portfolio_list:
        log_text.insert(tk.END, "No portfolios to process. Exiting.\n")
        log_text.update()
        return

    log_text.insert(tk.END, f"Portfolios to process: {portfolio_list}\n")
    log_text.update()

    continue_processing(
        param_inputs, mode_var, processing_mode_var, portfolio_list, query_directory, report_directory,
        log_text, progress, mark_daily, closed_periods, include_marks, fx_data, price_data
    )
import concurrent.futures
# ---- Continue Processing ----
import os
import zipfile
import pandas as pd


def continue_processing(param_inputs, mode_var, processing_mode_var, portfolio_list, query_directory, report_directory,
                        log_text, progress, mark_daily, closed_periods, include_marks, fx_data, price_data):
    log_text.insert(tk.END, "Starting portfolio processing...\n")
    log_text.update()

    processing_mode = processing_mode_var.get()

    # Determine shard count
    num_shards = 1 if mode_var.get() == "Single-threaded" else psutil.cpu_count(logical=False)
    shards = [[] for _ in range(num_shards)]

    # Allocate portfolios to shards
    for idx, portfolio in enumerate(portfolio_list):
        shards[idx % num_shards].append(portfolio)

    # if processing_mode == "Composite Performance":
    #     import combineperf
    #     for portfolio in portfolio_list:
    #         combineperf.consolidate_portfolio_summaries(portfolio, "", "")
    #     return

    if processing_mode == "Build Queries for GWI and Report Output":
        log_text.insert(tk.END, "Entering Queries Mode...\n")
        log_text.update()

        # Using multiprocessing for queries
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_shards) as executor:
            futures = []
            for shard in shards:
                futures.append(
                    executor.submit(
                        build_queries, shard, {
                            "current_period_start": param_inputs["Current Period Start"][0].get(),
                            "current_period_cutoff": param_inputs["Current Period Cutoff"][0].get()
                        }
                    )
                )
            for future in concurrent.futures.as_completed(futures):
                future.result()

    else:
        log_text.insert(tk.END, "Entering Processing Mode...\n")
        log_text.update()

        for shard in shards:
            for portfolio in shard:
                log_text.insert(tk.END, f"Processing portfolio: {portfolio}\n")
                log_text.update()

                prepared_data = prepare_parameters(sub_ledger, general_ledger, param_inputs, portfolio, query_directory, report_directory, log_text)

                build_accounting(prepared_data, sub_ledger, scheduler, stat_repo,
                                 price_data, fx_data, mark_daily,
                                 closed_periods, include_marks)

    log_text.insert(tk.END, "Portfolio processing complete.\n")
    log_text.update()

# ---- Queries Function ----
def build_queries(portfolio_list, current_period_data):
    logging.info("Entering Queries Mode.")

    report_directory = "C:/users/hjmne/pycharmprojects/chest/reports"
    os.makedirs(report_directory, exist_ok=True)

    for portfolio_name in portfolio_list:
        logging.info(f"Processing portfolio: {portfolio_name}")
        try:
            journal_entries = query_builder.fetch_journal_entries(portfolio_name)
            if not journal_entries:
                logging.warning(f"No journal entries found for portfolio: {portfolio_name}")
                continue

            import bigaccounting
            output_file = os.path.join(report_directory, f"{portfolio_name}_comprehensive_accounting.csv")

            # Overwrite existing file without creating a unique name
            bigaccounting.generate_comprehensive_report_and_pivot(
                None,  # space_manager not required for Queries Mode
                journal_entries,
                None,  # sub_ledger not required for Queries Mode
                current_period_data["current_period_start"],
                current_period_data["current_period_cutoff"],
                portfolio_name,
                output_file,
                False,  # derive_mktval
                None  # fx_data not needed
            )
            logging.info(f"Generated report for portfolio {portfolio_name}: {output_file}")

            # Introduce a small delay to ensure file is accessible for the next write
            time.sleep(0.5)

        except Exception as e:
            logging.error(f"Error processing portfolio {portfolio_name}: {e}")
    return

def process_shard(shard, current_period_data, sub_ledger, general_ledger,
                  processing_mode, query_directory, report_directory, mark_daily, closed_periods, include_marks):
    for portfolio_file in shard.portfolios:
        sub_ledger.reset_all()
        prepare_parameters(sub_ledger, general_ledger, current_period_data, portfolio_file,
                                              query_directory, report_directory,processing_mode)
# ---- Prepare Parameters ----
def prepare_parameters(sub_ledger, general_ledger, param_inputs, portfolio_name, query_directory, report_directory, log_text):
    """
    Prepares parameters for processing portfolios.

    Args:
        param_inputs (dict): The parameter inputs from the GUI.
        portfolio_name (str): The selected portfolio name.
        query_directory (str): Directory containing the query files.
        report_directory (str): Directory to save reports.
        log_text (tk.Text): Log text widget for displaying messages.

    Returns:
        dict: A dictionary of prepared parameters.
    """
    try:
        # Extract dates from the GUI inputs
        current_period_start = f"{param_inputs['Current Period Start'][0].get()} {param_inputs['Current Period Start'][1].get()}"
        current_period_cutoff = f"{param_inputs['Current Period Cutoff'][0].get()} {param_inputs['Current Period Cutoff'][1].get()}"
        current_period_knowledge = f"{param_inputs['Current Period Knowledge'][0].get()} {param_inputs['Current Period Knowledge'][1].get()}"
        prior_period_start = f"{param_inputs['Prior Period Start'][0].get()} {param_inputs['Prior Period Start'][1].get()}"
        prior_period_cutoff = f"{param_inputs['Prior Period Cutoff'][0].get()} {param_inputs['Prior Period Cutoff'][1].get()}"
        prior_period_knowledge = f"{param_inputs['Prior Period Knowledge'][0].get()} {param_inputs['Prior Period Knowledge'][1].get()}"

        log_text.insert(tk.END, f"Preparing parameters for portfolio: {portfolio_name}\n")
        log_text.update()

        prepared_data = {
            sub_ledger: sub_ledger,
            "report_directory": report_directory,
            "output_dir": os.path.join(report_directory, portfolio_name),
            "process_start_date": datetime.datetime.strptime(current_period_start, "%Y-%m-%d %H:%M:%S"),
            "current_period_start": datetime.datetime.strptime(current_period_start, "%Y-%m-%d %H:%M:%S"),
            "current_period_cutoff": datetime.datetime.strptime(current_period_cutoff, "%Y-%m-%d %H:%M:%S"),
            "current_period_knowledge": datetime.datetime.strptime(current_period_knowledge, "%Y-%m-%d %H:%M:%S"),
            "prior_period_start": datetime.datetime.strptime(prior_period_start, "%Y-%m-%d %H:%M:%S"),
            "prior_period_cutoff": datetime.datetime.strptime(prior_period_cutoff, "%Y-%m-%d %H:%M:%S"),
            "prior_period_knowledge": datetime.datetime.strptime(prior_period_knowledge, "%Y-%m-%d %H:%M:%S"),
            "tdate_fx": None,
            "general_ledger": None,
            "portfolio_name": portfolio_name
        }

        log_text.insert(tk.END, f"Parameters prepared successfully for {portfolio_name}\n")
        log_text.update()

        return prepared_data

    except Exception as e:
        log_text.insert(tk.END, f"Error preparing parameters: {e}\n")
        log_text.update()
        return None

# ---- Process Events ----
def build_accounting(prepared_data, sub_ledger, scheduler, stat_repo, price_data,
                     fx_data, mark_daily, include_marks, calendar):
    """
    Processes the portfolio events and stores the resulting JEs and report files.
    """
    from PySide6.QtWidgets import QMessageBox
    from PySide6.QtCore import QCoreApplication
    import os
    import pickle
    import pandas as pd
    from pathlib import Path
    from bookkeeping import Journals

    portfolio_name = prepared_data["portfolio_name"]
    start_date = prepared_data["current_period_start"]
    cutoff_date = prepared_data["current_period_cutoff"]
    knowledge_date = prepared_data["current_period_knowledge"]

    # ✅ DAILY / MONTHLY CALENDAR
    if calendar in ("Daily", "Monthly"):
        processing_box = QMessageBox()
        processing_box.setWindowTitle("Processing")
        processing_box.setText("Processing Data - Please Wait...")
        processing_box.setStandardButtons(QMessageBox.NoButton)
        processing_box.show()
        QCoreApplication.processEvents()

        closed_period.process_closed_periods_mode(
            space_manager, portfolio_name, start_date, smf, scheduler,
            stat_repo, price_data, fx_data,
            mark_daily, include_marks, None, calendar
        )

        processing_box.setText("Processing Complete!")
        processing_box.setStandardButtons(QMessageBox.Ok)
        processing_box.exec()
        return

    # ✅ GPU TEST MODE
    if calendar == "master_query_file":
        sub_ledger.reset_all()
        main.process_events(
            space_manager, "", portfolio_name,
            start_date, start_date, cutoff_date, knowledge_date,
            sub_ledger.journal_entries, sub_ledger,
            prepared_data["general_ledger"], prepared_data["tdate_fx"],
            scheduler, stat_repo, price_data, fx_data, smf,
            mark_daily, include_marks
        )

    # ✅ OPEN CALENDAR
    elif calendar == "Open":
        sub_ledger.reset_all()

        build_a_query_set.inputs_main(portfolio_name, start_date, cutoff_date)
        adj_period_start = business_days.get_previous_business_day(start_date)

        main.process_events(
            space_manager, "", portfolio_name,
            start_date, start_date, adj_period_start, knowledge_date,
            sub_ledger.journal_entries, sub_ledger,
            prepared_data["general_ledger"], prepared_data["tdate_fx"],
            scheduler, stat_repo, price_data, fx_data, smf,
            mark_daily, include_marks
        )

        asset_liability_accounts = sub_ledger.all_asset_liability_bookkeeping_accounts_info()
        report.position_report(
            asset_liability_accounts, portfolio_name, sub_ledger,
            adj_period_start, 'PeriodStartPositions', price_data, fx_data
        )

        report.cost_basis_balance_sheet(
            portfolio_name, sub_ledger.all_bookkeeping_accounts_info(),
            adj_period_start, 'PeriodStartBalances'
        )

        sub_ledger.reset_all()

        main.process_events(
            space_manager, "", portfolio_name,
            start_date, start_date, cutoff_date, knowledge_date,
            sub_ledger.journal_entries, sub_ledger,
            prepared_data["general_ledger"], prepared_data["tdate_fx"],
            scheduler, stat_repo, price_data, fx_data, smf,
            mark_daily, include_marks
        )

        import performance_for_real_time
        performance.calculate_and_report_performance(portfolio_name, sub_ledger.journal_entries)

        report.merge_journals_with_groupings(
            sub_ledger.journal_entries, start_date, cutoff_date, calendar, portfolio_name
        )

        investment_master_path = "C:/users/hjmne/pycharmprojects/chest/refdata/investment_master.csv"
        if not os.path.exists(investment_master_path):
            raise FileNotFoundError(f"Missing investment master: {investment_master_path}")

        df = report.prepare_data(
            sub_ledger.journal_entries, investment_master_path, start_date, cutoff_date
        )

        report.generate_all_nav_reports(df, "C:/users/hjmne/pycharmprojects/chest/reports")
        print("✅ NAV Analysis completed.")

        asset_liability_accounts = sub_ledger.all_asset_liability_bookkeeping_accounts_info()

        report.tax_lot_appraisal(
            asset_liability_accounts, portfolio_name, sub_ledger, stat_repo,
            start_date, cutoff_date, 'TaxLotAppraisal', price_data, fx_data
        )

        report.cost_basis_balance_sheet(
            portfolio_name, sub_ledger.all_bookkeeping_accounts_info(),
            cutoff_date, 'PeriodEndBalances'
        )

        report.position_report(
            asset_liability_accounts, portfolio_name, sub_ledger, cutoff_date,
            'PeriodEndPositions', price_data, fx_data
        )

        report.position_report_by_sector(
            asset_liability_accounts, portfolio_name, sub_ledger, cutoff_date,
            'PositionsBySector', price_data, fx_data, calendar
        )

        report.position_report_by_industry(
            asset_liability_accounts, portfolio_name, sub_ledger, cutoff_date,
            'PositionsByIndustry', price_data, fx_data
        )

        report.position_report_by_analyst(
            asset_liability_accounts, portfolio_name, sub_ledger, cutoff_date,
            'PositionsByAnalyst', price_data, fx_data
        )

        report.top_bottom_by_analyst(
            portfolio_name,
            f"C:/users/hjmne/pycharmprojects/chest/reports/{portfolio_name}_investmentReturnsSum.xlsx",
            investment_master_path
        )

    # ✅ INLINE DIFF REPORTS
    base_dir = f"C:/Users/hjmne/PycharmProjects/chest/funds/{portfolio_name}/Open/periods"
    file_path = os.path.join(base_dir, "mqs.pkl")
    backup_path = os.path.join(base_dir, "mqs_before.pkl")
    report_dir = Path("C:/Users/hjmne/PycharmProjects/chest/reports")
    report_static = report_dir / f"{portfolio_name}_KnowledgeStatic.xlsx"
    report_drift = report_dir / f"{portfolio_name}_KnowledgeDrift.xlsx"
    report_dir.mkdir(parents=True, exist_ok=True)

    # ✅ Save new journals
    with open(file_path, "wb") as f:
        pickle.dump(sub_ledger.journal_entries, f)
    print(f"✅ New journals saved to: {file_path}")

    if not os.path.exists(backup_path):
        print("📭 No prior journal file to diff against. Writing default Excel reports.")
        df = pd.DataFrame([{"ChangeType": "None", "JournalEntry": "No prior journal file found."}])
        df.to_excel(report_static, index=False)
        df.to_excel(report_drift, index=False)
        return

    try:
        with open(backup_path, "rb") as f1, open(file_path, "rb") as f2:
            old_raw = pickle.load(f1)
            new_raw = pickle.load(f2)

        def ensure_objects(obj_list):
            if isinstance(obj_list, list) and isinstance(obj_list[0], dict):
                return [Journals.from_dict(j) for j in obj_list]
            return obj_list

        old_journals = ensure_objects(old_raw)
        new_journals = ensure_objects(new_raw)

        def static_key(j):
            return (
                j.portfolio, j.investment, j.lotid, j.tax_date, j.ls,
                j.location, j.financial_account, j.tradedate, j.settledate,
                j.entry_type, j.quantity, j.local, j.book
            )

        def drift_key(j):
            return (
                j.portfolio, j.investment, j.lotid, j.tax_date, j.ls,
                j.location, j.financial_account, j.tradedate, j.settledate,
                j.entry_type, j.tranid, j.sequence_number, j.quantity,
                j.local, j.book
            )

        old_static = {static_key(j): j for j in old_journals}
        new_static = {static_key(j): j for j in new_journals}

        added = set(new_static) - set(old_static)
        removed = set(old_static) - set(new_static)

        static_diff = []
        for k in added:
            static_diff.append({"ChangeType": "Added", "JournalEntry": str(new_static[k])})
        for k in removed:
            static_diff.append({"ChangeType": "Removed", "JournalEntry": str(old_static[k])})

        if not static_diff:
            static_diff.append({"ChangeType": "None", "JournalEntry": "No differences found."})
            print("✅ No KnowledgeStatic differences.")
        else:
            print(f"📊 KnowledgeStatic: {len(static_diff)} entries changed.")

        pd.DataFrame(static_diff).to_excel(report_static, index=False)
        print(f"📄 KnowledgeStatic report written to: {report_static}")

        drift_added = set(map(drift_key, new_journals)) - set(map(drift_key, old_journals))
        drift_removed = set(map(drift_key, old_journals)) - set(map(drift_key, new_journals))

        drift_data = []
        for j in new_journals:
            if drift_key(j) in drift_added:
                drift_data.append({"ChangeType": "Added", "JournalEntry": str(j)})
        for j in old_journals:
            if drift_key(j) in drift_removed:
                drift_data.append({"ChangeType": "Removed", "JournalEntry": str(j)})

        if not drift_data:
            drift_data.append({"ChangeType": "None", "JournalEntry": "No knowledge drift found."})
            print("✅ No KnowledgeDrift differences.")
        else:
            print(f"📊 KnowledgeDrift: {len(drift_data)} entries changed.")

        pd.DataFrame(drift_data).to_excel(report_drift, index=False)
        print(f"📄 KnowledgeDrift report written to: {report_drift}")

    except Exception as e:
        print(f"❌ Error during diffing: {e}")

if __name__ == '__main__':
    setup_gui()
