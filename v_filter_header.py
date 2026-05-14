import pandas as pd
from PySide6.QtWidgets import QHeaderView, QMenu
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QAction
from v_filter_config_loader import VFilterConfigLoader

def enforce_filter_limits(values, max_values=50):
    """Limit the number of values shown in the filter dropdown."""
    if len(values) > max_values:
        return values[:max_values] + ["...more"]
    return values

class FilterableSortableHeader(QHeaderView):
    filter_applied = Signal(int)

    def __init__(self, orientation, parent=None, controller=None, table_view=None, config=None):
        super().__init__(orientation, parent)
        self.controller = controller
        self.table_view = table_view
        self.config = config or {}  # ✅ <<<< NEW
        self.setSectionsClickable(True)
        self.sectionClicked.connect(self.handle_sort)

    # One-time load when you start your program
    vfilter_config_loader = VFilterConfigLoader('C:/Users/hjmne/PycharmProjects/chest/refdata/v_filter.csv')

    def mousePressEvent(self, event):
        print(f"🖱️ mousePressEvent: button={event.button()}, section={self.logicalIndexAt(event.pos())}")
        section = self.logicalIndexAt(event.pos())
        if event.button() == Qt.LeftButton:
            self.handle_sort(section)
        elif event.button() == Qt.RightButton:
            self.open_filter_menu(section)

    def handle_sort(self, section):
        if not self.table_view:
            return

        header = self.table_view.horizontalHeader()
        current_sort_col = header.sortIndicatorSection()
        current_sort_order = header.sortIndicatorOrder()

        if current_sort_col == section:
            # 🔥 Toggle sort order
            new_order = Qt.DescendingOrder if current_sort_order == Qt.AscendingOrder else Qt.AscendingOrder
        else:
            # 🔥 New column clicked — start fresh ascending
            new_order = Qt.AscendingOrder

        self.table_view.sortByColumn(section, new_order)

    def open_filter_menu(self, section):
        col_name = self.model().headerData(section, Qt.Horizontal)
        if not col_name or not self.controller:
            return

        # Look up config for this column
        column_config = self.config.get(col_name, {})
        if column_config.get("disable_filter", False):
            print(f"⛔ Filtering disabled for column: {col_name}")
            return

        values = self.controller.available_values(col_name)

        # Limit number of shown values if max_values_shown is set
        max_values = column_config.get("max_values_shown")
        if max_values is not None and isinstance(max_values, int):
            values = values[:max_values]

        menu = QMenu(self)

        # Optional: Add search box if required
        if column_config.get("requires_search", False):
            from PySide6.QtWidgets import QWidgetAction, QLineEdit
            search_action = QWidgetAction(menu)
            search_box = QLineEdit()
            search_box.setPlaceholderText(f"Search {col_name}...")
            search_action.setDefaultWidget(search_box)
            menu.addAction(search_action)

            def filter_menu_items(text):
                for action in menu.actions():
                    if isinstance(action, QWidgetAction):
                        continue
                    action.setVisible(text.strip() in action.text())

            def try_auto_trigger(text):
                filter_menu_items(text)  # 🔧 Apply filter first
                visible_actions = [
                    a for a in menu.actions()
                    if not isinstance(a, QWidgetAction) and a.isVisible()
                ]
                print(f"🎯 Triggerable actions: {[a.text() for a in visible_actions]}")
                if len(visible_actions) == 1:
                    visible_actions[0].trigger()

            search_box.textChanged.connect(filter_menu_items)
            search_box.returnPressed.connect(lambda: try_auto_trigger(search_box.text()))

        # List all value options
        active_values = set(self.controller.get_active_filters().get(col_name, []))

        for val in values:
            action = QAction(str(val), self)
            action.setCheckable(True)
            action.setChecked(val in active_values)

            action.triggered.connect(lambda checked, v=val: self.toggle_filter(col_name, v, checked, section))
            menu.addAction(action)

        # Show the menu
        pos = self.mapToGlobal(QPoint(self.sectionPosition(section), 0))
        menu.exec(pos)

    def toggle_filter(self, column, value, checked, section):
        current = set(self.controller.get_active_filters().get(column, []))
        if value in current:
            current.remove(value)
        else:
            current.add(value)

        if current:
            self.controller.apply_filter(column, list(current))
        else:
            self.controller.clear_filter(column)

        self.filter_applied.emit(section)
