import dearpygui.dearpygui as dpg

def menu_item_callback(sender, app_data):
    print(f"Menu item clicked: {sender}")

with dpg.handler_registry():

    with dpg.menu_bar(label="MainMenuBar"):
        with dpg.menu(label="File"):
            dpg.add_menu_item(label="Open", callback=menu_item_callback)
            dpg.add_menu_item(label="Save", callback=menu_item_callback)
            dpg.add_menu_item(label="Exit", callback=lambda s, a: dpg.stop_dearpygui())

        with dpg.menu(label="Edit"):
            dpg.add_menu_item(label="Copy", callback=menu_item_callback)
            dpg.add_menu_item(label="Paste", callback=menu_item_callback)

    with dpg.window(label="Example Window"):
        dpg.add_text("Hello, world!")

dpg.create_context()
dpg.create_viewport(title='Dear PyGui Example', width=600, height=400)
dpg.setup_dearpygui()
dpg.show_viewport()
dpg.start_dearpygui()
dpg.destroy_context()

def display_processing_inputs(self):
    default_values = [
        '2022-05-05:00:00:00',  # Period_Start
        '2022-05-05:23:59:59',  # Period Cutoff
        '2029-05-05:10:00:00',  # Knowledge Cutoff
        'No',  # Process Base?
        'Yes',  # Process Current?
        'No',  # Report Adjustments?
        'No',  # TPS Check
        '1',  # Number of Portfolios
        '2022-05-04'  # Period Name
    ]

    labels = [
        "Period_Start",
        "Period Cutoff",
        "Knowledge Cutoff",
        "Process Base?",
        "Process Current?",
        "Report Adjustments?",
        "TPS Check",
        "Number of Portfolios",
        "Period Name"
    ]

    processing_inputs = easygui.multenterbox(
        "Please enter the following details:",
        "FundSmart Accounting Engine",
        labels,
        default_values
    )

    if None in processing_inputs:  # If the user presses cancel
        return None

    return tuple(processing_inputs)
# import tkinter as tk
# from tkinter import ttk, messagebox
# import easygui
# import datetime
#
# # Global Variables
# period_start = None
# period_cutoff = None
# knowledge_cutoff = None
# process_current = None
# process_base = None
# report_adjustments = None
# run_time = None
# numport = 1
# period_name = None
# import csv
#
# # ... [rest of the imports]
#
# from tkinter import simpledialog, filedialog  # For input and file dialogs
#
# # Global Variables
# counter = 1  # Global counter for period counting
# # ... [rest of the global variables]
#
# class App:
#     def __init__(self, root):
#         # ... [rest of the init code]
#
#         # Adjusting the columns to include counter
#         self.columns = ("#", "Open?", "Period Name", "Period Start", "Knowledge Start", "Period End", "Knowledge End")
#         # ... [rest of the init code]
#
#     def save_data_to_file(self):
#         file_name = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
#
#         if not file_name:
#             return
#
#         with open(file_name, "w", newline="") as file:
#             writer = csv.writer(file)
#             writer.writerow(self.columns)  # Write the headers
#             for row in self.tree.get_children():
#                 writer.writerow(self.tree.item(row)["values"])
#
#     def add_new_row(self):
#         global counter
#
#         is_open = simpledialog.askstring("Input", "Is the period currently open? (Yes/No)")
#         period_name = simpledialog.askstring("Input", "Enter Period Name:")
#         period_start = simpledialog.askstring("Input", "Enter Period Start (YYYY-MM-DD HH:MM:SS):")
#         knowledge_start = simpledialog.askstring("Input", "Enter Knowledge Start (YYYY-MM-DD HH:MM:SS):")
#         period_end = simpledialog.askstring("Input", "Enter Period End (YYYY-MM-DD HH:MM:SS):")
#         knowledge_end = simpledialog.askstring("Input", "Enter Knowledge End (YYYY-MM-DD HH:MM:SS):")
#
#         if all([period_name, period_start, knowledge_start, period_end, knowledge_end]):
#             self.tree.insert("", "end", values=(counter, 1 if is_open.lower() == "yes" else 0, period_name, period_start, knowledge_start, period_end, knowledge_end))
#             counter += 1  # Increment the counter after adding a period
#         else:
#             messagebox.showerror("Input Error", "All fields must be filled out.")
# # App class for tkinter GUI
# class App:
#     def __init__(self, root):
#         self.root = root
#         self.root.title("Closing Periods Management")
#
#         self.columns = ("Open?", "Period Name", "Period Start", "Knowledge Start", "Period End", "Knowledge End")
#         self.tree = ttk.Treeview(root, columns=self.columns, show="headings")
#
#         self.tree.heading("Open?", text="Open?")
#         self.tree.column("Open?", width=50)
#         self.save_button = tk.Button(root, text="Save Data", command=self.save_data_to_file)
#         self.save_button.pack(pady=10, side=tk.LEFT, padx=10)
#
#         for col in self.columns[1:]:
#             self.tree.heading(col, text=col)
#
#         sample_data = [
#             (0, "Period 1", "2022-01-01 00:00:00", "2022-01-02 00:00:00", "2022-01-31 23:59:59", "2022-02-01 00:00:00"),
#         ]
#
#         for item in sample_data:
#             self.tree.insert("", "end", values=item)
#
#         self.tree.pack(pady=20)
#
#         self.add_button = tk.Button(root, text="Add New Row", command=self.add_new_row)
#         self.add_button.pack(pady=10, side=tk.LEFT, padx=10)
#
#         self.edit_button = tk.Button(root, text="Edit Selected Row", command=self.edit_row)
#         self.edit_button.pack(pady=10, side=tk.LEFT, padx=10)
#
#         self.delete_button = tk.Button(root, text="Delete Selected Row", command=self.delete_row)
#         self.delete_button.pack(pady=10, side=tk.LEFT, padx=10)
#
#     def save_data_to_file(self):
#         # Ask the user for a file name
#         file_name = easygui.filesavebox(default="period_data.csv", filetypes=["*.csv"])
#
#         if not file_name:
#             return  # user cancelled
#
#         with open(file_name, "w", newline="") as file:
#             writer = csv.writer(file)
#             writer.writerow(self.columns)  # Write the headers
#             for row in self.tree.get_children():
#                 writer.writerow(self.tree.item(row)["values"])
#
#
#         for col in self.columns[1:]:
#             self.tree.heading(col, text=col)
#
#         sample_data = [
#             (0, "Period 1", "2022-01-01 00:00:00", "2022-01-02 00:00:00", "2022-01-31 23:59:59", "2022-02-01 00:00:00"),
#         ]
#
#         for item in sample_data:
#             self.tree.insert("", "end", values=item)
#
#         self.tree.pack(pady=20)
#
#         self.add_button = tk.Button(root, text="Add New Row", command=self.add_new_row)
#         self.add_button.pack(pady=10, side=tk.LEFT, padx=10)
#
#         self.edit_button = tk.Button(root, text="Edit Selected Row", command=self.edit_row)
#         self.edit_button.pack(pady=10, side=tk.LEFT, padx=10)
#
#         self.delete_button = tk.Button(root, text="Delete Selected Row", command=self.delete_row)
#         self.delete_button.pack(pady=10, side=tk.LEFT, padx=10)
#
#     def add_new_row(self):
#         is_open = easygui.ynbox("Is the period currently open?")
#         period_name = easygui.enterbox("Enter Period Name:")
#         period_start = easygui.enterbox("Enter Period Start (YYYY-MM-DD HH:MM:SS):")
#         knowledge_start = easygui.enterbox("Enter Knowledge Start (YYYY-MM-DD HH:MM:SS):")
#         period_end = easygui.enterbox("Enter Period End (YYYY-MM-DD HH:MM:SS):")
#         knowledge_end = easygui.enterbox("Enter Knowledge End (YYYY-MM-DD HH:MM:SS):")
#
#         if all([period_name, period_start, knowledge_start, period_end, knowledge_end]):
#             self.tree.insert("", "end", values=(
#                 1 if is_open else 0, period_name, period_start, knowledge_start, period_end, knowledge_end))
#         else:
#             messagebox.showerror("Input Error", "All fields must be filled out.")
#
#     def edit_row(self):
#         selected_item = self.tree.selection()  # Get selected item
#
#         if not selected_item:
#             messagebox.showerror("Selection Error", "No row selected.")
#             return
#
#         item_values = self.tree.item(selected_item, "values")
#
#         is_open = easygui.ynbox("Is the period currently open?", default="Yes" if item_values[0] == 1 else "No")
#         period_name = easygui.enterbox("Edit Period Name:", default=item_values[1])
#         period_start = easygui.enterbox("Edit Period Start (YYYY-MM-DD HH:MM:SS):", default=item_values[2])
#         knowledge_start = easygui.enterbox("Edit Knowledge Start (YYYY-MM-DD HH:MM:SS):", default=item_values[3])
#         period_end = easygui.enterbox("Edit Period End (YYYY-MM-DD HH:MM:SS):", default=item_values[4])
#         knowledge_end = easygui.enterbox("Edit Knowledge End (YYYY-MM-DD HH:MM:SS):", default=item_values[5])
#
#         if all([period_name, period_start, knowledge_start, period_end, knowledge_end]):
#             self.tree.item(selected_item, values=(
#                 1 if is_open else 0, period_name, period_start, knowledge_start, period_end, knowledge_end))
#         else:
#             messagebox.showerror("Input Error", "All fields must be filled out.")
#
#     def delete_row(self):
#         selected_item = self.tree.selection()  # Get selected item
#
#         if not selected_item:
#             messagebox.showerror("Selection Error", "No row selected.")
#             return
#
#         self.tree.delete(selected_item)
#
#
# # GUI Display Functions
# def display_processing_inputs():
#     default_values = [
#         '2022-05-05:00:00:00',  # Period_Start
#         '2022-05-05:23:59:59',  # Period Cutoff
#         '2029-05-05:10:00:00',  # Knowledge Cutoff
#         'No',  # Process Base?
#         'Yes',  # Process Current?
#         'No',  # Report Adjustments?
#         'No',  # TPS Check
#         '1',  # Number of Portfolios
#         '2022-05-04'  # Period Name
#     ]
#
#     labels = [
#         "Period_Start",
#         "Period Cutoff",
#         "Knowledge Cutoff",
#         "Process Base?",
#         "Process Current?",
#         "Report Adjustments?",
#         "TPS Check",
#         "Number of Portfolios",
#         "Period Name"
#     ]
#
#     processing_inputs = easygui.multenterbox(
#         "Please enter the following details:",
#         "FundSmart Accounting Engine",
#         labels,
#         default_values
#     )
#
#     if None in processing_inputs:  # If the user presses cancel
#         return None
#
#     return tuple(processing_inputs)
#
#
#
# # GUI function
# def display_gui():
#     processing_inputs = display_processing_inputs()
#
#     if processing_inputs is None:
#         # Handle the case when inputs are not provided
#         easygui.msgbox("Error: Please provide the required inputs.", title="Input Error")
#         return None
#
#     # Extract the captured input values
#     period_start_str = processing_inputs[0] if processing_inputs[0] else default_period_start
#     period_cutoff_str = processing_inputs[1] if processing_inputs[1] else default_period_cutoff
#     knowledge_cutoff_str = processing_inputs[2] if processing_inputs[2] else default_knowledge_cutoff
#     process_base = processing_inputs[3]
#     process_current = processing_inputs[4]
#     report_adjustments = processing_inputs[5]
#     run_time = processing_inputs[6]
#     numport = int(processing_inputs[7])  # Convert numport to integer
#     period_name = processing_inputs[8]
#
#     # Convert the string inputs to datetime objects
#     # Convert the string inputs to datetime objects
#     period_start = datetime.datetime.strptime(period_start_str, "%Y-%m-%d:%H:%M:%S")
#     period_cutoff = datetime.datetime.strptime(period_cutoff_str, "%Y-%m-%d:%H:%M:%S")
#     knowledge_cutoff = datetime.datetime.strptime(knowledge_cutoff_str, "%Y-%m-%d:%H:%M:%S")
#
#     return period_start, period_cutoff, knowledge_cutoff, process_current, process_base, report_adjustments, run_time, numport, period_name
#
# def launch_tkinter_app():
#     global period_start, period_cutoff, knowledge_cutoff, process_current, process_base, report_adjustments, run_time, numport, period_name
#
#     root = tk.Tk()
#     app = App(root)
#     root.mainloop()
# #
#
# def main_menu():
#     global period_start, period_cutoff, knowledge_cutoff, process_current, process_base, report_adjustments, run_time, numport, period_name
#
#     menu_choices = ["Enter Parameters", "Period Menu", "Run Reports", "Exit"]
#     user_choice = easygui.buttonbox("Choose an option:", title="Main Menu", choices=menu_choices)
#
#     if user_choice == "Enter Parameters":
#         gui_result = display_gui()
#         if gui_result is not None:
#             period_start, period_cutoff, knowledge_cutoff, process_current, process_base, report_adjustments, run_time, numport, period_name = gui_result
#
#     elif user_choice == "Period Menu":
#         launch_tkinter_app()
#     elif user_choice == "Run Reports":
#         # Logic for running reports
#         pass
#     elif user_choice == "Exit":
#         exit()
#
#
# if __name__ == "__main__":
#     while True:
#         main_menu()
