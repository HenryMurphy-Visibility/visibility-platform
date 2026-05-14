import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd

# Global reference to widgets
widget_refs = {}

layouts = {
    "ManageLinkSets": {
        "window_size": {"width": 1200, "height": 600},
        "num_cols": 6,
        "num_rows": 10,
        "file_path": "BASE_PATH/refdata/master_link_sets.csv",
        "widgets": [
            {"area": "A1-F1", "type": "title", "text": "Manage Link Sets"},
            {"area": "A2-F2", "type": "label", "text": "Edit, Add, or Modify Link Sets Below:"},
            {"area": "A3-F9", "type": "table", "key": "link_set_table"},
            {"area": "A10-B10", "type": "button", "action": "AddRow", "text": "Add Row"},
            {"area": "C10-D10", "type": "button", "action": "ModifyRow", "text": "Modify Row"}
        ]
    },
    "ManageFXRates": {
        "window_size": {"width": 800, "height": 600},
        "num_cols": 4,
        "num_rows": 5,
        "file_path": "BASE_PATH/refdata/fx_master.csv",
        "widgets": [
            {"area": "A1-D1", "type": "title", "text": "Manage FX Rates"},
            {"area": "A2-D2", "type": "table", "key": "fx_rate_table"},
            {"area": "A3-B3", "type": "button", "action": "AddRow", "text": "Add Row"},
            {"area": "C3-D3", "type": "button", "action": "ModifyRow", "text": "Modify Row"}
        ]
    },
    "ManagePrices": {
        "window_size": {"width": 800, "height": 600},
        "num_cols": 4,
        "num_rows": 5,
        "file_path": "BASE_PATH/refdata/price_master.csv",
        "widgets": [
            {"area": "A1-D1", "type": "title", "text": "Manage Prices"},
            {"area": "A2-D2", "type": "table", "key": "price_table"},
            {"area": "A3-B3", "type": "button", "action": "AddRow", "text": "Add Row"},
            {"area": "C3-D3", "type": "button", "action": "ModifyRow", "text": "Modify Row"}
        ]
    },
    "ManageInvestments": {
        "window_size": {"width": 800, "height": 600},
        "num_cols": 4,
        "num_rows": 5,
        "file_path": "BASE_PATH/refdata/investment_master.csv",
        "widgets": [
            {"area": "A1-D1", "type": "title", "text": "Manage Investments"},
            {"area": "A2-D2", "type": "table", "key": "investment_table"},
            {"area": "A3-B3", "type": "button", "action": "AddRow", "text": "Add Row"},
            {"area": "C3-D3", "type": "button", "action": "ModifyRow", "text": "Modify Row"}
        ]
    },
    "ManageBonds": {
        "window_size": {"width": 800, "height": 600},
        "num_cols": 4,
        "num_rows": 5,
        "file_path": "BASE_PATH/refdata/bond_info.csv",
        "widgets": [
            {"area": "A1-D1", "type": "title", "text": "Manage Bonds"},
            {"area": "A2-D2", "type": "table", "key": "bond_table"},
            {"area": "A3-B3", "type": "button", "action": "AddRow", "text": "Add Row"},
            {"area": "C3-D3", "type": "button", "action": "ModifyRow", "text": "Modify Row"}
        ]
    },
    "ManageAccounts": {
        "window_size": {"width": 800, "height": 600},
        "num_cols": 4,
        "num_rows": 5,
        "file_path": "BASE_PATH/refdata/chart_of_accounts.csv",
        "widgets": [
            {"area": "A1-D1", "type": "title", "text": "Manage Chart of Accounts"},
            {"area": "A2-D2", "type": "table", "key": "account_table"},
            {"area": "A3-B3", "type": "button", "action": "AddRow", "text": "Add Row"},
            {"area": "C3-D3", "type": "button", "action": "ModifyRow", "text": "Modify Row"}
        ]
    }
}

# Utility Functions
def parse_coord(cell):
    col = ord(cell[0].upper()) - ord('A')
    row = int(cell[1:]) - 1
    return row, col


def get_area_coordinates(area):
    start, end = area.split("-")
    start_row, start_col = parse_coord(start)
    end_row, end_col = parse_coord(end)
    row_span = end_row - start_row + 1
    col_span = end_col - start_col + 1
    return (start_row, start_col), (row_span, col_span)


def clear_widgets(root):
    for widget in root.winfo_children():
        widget.destroy()


def load_table_data(table, file_path):
    try:
        df = pd.read_csv(file_path)

        table["columns"] = list(df.columns)
        table["show"] = "headings"
        for col in table["columns"]:
            table.heading(col, text=col, anchor="center")
            table.column(col, width=150, anchor="center")

        for item in table.get_children():
            table.delete(item)

        for i, row in df.iterrows():
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            table.insert("", "end", values=list(row), tags=(tag,))

    except Exception as e:
        messagebox.showerror("Error", f"Failed to load data: {e}")


def add_table_row(table):
    table.insert("", "end", values=["" for _ in table["columns"]])


def modify_table_row(root, table, layout_name):
    selected_item = table.focus()
    if not selected_item:
        messagebox.showwarning("No Selection", "Please select a row to modify.")
        return

    selected_values = table.item(selected_item)["values"]
    columns = table["columns"]

    popup = tk.Toplevel(root)
    popup.title("Modify Row")
    popup.geometry("800x600")

    entry_widgets = {}

    for i, col in enumerate(columns):
        tk.Label(popup, text=col).grid(row=i, column=0, padx=10, pady=5, sticky="w")
        entry = tk.Entry(popup, width=30)
        entry.insert(0, selected_values[i])
        entry.grid(row=i, column=1, padx=10, pady=5, sticky="w")
        entry_widgets[col] = entry

    def save_changes():
        new_values = [entry_widgets[col].get() for col in columns]
        table.item(selected_item, values=new_values)

        layout_config = layouts.get(layout_name)
        save_table_data(table, layout_config["file_path"])
        messagebox.showinfo("Saved", "Changes saved successfully.")
        popup.destroy()

    tk.Button(popup, text="Save", command=save_changes).grid(row=len(columns), column=0, columnspan=2, pady=10)


def save_table_data(table, file_path):
    try:
        rows = [table.item(child)["values"] for child in table.get_children()]
        df = pd.DataFrame(rows, columns=table["columns"])
        df.to_csv(file_path, index=False)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save data: {e}")


# Dynamic GUI Rendering
def switch_layout(root, layout_name):
    clear_widgets(root)
    layout_config = layouts.get(layout_name)
    if not layout_config:
        messagebox.showerror("Error", f"Layout '{layout_name}' not found.")
        return

    root.geometry(f"{layout_config['window_size']['width']}x{layout_config['window_size']['height']}")

    num_cols = layout_config.get("num_cols", 1)
    num_rows = layout_config.get("num_rows", 1)
    # Ensure all columns and rows expand proportionally
    for i in range(num_rows):
        root.grid_rowconfigure(i, weight=1)
    for j in range(num_cols):
        root.grid_columnconfigure(j, weight=1)


    for widget in layout_config["widgets"]:
        widget_type = widget["type"]
        area = widget["area"]

        start_coord, (row_span, col_span) = get_area_coordinates(area)
        row_start, col_start = start_coord

        if widget_type == "title":
            label = ttk.Label(
                root,
                text=widget["text"],
                font=("Arial", 16, "bold"),
                background="#4B0082",
                foreground="white",
                anchor="center"  # Ensures the text is centered in the label
            )
            label.grid(
                row=row_start,
                column=col_start,
                rowspan=row_span,
                columnspan=col_span,
                sticky="nsew"  # Expands the label and centers it within the grid
            )

        # if widget_type == "title":
        #     label = ttk.Label(root, text=widget["text"], font=("Arial", 16, "bold"), background="#4B0082", foreground="white")
        #     label.grid(row=row_start, column=col_start, rowspan=row_span, columnspan=col_span, sticky="nsew")
        #
        #


        elif widget_type == "label":
            label = ttk.Label(root, text=widget["text"], background="#4B0082", foreground="white")
            label.grid(row=row_start, column=col_start, rowspan=row_span, columnspan=col_span, sticky="w", padx=5, pady=5)

        elif widget_type == "button":
            button = ttk.Button(
                root,
                text=widget["text"],
                command=lambda action=widget["action"]: handle_action(root, action, layout_name)
            )
            button.grid(row=row_start, column=col_start, rowspan=row_span, columnspan=col_span, padx=5, pady=5, sticky="nsew")

        elif widget_type == "table":
            frame = ttk.Frame(root)
            frame.grid(row=row_start, column=col_start, rowspan=row_span, columnspan=col_span, sticky="nsew")

            scrollbar = ttk.Scrollbar(frame, orient="vertical")
            table = ttk.Treeview(frame, yscrollcommand=scrollbar.set)
            scrollbar.config(command=table.yview)
            scrollbar.pack(side="right", fill="y")
            table.pack(side="left", fill="both", expand=True)

            table.tag_configure("evenrow", background="white")
            table.tag_configure("oddrow", background="#f0f0f0")

            widget_refs[widget["key"]] = table
            if "file_path" in layout_config:
                load_table_data(table, layout_config["file_path"])


# Action Handlers
def handle_action(root, action, layout_name):
    layout_config = layouts.get(layout_name)
    table_key = next(
        (widget["key"] for widget in layout_config["widgets"] if widget["type"] == "table"),
        None
    )
    if not table_key:
        messagebox.showerror("Error", "Table key not found in layout.")
        return

    table = widget_refs.get(table_key)
    if not table:
        messagebox.showerror("Error", "Table widget not initialized.")
        return

    if action == "AddRow":
        add_table_row(table)
    elif action == "ModifyRow":
        modify_table_row(root, table, layout_name)


# Main function
def main_gui():
    root = tk.Tk()
    root.title("Link Set Manager")
    switch_layout(root, "ManageInvestments")  # Change to "ManageLinkSets" for testing
    root.mainloop()


if __name__ == "__main__":
    main_gui()
