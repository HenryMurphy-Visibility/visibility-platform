
"""
============================================
   VISIBILITY - Graphical Workflow Interface (GWI)
============================================
=
📌 PROGRAM OVERVIEW:
This script implements the **GWI Ustonified Interface**, a PyQt-based application for financial data
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

----

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

📌0 **AUTHOR**:
Developed and optimized by **[Hal]**
Last updated: **[Current Date]**
"""
from v_config import BASE_PATH, FUNDS_PATH, REFDATA_PATH, REPORTS_PATH
import json

import sys
import os
import time
import pandas as pd
import shutil
import yfinance as yf
import os

from bookkeeping import EventScheduler, BookkeepingSpace
from v_filter_controller import load_vfilter_config  # ✅ ADD THIS at top of your file
from utilities import log

from datetime import datetime


from core_ingest import discover_snapshot_candidates
from event_repository import get_event_by_tranid
from utilities import enforce_sorted_dates, load_price_data_as_rows, load_fx_data_as_rows
import socket

from kernel_utilities import (materialize_period_outputs,
                              from_csv_date_to_app_new,
                              close_and_create_new_period,
                              update_period_end_knowledge,
                              select_best_qualifying_snapshot,
                              bootstrap_investment_attributes)

from financial_information_gateway.user_specifications.shape_definitions import SHAPES

from filelock import FileLock
from collections import defaultdict
import ast
from queryfql import translate_sentence_to_query_dict
from v_filter_config_loader import VFilterConfigLoader
def read_and_format_csv(file_path, date_column):
    try:
        df = pd.read_csv(file_path, parse_dates=[date_column])
        print(f"Initial format of dates in {file_path}:\n{df[date_column].head()}")
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None

import re

def natural_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'([0-9]+)', s)]

query_sets = {}
# 📌 Paths
portfolio_directory = "BASE_PATH/funds/"
reports_directory = "BASE_PATH/reports/"
master_link_sets_path = "BASE_PATH/refdata/master_link_sets.csv"

import os, gc
try:
    import psutil
    _process = psutil.Process(os.getpid())
except ImportError:
    _process = None

def log_mem(label):
    gc.collect()
    if _process:
        rss = _process.memory_info().rss / 1024 / 1024
        print(f"[MEM] {label:20s} RSS={rss:.1f} MB")
    else:
        print(f"[MEM] {label}")

SIMULATION_DATE = pd.Timestamp("2023-04-03")


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
    QApplication, QMainWindow, QDateTimeEdit, QFrame,  QSizePolicy,
    QLineEdit, QTabWidget, QTableView,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QMenu,
    QAbstractScrollArea, QVBoxLayout, QCheckBox, QComboBox,
     QScrollArea, QDialog, QLabel, QDateEdit, QPushButton,
    QWidget
)
from PySide6.QtCore import QSortFilterProxyModel

from multiprocessing import Queue

from PySide6.QtGui import (
    QFont, QIcon, QColor, QPixmap, QBrush, QAction, QStandardItem, QStandardItemModel
)

from PySide6.QtCore import Qt, QCoreApplication, QTime, QDate, QDateTime,QTimer


from PySide6.QtCore import QRunnable, QThreadPool, QObject, Signal

from PySide6.QtCore import QObject, Signal

from PySide6.QtWidgets import QGridLayout



class LoadWorkerSignals(QObject):
    finished = Signal()
    error = Signal(str)
    result = Signal(object)  # ✅ Add this to pass back DataFrame or other results


from multiprocessing import Process, Manager


def process_portfolio_worker(args):
    portfolio, calendar, period_name, mode = args

    print(f"🚀 Worker started: {portfolio}", flush=True)

    engine = GWIUnified()

    print(f"📦 Creating engine: {portfolio}", flush=True)

    engine.selected_portfolio = portfolio

    print(f"➡️ Calling serial process: {portfolio}", flush=True)

    return engine.start_and_execute_serial_process(
        mode=mode,
        calendar=calendar,
        period_name=period_name,
    )

import os
import pandas as pd

import os


#def resolve_portfolio_list(name, base_path, composites_by_name):
def resolve_portfolio_list(name, base_path):
    """
    Resolves a selection into a list of portfolio NAMES.

    Supports:
    - Single portfolio
    - Composite (replaces ZLIST)

    Returns:
        list[str]
    """

    funds_path = os.path.join(base_path, "funds")

    # ------------------------------------------------------------
    # COMPOSITE (NEW - replaces ZLIST)
    # ------------------------------------------------------------
    # if name in composites_by_name:
    #     return [p.name for p in composites_by_name[name].get_portfolios()]

    # ------------------------------------------------------------
    # SINGLE PORTFOLIO
    # ------------------------------------------------------------
    portfolio_dir = os.path.join(funds_path, name)

    if not os.path.isdir(portfolio_dir):
        raise RuntimeError(f"Portfolio directory not found: {portfolio_dir}")

    return [name]

def build_prepared_data(pname, start_date, cutoff_date, knowledge_date, shared_args):
    return {
        "portfolio_name": pname,
        "current_period_start": start_date,
        "current_period_cutoff": cutoff_date,
        "current_period_knowledge": knowledge_date,
        "calendar": shared_args["calendar"]
    }

class LoadWorker(QRunnable):
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = LoadWorkerSignals()

    def run(self):
        try:
            self.func(*self.args, **self.kwargs)
            self.signals.finished.emit()
        except Exception as e:
            import traceback
            print(f"❌ Worker error: {type(e).__name__}: {e}")
            traceback.print_exc()
            self.signals.error.emit(str(e))

class PasswordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Enter Password to Close Period")
        self.setModal(True)

        self.correct_password = "V"

        layout = QVBoxLayout(self)

        msg = QLabel("Enter password to close period:")
        layout.addWidget(msg)

        self.input = QLineEdit()
        self.input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.input)

        buttons = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

        ok_btn.clicked.connect(self.try_accept)
        cancel_btn.clicked.connect(self.reject)

    def try_accept(self):
        if self.input.text() == self.correct_password:
            self.accept()
        else:
            QMessageBox.warning(self, "Incorrect Password", "Password is not correct.")
            self.input.clear()

class AccountingModeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Processing Mode")

        layout = QVBoxLayout()

        label = QLabel("Choose processing type:")
        layout.addWidget(label)

        # Snapshot choice
        snap_btn = QPushButton("Snapshot View")
        snap_btn.clicked.connect(self.choose_snapshot)
        layout.addWidget(snap_btn)

        # Closed Period choice
        closed_btn = QPushButton("Closed Period")
        closed_btn.clicked.connect(self.choose_closed)
        layout.addWidget(closed_btn)

        self._result = None
        self.setLayout(layout)

    def choose_snapshot(self):
        self._result = "Snapshot View"
        self.accept()

    def choose_closed(self):
        self._result = "Closed Period"
        self.accept()

    def get_result(self):
        return self._result

    from PySide6.QtWidgets import (
        QDialog,
        QVBoxLayout,
        QLabel,
        QComboBox,
        QPushButton,
        QLineEdit,
    )
    import json
    import os


# --- snapshot_dialog.py ---
class ClosedPeriodDialog(QDialog):
    def __init__(self, parent, portfolio_name, session):
        super().__init__(parent)

        self.portfolio_name = portfolio_name
        self.session = session
        self.selected_mode = "Snapshot View"

        self.setWindowTitle("Closed Periods")

        layout = QVBoxLayout(self)

        # ------------------------------------------------------------
        # Calendar selector
        # ------------------------------------------------------------
        layout.addWidget(QLabel("Select Calendar:"))

        self.calendar_combo = QComboBox()
        self.calendar_combo.addItems(
            ["Operational", "Daily", "Monthly", "Quarterly", "Yearly"]
        )
        layout.addWidget(self.calendar_combo)

        # ------------------------------------------------------------
        # View calendar button
        # ------------------------------------------------------------
        view_btn = QPushButton("📅 View Calendar")
        view_btn.clicked.connect(self.view_calendar)
        layout.addWidget(view_btn)

        # ------------------------------------------------------------
        # Period name (editable, auto-populated)
        # ------------------------------------------------------------
        layout.addWidget(QLabel("Period Name:"))

        self.period_name_edit = QLineEdit()
        self.period_name_edit.setPlaceholderText("ALL PERIODS WILL BE RESTATED!!")
        layout.addWidget(self.period_name_edit)

        # Load pending record when calendar changes
        self.calendar_combo.currentTextChanged.connect(
            self.load_pending_record
        )

        # Initial load
        self.load_pending_record(self.calendar_combo.currentText())

        # ------------------------------------------------------------
        # Run button
        # ------------------------------------------------------------
        run_btn = QPushButton("Close Period")
        run_btn.clicked.connect(self.accept)
        layout.addWidget(run_btn)

    # ------------------------------------------------------------
    def view_calendar(self):
        selected_calendar = self.calendar_combo.currentText()
        dlg = GetCalendarToView(-
            self, self.portfolio_name, selected_calendar
        )
        dlg.exec()

    # ------------------------------------------------------------
    def load_pending_record(self, calendar_name):
        """
        Auto-populate period name from the Pending calendar record.
        User may type over this value.
        """
        record_file = (
            f"C:/Users/hjmne/PycharmProjects/chest/funds/"
            f"{self.portfolio_name}/Calendars/"
            f"{calendar_name}/{calendar_name}.txt"
        )

        self.period_name_edit.clear()

        if not os.path.exists(record_file):
            return

        try:
            with open(record_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or not line.startswith("{"):
                        continue

                    rec = json.loads(line)
                    if rec.get("period_status") == "Pending":
                        self.period_name_edit.setText(
                            rec.get("period_name", "")
                        )
                        return

        except Exception as e:
            print(f"⚠️ Could not load pending record: {e}")

    # ------------------------------------------------------------
    # Getters for downstream execution
    # ------------------------------------------------------------
    def get_calendar(self):
        return self.calendar_combo.currentText()

    def get_period_name(self):
        return self.period_name_edit.text().strip()

    def get_mode(self):
        return self.selected_mode


class SnapshotDialog(QDialog):
    def __init__(self, parent, portfolio_name, session):
        super().__init__(parent)

        self.portfolio_name = portfolio_name
        self.session = session
        self.selected_mode = "Snapshot View"

        self.setWindowTitle("Snapshot View Inputs")

        layout = QVBoxLayout(self)

        # ------------------------------------------------------------
        # Calendar selector
        # ------------------------------------------------------------
        layout.addWidget(QLabel("Select Calendar:"))

        self.calendar_combo = QComboBox()
        self.calendar_combo.addItems(
            ["Operational", "Daily", "Monthly", "Quarterly", "Yearly"]
        )
        layout.addWidget(self.calendar_combo)

        # ------------------------------------------------------------
        # View calendar button
        # ------------------------------------------------------------
        view_btn = QPushButton("📅 View Calendar")
        view_btn.clicked.connect(self.view_calendar)
        layout.addWidget(view_btn)

        # ------------------------------------------------------------
        # Period name (editable, auto-populated)
        # ------------------------------------------------------------
        layout.addWidget(QLabel("Period Name:"))

        self.period_name_edit = QLineEdit()
        self.period_name_edit.setPlaceholderText("ALL PERIODS WILL BE RESTATED!!")

        layout.addWidget(self.period_name_edit)

        # Load pending record when calendar changes
        self.calendar_combo.currentTextChanged.connect(
            self.load_pending_record
        )

        # Initial load
        self.load_pending_record(self.calendar_combo.currentText())

        # ------------------------------------------------------------
        # Run button
        # ------------------------------------------------------------
        run_btn = QPushButton("Run Snapshot View")
        run_btn.clicked.connect(self.accept)
        layout.addWidget(run_btn)

    # ------------------------------------------------------------
    def view_calendar(self):
        selected_calendar = self.calendar_combo.currentText()
        dlg = GetCalendarToView(
            self, self.portfolio_name, selected_calendar
        )
        dlg.exec()

    # ------------------------------------------------------------
    def load_pending_record(self, calendar_name):
        """
        Auto-populate period name from the Pending calendar record.
        User may type over this value.
        """
        record_file = (
            f"C:/Users/hjmne/PycharmProjects/chest/funds/"
            f"{self.portfolio_name}/Calendars/"
            f"{calendar_name}/{calendar_name}.txt"
        )

        self.period_name_edit.clear()

        if not os.path.exists(record_file):
            return

        try:
            with open(record_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or not line.startswith("{"):
                        continue

                    rec = json.loads(line)
                    if rec.get("period_status") == "Pending":
                        self.period_name_edit.setText(
                            rec.get("period_name", "")
                        )
                        return

        except Exception as e:
            print(f"⚠️ Could not load pending record: {e}")

    # ------------------------------------------------------------
    # Getters for downstream execution
    # ------------------------------------------------------------
    def get_calendar(self):
        return self.calendar_combo.currentText()

    def get_period_name(self):
        return self.period_name_edit.text().strip()

    def get_mode(self):
        return self.selected_mode

class GetCalendarToView(QDialog):
    """
    Displays the closed-period calendar file in a table.

    Reads:
        C:/Users/hjmne/PycharmProjects/chest/funds/{portfolio}/{calendar}/{calendar}.txt

    Enhancement:
        • Displays an extra UI-only info row for the Pending record:
              Period = "<Period>-Pending"
          All other columns for this row are blank.
    """

    def __init__(self, parent, portfolio_name, calendar="Monthly"):
        super().__init__(parent)
        self.setWindowTitle(f"{calendar} Calendar for {portfolio_name}")
        self.setMinimumSize(700, 500)

        self.portfolio_name = portfolio_name
        self.calendar = calendar

        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        layout.addWidget(self.table)

        try:
            records = self.load_calendar_records()
            self.populate(records)
        except Exception as e:
            QMessageBox.critical(self, "Calendar Load Failed", str(e))

        self.setLayout(layout)

    # ------------------------------------------------------------

    # ------------------------------------------------------------
    def load_calendar_records(self):
        """
        Robust calendar loader:
        - Skips headings ("Calendar Records")
        - Skips comments
        - Skips blank lines
        - Skips anything non-JSON
        """

        cal_path = (
            f"C:/Users/hjmne/PycharmProjects/chest/"
            f"funds/{self.portfolio_name}/Calendars/{self.calendar}/{self.calendar}.txt"
        )

        if not os.path.exists(cal_path):
            raise FileNotFoundError(f"Calendar file not found:\n{cal_path}")

        records = []
        with open(cal_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                if line.startswith("#") or line.lower().startswith("calendar"):
                    continue

                if not (line.startswith("{") or line.startswith("[")):
                    continue

                try:
                    rec = json.loads(line)
                    records.append(rec)
                except Exception:
                    continue

        return records
    # ------------------------------------------------------------
    def populate(self, records):
        """
        Populates the table. Adds a *visual-only* extra row:
            Period = "<PeriodName>-Pending"
        when encountering the Pending period.
        """

        columns = ["Period", "Start", "Cutoff",
                   "Knowledge Start", "Knowledge End", "Status"]

        total_rows = len(records)

        self.table.setRowCount(total_rows)
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)

        row = 0

        # Fill real records
        for rec in records:
            pname = rec.get("period_name", "")
            start = rec.get("current_period_start", "")
            cutoff = rec.get("current_period_cutoff", "")
            know_start = rec.get("prior_period_knowledge", "")
            know_end = rec.get("current_period_knowledge", "")
            status = rec.get("period_status", "")

            self.table.setItem(row, 0, QTableWidgetItem(pname))
            self.table.setItem(row, 1, QTableWidgetItem(start))
            self.table.setItem(row, 2, QTableWidgetItem(cutoff))
            self.table.setItem(row, 3, QTableWidgetItem(know_start))
            self.table.setItem(row, 4, QTableWidgetItem(know_end))
            self.table.setItem(row, 5, QTableWidgetItem(status))
            row += 1


        # Nice sizing
        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()

class SessionContext:
    def __init__(self):
        self.calendar = None
        self.period_start = None
        self.period_end = None
        self.portfolio_name = None
        self.journal_entries = None
        self.knowledge_date = None  # optional
        self.rebuild_marks = False

# ✅ Step 2: ReportSessionDialog class
class ReportSessionDialog(QDialog):
    def __init__(self, parent, session):
        super().__init__(parent)
        self.resize(975, 400)

        self.setWindowTitle("Start Report Session")

        # ------------------------------------------------------------
        # Core State
        # ------------------------------------------------------------
        self.session = session
        self.portfolio_name = parent.selected_portfolio

        if not self.portfolio_name:
            raise RuntimeError(
                "No portfolio selected before launching ReportSessionDialog."
            )

        layout = QVBoxLayout(self)

        # ------------------------------------------------------------
        # Calendar Selection
        # ------------------------------------------------------------
        layout.addWidget(QLabel("Choose Calendar Type:"))

        self.calendar_selection = QComboBox()
        self.calendar_selection.addItems(
            ["Operational", "Daily", "Monthly", "Quarterly", "Yearly"]
        )
        layout.addWidget(self.calendar_selection)

        # ------------------------------------------------------------
        # Shape Selection
        # ------------------------------------------------------------
        layout.addWidget(QLabel("Choose Shape:"))

        self.shape_selection = QComboBox()

        self.shape_selection.addItem("Security Rollover", "rollover")
        self.shape_selection.addItem("Security Rollover (Tax Lot Level)", "rollover_tax_lot")
        self.shape_selection.addItem("Reconciled Financial State", "reconciled_financial_state")

        layout.addWidget(self.shape_selection)

        # Restore prior selection if exists
        if hasattr(self.session, "shape"):
            index = self.shape_selection.findData(self.session.shape)
            if index >= 0:
                self.shape_selection.setCurrentIndex(index)

        # Prevent signal firing during init
        self.calendar_selection.blockSignals(True)

        if self.session.calendar in [
            "Operational", "Daily", "Monthly", "Quarterly", "Yearly"
        ]:
            self.calendar_selection.setCurrentText(self.session.calendar)

        self.calendar_selection.blockSignals(False)

        # ------------------------------------------------------------
        # Box Grid Container (Scrollable)
        # ------------------------------------------------------------
        layout.addWidget(QLabel("Select Reporting Period (Box View):"))

        self.box_scroll = QScrollArea()
        self.box_scroll.setWidgetResizable(True)
        self.box_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.box_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.box_container = QWidget()
        self.box_layout = QVBoxLayout(self.box_container)

        self.box_scroll.setWidget(self.box_container)

        layout.addWidget(self.box_scroll)

        # Build initial grid once
        self.box_grid = BoxCalendarGridWidget(
            portfolio_name=self.portfolio_name,
            calendar_name=self.calendar_selection.currentText()
        )
        self.box_layout.addWidget(self.box_grid)

        # Connect calendar change handler AFTER initial build
        self.calendar_selection.currentTextChanged.connect(
            self._rebuild_box_grid
        )

        # ------------------------------------------------------------
        # Confirm Button
        # ------------------------------------------------------------
        confirm_button = QPushButton("Start Report Session")
        confirm_button.clicked.connect(self.accept)
        layout.addWidget(confirm_button)

    # ------------------------------------------------------------
    # Rebuild Grid When Calendar Changes
    # ------------------------------------------------------------
    def _rebuild_box_grid(self, calendar_name):

        # Remove existing grid safely
        if hasattr(self, "box_grid") and self.box_grid is not None:
            self.box_layout.removeWidget(self.box_grid)
            self.box_grid.deleteLater()
            self.box_grid = None

        # Build new grid
        self.box_grid = BoxCalendarGridWidget(
            portfolio_name=self.portfolio_name,
            calendar_name=calendar_name
        )
        self.box_layout.addWidget(self.box_grid)

    # ------------------------------------------------------------
    # Update Session After Accept
    # ------------------------------------------------------------
    def update_session(self):

        start, end = self.box_grid.get_selected_range()

        if not start or not end:
            QMessageBox.warning(
                self,
                "Selection Required",
                "Please select at least one accounting period."
            )
            return False

        self.session.portfolio_name = self.portfolio_name
        self.session.calendar = self.calendar_selection.currentText()
        self.session.period_start = start
        self.session.period_end = end
        self.session.shape = self.shape_selection.currentData()
        self.session.view_type = "shape"

        return True

    # ------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------
    def get_calendar(self):
        return self.session.calendar

    def get_start_date(self):
        return self.session.period_start

    def get_end_date(self):
        return self.session.period_end


from PySide6.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem

from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget,
    QTableWidgetItem, QLabel
)
from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget,
    QTableWidgetItem, QLabel, QComboBox
)
from PySide6.QtCore import Qt


class ReportViewDialog(QDialog):

    def __init__(self, rows, portfolio, period_start, period_end, shape, parent=None):

        super().__init__(parent)

        self.shape = shape  # STORE SHAPE

        self.setWindowTitle("Report View")
        self.resize(1200, 750)

        self.all_rows = rows  # store canonical data

        layout = QVBoxLayout(self)

        # --- FILTER DROPDOWN ---
        self.filter_combo = QComboBox()
        layout.addWidget(self.filter_combo)

        self._populate_filter()

        self.filter_combo.currentTextChanged.connect(self._apply_filter)

        # --- SUMMARY HEADER ---
        summary_text = (
            f"{portfolio} SUMMARY FOR "
            f"{period_start} THROUGH {period_end}"
        )

        self.summary_label = QLabel(summary_text)

        self.summary_label.setAlignment(Qt.AlignCenter)
        self.summary_label.setStyleSheet(
            "font-weight: 600; font-size: 18px; padding: 6px;"
        )
        layout.addWidget(self.summary_label)

        # --- SUMMARY TABLE ---
        self.summary_table = QTableWidget()
        layout.addWidget(self.summary_table)

        # --- DETAIL HEADER ---
        self.detail_label = QLabel("JE DETAIL TO SUPPORT POSITION CHANGES")
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.setStyleSheet(
            "font-weight: 600; font-size: 18px; padding-top: 16px;"
        )
        layout.addWidget(self.detail_label)

        # --- JE TABLE ---
        self.je_table = QTableWidget()
        layout.addWidget(self.je_table)

        # initial render
        self._apply_filter("All")

    # ---------------------------------------------------------
    # FILTER SUPPORT
    # ---------------------------------------------------------

    def _populate_filter(self):
        investments = sorted({r["investment"] for r in self.all_rows})
        self.filter_combo.addItem("All")
        self.filter_combo.addItems(investments)

    def _apply_filter(self, investment):

        if investment == "All":
            filtered = self.all_rows
        else:
            filtered = [r for r in self.all_rows if r["investment"] == investment]

        summary_rows, je_rows = self._build_blocks(filtered)

        self._render_summary(summary_rows)
        self._render_je(je_rows)

    # ---------------------------------------------------------
    # BUILD SUMMARY + DETAIL FROM CANONICAL ROWS
    # ---------------------------------------------------------
    def _build_blocks(self, rows):

        # ---------------------------------------------------------
        # Shape Configuration
        # ---------------------------------------------------------
        shape_def = SHAPES[self.shape]

        summary_def = shape_def["summary"]
        detail_def = shape_def["detail"]

        include_accounts = summary_def["include_accounts"]
        group_by = summary_def["group_by"]

        detail_include_accounts = detail_def["include_accounts"]

        summary = {}
        je_rows = []

        total_qty = 0.0
        total_local = 0.0
        total_book = 0.0

        # ---------------------------------------------------------
        # Iterate Canonical Rows
        # ---------------------------------------------------------
        for r in rows:

            financial_account = r.get("financial_account")

            # ---------------------------------------------------------
            # SUMMARY FILTER (Shape Driven)
            # ---------------------------------------------------------
            if include_accounts != "ALL" and financial_account not in include_accounts:
                summary_include = False
            else:
                summary_include = True

            # ---------------------------------------------------------
            # SUMMARY BUILD
            # ---------------------------------------------------------
            if summary_include:

                if group_by:
                    key = tuple(r.get(field) for field in group_by)
                    label = " | ".join(str(r.get(field)) for field in group_by)
                else:
                    # No grouping → show raw balances
                    key = (id(r),)
                    label = r.get("financial_account", "")

                if key not in summary:
                    summary[key] = {
                        "label": label,
                        "opening_qty": 0.0,
                        "delta_qty": 0.0,
                        "closing_qty": 0.0,
                        "opening_local": 0.0,
                        "delta_local": 0.0,
                        "closing_local": 0.0,
                        "opening_book": 0.0,
                        "delta_book": 0.0,
                        "closing_book": 0.0,
                    }

                for field in summary[key].keys():
                    if field != "label":
                        summary[key][field] += r.get(field, 0.0)

            # ---------------------------------------------------------
            # JE DETAIL BUILD (Independent of Summary)
            # ---------------------------------------------------------
            for je in r.get("je_lines", []):

                je_fa = je.get("financial_account")

                # Shape-driven JE filtering
                if detail_include_accounts != "ALL" and je_fa not in detail_include_accounts:
                    continue

                qty = je.get("qty", 0.0)
                local = je.get("local", 0.0)
                book = je.get("book", 0.0)

                total_qty += qty
                total_local += local
                total_book += book

                je_rows.append({
                    "ibor_date": je.get("ibor_date"),
                    "tradedate": je.get("tradedate"),
                    "settledate": je.get("settledate"),
                    "kdbegin": je.get("kdbegin"),
                    "kdend": je.get("kdend"),
                    "tranid": je.get("tranid"),
                    "transaction": je.get("transaction"),
                    "investment": r.get("investment"),
                    "financial_account": je_fa,
                    "qty": qty,
                    "local": local,
                    "book": book,
                })

        # ---------------------------------------------------------
        # Append JE TOTAL Row
        # ---------------------------------------------------------
        if je_rows:
            je_rows.append({
                "ibor_date": "",
                "tradedate": "",
                "settledate": "",
                "kdbegin": "",
                "kdend": "",
                "tranid": "",
                "transaction": "TOTAL",
                "investment": "",
                "financial_account": "",
                "qty": total_qty,
                "local": total_local,
                "book": total_book,
                "_is_total": True,
            })

        # ---------------------------------------------------------
        # Final Summary Rows
        # ---------------------------------------------------------
        summary_rows = sorted(summary.values(), key=lambda x: x["label"])

        return summary_rows, je_rows

    # ---------------------------------------------------------
    # RENDER SUMMARY
    # ---------------------------------------------------------

    def _render_summary(self, rows):

        columns = [
            "Investment",
            "Open Qty", "Δ Qty", "Close Qty",
            "Open Local", "Δ Local", "Close Local",
            "Open Book", "Δ Book", "Close Book",
        ]

        self.summary_table.setColumnCount(len(columns))
        self.summary_table.setHorizontalHeaderLabels(columns)
        self.summary_table.setRowCount(len(rows))

        for i, row in enumerate(rows):

            self.summary_table.setItem(i, 0, QTableWidgetItem(row["label"]))

            values = [
                row.get("opening_qty", 0.0),
                row.get("delta_qty", 0.0),
                row.get("closing_qty", 0.0),
                row.get("opening_local", 0.0),
                row.get("delta_local", 0.0),
                row.get("closing_local", 0.0),
                row.get("opening_book", 0.0),
                row.get("delta_book", 0.0),
                row.get("closing_book", 0.0),
            ]

            for j, val in enumerate(values, start=1):
                self.summary_table.setItem(i, j, QTableWidgetItem(f"{val:,.2f}"))

        self.summary_table.resizeColumnsToContents()

    # ---------------------------------------------------------
    # RENDER JE
    # ---------------------------------------------------------

    def _render_je(self, rows):
        """
        Render JE Detail table with full audit-level fields.
        """

        # ------------------------------------------------------------
        # Define Institutional-Grade Columns
        # ------------------------------------------------------------

        columns = [
            "IBOR Date",
            "Trade Date",
            "TranID",
            "Transaction",
            "Investment",
            "Qty",
            "Local",
            "Book",
            "Financial Account",
            "Settle Date",
            "KKD Begin",
            "KKD End",
        ]

        self.je_table.setColumnCount(len(columns))
        self.je_table.setHorizontalHeaderLabels(columns)
        self.je_table.setRowCount(len(rows))

        # ------------------------------------------------------------
        # Populate Rows
        # ------------------------------------------------------------

        for i, row in enumerate(rows):
            self.je_table.setItem(i, 0, QTableWidgetItem(str(row.get("ibor_date", ""))))
            self.je_table.setItem(i, 1, QTableWidgetItem(str(row.get("tradedate", ""))))
            self.je_table.setItem(i, 2, QTableWidgetItem(str(row.get("tranid", ""))))
            self.je_table.setItem(i, 3, QTableWidgetItem(str(row.get("transaction", ""))))
            self.je_table.setItem(i, 4, QTableWidgetItem(str(row.get("investment", ""))))
            self.je_table.setItem(i, 8, QTableWidgetItem(str(row.get("financial_account", ""))))
            self.je_table.setItem(i, 9, QTableWidgetItem(str(row.get("settledate", ""))))
            self.je_table.setItem(i, 10, QTableWidgetItem(str(row.get("kdbegin", ""))))
            self.je_table.setItem(i, 11, QTableWidgetItem(str(row.get("kdend", ""))))

            qty_item = QTableWidgetItem(f"{row.get('qty', 0.0):,.4f}")
            local_item = QTableWidgetItem(f"{row.get('local', 0.0):,.2f}")
            book_item = QTableWidgetItem(f"{row.get('book', 0.0):,.2f}")

            self.je_table.setItem(i, 5, qty_item)
            self.je_table.setItem(i, 6, local_item)
            self.je_table.setItem(i, 7, book_item)

            # ------------------------------------------------------------
            # Bold TOTAL row
            # ------------------------------------------------------------
            if row.get("_is_total"):
                for col in range(self.je_table.columnCount()):
                    item = self.je_table.item(i, col)
                    if item:
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
        # ------------------------------------------------------------
        # Resize Behavior
        # ------------------------------------------------------------

        header = self.je_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(9, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(10, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(11, QHeaderView.ResizeToContents)

        # Enable sorting (institutional must-have)
        self.je_table.setSortingEnabled(True)


from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QMessageBox

# je_viewer_dialog.py
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit

class JEViewerDialog(QDialog):
    def __init__(self, je_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Journal Entries")
        layout = QVBoxLayout(self)
        text_edit = QTextEdit()
        text_edit.setPlainText(je_text)
        text_edit.setReadOnly(True)
        layout.addWidget(text_edit)
        self.resize(800, 400)

class EventViewerDialog(QDialog):
    def __init__(self, event_str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Event Viewer")
        self.setMinimumSize(700, 500)

        layout = QVBoxLayout()

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(event_str)  # Use setPlainText for raw JSON
        layout.addWidget(self.text_edit)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)

        self.setLayout(layout)
import sys

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton
)

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton
)
import pandas as pd


class CommandCenterDialog(QDialog):

    def __init__(self, gw):
        super().__init__(None)

        self.gw = gw
        self._initializing = True  # 🔥 guard flag

        print("🚀 CommandCenterDialog INIT START")

        self.setWindowTitle("Command Center")
        self.setMinimumSize(500, 350)

        layout = QVBoxLayout(self)

        # -----------------------------------
        # Calendar
        # -----------------------------------
        layout.addWidget(QLabel("Calendar"))

        self.calendar_selector = QComboBox()
        layout.addWidget(self.calendar_selector)

        # -----------------------------------
        # Period Start
        # -----------------------------------
        layout.addWidget(QLabel("Period Start"))

        self.period_start_selector = QComboBox()
        layout.addWidget(self.period_start_selector)

        # -----------------------------------
        # Period End
        # -----------------------------------
        layout.addWidget(QLabel("Period End"))

        self.period_end_selector = QComboBox()
        layout.addWidget(self.period_end_selector)

        # -----------------------------------
        # Shape
        # -----------------------------------
        layout.addWidget(QLabel("Shape"))

        self.shape_selector = QComboBox()
        self.shape_selector.addItems([
            "rollover",
            "reconciled_financial_state",
            "top_holdings"
        ])
        layout.addWidget(self.shape_selector)

        # -----------------------------------
        # Time Mode (Range vs Period Chain)
        # -----------------------------------
        layout.addWidget(QLabel("Time Mode"))

        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["range", "period_chain"])

        # Default to range (your current focus)
        self.mode_selector.setCurrentText("range")

        layout.addWidget(self.mode_selector)

        # -----------------------------------
        # Composite Mode
        # -----------------------------------
        layout.addWidget(QLabel("Composite Mode"))

        self.composite_selector = QComboBox()
        self.composite_selector.addItems(["aggregate", "list"])
        layout.addWidget(self.composite_selector)

        # -----------------------------------
        # Buttons
        # -----------------------------------
        self.run_button = QPushButton("Run View")
        self.run_button.clicked.connect(self.run_view)
        layout.addWidget(self.run_button)

        self.save_button = QPushButton("Save View")
        self.save_button.clicked.connect(self.save_view)
        layout.addWidget(self.save_button)

        self.prepared_button = QPushButton("Prepared Views")
        self.prepared_button.clicked.connect(self.show_prepared_views)

        layout.addWidget(self.prepared_button)

        # -----------------------------------
        # LOAD CALENDARS (SAFE — NO SIGNALS)
        # -----------------------------------
        self.calendar_selector.blockSignals(True)
        self.load_calendars()
        self.calendar_selector.blockSignals(False)

        # -----------------------------------
        # CONNECT SIGNAL (AFTER SAFE LOAD)
        # -----------------------------------
        self.calendar_selector.currentTextChanged.connect(self._safe_calendar_changed)

        # -----------------------------------
        # DONE INITIALIZING
        # -----------------------------------
        self._initializing = False

        print("✅ CommandCenterDialog INIT COMPLETE")

    def show_prepared_views(self):

        print("📂 PREPARED VIEWS CLICKED")

        from financial_information_gateway.preparation.prepared_io import (
            list_prepared_views,
            load_prepared_view,
        )
        from pathlib import Path
        from PySide6.QtWidgets import QInputDialog

        calendar = self.calendar_selector.currentText()
        selected = self.gw.selected_portfolio

        prepared_dir = Path(
            f"C:/Users/hjmne/PycharmProjects/chest/funds/{selected}/Calendars/{calendar}/Prepared"
        )

        # -----------------------------------
        # LIST FILES
        # -----------------------------------
        files = list_prepared_views(prepared_dir)

        if not files:
            print("❌ No prepared views found")
            return

        # -----------------------------------
        # USER SELECT
        # -----------------------------------
        file_name, ok = QInputDialog.getItem(
            self,
            "Prepared Views",
            "Select a prepared view:",
            files,
            0,
            False
        )

        if not ok or not file_name:
            print("❌ Selection cancelled")
            return

        file_path = prepared_dir / file_name

        print(f"⚡ Loading prepared view: {file_name}")

        # -----------------------------------
        # LOAD
        # -----------------------------------
        df = load_prepared_view(file_path)

        if df is None or df.empty:
            print("❌ Loaded view is empty")
            return

        # -----------------------------------
        # DISPLAY
        # -----------------------------------
        self.current_df = df

        try:
            self.gw.populate_tabs("PreparedView", df)
        except Exception as e:
            print(f"❌ Failed to display prepared view: {e}")
            return

        print("✅ Prepared view displayed")

    def _safe_calendar_changed(self):
        try:
            self.on_calendar_changed()
        except Exception as e:
            print(f"❌ Calendar change failed: {e}")

    # ===================================
    # LOAD CALENDARS (REAL SYSTEM)
    # ===================================
    def load_calendars(self):

        import os

        try:
            selected = getattr(self.gw, "selected_portfolio", None)

            if not selected:
                print("⚠️ No portfolio selected")
                return

            # ----------------------------------------
            # 🔥 RESOLVE ZLIST → USE FIRST REAL PORTFOLIO
            # ----------------------------------------

            base_root_for_resolve = "C:/Users/hjmne/PycharmProjects/chest"

            portfolios = resolve_portfolio_list(
                selected,
                base_root_for_resolve,
                self.gw.composites_by_name
            )

            if not portfolios:
                print("⚠️ No portfolios resolved")
                return

            reference_portfolio = portfolios[0]

            print(f"📌 Using reference portfolio for calendars: {reference_portfolio}")

            # ----------------------------------------
            # REAL PATH
            # ----------------------------------------
            base_path = os.path.join(
                "C:/Users/hjmne/PycharmProjects/chest/funds",
                reference_portfolio,
                "Calendars"
            )

            print(f"📂 Loading calendars from: {base_path}")

            if not os.path.exists(base_path):
                raise FileNotFoundError(f"Calendar path not found: {base_path}")

            calendars = [
                d for d in os.listdir(base_path)
                if os.path.isdir(os.path.join(base_path, d))
            ]

            print(f"📅 Found calendars: {calendars}")

            # ----------------------------------------
            # POPULATE UI
            # ----------------------------------------
            self.calendar_selector.clear()
            self.calendar_selector.addItems(sorted(calendars))

        except Exception as e:
            import traceback
            print("❌ ERROR in load_calendars:")
            traceback.print_exc()

    # ===================================
    # LOAD PERIODS (USING YOUR LOADER)
    # ===================================
    def load_periods(self, calendar):

        from financial_information_gateway.calendar.calendar_loader import load_calendar_records

        portfolio = self.gw.selected_portfolio

        records = load_calendar_records(
            portfolio=portfolio,
            calendar=calendar
        )

        print(f"📊 Loaded {len(records)} calendar records")

        # Expecting canonical fields
        periods = []

        for r in records:
            # Use your canonical naming if exists
            if "period_name" in r:
                periods.append(r["period_name"])
            else:
                # fallback — construct something readable
                start = r.get("current_period_start")
                periods.append(str(start))

        return periods

    # ===================================
    # CALENDAR CHANGE HANDLER
    # ===================================
    def on_calendar_changed(self):

        try:
            calendar = self.calendar_selector.currentText()

            if not calendar:
                return

            print(f"🔄 Calendar changed → {calendar}")

            import os
            from datetime import datetime

            selected = getattr(self.gw, "selected_portfolio", None)

            if not selected:
                print("⚠️ No portfolio selected")
                return

            # ----------------------------------------
            # 🔥 RESOLVE ZLIST → USE FIRST PORTFOLIO
            # ----------------------------------------

            base_root_for_resolve = "C:/Users/hjmne/PycharmProjects/chest"

            portfolios = resolve_portfolio_list(
                selected,
                base_root_for_resolve,
                self.gw.composites_by_name
            )

            if not portfolios:
                print("⚠️ No portfolios resolved")
                return

            reference_portfolio = portfolios[0]

            print(f"📌 Using reference portfolio: {reference_portfolio}")

            # ----------------------------------------
            # SNAPSHOT DIRECTORY
            # ----------------------------------------
            snapshot_path = os.path.join(
                "C:/Users/hjmne/PycharmProjects/chest/funds",
                reference_portfolio,
                "Calendars",
                calendar,
                "Snapshots"
            )

            print(f"📦 Snapshot path: {snapshot_path}")
            print(f"📦 Exists: {os.path.exists(snapshot_path)}")

            if not os.path.exists(snapshot_path):
                print("⚠️ Snapshot path missing")
                return

            # ----------------------------------------
            # DERIVE PERIOD NAMES (MATCH FIG LOGIC)
            # ----------------------------------------
            def derive_calendar_identity(base_date_str, calendar):
                dt = datetime.strptime(base_date_str, "%Y-%m-%d")

                if calendar == "Yearly":
                    return f"{dt.year}"

                if calendar == "Quarterly":
                    q = (dt.month - 1) // 3 + 1
                    return f"{dt.year}-Q{q}"

                if calendar == "Monthly":
                    return f"{dt.year}-{dt.month:02d}"

                if calendar == "Daily":
                    return dt.strftime("%Y-%m-%d")

                if calendar == "Operational":
                    return f"{dt.year}-{dt.month:02d}"

                raise ValueError(f"Unsupported calendar: {calendar}")

            # ----------------------------------------
            # LOAD SNAPSHOT FILES
            # ----------------------------------------
            snapshots = [
                f for f in os.listdir(snapshot_path)
                if f.endswith(".pkl")
            ]

            period_names = sorted({
                derive_calendar_identity(f.split("T")[0], calendar)
                for f in snapshots
            })

            print(f"📅 Periods loaded: {period_names[:5]}...")

            # ----------------------------------------
            # POPULATE SELECTORS
            # ----------------------------------------
            self.period_start_selector.blockSignals(True)
            self.period_end_selector.blockSignals(True)

            self.period_start_selector.clear()
            self.period_end_selector.clear()

            self.period_start_selector.addItems(period_names)
            self.period_end_selector.addItems(period_names)

            self.period_start_selector.blockSignals(False)
            self.period_end_selector.blockSignals(False)

        except Exception as e:
            import traceback
            print("❌ Error in on_calendar_changed:")
            traceback.print_exc()

    def load_periods_from_snapshots(self, calendar):

        from pathlib import Path
        from datetime import datetime

        # -----------------------------------
        # 🔥 CRITICAL FIX: resolve ZLIST → portfolios
        # -----------------------------------

        selected = self.gw.selected_portfolio

        print(f"🎯 Selected portfolio input: {selected}")

        if not selected:
            print("❌ No portfolio selected")
            return []

        base_root_for_resolve = "C:/Users/hjmne/PycharmProjects/chest"


        portfolios = resolve_portfolio_list(
            selected,
            base_root_for_resolve,
            self.gw.composites_by_name
        )


        print(f"📊 Resolved portfolios: {portfolios}")


        if not portfolios:
            print("❌ No portfolios resolved")
            return []

        # -----------------------------------
        # 🔥 USE FIRST REAL PORTFOLIO AS REFERENCE
        # -----------------------------------
        reference_portfolio = portfolios[0]

        print(f"📌 Using reference portfolio: {reference_portfolio}")

        # -----------------------------------
        # Build snapshot path
        # -----------------------------------
        base_dir = (
                Path(base_root)
                / reference_portfolio
                / "Calendars"
                / calendar
                / "Snapshots"
        )

        print(f"📦 Snapshot path: {base_dir}")
        print(f"📦 Exists: {base_dir.exists()}")

        if not base_dir.exists():
            print("⚠️ Snapshot path missing")
            return []

        # -----------------------------------
        # SAME LOGIC AS FIG (DO NOT CHANGE)
        # -----------------------------------
        def derive_calendar_identity(base_date_str: str, calendar: str):
            dt = datetime.strptime(base_date_str, "%Y-%m-%d")

            if calendar == "Yearly":
                return f"{dt.year}"

            if calendar == "Quarterly":
                q = (dt.month - 1) // 3 + 1
                return f"{dt.year}-Q{q}"

            if calendar == "Monthly":
                return f"{dt.year}-{dt.month:02d}"

            if calendar == "Daily":
                return dt.strftime("%Y-%m-%d")

            if calendar == "Operational":
                return f"{dt.year}-{dt.month:02d}"

            raise ValueError(f"Unsupported calendar: {calendar}")

        periods = sorted({
            derive_calendar_identity(snap.stem.split("T")[0], calendar)
            for snap in base_dir.glob("*.pkl")
        })

        print(f"📅 Periods loaded: {periods[:5]}...")

        return periods

    # ===================================
    # RESOLVE PERIOD → BOUNDS (REAL DATA)
    # ===================================
    def resolve_period_bounds(self, calendar, period):

        from financial_information_gateway.calendar.calendar_loader import load_calendar_records

        portfolio = self.gw.selected_portfolio

        records = load_calendar_records(
            portfolio=portfolio,
            calendar=calendar
        )

        for r in records:
            if r.get("period_name") == period:
                return (
                    r["current_period_start"],
                    r["current_period_cutoff"]
                )

        raise ValueError(f"Period not found: {period}")

    # ===================================
    # RUN VIEW (STABLE + GUARDED)
    # ===================================
    def run_view(self):

        print("\n🚀 COMMAND CENTER RUN VIEW")

        import pandas as pd

        # -----------------------------------
        # INPUTS
        # -----------------------------------
        calendar = self.calendar_selector.currentText()
        period_start = self.period_start_selector.currentText()
        period_end = self.period_end_selector.currentText()
        selected = self.gw.selected_portfolio

        print(f"Calendar: {calendar}")
        print(f"Period Start: {period_start}")
        print(f"Period End: {period_end}")
        print(f"Portfolio: {selected}")

        # -----------------------------------
        # RESOLVE PORTFOLIOS
        # -----------------------------------
        base_root = "C:/Users/hjmne/PycharmProjects/chest"

        try:
            portfolios = resolve_portfolio_list(
                selected,
                base_root,
                self.gw.composites_by_name
            )
        except Exception as e:
            print(f"❌ Failed to resolve portfolios: {e}")
            return

        if not portfolios:
            print("❌ No portfolios resolved — aborting")
            return

        print("📊 Portfolios:", portfolios)

        # -----------------------------------
        # RUN FIG (POSITION WITH LOTS)
        # -----------------------------------
        dfs = []

        for pname in portfolios:
            try:
                from financial_information_gateway.fig_position_with_lots import run_position_with_lots_view
                from financial_information_gateway.preparation.prepare_box_state import prepare_box_state

                prep = prepare_box_state(
                    portfolio=pname,
                    calendar=calendar,
                    period_start=period_start,
                    period_end=period_end,
                )

                state = prep["current_structural"]

                rows = run_position_with_lots_view(state)

                if not rows:
                    continue

                df = pd.DataFrame(rows)

                df["portfolio"] = pname

                dfs.append(df)

            except Exception as e:
                print(f"❌ FIG failed for {pname}: {e}")
                continue

        if not dfs:
            print("❌ No data built — aborting")
            return

        df = pd.concat(dfs, ignore_index=True)

        print("✅ Data ready for GWI")
        print("📊 Rows:", len(df))

        # -----------------------------------
        # OPTIONAL: SORT (VERY IMPORTANT FOR DISPLAY)
        # -----------------------------------
        df = df.sort_values(
            by=["Investment", "Indent", "FinancialAccount", "Lot"],
            ascending=[True, True, True, True]
        )

        print("\n🔥 FINAL DF SENT TO GWI 🔥")
        print(df.head(20))
        print("Columns:", df.columns.tolist())
        # -----------------------------------
        # DISPLAY
        # -----------------------------------
        try:
            self.gw.populate_tabs(
                "PositionWithLots",
                df,
                group_by=[]  # 🔥 CRITICAL
            )

        except Exception as e:
            print(f"❌ Failed to populate GWI: {e}")
            return

        self.current_df = df

    def save_view(self):

        print("💾 SAVE VIEW CLICKED")

        from financial_information_gateway.preparation.prepared_io import save_prepared_view
        from pathlib import Path

        if not hasattr(self, "current_df") or self.current_df is None:
            print("❌ No data to save — run a view first")
            return

        calendar = self.calendar_selector.currentText()
        period_start = self.period_start_selector.currentText()
        selected = self.gw.selected_portfolio

        prepared_dir = Path(
            f"C:/Users/hjmne/PycharmProjects/chest/funds/{selected}/Calendars/{calendar}/Prepared"
        )

        shape = self.shape_selector.currentText()
        composite_mode = self.composite_selector.currentText()

        shape_tag = shape.upper()
        mode_tag = composite_mode.upper()

        file_name = f"{period_start}__{shape_tag}__{mode_tag}"

        print(f"📁 Saving to directory: {prepared_dir}")
        print(f"📁 Absolute path: {prepared_dir.resolve()}")
        save_prepared_view(
            prepared_dir,
            file_name,
            self.current_df
        )
        import os

        print("📂 Files currently in directory:")
        for f in os.listdir(prepared_dir):
            print("   ", f)

        print(f"✅ View saved: {file_name}")

def load_view(self):

    print("📂 LOAD VIEW CLICKED")

    from financial_information_gateway.preparation.prepared_io import (
        load_prepared_view,
        list_prepared_views,
    )
    from pathlib import Path
    from PySide6.QtWidgets import QInputDialog

    calendar = self.calendar_selector.currentText()
    selected = self.gw.selected_portfolio

    prepared_dir = Path(
        f"C:/Users/hjmne/PycharmProjects/chest/funds/{selected}/Calendars/{calendar}/Prepared"
    )

    files = list_prepared_views(prepared_dir)

    if not files:
        print("❌ No prepared views found")
        return

    file_name, ok = QInputDialog.getItem(
        self,
        "Load Prepared View",
        "Select a prepared view:",
        files,
        0,
        False
    )

    if not ok or not file_name:
        print("❌ Load cancelled")
        return

    file_path = prepared_dir / file_name

    df = load_prepared_view(file_path)

    if df is None or df.empty:
        print("❌ Loaded view is empty")
        return

    self.current_df = df

    try:
        self.gw.populate_tabs("PreparedView", df)
    except Exception as e:
        print(f"❌ Failed to display prepared view: {e}")
        return

    print("✅ Prepared view loaded successfully")
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QPushButton
)
import os
import pickle


class LoadViewDialog(QDialog):

    def __init__(self, gw):
        super().__init__()

        self.gw = gw
        self.setWindowTitle("Load Saved View")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Available Views"))

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        self.load_button = QPushButton("Load Selected View")
        self.load_button.clicked.connect(self.load_selected_view)
        layout.addWidget(self.load_button)

        self.views_path = "C:/users/hjmne/pycharmprojects/chest/views"
        self.load_view_list()

    # ------------------------------------------------------------
    # Populate list
    # ------------------------------------------------------------
    def load_view_list(self):

        if not os.path.exists(self.views_path):
            print("⚠️ No views directory found")
            return

        files = [f for f in os.listdir(self.views_path) if f.endswith(".pkl")]

        self.list_widget.clear()

        for f in sorted(files, reverse=True):
            self.list_widget.addItem(f)

    # ------------------------------------------------------------
    # Load selected
    # ------------------------------------------------------------
    def load_selected_view(self):

        selected_item = self.list_widget.currentItem()

        if not selected_item:
            print("⚠️ No view selected")
            return

        filename = selected_item.text()
        filepath = os.path.join(self.views_path, filename)

        try:
            with open(filepath, "rb") as f:
                payload = pickle.load(f)

            df = payload.get("data")
            metadata = payload.get("metadata", {})

            if df is None or df.empty:
                print("⚠️ Loaded view has no data")
                return

            # Build meaningful tab name
            view_name = metadata.get("view_name")
            portfolio = metadata.get("portfolio")
            period = metadata.get("period")

            if view_name:
                tab_name = view_name
            elif portfolio and period:
                tab_name = f"{portfolio} | {period}"
            else:
                tab_name = filename.replace(".pkl", "")

            tab_name = f"Prepared: {tab_name}"

            self.gw.populate_tabs(tab_name, df)

            print(f"✅ Loaded view: {filename}")

            self.accept()

        except Exception as e:
            print(f"❌ Failed to load view: {e}")

class StderrRedirector:
    def __init__(self, status_queue):
        self.status_queue = status_queue
        self.buffer = ""

    def write(self, msg):
        self.buffer += msg
        if "\n" in msg:
            full_message = self.buffer.strip()
            self.buffer = ""

            if "FileNotFoundError" in full_message or "[WinError 3]" in full_message:
                self.status_queue.put(f"❌ Missing file or directory:\n{full_message}")
            elif "PermissionError" in full_message or "[WinError 5]" in full_message:
                self.status_queue.put(f"🚫 Permission denied:\n{full_message}")
            elif "Traceback" in full_message or "Exception" in full_message:
                self.status_queue.put(f"⚠️ Exception:\n{full_message}")

    def flush(self):
        pass


class BoxCalendarGridWidget(QWidget):
    def __init__(self, portfolio_name, calendar_name, parent=None):
        super().__init__(parent)

        self.portfolio_name = portfolio_name
        self.calendar_name = calendar_name
        self.selected_boxes = []

        self.layout = QGridLayout(self)
        self.setLayout(self.layout)

        self.records = self.load_calendar_records()
        self.build_grid()

    def load_calendar_records(self):
        import json
        import os

        cal_path = (
            f"C:/Users/hjmne/PycharmProjects/chest/funds/"
            f"{self.portfolio_name}/Calendars/"
            f"{self.calendar_name}/{self.calendar_name}.txt"
        )

        if not os.path.exists(cal_path):
            return []

        records = []
        with open(cal_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("{"):
                    records.append(json.loads(line))

        return records

    def build_grid(self):
        row = 0
        col = 0

        for rec in self.records:
            btn = QPushButton(rec["period_name"])
            btn.setFixedSize(70, 35)
            btn.setCheckable(True)

            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2b5797;
                    color: white;
                    border-radius: 7px;
                    font-weight: bold;
                    font-size: 7pt;
                }
                QPushButton:checked {
                    background-color: #d35400;
                }
            """)

            btn.clicked.connect(lambda _, r=rec, b=btn: self.toggle_selection(r, b))

            self.layout.addWidget(btn, row, col)

            col += 1
            if col == 12:
                col = 0
                row += 1

    def toggle_selection(self, record, button):
        if button.isChecked():
            self.selected_boxes.append(record)
        else:
            self.selected_boxes = [
                r for r in self.selected_boxes
                if r["period_name"] != record["period_name"]
            ]

        # limit to 2 selections
        if len(self.selected_boxes) > 2:
            self.selected_boxes.pop(0)

    def get_selected_range(self):
        if not self.selected_boxes:
            return None, None

        if len(self.selected_boxes) == 1:
            rec = self.selected_boxes[0]
            return (
                rec["period_name"],
                rec["period_name"],
            )

        # Two or more boxes selected
        from financial_information_gateway.extraction.period_normalizer import period_key

        sorted_boxes = sorted(
            self.selected_boxes,
            key=lambda r: period_key(r["period_name"])
        )

        start_rec = sorted_boxes[0]
        end_rec = sorted_boxes[-1]

        return (
            start_rec["period_name"],
            end_rec["period_name"],
        )


class GWIUnified(QMainWindow):
    def __init__(self):
        super().__init__()
        print(">>> ENTERED GWIUnified.__init__()")

        # ✅ Define Paths
        self.portfolio_directory = FUNDS_PATH
        self.reports_directory = REPORTS_PATH
        self.master_link_sets_path = os.path.join(REFDATA_PATH, "master_link_sets.csv")

        self.current_tab_name = None
        self.table_views = {}
        self.active_context_id = None
        self.tab_metadata = {}
        self.current_dataframes = {}
        self.query_context = None

        self.vfilter_controllers = {}
        self.vfilter_config = load_vfilter_config("C:/users/hjmne/pycharmprojects/chest/refdata/v_filter.csv")

        self.load_button_pulse_timer = None
        self.load_button_pulse_state = True

        self.query_cards_path = 'C:/users/hjmne/pycharmprojects/chest/refdata/query_cards.csv'

        self.session_period_start = pd.to_datetime("2023-01-01")
        self.session_period_end = pd.to_datetime("2023-03-31")
        self.session = SessionContext()

        print("✅ SessionContext initialized:", self.session)

        self.master_link_sets = pd.DataFrame()
        self.query_cards = pd.DataFrame()
        self.filter_query = ""
        self.lotid_to_tranid_map = {}

        # --------------------------------------------------
        # 🔥 BUILD PORTFOLIO + COMPOSITE STRUCTURE FIRST
        # --------------------------------------------------

        from load_core_defs import load_portfolios_from_funds, load_composites_from_csv
        from bookkeeping import CadenceStyle

        funds_root = FUNDS_PATH
        composite_csv = os.path.join(REFDATA_PATH, "composite_master.csv")

        portfolios = load_portfolios_from_funds(funds_root)
        portfolios_by_name = {p.name: p for p in portfolios}

        op_qtr = CadenceStyle("OP_QTR", ["Operational", "Quarterly"])
        cadence_styles = {"OP_QTR": op_qtr}

        # composites = load_composites_from_csv(
        #     composite_csv,
        #     portfolios_by_name,
        #     cadence_styles
        # )
        #
        # self.composites_by_name = {c.name: c for c in composites}
        #
        # print("AVAILABLE COMPOSITES:", self.composites_by_name.keys())

        # --------------------------------------------------
        # ✅ NOW SAFE TO LOAD UI SELECTION DATA
        # --------------------------------------------------

        self.portfolio_files = self.load_portfolio_files()
        self.selection_list = self.load_selection_list()

        # --------------------------------------------------
        # REMAINING DATA LOADS (UNCHANGED)
        # --------------------------------------------------

        self.cockpit_sets = self.load_cockpit_sets()
        self.query_cards_df = self.load_query_cards()
        self.cockpit_sets_df = self.load_cockpit_sets_df()
        self.cockpit_sets = self.build_cockpit_sets(self.cockpit_sets_df)

        # --------------------------------------------------
        # TAB CONFIG (UNCHANGED)
        # --------------------------------------------------

        self.gold_file_tabs = {
            "Events", "Prices", "FXRates", "BondInfo", "InvestmentMaster"
        }

        self.tabs_that_can_be_modified = {
            "Events", "Prices", "FXRates", "BondInfo", "InvestmentMaster",
            "QueryCards", "CockpitSets",
            "DailyCalendar", "MonthlyCalendar", "QuarterlyCalendar"
        }

        # --------------------------------------------------
        # FILE MAPPINGS (UNCHANGED)
        # --------------------------------------------------

        self.tab_to_master_file = {
            "Events": os.path.join(FUNDS_PATH, "{portfolio_name}/Events/{portfolio_name}.csv"),
            "DailyCalendar": os.path.join(FUNDS_PATH, "{portfolio_name}/Calendars/Daily/Daily.csv"),
            "MonthlyCalendar": os.path.join(FUNDS_PATH, "{portfolio_name}/Calendars/Monthly/Monthly.csv"),
            "QuarterlyCalendar": os.path.join(FUNDS_PATH, "{portfolio_name}/Calendars/Quarterly/Quarterly.csv"),
            "Prices": os.path.join(REFDATA_PATH, "price_master.csv"),
            "FXRates": os.path.join(REFDATA_PATH, "fx_master.csv"),
            "InvestmentMaster": os.path.join(REFDATA_PATH, "investment_master.csv"),
            "BondInfo": os.path.join(REFDATA_PATH, "bond_info.csv"),
            "ChartofAccounts": os.path.join(REFDATA_PATH, "chart_of_accounts.csv"),
            "QueryCards": os.path.join(REFDATA_PATH, "query_cards.csv"),
            "CockpitSets": os.path.join(REFDATA_PATH, "master_link_sets.csv"),
         }

        # --------------------------------------------------
        # MISC (UNCHANGED)
        # --------------------------------------------------

        self.SIMULATION_DATE = pd.Timestamp("2023-04-03")
        self.intervals = {
            "Today": 1,
            "Last Week + Today": 5,
            "Last Month + Today": 20,
            "Last Quarter + Today": 60
        }

        self.price_data = None
        self.positions = {}
        self.current_data = None
        self.floating_tabs = {}

        import re
        def natural_key(s):
            return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', s)]

        self.debug_filter_mode = True

        # Cockpit sets load (UNCHANGED)
        self.cockpit_sets = {}
        try:
            master_link_sets_df = pd.read_csv(self.master_link_sets_path)
            if "CockpitName" in master_link_sets_df.columns:
                self.cockpit_sets = {
                    row["CockpitName"]: [val for val in row.iloc[1:].dropna().tolist()]
                    for _, row in master_link_sets_df.iterrows()
                }
                print(f"✅ Cockpit Sets Loaded: {list(self.cockpit_sets.keys())}")
        except Exception as e:
            print(f"❌ Error loading cockpit sets: {e}")

        self.session_calendar = "Open"
        self.session_period_start = pd.to_datetime("2023-01-01")
        self.session_period_end = pd.to_datetime("2023-12-29")

        self.vfilter_config = VFilterConfigLoader(
            "C:/Users/hjmne/PycharmProjects/chest/refdata/v_filter.csv"
        ).config

        print("🚦 About to set up UI")
        self.setup_ui()
        print("✅ UI Setup complete")

        self.real_time_cache = {}
        self.filtered_dataframes = {}

        self.data = None
        sys.stderr = StderrRedirector(self.status_queue)

        print("⏳ Waiting for user to select Real-Time Performance before starting updates...")

    def _render_dataframe_to_tab(
            self,
            tab_name,
            dataframe,
            visible_columns=None,
            group_by=None,
            context_id=None
    ):

        from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableView
        from PySide6.QtGui import QStandardItemModel, QStandardItem, QColor
        from PySide6.QtCore import Qt, QSortFilterProxyModel

        print(f"🧩 Rendering tab: {tab_name}")

        # -----------------------------------
        # Apply visible column filtering
        # -----------------------------------
        if visible_columns:
            dataframe = dataframe[[c for c in visible_columns if c in dataframe.columns]]

        # -----------------------------------
        # Create tab container
        # -----------------------------------
        tab = QWidget()
        layout = QVBoxLayout(tab)

        table = QTableView()
        model = QStandardItemModel()

        # -----------------------------------
        # Headers
        # -----------------------------------
        columns = list(dataframe.columns)
        model.setColumnCount(len(columns))
        model.setHorizontalHeaderLabels(columns)

        # -----------------------------------
        # Rows (🔥 WITH ADJUSTMENT HIGHLIGHTING)
        # -----------------------------------
        for _, row in dataframe.iterrows():
            items = []

            # Detect adjustment row
            is_adjustment = False
            if "entry_type" in dataframe.columns:
                is_adjustment = (row["entry_type"] == "adjustment")

            for val in row:
                item = QStandardItem("" if val is None else str(val))
                item.setEditable(False)

                # -----------------------------------
                # 🔥 Highlight adjustment rows
                # -----------------------------------
                if is_adjustment:
                    item.setBackground(QColor(255, 230, 230))  # light red

                    # Optional: make text bold (nice visual cue)
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

                items.append(item)

            model.appendRow(items)

        # -----------------------------------
        # Sorting / Filtering Proxy
        # -----------------------------------
        proxy = QSortFilterProxyModel()
        proxy.setSourceModel(model)
        proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        proxy.setFilterRole(Qt.DisplayRole)

        table.setModel(proxy)
        table.setSortingEnabled(True)

        table.viewport().setContextMenuPolicy(Qt.CustomContextMenu)

        table.viewport().customContextMenuRequested.connect(
            lambda pos, t=table, p=proxy, m=model: self._debug_menu(pos, t, p, m)
        )

        # Stretch columns
        table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(table)

        # -----------------------------------
        # Add tab
        # -----------------------------------
        self.tab_widget.addTab(tab, tab_name)

        print(f"✅ Tab rendered: {tab_name}")

    def _show_filter_menu(self, pos, table, proxy, model):
        from PySide6.QtWidgets import QMenu

        menu = QMenu()

        action_filter = menu.addAction("Filter by value")
        action_clear = menu.addAction("Clear Filter")
        action_reset = menu.addAction("Reset All")  # 👈 THIS IS WHAT I MEANT

        action = menu.exec_(table.viewport().mapToGlobal(pos))

        index = table.indexAt(pos)
        col = index.column()

        if col < 0:
            return

        if action == action_filter:
            self._apply_filter(proxy, model, col)

        elif action == action_clear:
            proxy.setFilterRegularExpression("")

        elif action == action_reset:
            proxy.setFilterRegularExpression("")
            proxy.sort(-1)  # resets sort

    def _apply_filter(self, proxy, model, col):
        from PySide6.QtWidgets import QInputDialog
        from PySide6.QtCore import QRegularExpression

        values = set()

        for row in range(model.rowCount()):
            val = model.item(row, col).text()
            if val:
                values.add(val)

        values = sorted(list(values))[:200]

        if not values:
            return

        value, ok = QInputDialog.getItem(
            None,
            "Filter",
            "Select value:",
            values,
            0,
            False
        )

        if ok and value:
            proxy.setFilterKeyColumn(col)

            # 🔥 THIS IS THE FIX
            regex = QRegularExpression(f"^{value}$")
            proxy.setFilterRegularExpression(regex)

    def open_load_view_dialog(self):
        dialog = LoadViewDialog(self)
        dialog.exec()

    def open_command_center(self):

        print("🚀 Opening Command Center...")

        import traceback

        if not hasattr(self, "_dialogs"):
            self._dialogs = {}

        dialog = None

        try:
            dialog = CommandCenterDialog(self)
            self._dialogs["command_center"] = dialog

            print("✅ Dialog constructed")

            result = dialog.exec()

            print(f"✅ Dialog closed with result: {result}")

        except Exception:
            print("❌ Command Center failed with FULL TRACEBACK:")
            traceback.print_exc()

    def main_process_branch(self, use_multiprocessing=False, mode=None, period_name=None, calendar=None):

        print("🟢 ENTER main_process_branch")

   #     BASE_PATH = "C:/Users/hjmne/PycharmProjects/chest"

        portfolios = resolve_portfolio_list(
            self.selected_portfolio,
            BASE_PATH,
     #       self.composites_by_name
        )

        try:

            if use_multiprocessing:
                print("➡️ Calling start_and_execute_multi_process")
                return self.start_and_execute_multi_process(mode, period_name, calendar)

            # ----------------------------
            # SERIAL COMPOSITE EXECUTION
            # ----------------------------
            results = []
            original_portfolio = self.selected_portfolio

            # Ask user once for run parameters
            if calendar is None:
                dialog = SnapshotDialog(self, self.selected_portfolio, self.session)

                if dialog.exec() != QDialog.Accepted:
                    print("🔴 Snapshot dialog cancelled")
                    return []

                calendar = dialog.get_calendar()
                mode = dialog.get_mode()
                period_name = dialog.get_period_name()

            for p in portfolios:
                print(f"\n🚀 SERIAL PORTFOLIO START: {p}", flush=True)

                self.selected_portfolio = p

                r = self.start_and_execute_serial_process(
                    mode=mode,
                    calendar=calendar,
                    period_name=period_name
                )

                results.append(r)

            self.selected_portfolio = original_portfolio

            return results

        except Exception as e:
            import traceback
            print("❌ ERROR inside main_process_branch")
            print(e)
            traceback.print_exc()
            raise

    def start_and_execute_serial_process(
            self,
            mode=None,
            calendar=None,
            period_name=None,
    ):
        """
        SERIAL EXECUTION ENTRY POINT (GUI)

        RESPONSIBILITY:
        - Calendar-driven orchestration
        - Knowledge delta discovery
        - Snapshot selection (path only)
        - Replay start determination (authoritative)
        - Event bounding relative to replay start
        - Single handoff to CPH per period
        """

        # ------------------------------------------------------------
        # IMPORTS
        # ------------------------------------------------------------
        import json
        from pathlib import Path
        from datetime import datetime
        from PySide6.QtWidgets import QMessageBox

        from kernel_utilities import (
            from_csv_date_to_app_new,
            from_csv_date_to_app,
            load_events_csv_to_app,
            load_events_csv_to_app_with_cutoff,
        )
        from central_processing_hub import cph_run_and_materialize


        # ------------------------------------------------------------
        # CONTEXT
        # ------------------------------------------------------------

        #BASE_PATH = "C:/Users/hjmne/PycharmProjects/chest"
        portfolio = self.selected_portfolio

        # ------------------------------------------------------------
        # 1️⃣ USER SELECTION (ONLY IF NOT PROVIDED)
        # ------------------------------------------------------------
        if calendar is None and period_name is None:

            dialog = SnapshotDialog(self, portfolio, self.session)

            if dialog.exec() != QDialog.Accepted:
                print("🔴 Snapshot dialog cancelled — aborting process.")
                return []

            calendar = dialog.get_calendar()
            mode = dialog.get_mode()
            period_name = dialog.get_period_name()

        mode_norm = (mode or "").strip().lower()
        print("🟢 START SERIAL PROCESS")
        if not calendar:
            if mode_norm.startswith("closed"):
                QMessageBox.warning(
                    self,
                    "Execution Cancelled",
                    "Calendar must be selected for Closed Period.",
                )
                return []
            # Snapshot mode is allowed to continue without calendar

        # ============================================================
        # 2️⃣ LOAD CALENDAR (AUTHORITATIVE)
        # ============================================================
        cal_path = (
                Path(BASE_PATH)
                / "funds"
                / portfolio
                / "Calendars"
                / calendar
                / f"{calendar}.txt"
        )

        if not cal_path.exists():
            raise RuntimeError(f"Calendar file not found: {cal_path}")

        calendar_records = []
        with open(cal_path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                if not ln.startswith("{"):
                    continue
                calendar_records.append(json.loads(ln))

        if not calendar_records:
            raise RuntimeError(
                f"No calendar records found in {cal_path}. "
                f"Expected JSON calendar records."
            )

        # ============================================================
        # 3️⃣ SELECT PERIOD RECORDS
        # ============================================================
        if period_name:
            records_to_process = [
                r for r in calendar_records
                if r["period_name"] == period_name
            ]
            if not records_to_process:
                raise RuntimeError(f"Period not found: {period_name}")
        else:
            records_to_process = calendar_records

        # ============================================================
        # 4️⃣ LOAD EVENTS (ONCE)
        # ============================================================
        regular_events_path = (
                Path(BASE_PATH)
                / "funds"
                / portfolio
                / "Events"
                / f"{portfolio}.csv"
        )

        mark_events_path = (
                Path(BASE_PATH)
                / "funds"
                / portfolio
                / "Events"
                / f"{portfolio}_marks.csv"
        )

        if not regular_events_path.exists():
            raise RuntimeError(f"Regular events CSV not found: {regular_events_path}")

        if not mark_events_path.exists():
            raise RuntimeError(f"Mark events CSV not found: {mark_events_path}")

        if period_name:
            rec0 = records_to_process[0]
            current_period_knowledge = from_csv_date_to_app(
                rec0["current_period_knowledge"],
                field_name="calendar.current_period_knowledge",
            )

            regular_events = load_events_csv_to_app_with_cutoff(
                str(regular_events_path),
                knowledge_cutoff_date=current_period_knowledge,
            )
            mark_events = load_events_csv_to_app_with_cutoff(
                str(mark_events_path),
                knowledge_cutoff_date=current_period_knowledge,
            )
        else:
            regular_events = load_events_csv_to_app(str(regular_events_path))
            mark_events = load_events_csv_to_app(str(mark_events_path))

        all_events = regular_events + mark_events

        # ------------------------------------------------------------
        # VALIDATE PORTFOLIO COLUMN IN EVENTS
        # ------------------------------------------------------------
        for e in all_events:

            if "portfolio" not in e:
                raise RuntimeError(
                    "Event missing required 'portfolio' column. "
                    "All event records must contain portfolio."
                )

            if e["portfolio"] != portfolio:
                raise RuntimeError(
                    f"Event portfolio mismatch. "
                    f"Processing portfolio '{portfolio}' but event contains '{e['portfolio']}'"
                )

        # ============================================================
        # 5️⃣ PERIOD LOOP
        # ============================================================
        all_metrics = []

        for rec in records_to_process:

            per_period_ctx = {
                "portfolio": portfolio,
                "calendar": calendar,
                "period_name": rec["period_name"],
                "prior_period_start": from_csv_date_to_app_new(rec["prior_period_start"]),
                "prior_period_cutoff": from_csv_date_to_app_new(rec["prior_period_cutoff"]),
                "prior_period_knowledge": from_csv_date_to_app_new(rec["prior_period_knowledge"]),
                "current_period_start": from_csv_date_to_app_new(rec["current_period_start"]),
                "current_period_cutoff": from_csv_date_to_app_new(rec["current_period_cutoff"]),
                "current_period_knowledge": from_csv_date_to_app_new(rec["current_period_knowledge"]),
            }

            print(f"\n▶ PROCESSING PERIOD: {per_period_ctx['period_name']}")

            newly_known_events = [
                e for e in all_events
                if (
                        e["kdbegin"] > per_period_ctx["prior_period_knowledge"]
                        and e["kdbegin"] <= per_period_ctx["current_period_knowledge"]
                )
            ]

            earliest_trade_date = (
                min(e["tradedate"] for e in newly_known_events)
                if newly_known_events
                else None
            )

            snapshots_dir = (
                    Path(BASE_PATH)
                    / "funds"
                    / portfolio
                    / "Calendars"
                    / calendar
                    / "Snapshots"
            )

            selected_snapshot_path = None
            selected_snapshot_kd = None

            if earliest_trade_date and snapshots_dir.exists():
                for fn in snapshots_dir.iterdir():
                    if fn.suffix != ".pkl":
                        continue
                    try:
                        snapshot_kd = datetime.strptime(fn.stem, "%Y-%m-%dT%H-%M-%S")
                    except Exception:
                        continue
                    if snapshot_kd < earliest_trade_date:
                        if selected_snapshot_kd is None or snapshot_kd > selected_snapshot_kd:
                            selected_snapshot_kd = snapshot_kd
                            selected_snapshot_path = fn

            if selected_snapshot_kd is not None:
                replay_start = selected_snapshot_kd
            else:
                replay_start = per_period_ctx["prior_period_knowledge"]

            accelerant_event_pool = [
                e for e in all_events
                if (
                        e["tradedate"] > replay_start
                        and e["kdbegin"] <= per_period_ctx["current_period_knowledge"]
                        and e["tradedate"] <= per_period_ctx["current_period_cutoff"]
                )
            ]

            is_first_calendar_period = (
                    rec["period_name"] == calendar_records[0]["period_name"]
            )

            print(
                f"⚙️ CPH START | {portfolio} | period {per_period_ctx['period_name']} | "
                f"{len(accelerant_event_pool)} events",
                flush=True
            )


            period_metrics = cph_run_and_materialize(
                portfolio=portfolio,
                calendar=calendar,
                per_period_ctx=per_period_ctx,
                snapshot_path=selected_snapshot_path,
                replay_start=replay_start,
                events=accelerant_event_pool,
                is_first_calendar_period=is_first_calendar_period,
            )

            all_metrics.append(period_metrics)

            SUBMISSION_KD = datetime.utcnow()

            update_period_end_knowledge(
                fund=portfolio,
                calendar=calendar,
                period_name=per_period_ctx["period_name"],
                current_period_knowledge=SUBMISSION_KD,
            )

            if mode == "Closed Period":
                close_and_create_new_period(
                    fund=portfolio,
                    calendar=calendar,
                    period_name=per_period_ctx["period_name"],
                )

        print("\n📊 SERIAL METRICS SUMMARY")
        for m in all_metrics:
            print(
                f"Period {m['period_name']} | "
                f"Regular JEs: {m['regular_journal_entries']} | "
                f"Adjusting JEs: {m['adjusting_journal_entries']} | "
                f"CPH Time: {m['total_time']:.3f}s"
            )

        print("✅ SERIAL PROCESS COMPLETE")
        return all_metrics

    def start_and_execute_multi_process(self, mode=None, calendar=None, period_name=None):
        """
        Run accounting across multiple processes for parallel portfolios.
        """

        import time
        import multiprocessing
        from PySide6.QtWidgets import QMessageBox
        from PySide6.QtCore import QCoreApplication

        print("🟢 GUI start_and_execute_multi_process")

        BASE_PATH = "C:/Users/hjmne/PycharmProjects/chest"

        portfolio_name = self.selected_portfolio

        # ------------------------------------------------------------
        # Resolve portfolio list (handles ZLIST composites)
        # ------------------------------------------------------------
        base_root_for_resolve = "C:/Users/hjmne/PycharmProjects/chest"
        portfolios = resolve_portfolio_list(
            selected,
            base_root_for_resolve,
            self.gw.composites_by_name
        )


        # ------------------------------------------------------------
        # Dialog selection (RUN ONCE)
        # ------------------------------------------------------------
        if mode == "Closed Period":
            dialog = ClosedPeriodDialog(self, portfolio_name, self.session)
        else:
            dialog = SnapshotDialog(self, portfolio_name, self.session)

        if not dialog.exec():
            return

        calendar = dialog.get_calendar() if calendar is None else calendar
        period_name = dialog.get_period_name()
        mode = dialog.get_mode() if mode is None else mode

        # ------------------------------------------------------------
        # Processing notice (ACQUIRE UI STATE)
        # ------------------------------------------------------------
        self.processing_box = QMessageBox(self)
        self.processing_box.setWindowTitle("Processing")
        self.processing_box.setText("⏳ Processing in progress. Please wait...")
        self.processing_box.setStandardButtons(QMessageBox.NoButton)
        self.processing_box.show()
        QCoreApplication.processEvents()

        try:
            t0_wall = time.perf_counter()

            num_workers = min(6, len(portfolios), multiprocessing.cpu_count())
            print(f"⚙️ Launching {num_workers} worker processes")

            args = [(p, calendar, period_name, mode) for p in portfolios]

            with multiprocessing.Pool(processes=num_workers) as pool:
                results = pool.map(process_portfolio_worker, args)

            wall_time = time.perf_counter() - t0_wall

            # ------------------------------------------------------------
            # ALL PORTFOLIOS NO-OP?
            # ------------------------------------------------------------
            if all(r.get("no_new_events") for r in results):
                message = "No new processing required. Events up to date."
                return

            # ------------------------------------------------------------
            # AGGREGATE METRICS
            # ------------------------------------------------------------
            totals = {
                "core_events": 0,
                "scheduled_events": 0,
                "mark_events": 0,
                "event_rules": set(),
                "journals_posted": 0,
                "total_cpu_time": 0.0
            }

            for r in results:
                if r.get("no_new_events"):
                    continue

                totals["core_events"] += r.get("core_events", 0)
                totals["scheduled_events"] += r.get("scheduled_events", 0)
                totals["mark_events"] += r.get("mark_events", 0)
                totals["journals_posted"] += r.get("journals_posted", 0)
                totals["total_cpu_time"] += r.get("total_time", 0.0)
                totals["event_rules"].update(r.get("event_rules", []))

            # ------------------------------------------------------------
            # REPORT
            # ------------------------------------------------------------
            print("\n================ MULTIPROCESS SUMMARY ================")
            print(f"Portfolios processed:   {len(portfolios)}")
            print(f"Worker processes:       {num_workers}")
            print("-----------------------------------------------------")
            print(f"Core events ingested:   {totals['core_events']:,}")
            print(f"Scheduled events:       {totals['scheduled_events']:,}")
            print(f"Mark events:            {totals['mark_events']:,}")
            print(f"Distinct event rules:   {len(totals['event_rules'])}")
            print(f"Journals posted:        {totals['journals_posted']:,}")
            print("-----------------------------------------------------")
            print(f"Total CPU time:         {totals['total_cpu_time']:8.2f}s")
            print(f"Wall-clock time:        {wall_time:8.2f}s")
            print(f"Parallel efficiency:   {totals['total_cpu_time'] / wall_time:6.2f}×")
            print("=====================================================\n")

            message = "Processing Complete!"

        except Exception as e:
            message = f"❌ Processing Failed: {str(e)}"
            raise

        finally:
            # ------------------------------------------------------------
            # GUARANTEED UI TEARDOWN
            # ------------------------------------------------------------
            self.processing_box.setText(message or "Processing Complete.")
            self.processing_box.setStandardButtons(QMessageBox.Ok)
            self.processing_box.exec()

    import os
    import pickle


    import pandas as pd

    from bookkeeping import BookkeepingSpace, EventScheduler, StatisticalRepository, AdministrativeFacility
    import main  # your canonical process_events
    from utilities import load_fx_data_as_rows, load_price_data_as_rows

    # ---------------------------------------------
    # Helper functions that already exist (or match your structure)
    # ---------------------------------------------

    def load_period_records(path):
        records = []
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                records.append(rec)
        return records

    def write_period_records(path, records):
        with open(path, "w") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

    def get_period_dir(portfolio, calendar, period_name):
        return f"{FUNDS}/{portfolio}/{calendar}/Periods/{period_name}"

    def load_events_for_portfolio(portfolio):
        path = f"{FUNDS}/{portfolio}/Events/{portfolio}.csv"
        return pd.read_csv(path)

    def parse_dt(s):
        return datetime.strptime(s, "%Y-%m-%d:%H:%M:%S")

    def now_timestamp():
        return datetime.now().strftime("%Y-%m-%d:%H:%M:%S")

    # ============================================================
    # 1️⃣  BUILD BK SNAPSHOTS FOR ALL PERIODS
    # ============================================================

    def build_derive_bk_snapshot(portfolio: str, snapshot_date: str) -> bool:
        """
        Build a Operational snapshot for a portfolio.

        - Replays ALL events up to `snapshot_date` (as-of accounting cutoff).
        - Uses Operational (now) as knowledge_cutoff.
        - NEVER uses adjusting entries (Derive is pure current-knowledge replay).
        - Saves:
            - bk_space.pkl
            - stat_repo.pkl
            - settle_admin_facility.pkl
            - derive_metadata.json
            - Operational.txt (single-line JSONL with same metadata)
        - Overwrites any prior Operational snapshot (only one Operational snapshot exists).

        Assumes:
            - FUNDS constant is defined at module level, e.g.
              FUNDS = "C:/Users/hjmne/PycharmProjects/chest/funds"
            - process_events reads events internally based on `fund`.
        """
        import os
        import json
        import pickle
        from datetime import datetime

        from bookkeeping import BookkeepingSpace, EventScheduler
        from main import process_events

        # ------------------------------------------------------------------
        # Paths
        # ------------------------------------------------------------------
        derive_root = os.path.join(FUNDS, portfolio, "Operational")
        snapshot_dir = os.path.join(derive_root, "Snapshot")
        os.makedirs(snapshot_dir, exist_ok=True)

        periods_dir = os.path.join(derive_root, "Periods")
        os.makedirs(periods_dir, exist_ok=True)

        # ------------------------------------------------------------------
        # Knowledge cutoff = "now" (recorded explicitly)
        # ------------------------------------------------------------------
        knowledge_cutoff = datetime.now().strftime("%Y-%m-%d:%H:%M:%S")

        # ------------------------------------------------------------------
        # Fresh bookkeeping space + scheduler
        # ------------------------------------------------------------------
        space = BookkeepingSpace()
        scheduler = EventScheduler()

        # ------------------------------------------------------------------
        # Run derive processing
        # NOTE:
        # - period_start=None → let process_events decide how to handle "from inception"
        # - journal_entries=None → no journals in Operational
        # - price_data/fx_data/af=None → let process_events load as it currently does
        # - rebuild_marks=True → force fresh marks/accruals for this derive run
        # ------------------------------------------------------------------
        process_events(
            fund=portfolio,
            period_start=None,
            period_cutoff=snapshot_date,
            knowledge_cutoff=knowledge_cutoff,
            journal_entries=None,
            space=space,
            scheduler=scheduler,
            price_data=None,
            fx_data=None,
            af=None,
            stat_repo=space.statistical_repository,
            rebuild_marks=True,
        )

        # ------------------------------------------------------------------
        # Save snapshot artifacts
        # ------------------------------------------------------------------
        with open(os.path.join(snapshot_dir, "bk_space.pkl"), "wb") as f:
            pickle.dump(space, f)

        with open(os.path.join(snapshot_dir, "stat_repo.pkl"), "wb") as f:
            pickle.dump(space.statistical_repository, f)

        # BookkeepingSpace already has settle_admin_facility; derive should persist it too
        with open(os.path.join(snapshot_dir, "settle_admin_facility.pkl"), "wb") as f:
            pickle.dump(space.settle_admin_facility, f)

        # ------------------------------------------------------------------
        # Metadata: this is what AI / future validation will key off of
        # ------------------------------------------------------------------
        metadata = {
            "period_name": "Operational",
            "snapshot_date": snapshot_date,
            "knowledge_date": knowledge_cutoff,
            "period_status": "Open",
            # asof_lock_date can be added later when you wire in validation;
            # keeping it out of the core for now per your last call.
        }

        # JSON metadata alongside the snapshot
        with open(os.path.join(snapshot_dir, "derive_metadata.json"), "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4)

        # Single-line JSONL Operational.txt in Periods dir
        derive_txt_path = os.path.join(periods_dir, "Operational.txt")
        with open(derive_txt_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(metadata) + "\n")

        return True



    # ============================================================
    # 2️⃣  CLOSE A SINGLE PERIOD
    # ============================================================

    def close_a_single_period(portfolio, calendar):
        """
        Close the one and only Open period for a portfolio + calendar.
        Uses the real closed-period processing engine.
        Produces:
            journals.pkl
            adjusting_journals.pkl
            bksnapshot/
        Then:
            marks the period Closed
            creates a new Open period
            saves updated calendar file
        """
        import os
        import pickle

        from central_processing_hub import process_qualifying_periods  # your engine

        # ------------------------------------------------------------
        # Load calendar file
        # ------------------------------------------------------------
        calendar_path = f"{FUNDS}/{portfolio}/{calendar}/Periods/{calendar}.txt"
        records = load_period_records(calendar_path)

        # Find the open period
        open_rec = next((r for r in records if r["period_status"] == "Open"), None)
        if open_rec is None:
            raise RuntimeError("No Open period found. Nothing to close.")

        period_name = open_rec["period_name"]

        # ------------------------------------------------------------
        # Run the REAL closed-period 3-pass process
        # ------------------------------------------------------------
        # This will generate journals.pkl and adjusting_journals.pkl
        # exactly the way your architecture already expects.
        process_qualifying_periods(
            portfolio_name=portfolio,
            calendar=calendar,
            rebuild_marks=False  # closed-periods always skip mark rebuild
        )

        # ------------------------------------------------------------
        # Create a BK snapshot for the newly closed period
        # ------------------------------------------------------------
        snap_dir = (
            f"{FUNDS}/{portfolio}/{calendar}/Periods/{period_name}/bksnapshot"
        )
        os.makedirs(snap_dir, exist_ok=True)

        # Find artifacts
        journals_path = (
            f"{FUNDS}/{portfolio}/{calendar}/Periods/{period_name}/journals.pkl"
        )
        adj_path = (
            f"{FUNDS}/{portfolio}/{calendar}/Periods/{period_name}/adjusting_journals.pkl"
        )

        # Load spaces from processing engine (the space was saved somewhere upstream)
        bk_space = load_bk_space_after_processing()  # uses your existing method
        stat_repo = bk_space.statistical_repository
        admin_facility = bk_space.settle_admin_facility

        with open(f"{snap_dir}/bk_space.pkl", "wb") as f:
            pickle.dump(bk_space, f)
        with open(f"{snap_dir}/stat_repo.pkl", "wb") as f:
            pickle.dump(stat_repo, f)
        with open(f"{snap_dir}/settle_admin_facility.pkl", "wb") as f:
            pickle.dump(admin_facility, f)

        # ------------------------------------------------------------
        # Mark period as closed + create new open period
        # ------------------------------------------------------------
        open_rec["period_status"] = "Closed"
        new_rec = make_new_period_record(open_rec)
        records.append(new_rec)

        save_period_records(portfolio, calendar, records)

        return period_name, new_rec

    def load_period_records(portfolio, calendar):
        path = f"C:/Users/hjmne/PycharmProjects/chest/funds/{portfolio}/{calendar}/{calendar}.txt"
        records = []
        with open(path, "r", encoding="utf-8") as f:
            first = True
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if first and line.startswith("#"):
                    first = False
                    continue
                first = False
                records.append(json.loads(line))
        return records

    def find_open_period(records):
        for rec in records:
            if rec["period_status"] == "Open":
                return rec
        return None

    def attach_tranid_double_click_handler(self, table_view):
        table_view.doubleClicked.connect(lambda index: self.on_table_double_click(index, table_view))

    from event_repository import get_event_by_tranid
    import json

    def on_table_double_click(self, index, table_view):
        model = table_view.model()
        if model is None:
            return
        raw_value = model.data(index)

        try:
            # Convert float-like TRANID (e.g., 123.0) to clean string "123"
            tranid = str(int(float(raw_value)))
        except (ValueError, TypeError):
            print(f"❌ Invalid TRANID: {raw_value}")
            return

        column_name = model.headerData(index.column(), Qt.Horizontal).upper()
        if column_name != "TRANID":
            return


        tranid = model.data(index)
        if not tranid:
            return

        # 🔍 Lookup event
        from event_repository import get_event_by_tranid
        event = get_event_by_tranid(
            tranid,
            portfolio_name=self.session.portfolio_name,
            portfolio_directory=self.portfolio_directory
        )

        if event is None:
            QMessageBox.warning(self, "Not Found", f"No event found for TRANID {tranid}")
            return

        # 🔎 Show the event
        import json
        event_str = json.dumps(event, indent=4)
        dialog = EventViewerDialog(event_str, parent=self)
        dialog.exec()


    from PySide6.QtCore import QTimer

    from PySide6.QtCore import QTimer, QCoreApplication

    def poll_status_queue(self):
        while not self.status_queue.empty():
            msg = self.status_queue.get()
            self.status_log.append(msg)

    def start_load_button_pulse(self):
        """Start the pulsing effect on the Load button."""
        if not hasattr(self, "load_button_pulse_timer") or self.load_button_pulse_timer is None:
            self.load_button_pulse_timer = QTimer()
            self.load_button_pulse_timer.timeout.connect(self.pulse_load_button)

        self._pulse_state = False  # Reset the pulse toggle state

        self.load_button.setStyleSheet("""
            QPushButton {
                background-color: #FF4136; /* Dark Red */
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 5px;
            }
        """)
        self.load_button.setEnabled(False)
        self.load_button_pulse_timer.start(500)  # Every 0.5 seconds

        QCoreApplication.processEvents()  # Force immediate update to show red button immediately

    def pulse_load_button(self):
        """Toggle the load button color between two shades of red."""
        if getattr(self, "_pulse_state", False):
            # Even lighter pulse for better visibility
            self.load_button.setStyleSheet("""
                QPushButton {
                    background-color: #FF8888; /* Lighter Pink-Red */
                    color: white;
                    font-weight: bold;
                    border-radius: 6px;
                    padding: 5px;
                }
            """)
        else:
            # Normal dark red
            self.load_button.setStyleSheet("""
                QPushButton {
                    background-color: #FF4136; /* Dark Red */
                    color: white;
                    font-weight: bold;
                    border-radius: 6px;
                    padding: 5px;
                }
            """)
        self._pulse_state = not self._pulse_state

    def stop_load_button_pulse(self):
        """Stop pulsing and set button to Green."""
        if hasattr(self, "load_button_pulse_timer") and self.load_button_pulse_timer:
            self.load_button_pulse_timer.stop()
            self.load_button_pulse_timer = None

        self.load_button.setStyleSheet("""
            QPushButton {
                background-color: #2ECC40; /* Green */
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 5px;
            }
        """)
        self.load_button.setEnabled(True)

    def reset_load_button(self):
        """Reset the Load button to initial Grey state and stop any pulse."""
        if hasattr(self, "load_button_pulse_timer") and self.load_button_pulse_timer:
            self.load_button_pulse_timer.stop()
            self.load_button_pulse_timer = None

        self.load_button.setStyleSheet("""
            QPushButton {
                background-color: #AAAAAA; /* Grey */
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 5px;
            }
        """)
        self.load_button.setEnabled(True)

    def prepare_context_for_data_ingestion(self, new_context_id: str):
        """
        Safely switches context without clearing unrelated tabs.
        Only clears memory structures tied to the previous context.
        """
        if new_context_id == self.active_context_id:
            print(f"🔁 Reusing context: {new_context_id}")
            return  # No switch needed

        print(f"🧹 Switching to new context: {new_context_id} (was: {self.active_context_id})")

        # Do NOT remove tabs here — we are mid-cockpit load, possibly populating multiple related tabs.
        # Instead, just update context-related internal memory (filters, state, etc.)

        self.vfilter_controllers = {}  # Reset per-context filters if needed
        self.query_context = None
        self.active_context_id = new_context_id

        print(f"✅ Context switched. Ready for: {new_context_id}")

    def handle_header_clicked(self, logicalIndex):
        """Toggle sort order when header is clicked."""
        header = self.table.horizontalHeader()
        current_sort_order = header.sortIndicatorOrder()

        if current_sort_order == Qt.AscendingOrder:
            new_order = Qt.DescendingOrder
        else:
            new_order = Qt.AscendingOrder

        self.proxy_model.sort(logicalIndex, new_order)

    def handle_load_error(self, *args, **kwargs):
        """Handle any load error gracefully."""
        print("⚠️ Load error occurred. Stopping pulse and resetting button.")
        self.stop_load_button_pulse()

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

    def open_report_session_dialog(self):
        """Launch the Report Session dialog and render summary + JE detail."""

        dialog = ReportSessionDialog(self, self.session)

        if dialog.exec():
            dialog.update_session()

            try:
                from financial_information_gateway.adapters.shape_adapter import run_shape
                from financial_information_gateway.rendering.console_renderer import (
                    build_summary_with_je_flat_rows,
                )

                # 1️⃣ Run shape using COMPLETE perspective

                view_type = getattr(self.session, "view_type", "shape")

                if view_type == "shape":

                    shape_result = run_shape(
                        portfolio=self.session.portfolio_name,
                        calendar=self.session.calendar,
                        period_start=self.session.period_start,
                        period_end=self.session.period_end,
                        mode="range",
                        report_perspective="complete",
                        group_by=None,
                        uber_filter=None,
                        include_je_detail=True,
                        shape=getattr(self.session, "shape", "rollover"),
                    )

                    data = shape_result["data"]
                    rows = data["summary_rows"]

                elif view_type == "performance":

                    from financial_information_gateway.fig_performance import run_performance_view

                    perf_result = run_performance_view(
                        portfolio=self.session.portfolio_name,
                        calendar=self.session.calendar,
                        period_start=self.session.period_start,
                        period_end=self.session.period_end
                    )

                    df = perf_result["summary"]

                    # convert to existing dialog format
                    rows = df.to_dict("records")

                print("DEBUG SHAPE:", self.session.shape)
                for i, r in enumerate(rows[:10]):
                    print(f"DEBUG ROW {i}:", r)


                report_view = ReportViewDialog(
                    rows,
                    portfolio=self.session.portfolio_name,
                    period_start=self.session.period_start,
                    period_end=self.session.period_end,
                    shape=self.session.shape,
                    parent=self
                )

                report_view.exec()

                print("🟢 Summary + JE rendering active.")

            except Exception as e:
                print(f"❌ Report execution failed: {e}")

            if hasattr(self, "update_session_period_label"):
                self.update_session_period_label()

    def run_shape_session(
            self,
            portfolio,
            calendar,
            period_start,
            period_end,
            mode,
            report_perspective,
            group_by=None,
            investment_filter=None,
            value_field="local",
    ):

        shape_result = run_shape(
            portfolio=portfolio,
            calendar=calendar,
            period_start=period_start,
            period_end=period_end,
            mode=mode,
            report_perspective=report_perspective,
            group_by=None,
            uber_filter=None,
            include_je_detail=True,
            shape=getattr(self.session, "shape", "rollover"),
        )

        data = shape_result["data"]

        # ------------------------------------------------------------
        # SUMMARY
        # ------------------------------------------------------------

        if data.get("summary_tree"):
            rows = flatten_projection_tree(data["summary_tree"])
        else:
            rows = data["summary_rows"]

        # Optional UI-level filtering
        if investment_filter:
            rows = [r for r in rows if r.get("investment") == investment_filter]

        # Optional UI-level projection
        if group_by:
            projection = run_projection(rows, group_by=group_by)
            rows = flatten_projection_tree(projection)

        self.render_projected_rows_to_table(rows)

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

    def route_context_menu(self, table_view, tab_name, pos):
        """Route right-click to filter menu (header) or edit/save menu (data cell)."""
        index = table_view.indexAt(pos)
        if index.isValid():
            # 👉 Clicked on a cell — show row-level actions (duplicate, save)
            self.show_context_menu(table_view, tab_name, pos)
        else:
            # 👉 Clicked on a header — do nothing (v_filter handles it)
            pass

    def format_data(self, value):
        """Ensure all values are formatted safely for GUI display."""
        import datetime

        try:
            if pd.isna(value) or value is pd.NaT:
                return ""
            elif isinstance(value, (pd.Timestamp, datetime.datetime)):
                return value.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(value, float):
                return f"{value:,.2f}"
            elif isinstance(value, int):
                return str(value)
            elif isinstance(value, str):
                return value.strip()
            else:
                # Fallback for unexpected types
                return str(value)
        except Exception as e:
            print(f"⚠️ format_data error on value {repr(value)}: {e}")
            return "!!ERR!!"

    def debug(self, msg):
        if self.debug_filter_mode:
            print(f"[DEBUG] {msg}")

    def deformat_data(self, value):
        if isinstance(value, (int, float)):
            return value

        if not isinstance(value, str) or value.strip() == "":
            return ""

        val = value.strip().replace(",", "").replace("$", "").replace("%", "")

        # ✅ Try converting only if it *looks* like a number
        if any(char.isdigit() for char in val):
            try:
                return float(val) if "." in val else int(val)
            except ValueError:
                return value

        return value  # ⛔ Leave string fields like "AAPL, Inc." untouched


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

            portfolio_name = self.session.portfolio_name
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

    def update_session_period_label(self):
        try:
            start = self.session.period_start
            end = self.session.period_end
            cal = self.session.calendar or "Open"

            # Normalize: support datetime/pandas Timestamp/date/None
            if start is None or end is None:
                start_str, end_str = "—", "—"
            else:
                if hasattr(start, "date"):  # datetime or pandas Timestamp
                    start = start.date()
                if hasattr(end, "date"):
                    end = end.date()
                start_str, end_str = str(start), str(end)

            self.session_period_label.setText(
                f"🗓️ Reporting Period: {start_str} → {end_str}   |   📘 Calendar: {cal}"
            )
        except Exception as e:
            print(f"⚠️ Failed to update session period label: {e}")

    def setup_ui(self):
        self.setWindowTitle("VISIBILITY - Graphical Workflow Interface (GWI)")
        self.setMinimumSize(1200, 800)

        # Scrollable container
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        scroll.viewport().setStyleSheet("background: transparent;")

        # Container widget and main layout
        container = QWidget()
        container.setStyleSheet("background-color: rgb(25, 25, 112); color: white;")
        self.layout = QVBoxLayout(container)  # ✅ Set layout and attach to container

        # --- ENSURE CONTAINER EXPANDS PROPERLY INSIDE SCROLL AREA ---
        # Without this, the scroll area may calculate minimal height
        # and not expand until user interaction triggers geometry refresh.
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Keep layout pinned to top so content grows downward naturally
        self.layout.setAlignment(Qt.AlignTop)

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

        self.status_queue = Queue()
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.poll_status_queue)
        self.status_timer.start(200)  # check for messages every 200 ms

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
            QTableView, QTableWidget {
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
            /* --- TAB STYLING FIX --- */
            
            QTabWidget::pane {
                border: none;
            }
            
            QTabWidget QTabBar::tab {
                background-color: #e6e6e6;
                color: black;
                padding: 6px 12px;
                border: 1px solid #b0b0b0;
                min-width: 100px;
            }
            
            QTabWidget QTabBar::tab:selected {
                background-color: rgb(70, 130, 180);
                color: white;
                font-weight: bold;
            }
            
            QTabWidget QTabBar::tab:hover {
                background-color: #d0d0d0;
            }
            """)

        self.session_period_label = QLabel("🗓️ Reporting Period: —")
        self.session_period_label.setAlignment(Qt.AlignCenter)
        self.session_period_label.setStyleSheet("font-size: 12px; color: lightgray;")
        self.layout.addWidget(self.session_period_label)

        # Set initial period text

        # 🧠 Initial label update
        self.update_session_period_label()

        # Top-right button bar
        from PySide6.QtWidgets import QHBoxLayout, QFileDialog
        top_right_layout = QHBoxLayout()
        top_right_layout.addStretch(1)

        # ─── RELOAD Button ───
        self.reload_button = QPushButton("RELOAD")
        self.reload_button.setToolTip("Reload full original data for current tab")
        self.reload_button.setFixedSize(80, 30)
        self.reload_button.setStyleSheet("""
            QPushButton {
                background-color: #27AE60;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #1E8449;
            }
        """)
        self.reload_button.clicked.connect(lambda: self.reload_tab_data(self.get_current_tab_name()))

        # ─── EXCEL Button ───
        self.excel_button = QPushButton("EXCEL")
        self.excel_button.setToolTip("Export current tab to Excel")
        self.excel_button.setFixedSize(80, 30)
        self.excel_button.setStyleSheet("""
            QPushButton {
                background-color: #27AE60;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #1E874B;
            }
        """)
        self.excel_button.clicked.connect(self.export_current_tab_to_excel)

        # ─── Add to Layout ───
        top_right_layout.addWidget(self.reload_button)
        top_right_layout.addWidget(self.excel_button)
        self.layout.addLayout(top_right_layout)

        # Dropdowns
        self.portfolio_dropdown = QComboBox()
        self.portfolio_dropdown.currentIndexChanged.connect(self.on_portfolio_selection_changed)

        data = self.load_selection_list()

        self.portfolio_dropdown.clear()

        # Add composites first
        # for c in data["composites"]:
        #     self.portfolio_dropdown.addItem(f"[C] {c}")

        # Add portfolios
        for p in data["portfolios"]:
            self.portfolio_dropdown.addItem(p)

        self.layout.addWidget(self.portfolio_dropdown)
        self.portfolio_dropdown.addItems(self.portfolio_files)
        self.layout.addWidget(self.portfolio_dropdown)

        self.query_dropdown = QComboBox()
        self.query_dropdown.addItems(list(self.cockpit_sets.keys()))
        initial = self.query_dropdown.currentText()
        self.selected_cockpit_name = initial  # ✅ Set initial value explicitly
        self.query_dropdown.currentIndexChanged.connect(self.handle_cockpit_selection)
        self.layout.addWidget(self.query_dropdown)

        # Button bar
        self.buttons_layout = QHBoxLayout()

        self.report_session_button = QPushButton("📄 Establish a Report Session")
        self.report_session_button.clicked.connect(self.open_report_session_dialog)
        self.buttons_layout.addWidget(self.report_session_button)

        self.process_changes_button = QPushButton("✅ Process Accounting Views")
        # Processing button wiring
        self.process_changes_button.clicked.connect(
            lambda: self.main_process_branch(
                use_multiprocessing=self.use_mp_checkbox.isChecked(),
                mode=self.get_accounting_mode() # go to toggle to choose closed period or snapshot
            )
        )
        self.buttons_layout.addWidget(self.process_changes_button)

        self.use_mp_checkbox = QCheckBox("Use Multiprocessing")
        self.use_mp_checkbox.setChecked(False)

        self.command_center_button = QPushButton("Command Center")
        self.command_center_button.clicked.connect(self.open_command_center)
        self.buttons_layout.addWidget(self.command_center_button)


        # Add to layout (example)
        self.buttons_layout.addWidget(self.command_center_button)


        self.load_button = QPushButton("Cockpit Results")
        self.load_button.clicked.connect(self.execute_primary_load_and_filter)
        self.buttons_layout.addWidget(self.load_button)


        # self.save_button = QPushButton("Save Changes")
        # self.save_button.clicked.connect(self.on_save_clicked)
        # self.buttons_layout.addWidget(self.save_button)

        self.layout.addLayout(self.buttons_layout)

        # Filter input
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("🔍 Type to filter data...")
        self.filter_input.textChanged.connect(self.store_filter_query)
        self.layout.addWidget(self.filter_input)

        # Tabs
        self.tab_widget = QTabWidget()
        self.tab_widget.setFixedHeight(400)
        self.tab_widget.currentChanged.connect(self.on_tab_selected)
        self.layout.addWidget(self.tab_widget)


        self.tab_widget.tabBarDoubleClicked.connect(self.on_tab_double_clicked)

        # Finalize scrollable container
        scroll.setWidget(container)
        scroll.setAlignment(Qt.AlignTop)
        self.setCentralWidget(scroll)

        # --- ENABLE SCROLL AREA TO RESIZE WITH MAIN WINDOW ---
        # Required so internal layout expands correctly.
        scroll.setWidgetResizable(True)

        # ✅ Keyboard shortcut to refresh cockpit sets
        from PySide6.QtGui import QShortcut, QKeySequence

        refresh_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        refresh_shortcut.activated.connect(self.refresh_cockpit_sets)

        QShortcut(QKeySequence("Ctrl+P"), self).activated.connect(self.populate_selected_cockpit_set)

        report_action = QAction("Start Report Session", self)
        report_action.triggered.connect(self.open_report_session_dialog)
        self.menuBar().addAction(report_action)

        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        self.layout.addWidget(self.status_log)

        clear_log_button = QPushButton("🧹 Clear Log")
        clear_log_button.setToolTip("Clear the status/error log below")
        clear_log_button.setFixedSize(100, 28)
        clear_log_button.setStyleSheet("""
            QPushButton {
                background-color: #CD5C5C;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #B22222;
            }
        """)
        clear_log_button.clicked.connect(self.status_log.clear)
        self.layout.addWidget(clear_log_button)

        print("Stylesheet length:", len(self.styleSheet()))

    def resolve_fig_shape(item_name: str):
        name = item_name.lower()

        if "top" in name and "holding" in name:
            return "top_holdings"

        if "roll" in name or "position" in name:
            return "rollover"

        if "activity" in name:
            return "activity"

        return "rollover"

    def render_summary_table(self, rows):

        table = self.summary_table
        table.clear()

        columns = [
            "Investment",
            "Open Qty", "Δ Qty", "Close Qty",
            "Open Local", "Δ Local", "Close Local",
            "Open Book", "Δ Book", "Close Book",
        ]

        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setRowCount(len(rows))

        for i, row in enumerate(rows):

            table.setItem(i, 0, QTableWidgetItem(row["label"]))

            values = [
                row.get("opening_qty", 0.0),
                row.get("delta_qty", 0.0),
                row.get("closing_qty", 0.0),
                row.get("opening_local", 0.0),
                row.get("delta_local", 0.0),
                row.get("closing_local", 0.0),
                row.get("opening_book", 0.0),
                row.get("delta_book", 0.0),
                row.get("closing_book", 0.0),
            ]

            for j, val in enumerate(values, start=1):
                table.setItem(i, j, QTableWidgetItem(f"{val:,.2f}"))

        table.resizeColumnsToContents()

    def render_je_table(self, rows):

        table = self.je_table
        table.clear()

        columns = ["Date", "Transaction", "Investment", "Qty", "Local", "Book"]

        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setRowCount(len(rows))

        for i, row in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(str(row.get("date", ""))))
            table.setItem(i, 1, QTableWidgetItem(str(row.get("transaction", ""))))
            table.setItem(i, 2, QTableWidgetItem(str(row.get("investment", ""))))
            table.setItem(i, 3, QTableWidgetItem(f"{row.get('qty', 0.0):,.4f}"))
            table.setItem(i, 4, QTableWidgetItem(f"{row.get('local', 0.0):,.2f}"))
            table.setItem(i, 5, QTableWidgetItem(f"{row.get('book', 0.0):,.2f}"))

        table.resizeColumnsToContents()

    def get_accounting_mode(self):
        print("OPENING DIALOG")

        dlg = AccountingModeDialog(self)

        result = dlg.exec()

        print("DIALOG CLOSED:", result)

        if result:
            return dlg.get_result()
        return None

    # def get_accounting_mode(self):
    #     dlg = AccountingModeDialog(self)
    #     if dlg.exec():
    #         return dlg.get_result()
    #     return None

    def render_projected_rows_to_table(self, flat_rows):

        self.report_table.setRowCount(0)

        if not flat_rows:
            return

        self.report_table.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding
        )
        self.report_table.setMinimumHeight(400)

        # ---------------------------------------------------------
        # Detect numeric fields across all rows
        # ---------------------------------------------------------

        preferred_order = [
            "opening_qty", "delta_qty", "closing_qty",
            "opening_local", "delta_local", "closing_local",
            "opening_book", "delta_book", "closing_book"
        ]

        detected_fields = set()

        for row in flat_rows:
            for k, v in row.items():
                if isinstance(v, (int, float)):
                    detected_fields.add(k)

        numeric_fields = [f for f in preferred_order if f in detected_fields]

        columns = ["Label"] + numeric_fields

        self.report_table.setColumnCount(len(columns))
        self.report_table.setHorizontalHeaderLabels(columns)
        self.report_table.setRowCount(len(flat_rows))

        # ---------------------------------------------------------
        # Render rows
        # ---------------------------------------------------------

        for row_idx, row in enumerate(flat_rows):

            label = row.get("label", "")
            level = row.get("level", 0)
            row_type = row.get("row_type")

            indent = "    " * level
            label_item = QTableWidgetItem(indent + label)

            # ----------------------------
            # Styling rules
            # ----------------------------

            if row_type in ("subtotal", "grand_total", "summary", "divider"):
                font = label_item.font()
                font.setBold(True)
                label_item.setFont(font)

            elif row_type == "je_detail":
                font = label_item.font()
                font.setItalic(True)
                label_item.setFont(font)

            self.report_table.setItem(row_idx, 0, label_item)

            # ----------------------------
            # Numeric fields
            # ----------------------------

            for col_idx, field in enumerate(numeric_fields, start=1):

                value = row.get(field, 0.0)

                if isinstance(value, float):
                    # Better formatting for qty vs money
                    if "qty" in field:
                        value_str = f"{value:,.4f}"
                    else:
                        value_str = f"{value:,.2f}"
                else:
                    value_str = str(value)

                item = QTableWidgetItem(value_str)

                # Apply same styling to numeric cells
                if row_type in ("subtotal", "grand_total", "summary"):
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

                elif row_type == "je_detail":
                    font = item.font()
                    font.setItalic(True)
                    item.setFont(font)

                self.report_table.setItem(row_idx, col_idx, item)

        # ---------------------------------------------------------
        # Cross-foot validation (projection mode only)
        # ---------------------------------------------------------

        grand = None
        computed = {field: 0.0 for field in numeric_fields}

        for r in flat_rows:
            if r.get("row_type") == "grand_total":
                grand = r
            elif r.get("row_type") == "data":
                for field in numeric_fields:
                    computed[field] += r.get(field, 0.0)

        if grand:
            for field in numeric_fields:
                if abs(computed[field] - grand.get(field, 0.0)) > 0.0001:
                    print(f"❌ Cross-foot failed for {field}")
                    break
            else:
                print("✔ Cross-foot validation PASSED")

        # ---------------------------------------------------------
        # Column sizing
        # ---------------------------------------------------------

        header = self.report_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)

        for col in range(1, len(columns)):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        self.report_table.show()


    def report_status_message(self, message, level="info"):
        """
        Push a message to the status queue.
        Level can be 'info', 'warning', or 'error'
        """
        prefix = {"info": "ℹ️", "warning": "⚠️", "error": "❌"}.get(level, "ℹ️")
        self.status_queue.put(f"{prefix} {message}")

    def export_current_tab_to_excel(self):
        current_tab = self.tab_widget.currentWidget()
        if hasattr(current_tab, "_df") and isinstance(current_tab._df, pd.DataFrame):
            path = QFileDialog.getSaveFileName(self, "Save to Excel", "", "Excel Files (*.xlsx)")[0]
            if path:
                current_tab._df.to_excel(path, index=False)
                print(f"✅ Saved: {path}")

    import sys
    import threading

    class StderrRedirector:
        def __init__(self, status_queue):
            self.status_queue = status_queue
            self.buffer = ""

        def write(self, msg):
            self.buffer += msg
            if "\n" in msg:
                full_message = self.buffer.strip()
                self.buffer = ""

                if "FileNotFoundError" in full_message or "[WinError 3]" in full_message:
                    self.status_queue.put(f"❌ Missing file or directory:\n{full_message}")
                elif "PermissionError" in full_message or "[WinError 5]" in full_message:
                    self.status_queue.put(f"🚫 Permission denied:\n{full_message}")
                elif "Traceback" in full_message or "Exception" in full_message:
                    self.status_queue.put(f"⚠️ Exception:\n{full_message}")
                # You can add more filters here if desired

        def flush(self):
            pass  # required for file-like compatibility

    def load_selection_list(self):
        import os

        raw_dirs = os.listdir(self.portfolio_directory)

        portfolios = [
            name for name in raw_dirs
            if os.path.isdir(os.path.join(self.portfolio_directory, name))
               and name != "Composites"
               and not name.startswith("ZLIST")
        ]

        portfolios = sorted(portfolios, key=natural_key)

#        composites = sorted(self.composites_by_name.keys(), key=natural_key)

        return {
  #          "composites": composites,
            "portfolios": portfolios
        }

    def on_portfolio_selection_changed(self):
        """
        Handles selection of portfolio or composite from dropdown.
        """

        selected = self.portfolio_dropdown.currentText()

        # ------------------------------------------------------------
        # Strip composite prefix
        # ------------------------------------------------------------
        if selected.startswith("[C] "):
            selected = selected.replace("[C] ", "")

        # ------------------------------------------------------------
        # Store clean selection
        # ------------------------------------------------------------
        self.selected_portfolio = selected

        # Optional debug (remove later)
        print("SELECTED:", self.selected_portfolio)

    def apply_query_filter(self):
        try:
            cockpit_name = self.query_dropdown.currentText()
            selected_portfolio = self.portfolio_dropdown.currentText()

            # 🧠 Parse filter text like: aapl, goog, ==REALIZEDINCOME
            filter_text = self.filter_input.text().strip()
            parsed_filters = self.parse_filter_text(filter_text)

            print("🔍 Parsed Filters:", parsed_filters)

            print(f"🔍 Applying parsed query filters: {parsed_filters}")

            self.read_card_and_generate_results(
                selected_portfolio=selected_portfolio,
                cockpit_name=cockpit_name,
                period_start=self.session_period_start,
                period_end=self.session_period_end,
                filters=parsed_filters
            )
        except Exception as e:
            print(f"❌ Error applying query filter: {e}")

    def update_session_dates_from_dialog(self, dialog):
        self.session_period_start = pd.to_datetime(dialog.get_start_date())
        self.session_period_end = pd.to_datetime(dialog.get_cutoff_date())

        if hasattr(self, "session_period_label"):
            self.session_period_label.setText(
                f"🗓️ Reporting Period: {self.session_period_start.date()} → {self.session_period_end.date()}"
            )

        print(f"🔁 Session dates updated to: {self.session_period_start} → {self.session_period_end}")
        print(f"🔍 Filter input before reload: '{self.filter_input.text()}'")  # ← this line

        self.execute_primary_load_and_filter(


        )

    def on_tab_double_clicked(self, index):
        if index < 0:
            return

        tab_name = self.tab_widget.tabText(index)
        original_tab = self.tab_widget.widget(index)

        if tab_name in self.floating_tabs:
            print(f"⚠️ Tab '{tab_name}' already floating.")
            return

        table_view = self.table_views.get(tab_name)
        if not table_view:
            print(f"❌ No table view found for tab '{tab_name}'")
            return

        self.tab_widget.removeTab(index)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(table_view)

        float_window = QMainWindow()
        float_window.setWindowTitle(f"📤 {tab_name}")
        float_window.setCentralWidget(container)
        float_window.resize(1000, 600)
        float_window.setAttribute(Qt.WA_DeleteOnClose)
        float_window.show()
        container.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border: 2px solid #4682B4;  /* SteelBlue */
                border-radius: 10px;
                padding: 6px;
            }
            QTableView {
                background-color: #ffffff;
                alternate-background-color: #f5faff;  /* Light blueish rows */
                gridline-color: #d3d3d3;
                selection-background-color: #cce5ff;
                selection-color: #000000;
                border: none;
            }
            QHeaderView::section {
                background-color: #f0f0f0;  /* Light gray that won’t overwrite */
                color: #000000;
                font-weight: bold;
                padding: 4px;
                border: 1px solid #dcdcdc;
            }
        """)

        def on_close(event):
            print(f"🔁 Re-docking tab '{tab_name}'")

            existing_index = self.tab_widget.indexOf(table_view)
            if existing_index != -1:
                self.tab_widget.removeTab(existing_index)

            new_tab = QWidget()
            new_layout = QVBoxLayout(new_tab)
            new_layout.addWidget(table_view)
            self.table_views[tab_name] = table_view
            self.tab_widget.addTab(new_tab, tab_name)
            self.floating_tabs.pop(tab_name, None)

            event.accept()

        float_window.closeEvent = on_close
        self.floating_tabs[tab_name] = float_window


    def closeEvent(self, event):
        # Always update parent session dates, even if window was closed via X
        if hasattr(self.parent(), "update_session_dates_from_dialog"):
            self.parent().update_session_dates_from_dialog(self)
        event.accept()

    def load_portfolio_files(self):
        """
        Load and return naturally sorted portfolio names from funds directory.
        """

        import os

        raw_dirs = os.listdir(self.portfolio_directory)

        portfolio_names = [
            name.strip()
            for name in raw_dirs
            if os.path.isdir(os.path.join(self.portfolio_directory, name))
               and name != "Composites"
               and not name.startswith("ZLIST")
        ]

        return sorted(portfolio_names, key=natural_key)

    def load_files(self):
        """
        This method is triggered to load both query cards and master link sets into memory.
        """
        print("Loading files...")

        try:
            # Load the data from the CSV files into pandas DataFrames
            self.master_link_sets = pd.read_csv(self.master_link_sets_path)
            self.query_cards = pd.read_csv(self.query_cards_path)

            # Convert column names to uppercase for consistency
            self.master_link_sets.columns = self.master_link_sets.columns.str.upper()
            self.query_cards.columns = self.query_cards.columns.str.upper()

            print("✅ Files loaded successfully!")

        except Exception as e:
            print(f"❌ Error loading files: {e}")

    def clear_dynamic_tabs(self):
        for i in reversed(range(self.tab_widget.count())):
            tab_name = self.tab_widget.tabText(i)
            if "QueryGet_" in tab_name or "Summary" in tab_name or "Detail" in tab_name:
                self.tab_widget.removeTab(i)

    def load_query_cards(self):
        import pandas as pd
        import os

        query_card_path = os.path.join(REFDATA_PATH, "query_cards.csv")

        try:
            df = pd.read_csv(query_card_path)
            df["CardName"] = df["CardName"].astype(str).str.strip()
            print(f"✅ Loaded QueryCards: {len(df)} rows")
            return df
        except Exception as e:
            print(f"❌ Error loading query_cards.csv: {e}")
            return pd.DataFrame()

    def build_cockpit_sets(self, df):
        """Converts cockpit_sets_df into a dict of cockpit_name → list of files."""
        if "CockpitName" not in df.columns:
            print("❌ 'CockpitName' column not found in cockpit_sets DataFrame.")
            return {}

        cockpit_sets = {}
        for _, row in df.iterrows():
            cockpit_name = row["CockpitName"]
            cockpit_set_items = [val for val in row.iloc[1:].dropna().tolist()]
            cockpit_sets[cockpit_name] = cockpit_set_items

        print(f"✅ Built cockpit_sets dictionary: {list(cockpit_sets.keys())}")
        return cockpit_sets

    def load_cockpit_sets_df(self):
        try:
            path = os.path.join(BASE_PATH, "refdata/master_link_sets.csv")
            df = pd.read_csv(path)
            print(f"✅ Loaded CockpitSets: {len(df)} rows")
            return df
        except Exception as e:
            print(f"❌ Error loading master_link_sets.csv: {e}")
            return pd.DataFrame()

    def load_cockpit_sets(self):
        """Load cockpit sets from the master link CSV."""
        cockpit_sets = {}
        try:
            # Read the cockpit set file
            master_link_sets_df = pd.read_csv(self.master_link_sets_path)

            # Check if the 'CockpitName' column exists
            if "CockpitName" in master_link_sets_df.columns:
                # Populate the cockpit_sets dictionary
                for _, row in master_link_sets_df.iterrows():
                    cockpit_name = row["CockpitName"]
                    cockpit_set_items = [val for val in row.iloc[1:].dropna().tolist()]
                    cockpit_sets[cockpit_name] = cockpit_set_items

                print(f"✅ Loaded {len(cockpit_sets)} cockpit sets from {self.master_link_sets_path}.")
            else:
                print("❌ 'CockpitName' column not found in master_link_sets.csv")
        except Exception as e:
            print(f"❌ Error loading cockpit sets: {e}")

        return cockpit_sets

    def refresh_cockpit_sets(self):
        """Reloads the cockpit sets from the CSV and updates the dropdown."""
        try:
            self.cockpit_sets_df = self.load_cockpit_sets_df()
            self.cockpit_sets = self.build_cockpit_sets(self.cockpit_sets_df)

            self.query_dropdown.clear()
            self.query_dropdown.addItems(list(self.cockpit_sets.keys()))

            print("🔄 Cockpit sets refreshed from CSV.")
            QMessageBox.information(self, "Refreshed", "Cockpit sets reloaded successfully.")


        except Exception as e:
            print(f"❌ Faile to refresh cockpit sets: {e}")
            QMessageBox.critical(self, "Error", str(e))
    def refresh_data(self):
        """
        Reloads the data from the CSV files and updates the internal data structures.
        """
        print("Refreshing data...")

        try:
            # Reload the data from the CSV files into pandas DataFrames
            self.master_link_sets = pd.read_csv(self.master_link_sets_path)
            self.query_cards = pd.read_csv(self.query_cards_path)

            # Convert column names to uppercase for consistency
            self.master_link_sets.columns = self.master_link_sets.columns.str.upper()
            self.query_cards.columns = self.query_cards.columns.str.upper()

            print("✅ Files loaded successfully!")

            # Optionally, refresh cockpit sets
            self.refresh_cockpit_sets()

            # Update the UI components as needed
            self.update_ui_components()

        except Exception as e:
            print(f"❌ Error loading files: {e}")


    def on_tab_selected(self, index):
        """Tracks the currently selected tab and updates the active tab name."""
        if index < 0:  # No valid tab selected
            return

        self.current_tab_name = self.tab_widget.tabText(index)
        print(f"📌 DEBUG: User switched to tab {self.current_tab_name}")

        # ✅ Only track Certain
        # Files for modification
        if self.current_tab_name in self.tabs_that_can_be_modified:
            print(f"✅ User selected a Gold File tab: {self.current_tab_name}")

    def update_current_data_from_ui(self):
        """Updates current_data from the currently active tab before saving."""
        if self.current_tab_name not in self.tabs_that_can_be_modified:
            return  # ✅ Only update for Gold Files

        model = self.table_view.model()
        self.current_data = self.extract_data_from_model(model)

        print(f"📌 DEBUG: current_data updated from UI for {self.current_tab_name}")

    def _run_query(self, selected_portfolio, cockpit_name):
        print(f"🟡 STEP 3: _run_query called for {selected_portfolio} / {cockpit_name}")
        print(
            f"📤 Calling read_card_and_generate_results with selected_portfolio='{selected_portfolio}', cockpit_name='{cockpit_name}', gw={self}")

        self.read_card_and_generate_results(

            selected_portfolio=selected_portfolio,
            cockpit_name=cockpit_name,
            gw=self
        )


        if df is None:
            print("❌ STEP 4: No result returned from query")
        else:
            print(f"✅ STEP 4: Received DataFrame with {len(df)} rows")

        if isinstance(df, pd.DataFrame) and not df.empty:
            index = self.tab_widget.currentIndex()
            tab_name = self.tab_widget.tabText(index) if index != -1 else f"{cockpit_name} Results"
            self.populate_tabs(tab_name, df, context_id=context_id)
        else:
            print("⚠️ No data to populate tabs.")

        self.stop_load_button_pulse()
        print("🟩 STEP 5: Button pulse stopped")

    def clear_existing_query_tabs(self):
        """Closes all query-generated tabs before reloading new ones."""
        for i in reversed(range(self.tab_widget.count())):
            tab_name = self.tab_widget.tabText(i)
            if tab_name.startswith("QueryGet_") or "BalanceRoll" in tab_name or "Journal Entry" in tab_name:
                self.tab_widget.removeTab(i)

    def handle_query_result(self, df):
        tab_name = self.tab_widget.tabText(self.tab_widget.currentIndex())
        if isinstance(df, pd.DataFrame):
            self.populate_tabs(tab_name, df, context_id=context_id)
        else:
            print("⚠️ No DataFrame returned or invalid format.")

    def execute_primary_load_and_filter(self):
        print("🔴 STEP 1: execute_primary_load_and_filter triggered")

        selected_portfolio = self.portfolio_dropdown.currentText().strip()
        cockpit_name = self.query_dropdown.currentText().strip()
        self.session.portfolio_name = selected_portfolio
        self.reset_load_button()

        if not selected_portfolio or not cockpit_name:
            print("⚠️ Missing portfolio or cockpit selection.")
            return

        self.start_load_button_pulse()
        print("🟥 STEP 2: Red button pulse started")

        # ✅ Single source of truth: asynchronous, avoids recursion
        QTimer.singleShot(0, lambda: self._run_query(selected_portfolio, cockpit_name))


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
            # ✅ Pull updated data from the model
            df = self.extract_data_from_model(model)

            portfolio_name = self.session.portfolio_name
            filepath_template = self.tab_to_master_file[current_tab_name]

            filepath = filepath_template.format(portfolio_name=portfolio_name) \
                if "{portfolio_name}" in filepath_template else filepath_template

            self.save_changes(df, filepath)
            QMessageBox.information(self, "Save Successful", f"Changes saved to {filepath}")

        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))
            import traceback
            traceback.print_exc()

    def save_changes(self, df, filepath):
        from filelock import FileLock

        backup_path = filepath + ".bak"
        lock = FileLock(filepath + ".lock")

        with lock:
            print(f"🔒 Lock acquired for {filepath}")

            if os.path.exists(filepath):
                shutil.copy(filepath, backup_path)
                print(f"📦 Backup created: {backup_path}")

            try:
                df = self.validate_dataframe(df, df.columns)  # ✅ FIXED typo here

                # ✅ Deformat numeric values before saving
                for col in df.columns:
                    df[col] = df[col].apply(self.deformat_data)

                import csv
                df.to_csv(filepath, index=False, quoting=csv.QUOTE_MINIMAL)
                print(f"✅ Successfully saved to {filepath}")

            except Exception as e:
                print(f"❌ ERROR: Failed to save data to '{filepath}': {e}")
                if os.path.exists(backup_path):
                    shutil.copy(backup_path, filepath)
                    print(f"🔄 Rollback applied: Restored {filepath} from backup.")

            finally:
                print(f"🔓 Lock released for {filepath}")

    def handle_cockpit_selection(self, index):
        self.selected_cockpit_name = self.query_dropdown.currentText()
        selected = self.query_dropdown.currentText()
        self.selected_cockpit_name = selected
        print(f"🎯 Cockpit selected: {selected}")

    from dateutil.parser import parse

    def parse_filter_text(self, filter_text):
        filters = {}
        if not filter_text:
            return filters

        try:
            key, value = filter_text.strip().split("=", 1)
            filters[key.strip().upper()] = f"=={value.strip()}"
        except ValueError:
            print("❌ Could not parse filter text. Expected format: FIELD = VALUE")

        return filters

    def trigger_je_drilldown(self, summary_tab_name, row_index):
        """
        Trigger JE Detail drilldown using a specific row's context (e.g., tranid).
        Intended to run from summary views like Position Roll or Balance Sheet.
        """
        try:
            if summary_tab_name not in self.table_views:
                print(f"❌ No table view found for tab '{summary_tab_name}'")
                return

            table_view = self.table_views[summary_tab_name]
            model = table_view.model()

            if row_index < 0 or row_index >= model.rowCount():
                print(f"❌ Invalid row index {row_index}")
                return

            # 🔍 Extract values from the row
            row_context = {}
            for col in range(model.columnCount()):
                header = model.headerData(col, Qt.Horizontal)
                cell_value = model.data(model.index(row_index, col), Qt.DisplayRole)
                row_context[header] = cell_value

            print(f"🕵️ Drilldown context from row {row_index}: {row_context}")

            # ✅ Identify key field for JE drilldown (e.g., tranid)
            tranid = row_context.get("tranid") or row_context.get("TranID")
            if not tranid:
                QMessageBox.warning(self, "Drilldown Skipped", "No 'tranid' found in row.")
                return

            # ✅ Build filters for drilldown query
            filter_dict = {"tranid": f"=={tranid}"}

            from centralized_reporting_hub import run_query_from_card
            df = run_query_from_card(
                card_name="QueryGet_JEDetail",
                portfolio=self.portfolio_dropdown.currentText(),
                period_start=self.session_period_start,
                period_end=self.session_period_end,
                filters=filter_dict,
                card_type="SECOND",  # Optional: distinguish from primary
                gw=self
            )

            if df is not None and not df.empty:
                self.populate_tabs("JEDetail_Drilldown", df, context_id=context_id)
            else:
                QMessageBox.information(self, "No Data", "No matching JEs found for selected context.")

        except Exception as e:
            print(f"❌ Error during JE drilldown: {e}")

    def on_cell_double_clicked(self, index):
        # Step 1: Find the current tab name
        current_widget = self.tab_widget.currentWidget()
        current_tab_name = None
        for name, view in self.table_views.items():
            if view.parent() == current_widget:
                current_tab_name = name
                break

        if not current_tab_name:
            print("⚠ Could not resolve active tab to table view.")
            return

        table_view = self.table_views[current_tab_name]
        model = table_view.model()

        if not model:
            print("⚠ No model found for selected tab.")
            return

        row = index.row()
        headers = [model.headerData(i, Qt.Horizontal) for i in range(model.columnCount())]

        if "INVESTMENT" in headers:
            investment_idx = headers.index("INVESTMENT")
            investment_name = model.index(row, investment_idx)

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
        """Loads selected portfolio and query set, and resolves file paths for saving."""
        selected_query_set = self.query_dropdown.currentText()
        selected_portfolio = self.portfolio_dropdown.currentText()
        self.session.portfolio_name = self.portfolio_dropdown.currentText().strip()

        if not selected_portfolio or not selected_query_set:
            print("⚠ No portfolio or query set selected.")
            return

        print(f"📌 DEBUG: Loading Query Set '{selected_query_set}' for Portfolio '{selected_portfolio}'")

        # ✅ Load the data (calls FQL engine if query card)
        self.read_card_and_generate_results(
            selected_portfolio=selected_portfolio,
            cockpit_name=selected_query_set,
            period_start=self.session_period_start if hasattr(self, 'session_period_start') else pd.to_datetime(
                "2023-01-03"),
            period_end=self.session_period_end if hasattr(self, 'session_period_end') else pd.to_datetime("2023-03-31"),
            filters=None,
            gw=self
        )

        # ✅ Assign save file path
        self.current_data = None
        if self.current_tab_name in self.tab_to_master_file:
            self.current_filepath = self.tab_to_master_file[self.current_tab_name].replace(
                "{portfolio_name}", selected_portfolio)
        else:
            self.current_filepath = f"{BASE_PATH}/funds/{selected_portfolio}.csv"

        print(f"📌 DEBUG: self.current_filepath SET TO: {self.current_filepath}")
        print(f"✅ Data Loaded: {self.current_data.shape if self.current_data is not None else 'No Data'}")
        print(f"✅ Save Path Set: {self.current_filepath}")

    def read_card_and_generate_results(self, selected_portfolio, cockpit_name,
                                       period_start=None, period_end=None,
                                       filters=None, gw=None):
        import os
        import pandas as pd
        from ast import literal_eval
        import traceback

        print("🔵 STEP 3a: read_card_and_generate_results started")

        if getattr(self, "_is_generating", False):
            print("⛔ Preventing recursive call to read_card_and_generate_results")
            return

        self._is_generating = True
        self.start_load_button_pulse()

        try:
            if cockpit_name not in self.cockpit_sets:
                print(f"⚠️ Cockpit set not found: {cockpit_name}")
                return

            self.tab_widget.clear()
            self.table_views.clear()
            self.filter_query = ""
            filters = filters or {}

            cockpit_items = self.cockpit_sets[cockpit_name]
            period_start = pd.to_datetime(period_start or self.session_period_start)
            period_end = pd.to_datetime(period_end or self.session_period_end)

            # 🔹 Load query cards once
            query_card_path = os.path.join(self.base_directory, "refdata/query_cards.csv")
            query_cards = None
            if os.path.exists(query_card_path):
                query_cards = pd.read_csv(query_card_path)
                query_cards["CardName"] = query_cards["CardName"].astype(str).str.strip()
            else:
                print(f"❌ query_cards.csv not found at {query_card_path}")

            for item in cockpit_items:
                # ───────────────────────────────────────────────
                # 🔹 QUERY CARD (exists in query_cards.csv)
                # ───────────────────────────────────────────────
                if query_cards is not None and item in query_cards["CardName"].values:

                    tab_name = item
                    context_id = f"{selected_portfolio}:{tab_name}"

                    try:
                        portfolios = resolve_portfolio_list(
                            selected_portfolio,
                            "C:/Users/hjmne/PycharmProjects/chest/funds"
                        )

                        from financial_information_gateway.fig import run_box_balance_view_from_state
                        from financial_information_gateway.prep import prepare_box_state
                        from financial_information_gateway.rendering.gwi_adapter import flatten_states_for_gwi

                        states = {}

                        # ✅ Determine shape ONCE
                        shape = resolve_fig_shape(item)

                        for pname in portfolios:
                            prep = prepare_box_state(
                                portfolio=pname,
                                calendar=self.session_calendar,
                                period_start=period_start,
                                period_end=period_end,
                            )

                            state = run_box_balance_view_from_state(
                                prep,
                                include_je_detail=False,
                                shape=shape
                            )

                            states[pname] = state

                        # ---------------------------------------
                        # 🔹 COMPOSITE HANDLING (YOUR SPEC)
                        # ---------------------------------------
                        if shape == "top_holdings":

                            if self.composite_mode == "aggregate":

                                result = build_aggregate_top_holdings(states)

                                rows = []
                                for inv, row in result.items():
                                    r = dict(row)
                                    r["investment"] = inv
                                    rows.append(r)

                                df = pd.DataFrame(rows)

                            elif self.composite_mode == "list":

                                result = build_list_top_holdings(states)

                                rows = []
                                for portfolio, holdings in result.items():
                                    for inv, row in holdings.items():
                                        r = dict(row)
                                        r["portfolio"] = portfolio
                                        r["investment"] = inv
                                        rows.append(r)

                                df = pd.DataFrame(rows)

                        # ---------------------------------------
                        # 🔹 DEFAULT (NON-COMPOSITE)
                        # ---------------------------------------
                        else:
                            rows = flatten_states_for_gwi(states)
                            df = pd.DataFrame(rows)

                        # ✅ DO NOT overwrite rows here

                        if not df.empty:
                            self.populate_tabs(tab_name, df, context_id=context_id)
                        else:
                            print(f"⚠️ No FIG data for {tab_name}")

                    except Exception as e:
                        print(f"❌ FIG query failed for {tab_name}: {e}")
                        traceback.print_exc()
                # ───────────────────────────────────────────────
                # 🔹 EXTERNAL FILE (.csv/.xlsx)
                # ───────────────────────────────────────────────
                elif item.lower().endswith((".csv", ".xlsx")):
                    tab_name = os.path.splitext(os.path.basename(item))[0]
                    context_id = f"{selected_portfolio}:{tab_name}"
                    report_path = os.path.join(self.reports_directory, item)

                    if not os.path.exists(report_path):
                        print(f"❌ Report file not found: {report_path}")
                        continue

                    try:
                        df = pd.read_excel(report_path) if item.endswith(".xlsx") else pd.read_csv(report_path)
                        self.populate_tabs(tab_name, df, context_id=context_id)
                    except Exception as e:
                        print(f"❌ Failed to read report file: {report_path} — {e}")
                        traceback.print_exc()

                # ───────────────────────────────────────────────
                # 🔹 MAPPED GOLD FILE
                # ───────────────────────────────────────────────
                elif item in self.tab_to_master_file:
                    tab_name = item
                    context_id = f"{selected_portfolio}:{tab_name}"
                    filepath = self.tab_to_master_file[item].format(portfolio_name=selected_portfolio)

                    if not os.path.exists(filepath):
                        print(f"❌ Mapped file does not exist: {filepath}")
                        continue

                    try:
                        df = pd.read_csv(filepath)
                        self.populate_tabs(tab_name, df, context_id=context_id)
                    except Exception as e:
                        print(f"❌ Failed to load mapped file '{filepath}': {e}")
                        traceback.print_exc()

                # ───────────────────────────────────────────────
                # 🔹 UNRECOGNIZED
                # ───────────────────────────────────────────────
                else:
                    print(f"⚠️ Unrecognized cockpit item: {item}")

        finally:
            self._is_generating = False
            self.stop_load_button_pulse()
            print(f"✅ Finished Loading Cockpit: {cockpit_name}")

    def run_composite_query(portfolio_list, cockpit_item, settings,
                            period_start, period_end, calendar):
        import multiprocessing

        def worker(portfolio_name, out_q):
            result = run_query_card_for_portfolio(portfolio_name, cockpit_item, settings, period_start, period_end,
                                                  calendar)
            if isinstance(result, pd.DataFrame) and not result.empty:
                result["PORTFOLIO"] = portfolio_name
                out_q.put(result)

        out_q = multiprocessing.Queue()
        jobs = []

        for name in portfolio_list:
            p = multiprocessing.Process(target=worker, args=(name, out_q))
            jobs.append(p)
            p.start()

        for job in jobs:
            job.join()

        results = []
        while not out_q.empty():
            results.append(out_q.get())

        if results:
            return pd.concat(results, ignore_index=True)
        else:
            return pd.DataFrame()

    def validate_query_card_structure(card, required_fields=("CardName", "Mode")):
        for field in required_fields:
            if field not in card or pd.isna(card[field]) or not str(card[field]).strip():
                raise ValueError(f"❌ Query card is missing or has an invalid '{field}' field.")

    def get_tab_name_from_item(self, cockpit_item):
        if cockpit_item.startswith("QueryGet_"):
            return cockpit_item.replace("QueryGet_", "")
        return cockpit_item

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

    def show_gold_context_menu(self, table_view, tab_name, position):
        """Provides right-click options specific to gold file tabs."""
        index = table_view.indexAt(position)
        if not index.isValid():
            return

        menu = QMenu(table_view)
        duplicate_action = QAction("➕ Duplicate Row", self)
        duplicate_action.triggered.connect(lambda: self.handle_gold_row_double_click(index))
        menu.addAction(duplicate_action)

        save_action = QAction("💾 Save Changes", self)
        save_action.triggered.connect(lambda: self.on_save_clicked())
        menu.addAction(save_action)

        menu.exec(table_view.viewport().mapToGlobal(position))

    def lookup_event_by_tranid(self, tranid):
        print(f"📎 Opening event for TRANID: {tranid}")
        # Replace with real event loading logic
        self.get_event_by_tranid(tranid)  # ✅ If you already have this defined

    def show_context_menu(self, table_view, tab_name, pos):
        """Shows right-click context menu with conditional gold file support."""
        index = table_view.indexAt(pos)
        if not index.isValid():
            return

        menu = QMenu()

        # ✅ Gold-only: Add "Duplicate Row"
        if tab_name in self.tabs_that_can_be_modified:
            duplicate_action = QAction("📎 Duplicate Row", self)
            duplicate_action.triggered.connect(lambda: self.handle_gold_row_double_click(index))
            menu.addAction(duplicate_action)

        # ✅ Universal: Add "Save Changes"
        save_action = QAction("💾 Save Changes", self)
        save_action.triggered.connect(self.on_save_clicked)
        menu.addAction(save_action)

        menu.exec(table_view.viewport().mapToGlobal(pos))

    def create_table(df, tab_name, gw):
        """Creates a new tab with the given DataFrame in the GUI."""
        if gw:
            context_id = f"{gw.selected_portfolio}:{tab_name}"  # or pull from df/session metadata
            gw.populate_tabs(tab_name, df, context_id=context_id)

    def update_table(df, tab_name, gw):
        """Updates an existing tab (or creates one) with the given DataFrame."""
        if gw:
            context_id = f"{gw.selected_portfolio}:{tab_name}"  # or pull from df/session metadata
            gw.populate_tabs(tab_name, df, context_id=context_id)

    def current_table_view(self):
        return self.table_views.get(self.current_tab_name)

    def duplicate_gold_row(self, table_view, row_index, tab_name):
        """Duplicates a row and updates kdend/kdbegin logic."""
        try:
            model = table_view.model()
            if not model:
                raise ValueError("No model found for table view")

            duplicated_items = []
            for col in range(model.columnCount()):
                original_item = model.item(row_index, col)
                new_item = QStandardItem(original_item.text())
                new_item.setFont(QFont("Arial", 10))
                new_item.setEditable(True)
                duplicated_items.append(new_item)

            # Update knowledge dates
            column_names = [model.headerData(col, Qt.Horizontal) for col in range(model.columnCount())]
            kdend_idx = column_names.index("kdend")
            kdbegin_idx = column_names.index("kdbegin")

            old_kdend_str = model.item(row_index, kdend_idx).text()
            old_kdend = pd.to_datetime(old_kdend_str, errors="coerce", format="%m/%d/%Y:%H:%M:%S")
            if pd.isnull(old_kdend):
                old_kdend = pd.to_datetime(old_kdend_str)  # fallback

            new_kdend = datetime.now().strftime("%m/%d/%Y:%H:%M:%S")
            model.item(row_index, kdend_idx).setText(new_kdend)

            new_kdbegin = (pd.to_datetime(new_kdend) + timedelta(seconds=1)).strftime("%m/%d/%Y:%H:%M:%S")
            duplicated_items[kdbegin_idx].setText(new_kdbegin)
            duplicated_items[kdend_idx].setText("12/31/2099:00:00:00")

            # Insert below the original row
            insert_index = row_index + 1
            model.insertRow(insert_index, duplicated_items)

            # Refresh current_data
            self.current_data = self.extract_data_from_model(model)
            print(f"📌 Row {row_index} duplicated in tab '{tab_name}'.")
        except Exception as e:
            print(f"❌ Error duplicating row in tab '{tab_name}': {e}")

    def handle_gold_row_double_click(self, index):
        try:
            tab_name = self.current_tab_name
            if tab_name not in self.tabs_that_can_be_modified:
                print(f"⚠️ Double-click ignored — tab '{tab_name}' is not a modifiable file.")
                return

            table = self.current_table_view()
            model = table.model()
            row = index.row()

            print(f"📌 Gold row double-clicked at index {row} in tab '{tab_name}'")

            original_items = [model.item(row, col) for col in range(model.columnCount())]
            duplicated_items = [item.clone() for item in original_items]

            if tab_name in self.gold_file_tabs:
                # ✅ Add timestamp logic only for gold tabs
                now = datetime.now()
                now_str = now.strftime("%m/%d/%Y:%H:%M:%S")
                next_second_str = (now + timedelta(seconds=1)).strftime("%m/%d/%Y:%H:%M:%S")

                headers = [model.headerData(col, Qt.Horizontal) for col in range(model.columnCount())]
                kdend_col = headers.index("kdend")
                kdbegin_col = headers.index("kdbegin")

                model.item(row, kdend_col).setText(now_str)
                duplicated_items[kdbegin_col].setText(next_second_str)
                duplicated_items[kdend_col].setText("12/31/2099:00:00:00")

            model.insertRow(row + 1, duplicated_items)
            self.current_data = self.extract_data_from_model(model)
            print(f"✅ Row duplicated in tab '{tab_name}'")

        except Exception as e:
            print(f"❌ Error in handle_gold_row_double_click: {e}")

    def enter_flow_view_mode(self, df, hierarchy):
        from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableView, QComboBox
        from PyQt5.QtGui import QStandardItemModel, QStandardItem
        from PyQt5.QtCore import Qt

        # 🧼 Step 1: Clear old layout and hide tabs
        self.tab_widget.hide()

        if hasattr(self, "flow_container"):
            self.flow_container.setParent(None)  # Remove previous flow view

        self.flow_container = QWidget()
        flow_layout = QVBoxLayout()
        self.flow_container.setLayout(flow_layout)
        self.centralWidget().layout().addWidget(self.flow_container)

        # 🧭 Step 2: View selector (BS Start / Activity / BS End)
        self.flow_selector = QComboBox()
        self.flow_selector.addItems(["BS Start", "Activity", "BS End"])
        flow_layout.addWidget(QLabel("View:"))
        flow_layout.addWidget(self.flow_selector)

        # 📋 Step 3: Main table view
        self.flow_table = QTableView()
        flow_layout.addWidget(self.flow_table)

        # 💾 Step 4: Cache the data and hierarchy
        self.flow_df = df
        self.flow_hierarchy = hierarchy

        # 🔄 Step 5: Populate the table
        self.load_flowview_table(df)

        # 🎯 Optional: Hook for changing selector
        self.flow_selector.currentTextChanged.connect(lambda val: self.on_flow_view_selection_changed(val))

    def load_flowview_table(self, df):
        """Populates the flow table from the DataFrame."""
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(df.columns.tolist())

        for row in df.itertuples(index=False):
            items = []
            for value in row:
                item = QStandardItem(str(value))
                item.setEditable(False)
                items.append(item)
            model.appendRow(items)

        self.flow_table.setModel(model)
        self.flow_table.resizeColumnsToContents()

    def get_current_tab_name(self):
        """
        Returns the current active tab name.
        """
        index = self.tab_widget.currentIndex()
        if index == -1:
            return None
        return self.tab_widget.tabText(index)

    def reload_tab_data(self, tab_name):
        """
        Reloads the original data by clearing all filters.
        """
        print(f"🔍 Reload requested for tab_name='{tab_name}'")

        controller = None
        if hasattr(self, "vfilter_controllers"):
            controller = self.vfilter_controllers.get(tab_name)
        if not controller and hasattr(self, "v_filter_controllers"):
            controller = self.v_filter_controllers.get(tab_name)

        if not controller:
            print(f"❌ No v_filter controller found for tab: {tab_name}")
            return

        controller.reset_filters()
        self.update_tab_from_v_filter(tab_name)
        print(f"🔄 Reloaded original data for tab '{tab_name}'.")

    def update_tab_from_v_filter(self, tab_name):
        """
        Applies the active v_filter to the tab and refreshes its data.
        """
        print(f"🔍 Looking up controller for tab_name='{tab_name}'")

        controller = None
        if hasattr(self, "vfilter_controllers"):
            controller = self.vfilter_controllers.get(tab_name)
        if not controller and hasattr(self, "v_filter_controllers"):
            controller = self.v_filter_controllers.get(tab_name)

        if not controller:
            print(f"❌ No v_filter controller found for tab: {tab_name}")
            return

        df = controller.get_current_view()
        if df.empty:
            print(f"⚠ Filtered data is empty for tab: {tab_name}")
            return

        table_view = self.table_views.get(tab_name)
        if not table_view:
            print(f"❌ No table view found for tab: {tab_name}")
            return

        header = table_view.horizontalHeader()
        try:
            header.filter_applied.disconnect()
        except Exception:
            pass  # already disconnected

        self.refresh_tab_data_only(tab_name, df)

        # Reconnect cleanly
        header.filter_applied.connect(lambda: self.update_tab_from_v_filter(tab_name))
        print(f"✅ Tab '{tab_name}' successfully updated from v_filter.")

    def on_flow_view_selection_changed(self, selected):
        # Placeholder logic: In a real version this would switch between pre-filtered views
        print(f"🔄 FlowView selection changed to: {selected}")
        # For now, just reload same table
        self.load_flowview_table(self.flow_df)

    def refresh_tab_data_only(self, tab_name, df):
        from PySide6.QtGui import QStandardItemModel, QStandardItem, QFont
        table_view = self.table_views.get(tab_name)
        if table_view is None:
            print(f"❌ No table view found for '{tab_name}' to refresh data.")
            return

        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(df.columns.tolist())

        for _, row in df.iterrows():
            items = [QStandardItem(str(val)) for val in row]
            for item in items:
                item.setFont(QFont("Arial", 10))
                item.setEditable(True)
            model.appendRow(items)

        table_view.setModel(model)
        print(f"✅ Refreshed data for tab '{tab_name}' with {df.shape[0]} rows.")

    from PySide6.QtGui import QColor, QBrush

    def apply_row_highlighting_based_on_ppa_flag(self, row, columns):
        items = []
        is_prior_adj = "TRANSACTION" in columns and row.get("TRANSACTION") == "PriorPeriodAdjustment"
        for val in row:
            item = QStandardItem(str(val))
            item.setFont(QFont("Arial", 10))
            item.setEditable(True)
            if is_prior_adj:
                item.setBackground(QBrush(QColor(255, 230, 230)))  # Light red
            items.append(item)
        return items

    def route_context_menu(self, table_view, tab_name, pos):
        """Route right-clicks: header → filter, cells → edit/save actions."""
        index = table_view.indexAt(pos)
        if index.isValid():
            # ✅ Right-clicked on a cell — show your edit/save menu
            self.show_context_menu(table_view, tab_name, pos)
        else:
            # 🛑 Right-clicked on header — v_filter_header takes over
            pass  # Do nothing; header is already interactive

    from PySide6.QtWidgets import QAbstractItemView

    # def enable_column_swapping(self, table_view):
    #     header = table_view.horizontalHeader()
    #     header.setSectionsMovable(True)
    #     header.setStretchLastSection(False)
    #     header.setDragEnabled(True)
    #     header.setDragDropMode(QAbstractItemView.InternalMove)
    #

    def run_query_from_manifest(self, manifest_path, group_by, sum_fields, sort_by=None):
        import os
        import pandas as pd

        print(f"📄 Running Vantage Query from Manifest: {manifest_path}")
        df_manifest = pd.read_csv(manifest_path)

        all_dfs = []
        for _, row in df_manifest.iterrows():
            file_path = os.path.join(os.path.dirname(manifest_path), "files", row["filename"])
            if os.path.exists(file_path):
                df = pd.read_csv(file_path)
                df["portfolio"] = row.get("portfolio", "UNKNOWN")
                all_dfs.append(df)
            else:
                print(f"⚠️ Missing file: {file_path}")

        if not all_dfs:
            print("❌ No data found.")
            return pd.DataFrame()

        df_all = pd.concat(all_dfs, ignore_index=True)

        # Normalize column names to lowercase
        df_all.columns = [col.strip().lower().replace("Â", "") for col in df_all.columns]
        if "r²" in df_all.columns:
            df_all.rename(columns={"r²": "r2"}, inplace=True)

        # Coerce only the sum fields to numeric
        for col in sum_fields:
            if col in df_all.columns:
                df_all[col] = pd.to_numeric(df_all[col], errors="coerce")

        # Group and summarize
        df_grouped = df_all.groupby(group_by)[sum_fields].sum().reset_index()

        # Optional sort
        if sort_by and sort_by in df_grouped.columns:
            df_grouped = df_grouped.sort_values(by=sort_by, ascending=False)

        return df_grouped

    def populate_tabs(
            self,
            tab_name,
            data,
            visible_columns=None,
            group_by=None,
            *,
            context_id=None
    ):
        import pandas as pd
        import traceback

        print("in populate tabs")

        try:
            if context_id is None:
                context_id = f"{getattr(self, 'selected_portfolio', 'UNKNOWN')}:{tab_name}"

            print(f"\n📋 Populating tab: {tab_name}")
            print(f"🧪 Context: {context_id}")

            # ============================================================
            # 🔥 NEW: HANDLE FIG RESULT WITH STATES
            # ============================================================
            if isinstance(data, dict) and "states" in data:
                print("🧪 Detected period_chain states")

                blocks = build_render_blocks(
                    data,
                    visible_columns=visible_columns,
                    group_by=group_by
                )

                for i, block in enumerate(blocks):
                    df = block.get("dataframe")
                    if df is None or df.empty:
                        continue

                    print(f"🧪 Rendering block {i} shape: {df.shape}")

                    self._render_dataframe_to_tab(
                        tab_name,
                        df,
                        visible_columns=visible_columns,
                        group_by=group_by,
                        context_id=context_id
                    )

                return

            # ============================================================
            # 🔥 NEW: HANDLE FIG RESULT WITH "data"
            # ============================================================
            if isinstance(data, dict) and "data" in data:
                df = data["data"]
                if isinstance(df, pd.DataFrame):
                    print("🧪 Detected dict with DataFrame")
                    self._render_dataframe_to_tab(
                        tab_name,
                        df,
                        visible_columns=visible_columns,
                        group_by=group_by,
                        context_id=context_id
                    )
                    return

            # ============================================================
            # 🔥 EXISTING: DATAFRAME PATH (UNCHANGED)
            # ============================================================
            if isinstance(data, pd.DataFrame):

                if data.empty:
                    print(f"⚠️ Skipping tab '{tab_name}' — no data.")
                    return

                print(f"🧪 DataFrame Shape: {data.shape}")

                self._render_dataframe_to_tab(
                    tab_name,
                    data,
                    visible_columns=visible_columns,
                    group_by=group_by,
                    context_id=context_id
                )
                return

            # ============================================================
            # FALLBACK
            # ============================================================
            print(f"⚠️ Unsupported data type for tab '{tab_name}'")

        except Exception as e:
            print(f"❌ Error populating tab '{tab_name}': {e}")
            traceback.print_exc()

    def build_render_blocks(data, visible_columns=None, group_by=None):

        import pandas as pd

        # FIG result with states
        if isinstance(data, dict) and "states" in data:
            states = data["states"]

            if not states:
                return []

            # Use latest state (or adjust later)
            df = states[-1].get("data")

            if isinstance(df, pd.DataFrame):
                return [{"dataframe": df}]

        # FIG result with direct data
        if isinstance(data, dict) and "data" in data:
            df = data["data"]
            if isinstance(df, pd.DataFrame):
                return [{"dataframe": df}]

        # Already a DataFrame
        if isinstance(data, pd.DataFrame):
            return [{"dataframe": data}]

        return []


    def apply_secondary_filters(self, df, filters):
        if not filters:
            return df

        for key, condition in filters.items():
            if key not in df.columns:
                print(f"⚠ Column '{key}' not in DataFrame.")
                continue

            operator = condition[:2]
            value = condition[2:]

            try:
                if operator == "==":
                    df = df[df[key] == value]
                elif operator == "!=":
                    df = df[df[key] != value]
                elif operator == ">=":
                    df = df[df[key] >= value]
                elif operator == "<=":
                    df = df[df[key] <= value]
                elif operator == ">>":
                    df = df[df[key] > value]
                elif operator == "<<":
                    df = df[df[key] < value]
                else:
                    print(f"⚠ Unsupported operator: {operator}")
            except Exception as e:
                print(f"❌ Error applying filter on {key}: {e}")

        return df

    def store_filter_query(self):
        """Stores the filter query for later execution when Load Cockpit Set is clicked."""
        self.filter_query = self.filter_input.text().strip().lower()
        print(f"📝 Stored filter query: {self.filter_query}")  # Debugging

    def map_lotid_to_tranid(self, lotid):
        return self.lotid_to_tranid_map.get(lotid) if hasattr(self, "lotid_to_tranid_map") else None

    def handle_all_double_clicks(self, index, tab_name, table_view):
        model = table_view.model()
        column_name = model.headerData(index.column(), Qt.Horizontal).upper()
        value = model.data(index)

        print(f"📌 Double-clicked column: {column_name} — Value: {value}")

        if column_name == "TRANID":
            self.on_table_double_click(index, table_view)

        elif column_name == "INVESTMENT":
            self.on_cell_double_clicked(index, table_view)

        elif column_name == "LOTID":
            tranid = self.lotid_to_tranid_map.get(value)
            if tranid:
                print(f"🔍 Resolved TRANID {tranid} from LOTID {value} — invoking lookup...")
                self.lookup_event_by_tranid(tranid)
            else:
                print(f"⚠️ No TRANID found for LOTID: {value}")

    def apply_stored_filter(self):
        """Applies a flexible, case-insensitive multi-term text filter across all tabs with AND/OR logic."""
        if not hasattr(self, 'filter_query') or not self.filter_query:
            print("🔄 No stored filter to apply. Leaving current data visible.")
            return

        filter_query = self.filter_query.lower().strip()

        # Determine logic type: OR if ' or ' is present, otherwise AND
        if " or " in filter_query:
            filter_terms = [term.strip() for term in filter_query.split(" or ") if term.strip()]
            logic = "OR"
        else:
            filter_terms = [term.strip() for term in filter_query.replace(",", " ").split() if term.strip()]
            logic = "AND"

        print(f"🔍 Applying filter ({logic}): {filter_terms}")

        for i in range(self.tab_widget.count()):
            tab_name = self.tab_widget.tabText(i)
            tab = self.tab_widget.widget(i)
            table_view = tab.findChild(QTableView)

            if not table_view:
                continue

            model = table_view.model()
            if not isinstance(model, QStandardItemModel):
                continue

            # ✅ Build filtered model
            filtered_model = QStandardItemModel()
            filtered_model.setHorizontalHeaderLabels(
                [model.horizontalHeaderItem(c).text() for c in range(model.columnCount())]
            )

            for row in range(model.rowCount()):
                row_data = [model.item(row, col).text().lower() for col in range(model.columnCount())]

                if logic == "AND":
                    match = all(any(term in cell for cell in row_data) for term in filter_terms)
                else:  # OR logic
                    match = any(term in cell for term in filter_terms for cell in row_data)

                if match:
                    filtered_model.appendRow(
                        [QStandardItem(model.item(row, col).text()) for col in range(model.columnCount())]
                    )

            table_view.setModel(filtered_model)
            print(f"✅ Filter applied on '{tab_name}', {filtered_model.rowCount()} rows match.")


    def show_message(self, message, title="Info"):
        QMessageBox.information(None, title, message)


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

    def populate_selected_cockpit_set(self):
        try:
            cockpit_tab = self.table_views.get("CockpitSets")
            if cockpit_tab is None:
                print("❌ CockpitSets tab not found.")
                return

            table = cockpit_tab
            model = table.model()
            selected = table.selectionModel().selectedIndexes()
            if not selected:
                print("⚠ No row selected for population.")
                return

            selected_row = selected[0].row()
            cockpit_name_item = model.item(selected_row, 0)
            if cockpit_name_item is None:
                print("❌ Could not get CockpitName from selected row.")
                return

            cockpit_name = cockpit_name_item.text().strip()
            component_file = "BASE_PATH/refdata/cockpit_components.csv"

            import pandas as pd
            df_components = pd.read_csv(component_file)

            row_match = df_components[df_components["CockpitName"].str.strip() == cockpit_name]
            if row_match.empty:
                print(f"⚠ No components found for '{cockpit_name}' in cockpit_components.csv.")
                return

            component_values = row_match.iloc[0].tolist()[1:]  # skip the CockpitName column
            component_values = [c for c in component_values if pd.notna(c) and str(c).strip()]

            print(f"🧩 Populating row for '{cockpit_name}' with: {component_values}")

            for i, val in enumerate(component_values, start=1):
                if i >= model.columnCount():
                    model.setColumnCount(i + 1)
                    model.setHorizontalHeaderItem(i, QStandardItem(f"Component{i}"))
                model.setItem(selected_row, i, QStandardItem(str(val)))

            print(f"✅ Row updated for '{cockpit_name}'. Save changes (Ctrl+S or right-click).")

        except Exception as e:
            print(f"❌ Error in populate_selected_cockpit_set: {e}")


if __name__ == "__main__":

    import multiprocessing
    multiprocessing.freeze_support()

    print(">>> ENTER main.py")

    app = QApplication(sys.argv)
    window = GWIUnified()
    window.show()

    print(">>> LEAVE main.py")

    sys.exit(app.exec())
