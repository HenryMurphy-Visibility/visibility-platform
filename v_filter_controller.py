# v_filter_controller.py
# Visibility Filter Engine – Column-based Data Refinement with Header Interactivity

import pandas as pd
import os


def load_vfilter_config(path):
    """
    Loads v_filter configuration from a CSV file.
    Returns a dictionary:
    {
        "COLUMN_NAME": {
            "max_values": int or None,
            "requires_search": bool,
            "disable_filter": bool
        },
        ...
    }
    """
    config = {}

    if not os.path.exists(path):
        print(f"⚠️ v_filter config file not found at {path}. Proceeding without special column rules.")
        return config

    try:
        df = pd.read_csv(path)

        for _, row in df.iterrows():
            col = str(row.get("COLUMN_NAME", "")).strip()
            if not col:
                continue  # Skip blank column names

            config[col] = {
                "max_values": int(row["MAX_VALUES_SHOWN"]) if not pd.isna(row.get("MAX_VALUES_SHOWN")) else None,
                "requires_search": str(row.get("REQUIRES_SEARCH", "")).strip().upper() == "TRUE",
                "disable_filter": str(row.get("DISABLE_FILTER", "")).strip().upper() == "TRUE",
            }

        print(f"✅ Loaded v_filter config for {len(config)} columns.")

    except Exception as e:
        print(f"❌ Error loading v_filter config: {e}")

    return config


class VFilterController:
    def __init__(self, original_df):
        """
        Initialize the v_filter engine with a base DataFrame.
        This DataFrame will not be modified — all filters apply to a working copy.
        """
        self.original_df = original_df.copy()
        self.filtered_df = original_df.copy()
        self.active_filters = {}  # Dictionary of {column: list of allowed values}

    import pandas as pd
    import os


    def apply_filter(self, column, values):
        """
        Apply a filter to a specific column.
        :param column: Column name to filter on
        :param values: List of accepted values for this column
        """
        if not isinstance(values, list):
            values = [values]
        self.active_filters[column] = values
        self._update_filtered_df()

    def clear_filter(self, column):
        """
        Remove filter for a specific column.
        """
        if column in self.active_filters:
            del self.active_filters[column]
            self._update_filtered_df()

    def reset_filters(self):
        """
        Clear all filters and restore the original DataFrame.
        """
        self.active_filters.clear()
        self.filtered_df = self.original_df.copy()

    def _update_filtered_df(self):
        """
        Internal method to rebuild filtered_df based on active filters.
        """
        df = self.original_df
        for col, accepted_values in self.active_filters.items():
            if col in df.columns:
                df = df[df[col].isin(accepted_values)]
        self.filtered_df = df.copy()

    def get_current_view(self):
        """
        Return the current filtered DataFrame.
        """
        return self.filtered_df

    def get_active_filters(self):
        """
        Return a dictionary of currently applied filters.
        """
        return self.active_filters.copy()

    def is_filtered(self):
        """
        Return True if any filters are currently applied.
        """
        return bool(self.active_filters)

    def available_columns(self):
        """
        Return a list of columns from the original DataFrame.
        Useful for building dynamic UI selectors.
        """
        return list(self.original_df.columns)

    def available_values(self, column):
        """
        Return a list of unique values for a given column.
        """
        if column in self.original_df.columns:
            return sorted(self.original_df[column].dropna().unique().tolist())
        return []

    def is_filter_active_for_column(self, column):
        """
        Return True if a filter is applied on this column.
        """
        return column in self.active_filters

    def filter_icon_for_column(self, column):
        """
        Return a Unicode icon for the header depending on filter state.
        """
        return "▾" if self.is_filter_active_for_column(column) else "▸"
from PySide6.QtWidgets import QHeaderView, QMenu
from PySide6.QtCore import Qt, Signal

class FilterableSortableHeader(QHeaderView):
    filter_applied = Signal(int)  # Signal to notify when a filter is applied

    def __init__(self, orientation, parent=None, controller=None, table_view=None):
        super().__init__(orientation, parent)
        self.controller = controller
        self.table_view = table_view
        self.setSectionsClickable(True)
        self.sectionClicked.connect(self.handle_sort)

    def mousePressEvent(self, event):
        section = self.logicalIndexAt(event.pos())
        if event.button() == Qt.LeftButton:
            print(f"🖱️ Left-click on section: {section}")
            self.handle_sort(section)
        elif event.button() == Qt.RightButton:
            print(f"🖱️ Right-click on section: {section}")
            self.open_filter_menu(section)


    def handle_sort(self, section):
        if not self.table_view:
            return
        col_name = self.model().headerData(section, Qt.Horizontal)
        self.table_view.sortByColumn(section, Qt.AscendingOrder)

    def open_filter_menu(self, section):
        if not self.controller:
            return

        col_name = self.model().headerData(section, Qt.Horizontal)
        unique_values = self.controller.available_values(col_name)

        menu = QMenu(self)
        for val in unique_values:
            action = QAction(str(val), self)
            action.setCheckable(True)
            action.setChecked(val in self.controller.get_active_filters().get(col_name, []))
            action.triggered.connect(lambda checked, v=val: self.toggle_filter(col_name, v))
            menu.addAction(action)

        menu.exec(self.mapToGlobal(self.sectionPosition(section)))

    def toggle_filter(self, column, value):
        active = self.controller.get_active_filters().get(column, [])
        if value in active:
            active.remove(value)
        else:
            active.append(value)

        if active:
            self.controller.apply_filter(column, active)
        else:
            self.controller.clear_filter(column)

        self.filter_applied.emit(self.logicalIndex(column))
