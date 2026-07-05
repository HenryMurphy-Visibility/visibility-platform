
"""
============================================
   VISIBILITY - Graphical Workflow Interface (GWI)
============================================

📌 PROGRAM OVERVIEW:
This script implements the **GWI Unified Interface**, a PyQt-based application for financial data
processing, portfolio tracking, and real-time performance updates. It follows a carefully structured
initialization sequence to **avoid execution order issues** and **ensure dependencies are properly loaded**.

🚀 **KEY FEATURES & MODULES:**
- **Master Link Management:** Loads and maps master link sets from CSV.
- **Data Processing:** Loads FX rates, price data, and executes accounting workflows.
- **Real-Time Updates:** Optional real-time performance tracking for assets.
- **UI System (PyQt):** Provides a structured graphical interface with interactive components.

---

📌 **WHY THIS STRUCTURE WORKS (AND WHAT WENT WRONG BEFORE)**
Previous versions of this script encountered **execution order issues** that caused:
❌ `super().__init__()` failing due to premature function calls.
❌ `query_sets` and `master_link_sets_df` being modified in multiple places.
❌ `load_fx_data()` and `load_price_data()` running before PyQt initialization.
❌ Global variables conflicting with class attributes.

✅ **HOW WE FIXED IT:**
- **Step 1:** Global paths and master link sets are loaded **before class instantiation**.
- **Step 2:** PyQt (`QApplication`) is initialized **before creating `GWIUnified`**.
- **Step 3:** `super().__init__()` is the **first** operation in `GWIUnified.__init__()`.
- **Step 4:** Data (`fx_data`, `price_data`, `query_sets`) is **fully initialized before use**.
- **Step 5:** No class method runs before its dependencies are properly loaded.

---

📌 **INITIALIZATION SEQUENCE (AVOIDING EXECUTION ISSUES)**
✅ **1. Load Global Configurations**
   - Define all directory paths (`portfolio_directory`, `reports_directory`, `master_link_sets_path`).
   - Load the master link set **once** globally to avoid conflicting state.

✅ **2. Initialize PyQt (`QApplication`)**
   - PyQt requires a valid application instance before creating a `QMainWindow`.

✅ **3. Instantiate `GWIUnified` Class**
   - Call `super().__init__()` **first** to ensure proper UI setup.
   - Load FX & Price data **after** Qt setup completes.
   - Populate `query_sets` and `report_mappings` from the **pre-loaded** master link data.

✅ **4. UI & Event Handling Setup**
   - Ensure all event handlers (`QComboBox` selections, query dropdown changes) are connected **after** UI setup.

✅ **5. Start Optional Real-Time Updates**
   - Enable real-time tracking only when the user selects it (prevents unnecessary processing).

---

📌 **USAGE NOTES & FUTURE MAINTENANCE**
- If modifying **data loading functions**, ensure they do **not execute before PyQt setup**.
- If adding **new UI components**, ensure they are set up **after `super().__init__()`**.
- If changing **query set handling**, avoid reloading `query_sets` multiple times (load once globally).

---

🔧 **TROUBLESHOOTING GUIDE**
❌ **Error: `super().__init__()` crashes**
   ✅ Fix: Ensure no functions execute before `super().__init__()` in `GWIUnified`.

❌ **Error: UI elements don't load properly**
   ✅ Fix: Make sure `setup_ui()` is called at the **end** of `__init__()`.

❌ **Error: Master Link Data is inconsistent**
   ✅ Fix: Ensure `master_link_sets_df` is **only loaded once** and referenced correctly.

❌ **Error: `fx_data` or `price_data` is `None`**
   ✅ Fix: Debug `load_fx_data()` and `load_price_data()` with `print()` statements before usage.

---

📌 **AUTHOR**:
Developed and optimized by **[Hal]**
Last updated: **[Current Date]**
"""


import sys
import os
import time
import pandas as pd
import shutil
import yfinance as yf
import os
from utilities import enforce_sorted_dates, load_price_data, load_fx_data
import socket
from VisibilityProcessing import build_accounting
from bookkeeping import BookkeepingSpace, EventScheduler, StatisticalRepository, SpaceManager, AdministrativeFacility
af =  AdministrativeFacility()
stat_repo = StatisticalRepository()
space_manager = SpaceManager()
from filelock import FileLock
from collections import defaultdict
# Register spaces
space_manager.register_space('sub_ledger', BookkeepingSpace())
space_manager.register_space('general_ledger', BookkeepingSpace())
# Retrieve the registered spaces from the space manager-
sub_ledger = space_manager.get_space('sub_ledger')
general_ledger = space_manager.get_space('general_ledger')
import ast

def read_and_format_csv(file_path, date_column):
    try:
        df = pd.read_csv(file_path, parse_dates=[date_column])
        print(f"Initial format of dates in {file_path}:\n{df[date_column].head()}")
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None


price_data = load_price_data('C:/Users/hjmne/PycharmProjects/chest/refdata/price_master.csv')
fx_data = load_fx_data('C:/Users/hjmne/PycharmProjects/chest/refdata/fx_master.csv')


# Initialize the scheduler with the bookkeeping repository (sub_ledger from space_manager)
scheduler = EventScheduler(sub_ledger)

import pytz




query_sets = {}
# 📌 Paths
portfolio_directory = "BASE_PATH/refdata/pooltest/"
reports_directory = "BASE_PATH/reports/"
master_link_sets_path = "BASE_PATH/refdata/master_link_sets.csv"

SIMULATION_DATE = pd.Timestamp("2023-04-03")

# 📌 Load Portfolio List
portfolio_files = [f.split(".")[0] for f in os.listdir(portfolio_directory) if f.endswith(".csv")]

# ✅ Load Cockpit Sets from Master Link File (outside of class)
cockpit_sets = {}

master_link_sets_path = "BASE_PATH/refdata/master_link_sets.csv"

try:
    master_link_sets_df = pd.read_csv(master_link_sets_path)

    if "CockpitName" in master_link_sets_df.columns:
        for _, row in master_link_sets_df.iterrows():
            cockpit_name = row["CockpitName"]
            cockpit_set_items = [val for val in row.iloc[1:].dropna().tolist()]
            cockpit_sets[cockpit_name] = cockpit_set_items

        print(f"✅ Loaded {len(cockpit_sets)} cockpit sets from {master_link_sets_path}.")
    else:
        print("❌ 'CockpitName' column not found in master_link_sets.csv")

except Exception as e:
    print(f"❌ Error loading cockpit sets: {e}")

from datetime import datetime, timedelta

# ✅ Define market holidays
holidays_and_weekends = set([
    '2022-01-01', '2022-01-17', '2022-02-21', '2022-05-30', '2022-06-19',
    '2022-07-04', '2022-09-05', '2022-11-24', '2022-12-25',
    '2023-01-02', '2023-01-16', '2023-02-20', '2023-05-29', '2023-06-19',
    '2023-07-04', '2023-09-04', '2023-10-09', '2023-11-10', '2023-11-23',
    '2023-12-25'
])

# ✅ Convert to datetime objects
holidays_and_weekends = {datetime.strptime(date, "%Y-%m-%d").date() for date in holidays_and_weekends}

def get_last_business_day(start_date, days_back):
    """
    Moves back `days_back` business days from `start_date`, ensuring it avoids weekends and holidays.
    """
    current_date = start_date

    for _ in range(days_back):
        current_date -= timedelta(days=1)
        while current_date.weekday() >= 5 or current_date in holidays_and_weekends:
            current_date -= timedelta(days=1)  # Keep subtracting if it's a weekend/holiday

    return current_date




from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDateTimeEdit,
    QLineEdit, QTabWidget, QTableView,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox,
    QAbstractScrollArea, QVBoxLayout, QCheckBox, QComboBox,
    QWidget, QScrollArea, QDialog, QLabel, QDateEdit, QPushButton
)

from PySide6.QtGui import (
    QFont, QIcon, QColor, QPixmap, QBrush, QStandardItem, QStandardItemModel
)

from PySide6.QtCore import Qt, QCoreApplication, QTime, QDate, QDateTime



class ProcessChangesDialog(QDialog):
    def __init__(self, parent, portfolio_name):
        super().__init__(parent)
        self.setWindowTitle("Process Changes")

        layout = QVBoxLayout(self)

        # ✅ Portfolio Label
        layout.addWidget(QLabel(f"Processing Portfolio: {portfolio_name}"))

        # ✅ Default Dates
        default_start = QDate(2023, 1, 3)
        default_cutoff = QDate(2023, 3, 31)
        default_knowledge = QDate(2023, 3, 31)

        # ✅ Main Period Inputs
        self.start_date_edit = QDateEdit()
        self.cutoff_date_edit = QDateEdit()
        self.knowledge_date_edit = QDateEdit()

        for edit in [self.start_date_edit, self.cutoff_date_edit, self.knowledge_date_edit]:
            edit.setCalendarPopup(True)

        self.start_date_edit.setDate(default_start)
        self.cutoff_date_edit.setDate(default_cutoff)
        self.knowledge_date_edit.setDate(default_knowledge)

        layout.addWidget(QLabel("Start Date:"))
        layout.addWidget(self.start_date_edit)
        layout.addWidget(QLabel("Cutoff Date:"))
        layout.addWidget(self.cutoff_date_edit)
        layout.addWidget(QLabel("Knowledge Date:"))
        layout.addWidget(self.knowledge_date_edit)

        # ✅ Prior Period Inputs (for Knowledge Drift)
        self.prior_start_edit = QDateEdit()
        self.prior_cutoff_edit = QDateEdit()
        self.prior_knowledge_edit = QDateEdit()

        for edit in [self.prior_start_edit, self.prior_cutoff_edit, self.prior_knowledge_edit]:
            edit.setCalendarPopup(True)

        self.prior_start_edit.setDate(default_start)
        self.prior_cutoff_edit.setDate(default_cutoff)
        self.prior_knowledge_edit.setDate(default_knowledge)

        layout.addWidget(QLabel("Prior Period Start:"))
        layout.addWidget(self.prior_start_edit)
        layout.addWidget(QLabel("Prior Period Cutoff:"))
        layout.addWidget(self.prior_cutoff_edit)
        layout.addWidget(QLabel("Prior Knowledge Cutoff:"))
        layout.addWidget(self.prior_knowledge_edit)

        # ✅ Calendar Type
        self.calendar_selection = QComboBox()
        self.calendar_selection.addItems(["Open", "Daily", "Monthly", "master_query_file"])
        layout.addWidget(QLabel("Select Calendar:"))
        layout.addWidget(self.calendar_selection)

        # ✅ Checkboxes
        self.mark_daily_checkbox = QCheckBox("Mark Daily")
        self.include_marks_checkbox = QCheckBox("Include Marks")
        layout.addWidget(self.mark_daily_checkbox)
        layout.addWidget(self.include_marks_checkbox)

        # ✅ Confirm Button
        confirm_button = QPushButton("Start Processing")
        confirm_button.clicked.connect(self.accept)
        layout.addWidget(confirm_button)

        self.setLayout(layout)

    # ✅ Getters for retrieving the selected dates
    def get_start_date(self):
        return self.start_date_edit.date().toString("yyyy-MM-dd")

    def get_cutoff_date(self):
        return self.cutoff_date_edit.date().toString("yyyy-MM-dd")

    def get_knowledge_date(self):
        return self.knowledge_date_edit.date().toString("yyyy-MM-dd")

    def get_prior_start_date(self):
        return self.prior_start_edit.date().toString("yyyy-MM-dd")

    def get_prior_cutoff_date(self):
        return self.prior_cutoff_edit.date().toString("yyyy-MM-dd")

    def get_prior_knowledge_date(self):
        return self.prior_knowledge_edit.date().toString("yyyy-MM-dd")

    def get_calendar(self):
        return self.calendar_selection.currentText()

    def is_mark_daily_checked(self):
        return self.mark_daily_checkbox.isChecked()

    def is_include_marks_checked(self):
        return self.include_marks_checkbox.isChecked()

class GWIUnified(QMainWindow):
    def __init__(self):
        super().__init__()

        # ✅ Define Paths
        self.base_directory = "BASE_PATH/"
        self.portfolio_directory = os.path.join(self.base_directory, "refdata/pooltest/")
        self.reports_directory = os.path.join(self.base_directory, "reports/")
        self.master_link_sets_path = os.path.join(self.base_directory, "refdata/master_link_sets.csv")
        self.current_tab_name = None
        self.table_views = {}

        # ✅ Define Gold File Tabs
        self.gold_file_tabs = {"Events", "Prices", "FXRates", "BondInfo", "InvestmentMaster"}

        # ✅ File Mappings
        self.tab_to_master_file = {
            "Events": os.path.join(self.portfolio_directory, "{portfolio_name}.csv"),
            "Prices": os.path.join(self.base_directory, "refdata/price_master.csv"),
            "FXRates": os.path.join(self.base_directory, "refdata/fx_master.csv"),
            "InvestmentMaster": os.path.join(self.base_directory, "refdata/investment_master.csv"),
            "BondInfo": os.path.join(self.base_directory, "refdata/bond_info.csv"),
            "ChartofAccounts": os.path.join(self.base_directory, "refdata/chart_of_accounts.csv"),
        }

        # ✅ Define Simulation Date & Performance Intervals
        self.SIMULATION_DATE = pd.Timestamp("2023-04-03")
        self.intervals = {
            "Today": 1,
            "Last Week + Today": 5,
            "Last Month + Today": 20,
            "Last Quarter + Today": 60
        }

        # ✅ Initialize Storage
        self.price_data = None
        self.positions = {}
        self.current_data = None
        self.current_tab_name = None
        self.table_views = {}

        # ✅ Load Portfolio List
        self.portfolio_files = [
            f.split(".")[0] for f in os.listdir(self.portfolio_directory) if f.endswith(".csv")
        ]

        # ✅ Load Cockpit Sets (replaces query_sets)
        self.cockpit_sets = {}
        try:
            master_link_sets_df = pd.read_csv(self.master_link_sets_path)
            if "CockpitName" in master_link_sets_df.columns:
                self.cockpit_sets = {
                    row["CockpitName"]: [val for val in row.iloc[1:].dropna().tolist()]
                    for _, row in master_link_sets_df.iterrows()
                }
                print(f"✅ Cockpit Sets Loaded: {list(self.cockpit_sets.keys())}")
            else:
                print("❌ Column 'CockpitName' not found in master_link_sets.csv")
        except Exception as e:
            print(f"❌ Error loading cockpit sets from {self.master_link_sets_path}: {e}")

        # ✅ Setup UI
        self.setup_ui()

        # ✅ Init Flags & Cache
        self.enable_real_time_updates = True
        self.real_time_cache = {}
        self.filtered_dataframes = {}

        # # ✅ Connect Dropdown Handler
        # self.query_dropdown.currentIndexChanged.connect(self.handle_cockpit_selection)

        print("⏳ Waiting for user to select Real-Time Performance before starting updates...")

    def get_portfolio_price_data(self, portfolio_name):
        """Returns filtered price data for the given portfolio."""
        if self.price_data is None or self.price_data.empty:
            print("⚠ WARNING: Price data is empty. Using default empty DataFrame.")
            return pd.DataFrame()

        try:
            if "portfolio" in self.price_data.columns:
                filtered_data = self.price_data[self.price_data["portfolio"] == portfolio_name]
                print(f"✅ Loaded price data for {portfolio_name} ({len(filtered_data)} rows).")
                return filtered_data
            else:
                print("⚠ WARNING: 'portfolio' column not found in price data. Returning full dataset.")
                return self.price_data
        except KeyError as e:
            print(f"❌ Error filtering price data: {e}")
            return self.price_data

    def get_portfolio_fx_data(self):
        """Returns FX rates for the required date range."""
        if not self.fx_data:
            print("⚠ WARNING: FX data is empty. Returning empty dictionary.")
            return {}

        try:
            relevant_dates = {
                datetime.strptime("2023-01-01", "%Y-%m-%d"),
                datetime.strptime("2023-03-31", "%Y-%m-%d"),
            }

            filtered_fx = {
                currency: {date: rate for date, rate in rates.items() if date in relevant_dates}
                for currency, rates in self.fx_data.items()
            }

            print(f"✅ Filtered FX data: {len(filtered_fx)} currencies loaded.")
            return filtered_fx
        except Exception as e:
            print(f"❌ Error filtering FX data: {e}")
            return {}


    def format_data(self, value):
        """Ensure all values are formatted correctly before passing to QStandardItem."""
        import datetime

        if pd.isna(value) or value is pd.NaT:  # ✅ Handle NaT and NaN
            return ""  # Return an empty string instead of attempting strftime
        if isinstance(value, (pd.Timestamp, datetime.datetime)):
            return value.strftime('%Y-%m-%d %H:%M:%S')  # Convert datetime to string
        elif isinstance(value, float):
            return f"{value:,.2f}"  # Format numbers properly
        elif isinstance(value, (int, str)):
            return str(value)  # Convert to string
        else:
            return ""  # Handle None values safely

    def deformat_data(self, value):
        """Removes formatting (commas, currency symbols, and percentages) and converts to a raw number."""

        if isinstance(value, (int, float)):
            return value  # ✅ Already a number, return as-is

        if not isinstance(value, str) or value.strip() == "":
            return ""  # ✅ Keep empty values unchanged

        # ✅ Remove formatting characters
        value = value.replace(",", "")  # Remove commas
        value = value.replace("$", "")  # Remove currency symbols
        value = value.replace("%", "")  # Remove percentage symbols

        try:
            # ✅ Convert to float if decimal exists, else convert to integer
            return float(value) if "." in value else int(value)
        except ValueError:
            return value  # ✅ Return original if conversion fails

    def on_save_clicked(self):
        print("🔥 Save button clicked")

        current_index = self.tab_widget.currentIndex()
        current_tab_name = self.tab_widget.tabText(current_index)

        if current_tab_name not in self.tab_to_master_file:
            QMessageBox.warning(self, "Cannot Save", f"Tab '{current_tab_name}' is not a gold-backed file.")
            return

        view = self.table_views.get(current_tab_name)
        if view is None:
            QMessageBox.warning(self, "Save Error", f"No view found for tab '{current_tab_name}'.")
            return

        model = view.model()
        if model is None:
            QMessageBox.warning(self, "Save Error", f"No model attached to tab '{current_tab_name}'.")
            return

        try:
            df = self.extract_data_from_model(model)

            portfolio_name = self.portfolio_dropdown.currentText()
            filepath_template = self.tab_to_master_file[current_tab_name]

            # 🧠 Substitution Logic
            if "{portfolio_name}" in filepath_template:
                filepath = filepath_template.format(portfolio_name=portfolio_name)
            else:
                filepath = filepath_template

            self.save_changes(df, filepath)
            QMessageBox.information(self, "Save Successful", f"Changes saved to {filepath}")
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))
            import traceback
            traceback.print_exc()

    def setup_ui(self):
        self.setWindowTitle("VISIBILITY - Graphical Workflow Interface (GWI)")
        self.setMinimumSize(1200, 800)

        # Scrollable container
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        # Container widget and main layout
        container = QWidget()
        self.layout = QVBoxLayout(container)  # ✅ Set layout and attach to container

        # Logo (Optional - comment out if causing issues)
        self.logo_label = QLabel()
        logo_path = "BASE_PATH/visibility.png"
        pixmap = QPixmap(logo_path)
        if not pixmap.isNull():
            resized_pixmap = pixmap.scaled(250, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_label.setPixmap(resized_pixmap)
        else:
            self.logo_label.setText("Logo Not Found")
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.logo_label)

        # Title label
        self.title_label = QLabel("VISIBILITY - Graphical Workflow Interface (GWI)")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.title_label)

        # Set scroll and main container
        scroll.setWidget(container)
        self.setCentralWidget(scroll)

        # Apply stylesheet
        self.setStyleSheet("""
            QWidget {
                background-color: rgb(25, 25, 112);
                color: white;
            }
            QLabel {
                color: white;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton {
                background-color: white;
                color: black;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: lightgray;
            }
            QTableView {
                background-color: white;
                color: black;
                gridline-color: lightgray;
                selection-background-color: rgb(173, 216, 230);
                selection-color: black;
            }
            QHeaderView::section {
                background-color: rgb(70, 130, 180);
                color: white;
                padding: 4px;
                border: 1px solid white;
            }
            QTableView::item:selected {
                background-color: rgb(173, 216, 230);
                color: black;
            }
            QComboBox {
                background-color: white;
                color: black;
            }
        """)

        # Logo
        # self.logo_label = QLabel()
        # logo_path = "BASE_PATH/visibility.png"
        # pixmap = QPixmap(logo_path)
        # if not pixmap.isNull():
        #     resized_pixmap = pixmap.scaled(250, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        #     self.logo_label.setPixmap(resized_pixmap)
        # else:
        #     self.logo_label.setText("Logo Not Found")
        # self.logo_label.setAlignment(Qt.AlignCenter)
        # self.layout.addWidget(self.logo_label)

        # Title
        self.title_label = QLabel("VISIBILITY - Graphical Workflow Interface (GWI)")
    #    self.title_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.title_label)

        # Top-right button bar
        from PySide6.QtWidgets import QHBoxLayout
        top_right_layout = QHBoxLayout()
        top_right_layout.addStretch(1)

        icon_path = "BASE_PATH/refdata/ticker.jpg"
        self.real_time_button = QPushButton()
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(75, 75, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon = QIcon(pixmap)
            self.real_time_button.setIcon(icon)
            self.real_time_button.setIconSize(self.real_time_button.size())
        self.real_time_button.setFixedSize(50, 50)
        self.real_time_button.setToolTip("📊 View Real-Time Performance")
        self.real_time_button.setStyleSheet("QPushButton { border: none; padding: 0px; }")
        top_right_layout.addWidget(self.real_time_button)
        self.layout.addLayout(top_right_layout)

        # Dropdowns
        self.portfolio_dropdown = QComboBox()
        self.portfolio_dropdown.addItems(self.portfolio_files)
        self.layout.addWidget(self.portfolio_dropdown)

        self.query_dropdown = QComboBox()
        self.query_dropdown.addItems(list(self.cockpit_sets.keys()))
        self.query_dropdown.currentIndexChanged.connect(self.handle_cockpit_selection)
        self.layout.addWidget(self.query_dropdown)

        # Button bar
        self.buttons_layout = QHBoxLayout()

        self.load_button = QPushButton("Load Cockpit Set")
        self.load_button.clicked.connect(self.execute_load_and_filter)
        self.buttons_layout.addWidget(self.load_button)

        self.process_changes_button = QPushButton("✅ Process Changes")
        self.process_changes_button.clicked.connect(self.open_process_changes_dialog)
        self.buttons_layout.addWidget(self.process_changes_button)

        self.save_button = QPushButton("Save Changes")
        self.save_button.clicked.connect(self.on_save_clicked)
        self.buttons_layout.addWidget(self.save_button)

        self.layout.addLayout(self.buttons_layout)

        # Filter input
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("🔍 Type to filter data...")
        self.filter_input.textChanged.connect(self.store_filter_query)
        self.layout.addWidget(self.filter_input)

        # Tabs
        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self.on_tab_selected)
        self.layout.addWidget(self.tab_widget)

        # Finalize scrollable container
        scroll.setWidget(container)
        self.setCentralWidget(scroll)



    from PySide6.QtWidgets import QMessageBox
    import time

    def open_process_changes_dialog(self):
        """Opens the Process Changes dialog and starts processing based on user inputs."""
        portfolio_name = self.portfolio_dropdown.currentText()

        if not portfolio_name:
            QMessageBox.warning(self, "Warning", "Please select a portfolio before processing.")
            return

        # ✅ Open the dialog
        dialog = ProcessChangesDialog(self, portfolio_name)

        if dialog.exec():
            # ✅ Get all dates and options
            start_date = dialog.get_start_date()
            cutoff_date = dialog.get_cutoff_date()
            knowledge_date = dialog.get_knowledge_date()
            prior_start = dialog.get_prior_start_date()
            prior_cutoff = dialog.get_prior_cutoff_date()
            prior_knowledge = dialog.get_prior_knowledge_date()
            calendar = dialog.get_calendar()
            mark_daily = dialog.is_mark_daily_checked()
            include_marks = dialog.is_include_marks_checked()

            # ✅ Show interim "Processing..." dialog
            self.processing_box = QMessageBox(self)
            self.processing_box.setWindowTitle("Processing")
            self.processing_box.setText("⏳ Processing in progress. Please wait...")
            self.processing_box.setStandardButtons(QMessageBox.NoButton)
            self.processing_box.show()

            QCoreApplication.processEvents()  # Allow UI to update

            try:
                # ✅ Call main processing logic
                self.process_portfolio(
                    portfolio_name,
                    start_date=start_date,
                    cutoff_date=cutoff_date,
                    knowledge_date=knowledge_date,
                    mark_daily=mark_daily,
                    include_marks=include_marks,
                    calendar=calendar,
                    prior_start_date=prior_start,
                    prior_cutoff_date=prior_cutoff,
                    prior_knowledge_date=prior_knowledge
                )

                # ✅ Update and show success message
                self.processing_box.setText("✅ Processing Complete!")
                self.processing_box.setStandardButtons(QMessageBox.Ok)
                self.processing_box.exec()

            except Exception as e:
                self.processing_box.hide()
                QMessageBox.critical(self, "Processing Failed", f"❌ Error: {str(e)}")

    def on_tab_selected(self, index):
        """Tracks the currently selected tab and updates the active tab name."""
        if index < 0:  # No valid tab selected
            return

        self.current_tab_name = self.tab_widget.tabText(index)
        print(f"📌 DEBUG: User switched to tab {self.current_tab_name}")

        # ✅ Only track Gold Files for modification
        if self.current_tab_name in self.gold_file_tabs:
            print(f"✅ User selected a Gold File tab: {self.current_tab_name}")

    def update_current_data_from_ui(self):
        """Updates current_data from the currently active tab before saving."""
        if self.current_tab_name not in self.gold_file_tabs:
            return  # ✅ Only update for Gold Files

        model = self.table_view.model()
        self.current_data = self.extract_data_from_model(model)

        print(f"📌 DEBUG: current_data updated from UI for {self.current_tab_name}")


    def execute_load_and_filter(self, cockpit_name=None):
        cockpit_name = cockpit_name or self.query_dropdown.currentText()
        print(f"🔄 Switching to Cockpit: {cockpit_name}")

        self.tab_widget.clear()  # remove previous tabs

        self.load_standard_query_set(
            selected_portfolio=self.portfolio_dropdown.currentText(),
            cockpit_name=cockpit_name,
            period_start=self.period_start if hasattr(self, 'period_start') else pd.to_datetime("2023-01-03"),
            period_end=self.period_end if hasattr(self, 'period_end') else pd.to_datetime("2023-03-31")
        )

        # 🧹 Optional: Clear filter between runs
        self.filter_query = ""

        if cockpit_name == "Real Time Performance":
            self.enable_real_time_updates = True
            self.start_real_time_updates()
        else:
            self.enable_real_time_updates = False

        if hasattr(self, 'filter_query') and self.filter_query:
            print(f"🔍 Applying stored filter: {self.filter_query}")
            self.apply_stored_filter()
        else:
            print("🔄 No filter query stored. Showing full dataset.")

    def update_dataframe_from_ui(self):
        """Writes UI table edits back to the DataFrame before saving."""
        if not hasattr(self, "table_view") or self.table_view is None:  # ✅ Ensure table exists
            print("❌ ERROR: No table found to update data from UI!")
            return

        model = self.table_view.model()  # ✅ Get the table model

        if model is None:
            print("❌ ERROR: Table model not initialized!")
            return

        # ✅ Ensure the DataFrame reference exists before updating
        if not hasattr(self, "current_dataframe") or self.current_dataframe is None:
            print("❌ ERROR: No DataFrame linked to UI!")
            return

        # ✅ Apply changes back to DataFrame
        for row in range(model.rowCount()):
            for col in range(model.columnCount()):
                index = model.index(row, col)
                value = model.data(index, Qt.DisplayRole)
                self.current_dataframe.iat[row, col] = value  # ✅ Update the DataFrame

        print("✅ UI changes applied to DataFrame successfully.")

    def validate_query_selection(self):
        """Ensures a valid selection is made before allowing data load."""
        selected_query = self.query_dropdown.currentText()
        if not selected_query:
            print("⚠ No query set selected.")
            return
        print(f"✅ Query set selected: {selected_query}")  # Debugging


    def validate_dataframe(self, df, expected_columns):
        """Ensure DataFrame integrity before saving."""
        missing_cols = set(expected_columns) - set(df.columns)
        if missing_cols:
            raise ValueError(f"❌ ERROR: Missing columns: {missing_cols}")

        if df.duplicated().any():
            print(f"⚠ WARNING: Duplicate rows detected. Removing duplicates...")
            df = df.drop_duplicates()

        if df.isna().any().any():
            print(f"⚠ WARNING: NaN values detected! Replacing with 'N/A'.")
            df = df.fillna("N/A")

        return df

    import os
    import shutil
    from filelock import FileLock

    def save_changes(self, df, filepath):
        """Save CSV safely with rollback and file locking, ensuring numbers are unformatted before saving."""
        backup_path = filepath + ".bak"
        lock = FileLock(filepath + ".lock")

        with lock:
            print(f"🔒 Lock acquired for {filepath}")

            if os.path.exists(filepath):
                shutil.copy(filepath, backup_path)
                print(f"📦 Backup created: {backup_path}")

            try:
                df = self.validate_dataframe(df, df.columns)

                # ✅ Deformat numeric values before saving
                for col in df.columns:
                    df[col] = df[col].apply(self.deformat_data)  # Convert formatted numbers to raw values

                df.to_csv(filepath, index=False)
                print(f"✅ Successfully saved to {filepath}")

            except Exception as e:
                print(f"❌ ERROR: Failed to save data to '{filepath}': {e}")

                if os.path.exists(backup_path):
                    shutil.copy(backup_path, filepath)
                    print(f"🔄 Rollback applied: Restored {filepath} from backup.")

            finally:
                print(f"🔓 Lock released for {filepath}")

    def handle_cockpit_selection(self):
        """Handles cockpit selection and triggers real-time updates only if applicable."""
        cockpit_name = self.query_dropdown.currentText()
        print(f"🔄 Cockpit Selected: {cockpit_name}")

        if cockpit_name == "Real Time Performance":
            print("🚀 Real-Time Performance selected! Activating live updates...")
            self.enable_real_time_updates = True
            self.start_real_time_updates()
        else:
            print("⏳ Non-real-time cockpit selected. Skipping Yahoo Finance updates.")
            self.enable_real_time_updates = False

    from dateutil.parser import parse

    def process_portfolio(self, portfolio_name, start_date, cutoff_date, knowledge_date,
                          mark_daily, include_marks, calendar,
                          prior_start_date=None, prior_cutoff_date=None, prior_knowledge_date=None):
        """
        Processes the portfolio with the selected calendar type and performs both static and drift comparisons
        if prior dates are supplied. All journals are posted into sub_ledger, and comparison reports are written.
        """
        print(f"\n🚀 Processing Portfolio: {portfolio_name} with Calendar Type: {calendar}")

        from datetime import datetime
        import pickle, os
        import pandas as pd
        from pathlib import Path
        from bookkeeping import Journals
        from VisibilityProcessing import build_accounting

        try:
            # ✅ Parse all date inputs
            current_start = datetime.strptime(start_date, "%Y-%m-%d")
            current_cutoff = datetime.strptime(cutoff_date, "%Y-%m-%d")
            current_knowledge = datetime.strptime(knowledge_date, "%Y-%m-%d")

            if prior_start_date and prior_cutoff_date and prior_knowledge_date:
                prior_start = datetime.strptime(prior_start_date, "%Y-%m-%d")
                prior_cutoff = datetime.strptime(prior_cutoff_date, "%Y-%m-%d")
                prior_knowledge = datetime.strptime(prior_knowledge_date, "%Y-%m-%d")
            else:
                prior_start = current_start
                prior_cutoff = current_cutoff
                prior_knowledge = current_knowledge

            # ✅ Paths
            base_dir = f"C:/Users/hjmne/PycharmProjects/chest/funds/{portfolio_name}/Open/periods"
            report_dir = Path("C:/Users/hjmne/PycharmProjects/chest/reports")
            report_dir.mkdir(parents=True, exist_ok=True)
            file_path = os.path.join(base_dir, "mqs.pkl")
            backup_path = os.path.join(base_dir, "mqs_before.pkl")
            report_path_static = report_dir / f"{portfolio_name}_KnowledgeStatic.xlsx"
            report_path_drift = report_dir / f"{portfolio_name}_KnowledgeDrift.xlsx"

            # ✅ First pass (current dates)
            sub_ledger.reset_all()
            build_accounting({
                "portfolio_name": portfolio_name,
                "current_period_start": current_start,
                "current_period_cutoff": current_cutoff,
                "current_period_knowledge": current_knowledge,
                "calendar": calendar,
                "tdate_fx": None,
                "general_ledger": None
            }, sub_ledger, scheduler, stat_repo, price_data, fx_data, mark_daily, include_marks, calendar)

            # ✅ Save current as after
            if os.path.exists(file_path):
                os.replace(file_path, backup_path)
                print(f"📦 Old journal file backed up to: {backup_path}")
            else:
                print("ℹ️ No existing journal file found to back up.")

            with open(file_path, "wb") as f:
                pickle.dump(sub_ledger.journal_entries, f)
            print(f"✅ New journals saved to: {file_path}")

            # ✅ Second pass (prior dates)
            sub_ledger.reset_all()
            build_accounting({
                "portfolio_name": portfolio_name,
                "current_period_start": prior_start,
                "current_period_cutoff": prior_cutoff,
                "current_period_knowledge": prior_knowledge,
                "calendar": calendar,
                "tdate_fx": None,
                "general_ledger": None
            }, sub_ledger, scheduler, stat_repo, price_data, fx_data, mark_daily, include_marks, calendar)

            with open(backup_path, "wb") as f:
                pickle.dump(sub_ledger.journal_entries, f)
            print(f"✅ Prior journals saved to: {backup_path}")

            # ✅ Load and diff
            with open(file_path, "rb") as f_after:
                after = pickle.load(f_after)
            with open(backup_path, "rb") as f_before:
                before = pickle.load(f_before)

            def to_obj(lst):
                if isinstance(lst, list) and isinstance(lst[0], dict):
                    return [Journals.from_dict(j) for j in lst]
                return lst

            old_journals = to_obj(before)
            new_journals = to_obj(after)

            def static_key(j):
                return (
                    j.portfolio, j.investment, j.lotid, j.tax_date, j.ls, j.location,
                    j.financial_account, j.tradedate, j.settledate, j.entry_type,
                    j.quantity, j.local, j.book
                )

            def drift_key(j):
                return (
                    j.portfolio, j.investment, j.lotid, j.tax_date, j.ls, j.location,
                    j.financial_account, j.tradedate, j.settledate, j.entry_type,
                    j.tranid, j.sequence_number, j.quantity, j.local, j.book
                )

            old_static = {static_key(j): j for j in old_journals}
            new_static = {static_key(j): j for j in new_journals}
            old_drift = {drift_key(j): j for j in old_journals}
            new_drift = {drift_key(j): j for j in new_journals}

            # ✅ Static Comparison
            static_diff = []
            for k in new_static.keys() - old_static.keys():
                static_diff.append({"ChangeType": "Added", "JournalEntry": str(new_static[k])})
            for k in old_static.keys() - new_static.keys():
                static_diff.append({"ChangeType": "Removed", "JournalEntry": str(old_static[k])})
            if not static_diff:
                static_diff.append({"ChangeType": "None", "JournalEntry": "No differences found."})
            pd.DataFrame(static_diff).to_excel(report_path_static, index=False)
            print(f"📄 KnowledgeStatic report written to: {report_path_static}")

            # ✅ Knowledge Drift Comparison
            drift_diff = []
            for k in new_drift.keys() - old_drift.keys():
                drift_diff.append({"ChangeType": "Added", "JournalEntry": str(new_drift[k])})
            for k in old_drift.keys() - new_drift.keys():
                drift_diff.append({"ChangeType": "Removed", "JournalEntry": str(old_drift[k])})
            if not drift_diff:
                drift_diff.append({"ChangeType": "None", "JournalEntry": "No knowledge drift found."})
            pd.DataFrame(drift_diff).to_excel(report_path_drift, index=False)
            print(f"📄 KnowledgeDrift report written to: {report_path_drift}")

            print(f"✅ Finished dual-period journal comparison for: {portfolio_name}")

        except Exception as e:
            print(f"❌ Error processing portfolio: {e}")

    def refresh_query_set(self):
        """Reloads query sets after processing to include any newly generated reports."""
        print("🔄 Refreshing Query Sets...")

        master_link_sets_path = "BASE_PATH/refdata/master_link_sets.csv"
        master_link_sets_df = pd.read_csv(master_link_sets_path)

        self.query_sets = {}  # ✅ Reset query sets

        if "Set Name" in master_link_sets_df.columns:
            for _, row in master_link_sets_df.iterrows():
                set_name = row["Set Name"]
                reports = [val for val in row[1:].dropna().tolist()]
                self.query_sets[set_name] = reports

        # ✅ Update dropdown with new query sets
        self.query_dropdown.clear()
        self.query_dropdown.addItems(list(self.query_sets.keys()))

        print(f"✅ Updated Query Sets: {self.query_sets.keys()}")
        QMessageBox.information(self, "Query Set Updated", "Query sets refreshed successfully.")

    import time  # Ensure this is imported at the top

    def load_selected_unified_query_set(self):
        """Loads the query set, assigns correct filepaths, and ensures saving works for all gold files."""

        selected_query_set = self.query_dropdown.currentText()
        selected_portfolio = self.portfolio_dropdown.currentText()

        if not selected_portfolio or not selected_query_set:
            print("⚠ No portfolio or query set selected.")
            return

        print(f"📌 DEBUG: Loading Query Set '{selected_query_set}' for Portfolio '{selected_portfolio}'")

        if selected_query_set == "Real Time Performance":
            print("🚀 Real-Time Performance selected! Activating live updates...")
            self.enable_real_time_updates = True
            self.load_real_time_performance(selected_portfolio)
            self.current_data = None
            self.current_filepath = None  # ❌ Real-time performance does not save to a file
        else:
            print("📊 Standard Query Set Selected. Loading from CSV...")
            self.enable_real_time_updates = False

            # ✅ Load Data as DataFrame
            self.load_standard_query_set(
                selected_portfolio,
                selected_query_set,
                period_start=self.period_start if hasattr(self, 'period_start') else pd.to_datetime("2023-01-03"),
                period_end=self.period_end if hasattr(self, 'period_end') else pd.to_datetime("2023-03-31")
            )
            self.current_data = None  # optional if you need it for Save

            # ✅ Assign file path dynamically based on the active tab
            # ✅ Assign correct filepath by replacing {portfolio_name}
            if self.current_tab_name in self.tab_to_master_file:
                self.current_filepath = self.tab_to_master_file[self.current_tab_name].replace("{portfolio_name}",
                                                                                               selected_portfolio)
            else:
                self.current_filepath = f{BASE_PATH}/refdata/pooltest/{selected_portfolio}.csv"

            print(f"📌 DEBUG: self.current_filepath SET TO: {self.current_filepath}")

        print(f"✅ Data Loaded: {self.current_data.shape if self.current_data is not None else 'No Data'}")
        print(f"✅ Save Path Set: {self.current_filepath}")

    def load_standard_query_set(self, selected_portfolio, cockpit_name, period_start=None, period_end=None):
        """Loads all items in the selected cockpit (gold files, static reports, query cards)."""
        print(f"📊 Loading Cockpit: {cockpit_name} for Portfolio: {selected_portfolio}")

        if cockpit_name not in self.cockpit_sets:
            print(f"⚠ WARNING: Cockpit '{cockpit_name}' not found in cockpit_sets.")
            return

        for cockpit_item in self.cockpit_sets[cockpit_name]:
            file_path = None  # ✅ reset on each loop

            if cockpit_item.startswith("QueryGet_"):
                query_card_name = cockpit_item
                stripped_name = query_card_name.replace("QueryGet_", "", 1)

                print(f"🧠 Detected query card: {query_card_name}")
                try:
                    # Use default period unless passed in
                    period_start = period_start or pd.to_datetime("2023-01-01")
                    period_end = period_end or pd.to_datetime("2023-03-31")

                    from master_queries_new import run_query_from_card

                    df = run_query_from_card(
                        card_name=query_card_name,
                        portfolio=selected_portfolio,
                        period_start=period_start,
                        period_end=period_end
                    )

                    if df is not None and isinstance(df, pd.DataFrame):
                        self.populate_tabs(query_card_name, df)

                        # ✅ Optional: Save to temp Excel for review/export
                        temp_path = os.path.join(self.reports_directory, "temp_query_result.xlsx")
                        df.to_excel(temp_path, index=False)
                        print(f"📝 Temp query result saved to: {temp_path}")
                    else:
                        print(f"⚠ No data returned from query: {query_card_name}")

                except Exception as e:
                    print(f"❌ Error executing query card '{query_card_name}': {e}")
                continue  # ✅ Skip the rest of the loop — this was a query card

            # ✅ Static or Gold Files
            elif cockpit_item == "Events":
                file_path = os.path.join(self.portfolio_directory, f"{selected_portfolio}.csv")
            elif cockpit_item in self.tab_to_master_file:
                file_path = self.tab_to_master_file[cockpit_item]
            else:
                # Fallback to reports folder (e.g., custom exports)
                file_path = os.path.join(self.reports_directory, f"{selected_portfolio}_{cockpit_item}.xlsx")

            # ✅ Replace any placeholders
            if file_path and "{portfolio_name}" in file_path:
                file_path = file_path.format(portfolio_name=selected_portfolio)

            if file_path and not os.path.exists(file_path):
                print(f"⚠ WARNING: Missing file at {file_path}, skipping.")
                continue

            try:
                if file_path.endswith(".csv"):
                    print(f"📤 Loading CSV: {file_path}...")
                    df = pd.read_csv(file_path)
                else:
                    print(f"📤 Loading Excel: {file_path}...")
                    df = pd.read_excel(file_path, engine="openpyxl")

                print(f"✅ Loaded {cockpit_item} ({len(df)} rows). Sending to UI...")
                self.populate_tabs(cockpit_item, df)

            except Exception as e:
                print(f"❌ ERROR loading '{cockpit_item}': {e}")

        print(f"✅ Finished Loading Cockpit: {cockpit_name}")

    def on_table_edit(self, item):
        """Detects when a table cell is edited and updates current_data accordingly."""

        if not hasattr(self, 'current_tab_name') or self.current_tab_name not in self.table_views:
            print(f"❌ ERROR: No valid table found for tab '{self.current_tab_name}'!")
            return

        table_view = self.table_views[self.current_tab_name]  # ✅ Get the correct table view
        model = table_view.model()

        # ✅ Extract the updated data from the model
        self.current_data = self.extract_data_from_model(model)

        print(
            f"📌 DEBUG: current_data updated in on_table_edit() → {self.current_data.shape[0]} rows, {self.current_data.shape[1]} columns")

    def extract_data_from_model(self, model):
        """Extracts data from the table model into a DataFrame."""

        if model is None:

            print("❌ ERROR: Model is None. Cannot extract data.")
            return None

        row_count = model.rowCount()
        col_count = model.columnCount()

        if row_count == 0 or col_count == 0:
            print("❌ ERROR: Model has no data. Extraction failed.")
            return None

        # ✅ Extract the data from the table model
        data = []
        for row in range(row_count):
            row_data = []
            for col in range(col_count):
                index = model.index(row, col)
                row_data.append(model.data(index, Qt.DisplayRole))
            data.append(row_data)

        # ✅ Create a DataFrame from extracted data
        df = pd.DataFrame(data, columns=[model.headerData(col, Qt.Horizontal) for col in range(col_count)])

        print(f"📌 DEBUG: extract_data_from_model() extracted {df.shape[0]} rows, {df.shape[1]} columns")

        return df

    def populate_tabs(self, tab_name, dataframe):
        """Creates a tab with an auto-sized, formatted, and sortable table view."""

        # ✅ Store the table view per tab
        tab = QWidget()
        layout = QVBoxLayout(tab)
        table_view = QTableView()
        self.table_views[tab_name] = table_view  # Track table view for this tab

        # ✅ Create a new model
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(dataframe.columns.tolist())

        # ✅ Populate the model with formatted data
        for row_index, row in dataframe.iterrows():
            formatted_items = []
            for col in dataframe.columns:
                raw_value = row[col]

                # 🔥 Ensure datetime values are properly converted to strings
                if isinstance(raw_value, pd.Timestamp):
                    formatted_value = raw_value.strftime('%Y-%m-%d %H:%M:%S')  # Customize format if needed
                else:
                    formatted_value = self.format_data(raw_value)  # Format other data types as needed

                item = QStandardItem(formatted_value)
                item.setFont(QFont("Arial", 10))
                item.setEditable(True)  # ✅ Allow editing

                # ✅ Set alternating row colors
                row_color_1 = QColor(255, 255, 255)  # White
                row_color_2 = QColor(240, 248, 255)  # Light Blue (Alternating Row)
                item.setBackground(QBrush(row_color_1 if row_index % 2 == 0 else row_color_2))

                formatted_items.append(item)

            model.appendRow(formatted_items)

        table_view.setModel(model)
        table_view.setSortingEnabled(True)  # ✅ Enable column header sorting

        # ✅ Fix column sizing issues
        header = table_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)  # 🔥 Auto-size columns to fit content
        header.setStretchLastSection(False)  # ✅ Prevent last column from stretching unnaturally

        table_view.setAlternatingRowColors(True)
        table_view.setSelectionBehavior(QTableView.SelectRows)
        table_view.setEditTriggers(QTableView.DoubleClicked)  # ✅ Allow edits on double click

        layout.addWidget(table_view)
        # ✅ Connect double-click to trigger drilldown
        if "QueryGet_" in tab_name or "Valuation" in tab_name:
            table_view.doubleClicked.connect(lambda index, name=tab_name:
                                             self.trigger_drilldown_from_row(name, index.row()))
            print(f"🔗 Drilldown connected for tab '{tab_name}'")

        self.tab_widget.addTab(tab, tab_name)

        # ✅ Connect itemChanged signal for editing detection
        if tab_name in self.gold_file_tabs:
            model.itemChanged.connect(self.on_table_edit)

        print(f"✅ Tab '{tab_name}' populated with properly sized columns and formatted numbers.")

    def store_filter_query(self):
        """Stores the filter query for later execution when Load Cockpit Set is clicked."""
        self.filter_query = self.filter_input.text().strip().lower()
        print(f"📝 Stored filter query: {self.filter_query}")  # Debugging

    def apply_stored_filter(self):
        """Applies a flexible, case-insensitive multi-term text filter across all tabs."""
        if not hasattr(self, 'filter_query') or not self.filter_query:
            print("🔄 No stored filter to apply. Leaving current data visible.")
            return

        # ✅ Allow multiple search terms, separated by commas
        filter_terms = [term.strip().lower() for term in self.filter_query.split(",") if term.strip()]
        print(f"🔍 Applying stored filter: {filter_terms}")

        for i in range(self.tab_widget.count()):
            tab_name = self.tab_widget.tabText(i)
            tab = self.tab_widget.widget(i)
            table_view = tab.findChild(QTableView)

            if not table_view:
                continue

            model = table_view.model()
            if not isinstance(model, QStandardItemModel):
                continue

            # ✅ Create a filtered model
            filtered_model = QStandardItemModel()
            filtered_model.setHorizontalHeaderLabels(
                [model.horizontalHeaderItem(c).text() for c in range(model.columnCount())])

            for row in range(model.rowCount()):
                row_data = [model.item(row, col).text().strip().lower() for col in range(model.columnCount())]

                # ✅ Require ALL filter terms to be present in the row
                if all(any(term in cell for cell in row_data) for term in filter_terms):
                    filtered_model.appendRow(
                        [QStandardItem(model.item(row, col).text()) for col in range(model.columnCount())])

            table_view.setModel(filtered_model)
            print(f"✅ Filter applied on '{tab_name}', {filtered_model.rowCount()} rows match.")

    def trigger_drilldown_from_row(self, tab_name, row_index):
        """Triggers a drilldown query using data from a selected summary row."""
        if not hasattr(self, "period_start") or not hasattr(self, "period_end"):
            print("⚠ Setting default reporting period for drilldown.")
            self.period_start = pd.to_datetime("2023-01-01")
            self.period_end = pd.to_datetime("2023-03-31")

        if tab_name not in self.table_views:
            print(f"❌ No table view found for tab '{tab_name}'")
            return

        table_view = self.table_views[tab_name]
        model = table_view.model()

        if row_index < 0 or row_index >= model.rowCount():
            print(f"❌ Invalid row index {row_index}")
            return

        # 🔍 Extract clicked row context
        context = {}
        for col in range(model.columnCount()):
            header = model.headerData(col, Qt.Horizontal)
            cell_value = model.data(model.index(row_index, col), Qt.DisplayRole)
            context[header] = cell_value

        print(f"🕵️ Drilldown context from row {row_index}: {context}")

        # 🔍 Extract card name from tab
        if tab_name.startswith("QueryGet_"):
            main_card = tab_name.replace("QueryGet_", "")
        else:
            main_card = tab_name

        query_cards_path = "BASE_PATH/refdata/query_cards.csv"
        try:
            card_df = pd.read_csv(query_cards_path)
        except Exception as e:
            print(f"❌ Error loading query cards: {e}")
            return

        # 🔍 Find matching SECOND card
        secondary_row = card_df[
            (card_df["CardName"].str.strip() == main_card.strip()) &
            (card_df["Type"].str.upper() == "SECOND")
            ]

        if secondary_row.empty:
            print(f"⚠️ No secondary drilldown card found for '{main_card}'")
            return

        card = secondary_row.iloc[0].to_dict()
        portfolio = self.portfolio_dropdown.currentText()

        # ✅ Resolve filters using the clicked row
        filter_template = card.get("Filters", "{}")
        try:
            filters_str = filter_template.format(**context)
            filters = ast.literal_eval(filters_str)
            print(f"✅ Resolved drilldown filters: {filters}")
        except Exception as e:
            print(f"❌ Failed to resolve filters: {e}")
            filters = {}

        from master_queries_new import parse_card_value, run_query

        group_by = parse_card_value(card.get("GroupBy"), portfolio, self.period_start, self.period_end)
        sort_by = parse_card_value(card.get("SortBy"), portfolio, self.period_start, self.period_end)
        report_name = parse_card_value(
            card.get("ReportName") or f"Drill_{main_card}",
            portfolio, self.period_start, self.period_end
        )
        je_detail = str(card.get("JEDetail", "False")).strip().lower() == "true"

        try:
            df_drill = run_query(
                portfolio=portfolio,
                period_start=self.period_start,
                period_end=self.period_end,
                filters=filters,
                group_by=group_by,
                sort_by=sort_by,
                report_name=report_name,
                connect=True,
                je_detail=je_detail
            )

            # ✅ Optional tab splitting if ibor_date exists
            if je_detail and "ibor_date" in df_drill.columns:
                df_drill["Week"] = pd.to_datetime(df_drill["ibor_date"]).dt.strftime("W%U_%Y")
                for week_key, week_df in df_drill.groupby("Week"):
                    tab_name = f"JE_{main_card}_{week_key}"
                    if tab_name in self.table_views:
                        self.tab_widget.removeTab(self.tab_widget.indexOf(self.table_views[tab_name]))
                    self.populate_tabs(tab_name, week_df)
                    print(f"📁 Created tab for {week_key} with {len(week_df)} rows")
            else:
                detail_tab_name = f"Drill_{main_card}_{row_index}"
                if detail_tab_name in self.table_views:
                    self.tab_widget.removeTab(self.tab_widget.indexOf(self.table_views[detail_tab_name]))
                self.populate_tabs(detail_tab_name, df_drill)

        except Exception as e:
            print(f"❌ Error during drilldown execution: {e}")


    def create_tab(self, tab_name, dataframe, editable=True):
        """Creates a tab with formatted performance data."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        table_view = QTableWidget()
        table_view.setRowCount(dataframe.shape[0])
        table_view.setColumnCount(dataframe.shape[1])
        table_view.setHorizontalHeaderLabels(dataframe.columns.tolist())

        for row_idx, row in dataframe.iterrows():
            for col_idx, value in enumerate(row):
                table_view.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))

        layout.addWidget(table_view)
        self.tab_widget.addTab(tab, tab_name)
        print(f"📌 Tab Added: {tab_name}")  # ✅ Debug: Ensure the tab is added


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GWIUnified()
    window.show()
    sys.exit(app.exec())
