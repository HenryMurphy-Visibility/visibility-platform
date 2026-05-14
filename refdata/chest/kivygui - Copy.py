from validate import validate_records
from kivy.core.window import Window

# Set the background color to a deep dark blue
Window.clearcolor = (0.1, 0.1, 0.4, 1)  # R, G, B, A


def data_received(data):
    print("Here in Data Received")
    # Process the data with the main logic...
    import main
    main.main(data)


from kivy.uix.screenmanager import ScreenManager


from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.graphics import Color, Rectangle
from types import SimpleNamespace
from kivy.uix.checkbox import CheckBox
from kivy.uix.widget import Widget


import json
import subprocess
import time
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.label import Label
from kivy.properties import StringProperty
from bookkeeping import StatisticalRepository
stat_repo = StatisticalRepository()
class LocationRow(RecycleDataViewBehavior, BoxLayout):
    index = None

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        return super(LocationRow, self).refresh_view_attrs(rv, index, data)

    def on_touch_down(self, touch):
        if super(LocationRow, self).on_touch_down(touch):
            return True
        if self.collide_point(*touch.pos):
            return self.select_location(touch)

    def select_location(self, touch):
        print(f"Location {self.index} is selected!")

class ClosedPeriodPopup(Popup):
    def __init__(self, callback, **kwargs):
        super().__init__(**kwargs)
        self.callback = callback
        self.title = "Enter Period Names"
        self.size_hint = (0.8, 0.4)

        layout = BoxLayout(orientation='vertical', padding=(10, 10), spacing=10)

        self.prior_period_name_input = TextInput(hint_text="Enter Prior Period Name", size_hint=(1, 0.5))
        layout.add_widget(self.prior_period_name_input)

        self.current_period_name_input = TextInput(hint_text="Enter Current Period Name", size_hint=(1, 0.5))
        layout.add_widget(self.current_period_name_input)

        submit_button = Button(text="Submit", size_hint=(1, 0.5))
        submit_button.bind(on_press=self.submit_period_names)
        layout.add_widget(submit_button)

        self.add_widget(layout)

    def submit_period_names(self, instance):
        prior_period_name = self.prior_period_name_input.text
        current_period_name = self.current_period_name_input.text
        if prior_period_name and current_period_name:
            self.callback(prior_period_name, current_period_name)
            self.dismiss()

class DataEntryPopup(Popup):
    def __init__(self, add_callback, modify_callback=None, initial_data=None, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (0.8, 0.4)
        self.add_callback = add_callback
        self.modify_callback = modify_callback
        self.title = "Add Entry" if initial_data is None else "Modify Entry"

        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)

        self.id_input = TextInput(hint_text="locationID", text=initial_data.get('ID', '') if initial_data else '')
        self.name_input = TextInput(hint_text="locationName", text=initial_data.get('Name', '') if initial_data else '')
        self.group_input = TextInput(hint_text="locationGroup", text=initial_data.get('group', '') if initial_data else '')

        layout.add_widget(self.id_input)
        layout.add_widget(self.name_input)
        layout.add_widget(self.group_input)

        btn_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)
        save_btn = Button(text="Save")
        save_btn.bind(on_press=self.save_entry)
        btn_layout.add_widget(save_btn)

        cancel_btn = Button(text="Cancel")
        cancel_btn.bind(on_press=self.dismiss)
        btn_layout.add_widget(cancel_btn)

        layout.add_widget(btn_layout)
        self.add_widget(layout)

    def save_entry(self, instance):
        data = {
            'ID': self.id_input.text,
            'Name': self.name_input.text,
            'group': self.group_input.text
        }
        if self.modify_callback:
            self.modify_callback(data)
        else:
            self.add_callback(data)
        self.dismiss()

from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.graphics import Rectangle, Color
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget
from kivy.clock import Clock
from types import SimpleNamespace
import os
import datetime

def data_received(data):
    print("Data received:", data)


from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.graphics import Rectangle, Color
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget
from kivy.clock import Clock
from types import SimpleNamespace
import os
import datetime


def data_received(data):
    print("Data received:", data)


class ProcessingPopup(Popup):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = "Processing in Progress"
        self.content = Label(text="Processing... Please wait.")
        self.size_hint = (None, None)
        self.size = (300, 150)

    def close_popup(self):
        self.dismiss()


class ProcessPopup(Popup):
    def __init__(self, callback, **kwargs):
        super().__init__(**kwargs)
        self.callback = callback
        self.layout = BoxLayout(orientation='vertical')
        self.data_to_send = {}

        self.fund_spinner = Spinner(
            text='Select a Fund',
            values=('MyPortfolio', 'XYZMutualFund', 'XYZHedgeFund', 'XYZInstitutionalFund', 'XYZRetailFund',
                    'ScaleTest', 'ScaleTest2', 'ScaleTestRealTime'),
            size_hint=(1, 0.1)
        )
        self.layout.add_widget(self.fund_spinner)

        date_labels = [
            "Current Period Start:", "Current Period Cutoff:", "Current Knowledge Close:",
            "Prior Period Start:", "Prior Period Cutoff:", "Prior Knowledge Close:"
        ]

        default_dates = {  # Current
            "Current Period Start:": "2022-01-01:00:00:00",
            "Current Period Cutoff:": "2022-01-17:23:59:59",
            "Current Knowledge Close:": "2022-01-18:23:59:59",
            "Prior Period Start:": "2022-01-01:00:00:00",
            "Prior Period Cutoff:": "2022-01-17:23:59:59",
            "Prior Knowledge Close:": "2022-01-17:23:59:59",
        }

        self.date_inputs = {}

        row1 = BoxLayout(size_hint_y=None, height=60)
        with row1.canvas.before:
            Color(0.1, 0.1, 0.4, 1)
            row1.rect = Rectangle(pos=row1.pos, size=row1.size)
        row1.bind(pos=lambda instance, value: setattr(row1.rect, 'pos', value),
                  size=lambda instance, value: setattr(row1.rect, 'size', value))

        row2 = BoxLayout(size_hint_y=None, height=60)
        with row2.canvas.before:
            Color(0.1, 0.1, 0.4, 1)
            row2.rect = Rectangle(pos=row2.pos, size=row2.size)
        row2.bind(pos=lambda instance, value: setattr(row2.rect, 'pos', value),
                  size=lambda instance, value: setattr(row2.rect, 'size', value))

        for idx, label in enumerate(date_labels):
            vbox = BoxLayout(orientation='vertical')
            vbox.add_widget(Label(text=label, size_hint_y=None, height=30))
            text_input = TextInput(text=default_dates[label], hint_text='YYYY-MM-DD', size_hint_y=None, height=30)
            vbox.add_widget(text_input)
            self.date_inputs[label] = text_input
            if idx < 3:
                row1.add_widget(vbox)
            else:
                row2.add_widget(vbox)

        # In the ProcessPopup class, locate the compare_layout section:
        compare_layout = BoxLayout(orientation='horizontal', size_hint=(1, 0.1))

        with compare_layout.canvas.before:
            Color(0.5, 0.5, 0.5, 1)  # Grey
            compare_layout.rect = Rectangle(pos=compare_layout.pos, size=compare_layout.size)

        compare_label = Label(
            text="Compare to a Prior Period",
            halign='center',
            valign='center',
            size_hint_x=None,
            width=200  # Fixed width for the label
        )
        compare_label.bind(size=compare_label.setter('text_size'))

        self.compare_checkbox = CheckBox(active=True)

        # New checkbox label
        performance_checkbox_label = Label(
            text="Mark for Performance",  # Text for your new checkbox
            halign='center',
            valign='center',
            size_hint_x=None,
            width=150  # Fixed width for the label
        )
        performance_checkbox_label.bind(size=performance_checkbox_label.setter('text_size'))

        # New checkbox
        self.performance_checkbox = CheckBox(active=False)

        # Adjusting the widgets to push the label and checkbox
        compare_layout.add_widget(Widget(size_hint_x=0.25))  # Adjust spacing as needed
        compare_layout.add_widget(compare_label)
        compare_layout.add_widget(self.compare_checkbox)

        # Add the new checkbox and its label to the layout
        compare_layout.add_widget(performance_checkbox_label)  # Add the new label
        compare_layout.add_widget(self.performance_checkbox)  # Add the new checkbox

        # Adjust the size_hint_x of the following Widget if needed
        compare_layout.add_widget(Widget(size_hint_x=0.15))

        # Add layouts to the main layout
        self.layout.add_widget(row1)
        self.layout.add_widget(compare_layout)  # Adding the new layout in between row1 and row2
        self.layout.add_widget(row2)

        self.report_spinner = Spinner(
            text='Select a Report',
            values=('Report Type 1', 'Report Type 2', 'Report Type 3'),
            size_hint=(1, 0.1)
        )
        self.layout.add_widget(self.report_spinner)

        get_results_button = Button(text="Generate Accounting Results from Period Inputs", size_hint=(1, 0.1))
        get_results_button.bind(on_press=lambda instance: self.process_and_send_data())
        self.layout.add_widget(get_results_button)

        closed_period_management_button = Button(text="Go to Generate Close Period Results", size_hint=(1, 0.1))
        closed_period_management_button.bind(on_press=self.go_to_closed_period_management)
        self.layout.add_widget(closed_period_management_button)

        report_results_button = Button(text="Report Results", size_hint=(1, 0.1))

        report_results_button.bind(on_press=self.open_report_results_popup)
        self.layout.add_widget(report_results_button)

        self.add_widget(self.layout)

        # Return to Events Button
        return_to_events_button = Button(text="Return to Events", size_hint=(1, 0.1))
        return_to_events_button.bind(on_press=self.return_to_events)
        self.layout.add_widget(return_to_events_button)

    def _on_processing_complete(self):
        # Close processing popup
        self.processing_popup.close_popup()

        # Show success feedback
        self.show_process_feedback("Success", "Processing finished")

    def get_checkbox_value(self):
        return self.compare_checkbox.active

    def get_performance_checkbox_value(self):
        return self.performance_checkbox.active

    def return_to_events(self, instance):
        self.dismiss()

    def open_report(self, instance):
        file_path = instance.path
        import subprocess
        subprocess.Popen(['start', file_path], shell=True)

    def open_report_results_popup(self, instance):
        report_paths = [
            'C:/Users/hjmne/PycharmProjects/chest/repdata/AccountingPriorPeriodFund1.xlsx',
            'C:/Users/hjmne/PycharmProjects/chest/repdata/AccountingCurrentPeriodFund1.xlsx',
            'C:/Users/hjmne/PycharmProjects/chest/repdata/AccountingComparison.xlsx',
            'C:/Users/hjmne/PycharmProjects/chest/repdata/PerformanceReturnsCurrent.xlsx',
            'C:/Users/hjmne/PycharmProjects/chest/repdata/PerformanceReturnsPrior.xlsx',
            'C:/Users/hjmne/PycharmProjects/chest/repdata/PerformanceReturnsPrior.xlsx',
            'C:/Users/hjmne/PycharmProjects/chest/repdata/GeneralLedgerThroughPriorPeriod.xlsx',
            'C:/Users/hjmne/PycharmProjects/chest/repdata/GeneralLedgerThroughCurrentPeriod.xlsx'
        ]

        report_details = []
        for path in report_paths:
            if os.path.exists(path):
                last_modified_time = os.path.getmtime(path)
                readable_time = datetime.datetime.fromtimestamp(last_modified_time).strftime('%Y-%m-%d %H:%M:%S')
                report_details.append(f"{path} (Last Updated: {readable_time})")
            else:
                report_details.append(f"{path} (File not found)")

        # Assuming you're using a Label to display the report details
        report_label = Label(text='\n'.join(report_details))

        # Create a Popup to display the report details
        popup = Popup(title='Report Details',
                      content=report_label,
                      size_hint=(1, 0.5),  # Width takes full width, height is half of the parent layout
                      pos_hint={'center_x': 0.5, 'y': 0})  # Position at the bottom and center horizontally
        popup.open()
        box = BoxLayout(orientation='vertical', padding=(10))
        for path in report_paths:
            btn = Button(text=f'Open {os.path.basename(path)}', size_hint_y=None, height=44)

            # Here's the modified line:
            btn.bind(on_press=lambda instance, path=path: self.open_report(SimpleNamespace(path=path)))

            box.add_widget(btn)
        close_btn = Button(text="Close", size_hint_y=None, height=44)
        box.add_widget(close_btn)
        popup = Popup(title="Available Reports", content=box, size_hint=(0.8, 0.6))
        close_btn.bind(on_press=popup.dismiss)
        popup.open()

    def go_to_closed_period_management(self, instance):
        self.dismiss()  # close the current popup
        self.closed_period_popup = ClosedPeriodPopup(callback=self.process_and_send_data_for_closed_period)
        self.closed_period_popup.open()


    def process_and_send_data(self):
        from threading import Thread
        # Show processing popup
        self.processing_popup = ProcessingPopup()  # Create an instance of ProcessingPopup
        self.processing_popup.open()

        # Execute processing task in a separate thread
        Thread(target=self._process_data).start()
        # Call the callback function to start the processing
        self._process_data()

    def _process_data(self):
        # Perform processing logic here
        # Call the callback function for processing
        self.callback(self._on_processing_complete)

    def _on_processing_complete(self):
        # Close processing popup
        self.processing_popup.dismiss()

    def _close_processing_popup(self, dt):
        self.processing_popup.dismiss()

        # Show success feedback
        self.show_process_feedback("Success", "Processing finished")


    def process_and_send_data_for_closed_period(self, prior_period_name, current_period_name):
        # Extract other data from the UI elements
        selected_fund = self.fund_spinner.text
        current_period_start = self.date_inputs["Current Period Start:"].text
        current_period_cutoff = self.date_inputs["Current Period Cutoff:"].text
        current_period_knowledge = self.date_inputs["Current Knowledge Close:"].text
        prior_period_start = self.date_inputs["Prior Period Start:"].text
        prior_period_cutoff = self.date_inputs["Prior Period Cutoff:"].text
        prior_period_knowledge = self.date_inputs["Prior Knowledge Close:"].text
        selected_report = self.report_spinner.text

        data_to_send = {
            "selected_fund": selected_fund,
            "current_period_start": current_period_start,
            "current_period_cutoff": current_period_cutoff,
            "current_period_knowledge": current_period_knowledge,
            "prior_period_start": prior_period_start,
            "prior_period_cutoff": prior_period_cutoff,
            "prior_period_knowledge": prior_period_knowledge,
            "selected_report": selected_report,
            "period_name": current_period_name,  # renamed for clarity
            "prior_period_name": prior_period_name,
            "close_period": True
        }
        data_received(data_to_send)
        self.show_process_feedback("Success", "Processing finished")

    def show_process_feedback(self, title, message):
        box = BoxLayout(orientation='vertical', padding=(10))
        box.add_widget(Label(text=message))
        btn = Button(text="Close", size_hint_y=None, height=44)
        box.add_widget(btn)
        feedback_popup = Popup(title=title, content=box, size_hint=(None, None), size=(400, 200))
        btn.bind(on_press=feedback_popup.dismiss)
        feedback_popup.open()


import os
import time

import os
import subprocess

class ManageEvents(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = BoxLayout(orientation='vertical')
        title_label = Label(text="S4 Investment Management and Accounting Kernel", size_hint_y=None, height=44)
        layout.add_widget(title_label)

        open_excel_btn = Button(text="Events Management", size_hint=(1, 0.1))
        open_excel_btn.bind(on_press=self.open_excel)
        layout.add_widget(open_excel_btn)

        data_mgmt_btn = Button(text="Data Management", size_hint=(1, 0.1))
        data_mgmt_btn.bind(on_press=self.go_to_data_mgmt)
        layout.add_widget(data_mgmt_btn)

        process_button = Button(text="Process and Report", size_hint=(1, 0.1))
        process_button.bind(on_press=self.open_process_popup)  # Linking to the same popup you had before.
        layout.add_widget(process_button)

        self.add_widget(layout)

    def open_excel(self, instance):
        file_path = 'C:/Users/hjmne/PycharmProjects/chest/refdata/MyPortfolio.csv'
        subprocess.Popen(["start", "excel", file_path], shell=True)
        time.sleep(1)  # Give some time for Excel to open

    def open_process_popup(self, instance):
        self.process_popup = ProcessPopup(callback=data_received, title="Process Parameters")
        self.process_popup.open()

    def go_to_data_mgmt(self, instance):
        self.manager.current = 'managedata'

from utilities import load_location_data
from kivy.properties import ListProperty
from kivy.uix.recycleview import RecycleView


# ... other necessary imports ...

class ManageData(Screen):
    data_items = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Main layout
        main_layout = BoxLayout(orientation='vertical')

        # Title
        title_label = Label(text="Data Management", size_hint_y=None, height=50)
        main_layout.add_widget(title_label)

        # RecycleView
        rv = RecycleView(size_hint_y=0.8)  # Adjust this value as needed
        rv.data = [{'text': str(item)} for item in self.data_items]
        rv.viewclass = 'LocationRow'
        main_layout.add_widget(rv)

        # Buttons
        btn_layout = BoxLayout(size_hint_y=None, height=50)
        add_button = Button(text="Add")
        add_button.bind(on_press=self.add_entry_popup)
        btn_layout.add_widget(add_button)

        modify_button = Button(text="Modify")
        modify_button.bind(on_press=self.modify_entry_popup)
        btn_layout.add_widget(modify_button)

        main_layout.add_widget(btn_layout)

        self.add_widget(main_layout)


class ManageData(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = BoxLayout(orientation='vertical')

        title_label = Label(text="Data Management", size_hint_y=None, height=44)
        layout.add_widget(title_label)

        # Example list of tables
        tables = ['Locations', 'Strategies', 'Prices', 'Fx Rates', 'Investments']

        for table in tables:
            table_btn = Button(text=table, size_hint=(1, 0.1))

            # Depending on table name, bind to appropriate method
            if table == 'Locations':
                table_btn.bind(on_press=self.goto_location_table)

            layout.add_widget(table_btn)

        self.add_widget(layout)

    def goto_location_table(self, instance):
        self.manager.current = 'managelocationtable'
        print("Going to Location Table...")

class ManageLocationTable(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = BoxLayout(orientation='vertical')

        title_label = Label(text="Manage Location Table", size_hint_y=None, height=44)
        layout.add_widget(title_label)

        # For the sake of demonstration, just adding two buttons.
        # Ideally, you'll list records from the Location Table here.

        # Inside ManageLocationTable __init__ method:
        add_button = Button(text="Add", size_hint=(1, 0.1))
        add_button.bind(on_press=self.open_data_entry_popup)
        layout.add_widget(add_button)

        modify_button = Button(text="Modify", size_hint=(1, 0.1))
        layout.add_widget(modify_button)



        # Return to Main Menu Button
        return_button = Button(text="Return to Main Menu", size_hint=(1, 0.1))
        return_button.bind(on_press=self.return_to_main)
        layout.add_widget(return_button)

        self.add_widget(layout)

    def add_modify_data(self, data):
        current_data = self.load_location_data()

        # Check if ID already exists for modify operation
        found = next((item for item in current_data if item.get("id") == data["id"]), None)

        if found:
            current_data[current_data.index(found)] = data  # modify existing
        else:
            current_data.append(data)  # add new

        with open('C:/Users/hjmne/PycharmProjects/chest/refdata/reference_tables/location_table.json', 'w') as file:
            json.dump(current_data, file)

    def open_data_entry_popup(self, instance, data=None):
        popup = DataEntryPopup(self.add_modify_data, data)
        popup.open()


    def return_to_main(self, instance):
        self.manager.current = 'manageevents'

    def load_location_data(self):
        with open('C:/Users/hjmne/PycharmProjects/chest/refdata/reference_tables/location_table.json', 'r') as file:
            return json.load(file)


from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput


class AddEntryPopup(Popup):
    def __init__(self, save_callback, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (0.7, 0.5)
        self.title = "Add Entry"

        self.layout = BoxLayout(orientation='vertical')
        self.location_id_input = TextInput(hint_text="Location ID")
        self.layout.add_widget(self.location_id_input)

        self.location_name_input = TextInput(hint_text="Location Name")
        self.layout.add_widget(self.location_name_input)

        # ... add other inputs as needed ...

        save_button = Button(text="Save")
        save_button.bind(on_press=self.save_entry)
        self.layout.add_widget(save_button)

        self.add_widget(self.layout)
        self.save_callback = save_callback

    def save_entry(self, instance):
        data = {
            'ID': self.location_id_input.text,
            'Name': self.location_name_input.text
            # ... other fields ...
        }
        self.save_callback(data)
        self.dismiss()


# In your ManageData class:

def add_entry_popup(self, instance):
    popup = AddEntryPopup(self.add_entry_to_data)
    popup.open()


def add_entry_to_data(self, data):
    self.data_items.append(data)
    # Save to JSON and update your RecycleView here...


class DataEntryPopup(Popup):
    location_name = StringProperty('')
    location_id = StringProperty('')

    def __init__(self, save_function, data=None, **kwargs):
        super().__init__(**kwargs)
        self.save = save_function
        self.title = "Modify Location" if data else "Add Location"
        self.size_hint = (0.8, 0.4)

        layout = BoxLayout(orientation='vertical')

        layout.add_widget(Label(text="Location Name:"))
        self.location_name_input = TextInput(hint_text="Enter Location Name", text=data['name'] if data else '')
        layout.add_widget(self.location_name_input)

        layout.add_widget(Label(text="Location ID:"))
        self.location_id_input = TextInput(hint_text="Enter Location ID", text=data['id'] if data else '')
        layout.add_widget(self.location_id_input)

        save_btn = Button(text="Save")
        save_btn.bind(on_press=self.save_data)
        layout.add_widget(save_btn)

        self.add_widget(layout)

    def save_data(self, instance):
        self.location_name = self.location_name_input.text
        self.location_id = self.location_id_input.text
        self.save({
            'name': self.location_name,
            'id': self.location_id
        })
        self.dismiss()


import os

class Report(Screen):
    def open_report(self, file_path):
        print(f"Opening: {file_path}")
        subprocess.Popen(['start', file_path], shell=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = BoxLayout(orientation='vertical')

        report_paths = [
            'C:/Users/hjmne/PycharmProjects/chest/repdata/PriorPeriodResultsforFund1.xlsx',
            'C:/Users/hjmne/PycharmProjects/chest/repdata/CurrentPeriodResultsforFund1.xlsx',
            'C:/Users/hjmne/PycharmProjects/chest/repdata/Compare.xlsx'
        ]

        for path in report_paths:
            btn = Button(text=f'Open {os.path.basename(path)}')
            btn.bind(on_press=lambda instance, path=path: self.open_report(path))
            layout.add_widget(btn)

        self.add_widget(layout)


from kivy.properties import StringProperty
from kivy.logger import Logger


from kivy.uix.popup import Popup

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.screenmanager import ScreenManager
import datetime
#from validate import (validate_records, invalid_date_format, contains_whitespace, trade_date_greater_than_settle,
  #                    records, numeric_required, check_duplicate_tranid)
class MyApp(App):

    # def validate_data(self, instance):
    #     # Assuming you have a list of records named records
    #     for record in records:
    #         # Validate invalid_date_format
    #         has_error, column_with_error = invalid_date_format(record.get('tradedate', ''))
    #         if has_error:
    #             self.error_label.text = f"Error in column {column_with_error}."
    #             return
    #
    #         # Validate trade_date_greater_than_settle
    #         has_error, column_with_error = trade_date_greater_than_settle(record.get('tradedate', ''), record.get('settledate', ''))
    #         if has_error:
    #             self.error_label.text = f"Error in column {column_with_error}."
    #             return

            # Validate contains_whitespace
            # has_error, column_with_error = contains_whitespace(record)
            # if has_error:
            #     self.error_label.text = f"Error in column {column_with_error}."
            #     return
            #
            # # Validate numeric_required (assuming numeric_value is a key in the records)
            # if not numeric_required({"numeric_value": record.get('numeric_value', '')}):
            #     self.error_label.text = "Error: Numeric value required."
            #     return

        # # If no errors found
        # self.error_label.text = "No validation errors found."


    # def validate_data(self, instance):
    #     # Assuming the function perform_validation does the validation and returns an error message or None.
    #     error_message = self.perform_validation()
    #     if error_message:
    #         self.error_label.text = error_message
    #     else:
    #         self.error_label.text = "No errors found."
    #
    # def perform_validation(self):
    #     # This is a dummy validation function. Replace with your actual validation logic.
    #     # If there's an error, return a string (the error message). Otherwise, return None.
    #     # For demonstration, we'll simulate an error:
    #     return "Sample error: Invalid data in row 5."

    def build(self):
        sm = ScreenManager()
        sm.add_widget(ManageEvents(name='manageevents'))
        sm.add_widget(ManageData(name='managedata'))
        sm.add_widget(ManageLocationTable(name='managelocationtable'))
        sm.transition.direction = 'left'

        layout = BoxLayout(orientation='vertical')

        # Modify the size_hint to reduce the height of the button
        btn = Button(text="Validate", size_hint_y=0.1)
     #   btn.bind(on_press=self.validate_data)

        self.error_label = Label(size_hint_y=0.1, color=(1, 0, 0, 1))  # Adjust size_hint for label too

        layout.add_widget(sm)  # Add the screen manager to our layout
        layout.add_widget(self.error_label)  # Add the error label
        layout.add_widget(btn)  # Add the button below the error label

        sm.current = 'manageevents'
        return layout
    # def validate_data(self, instance):
    #     # Your validation logic here
    #     pass



#MyApp().run()

if __name__ == '__main__':
    print("Here before MyApp.Run")


MyApp().run()
print("Here after MyApp.Run")

