import time
import copy
from datetime import datetime
import csv
import psutil


class Event:
    def __init__(self, transaction=None, method=None, tradedate=None, settledate=None,
                 actualsettledate=None, ibor_date=None, portfolio=None, investment=None,
                 tranid=None, location=None, strategy=None, quantity=None, total_amount=None,
                 total_amount_base=None, fx_rate=None, accounting_impact_fields=None, data=None):
        self.transaction = transaction
        self.method = method
        self.tradedate = tradedate
        self.settledate = settledate
        self.actualsettledate = actualsettledate
        self.ibor_date = ibor_date
        self.portfolio = portfolio
        self.investment = investment
        self.tranid = tranid
        self.location = location
        self.strategy = strategy
        self.quantity = quantity
        self.total_amount = total_amount
        self.total_amount_base = total_amount_base
        self.fx_rate = fx_rate
        self.accounting_impact_fields = accounting_impact_fields
        self.data = data
        self.future_events = []
        self.trade_events = []



from collections import OrderedDict
import matplotlib.pyplot as plt


class EventScheduler:
    def __init__(self):
        self.events = OrderedDict()  # Assuming events is an OrderedDict for popitem to work correctly
        # Initialize the CSV file and write the headers once in the constructor
        with open('log_data.csv', 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Increment", "Elapsed Time", "Memory Usage", "Events Per Second"])

    def schedule_event(self, tradedate, TOpenPrecedence, counter, event_function, *args, event_type=None):
        event_key = (tradedate, TOpenPrecedence, counter)
        self.events[event_key] = (event_function, args, event_type)

    def sort_events(self):
        # This will sort the events in the reverse order based on the keys
        self.events = OrderedDict(sorted(self.events.items(), reverse=True))

    # Function to get current process memory usage
    def get_memory_usage(self):
        process = psutil.Process()
        memory_info = process.memory_info()
        return memory_info.rss  # Resident Set Size


    import os

    # ...


    def run_next_event(self, testcount, counter_start_time):
        previous_elapsed_time = 0
        while self.events:
            next_event_key, next_event_value = self.events.popitem(last=False)
            event_function, event_args, event_type = next_event_value
            event_function(*event_args)
            testcount += 1
            if testcount % 1000 == 0:
                counter_time = time.time()
                elapsed_time = counter_time - counter_start_time + 2
                memory_usage = self.get_memory_usage()
                events_per_second = 1000 / (elapsed_time - previous_elapsed_time) if testcount != 1000 else 0

                print("Increment", testcount)
                print("\nElapsed time {:.6f}".format(elapsed_time))
                print("Memory Usage".format(memory_usage))
                print("Events Per Second {:.2f}".format(events_per_second))

                # Check if file exists and write headers if it's new or empty
                if not os.path.isfile('log_data.csv') or os.path.getsize('log_data.csv') == 0:
                    with open('log_data.csv', 'w', newline='') as file:
                        writer = csv.writer(file)
                        writer.writerow(['Increment', 'Elapsed Time', 'Memory Usage', 'Events Per Second'])

                # Log the data to the CSV file
                with open('log_data.csv', 'a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(
                        [testcount, "{:.6f}".format(elapsed_time), memory_usage, "{:.2f}".format(events_per_second)])

                previous_elapsed_time = elapsed_time

                # If you want to measure elapsed time between logs, uncomment the next line
                # counter_start_time = time.time()
        # Clear the events dictionary after processing all events
       # self.events.clear()

        return testcount


    def generate_chart(csv_file_path):
        import pandas as pd
        data = pd.read_csv(csv_file_path)
        data = pd.read_csv(csv_file_path, header=None)
        data.columns = ['Increment', 'Elapsed Time', 'Memory Usage', 'Events Per Second']

        # Convert 'Events Per Second' to numeric, handling non-numeric values if necessary
        data['Events Per Second'] = pd.to_numeric(data['Events Per Second'], errors='coerce')


        data.at[1, 'Events Per Second'] = data.iloc[2]['Events Per Second']

        plt.figure(figsize=(14, 7))
        plt.plot(data['Increment'], data['Events Per Second'], marker='o', linestyle='-', color='b')
        plt.title('Events Processed per Second per 1000 Increment')
        plt.xlabel('Increment (x1000)')
        plt.ylabel('Events Processed per Second')
        plt.grid(True)
        plt.savefig('events_per_second_chart.png')
        plt.show()

   # generate_chart('log_data.csv')

    # def __init__(self):
    #     self.events = []  # Use list and pop
    # def schedule_event(self, tradedate, TOpenPrecedence, counter, event_function, *args, event_type=None):
    #     event_key = (tradedate, TOpenPrecedence, counter)
    #     heapq.heappush(self.events, (event_key, (event_function, args, event_type)))
    #
    #
    # def run_next_event(self):
    #     if self.events:
    #         next_event_key, next_event_value = heapq.heappop(self.events)
    #         event_function, event_args, event_type = next_event_value
    #         event_function(*event_args)
    #

class SpaceManager:
    def __init__(self):
        self.spaces = {
            'investment_accounting_space': {
                'data': BookkeepingSpace()  # Or however you instantiate this space
            },
            # ... other spaces ...
        }
    def clear_space(self, space_name):
        if space_name in self.spaces:
            space_instance = self.spaces[space_name]['data']
            space_instance.journal_entries = []
            space_instance.asset_liability_entries = []
            space_instance.revenue_expense_entries = []
            # ... clear other attributes similarly ...

    def get_space(self, space_name):
        # Return the space if it exists
        if space_name in self.spaces:
            return self.spaces[space_name]['data']

        # Otherwise, create a new space, register it, and return it
        else:
            new_space = BookkeepingSpace()  # or whatever the constructor for the space is
            self.register_space(space_name, new_space)
            return new_space

    def register_space(self, space_name, space_instance):
        self.spaces[space_name] = {'data': space_instance}

    def clear_space(self, space_name):
        if space_name in self.spaces:
            space_instance = self.spaces[space_name]['data']
            space_instance.journal_entries = []
            space_instance.asset_liability_entries = []
            space_instance.revenue_expense_entries = []
            # ... clear other attributes similarly ...
        else:
            raise ValueError(f"'{space_name}' not found in registered spaces.")

    def create_child_space(parent_space, data):
        child_space_id = uuid.uuid4()
        child_space = {
            "id": child_space_id,
            "parent_id": parent_space["id"],
            "data": data
        }
        return child_space

    def create_space(data):
        space_id = uuid.uuid4()
        space = {
            "id": space_id,
            "data": data
        }
        return space

    def interact_spaces(self, source_space_name, target_space_name, criteria):
        source_space = self.spaces[source_space_name]
        target_space = self.spaces[target_space_name]
        # ... define logic ...

    def change_space(self, from_space_name, to_space_name):
        # Assuming you want to transfer the data from one space to another:
        self.spaces[to_space_name].journal_entries.extend(self.spaces[from_space_name].journal_entries)
        self.spaces[from_space_name].journal_entries.clear()

    def query_sub_ledger(self, space_type, criteria):
        if space_type not in self.sub_ledger:
            raise ValueError(f"Invalid space_type: {space_type}")

        results = [e for e in self.sub_ledger[space_type].entries if
                   all(criteria[key] == e[0][key] for key in criteria)]
        return results

    def query_journal_entries(self, criteria):
        return [e for e in self.journal_entries if all(getattr(e, key) == criteria[key] for key in criteria)]

import pandas as pd

import pandas as pd

class Journals:
    def __init__(self, portfolio: str = "", investment: str = "", tax_date: datetime = None,
                 ls: str = "", location: str = "", financial_account: str = "",
                 quantity: float = 0.0, local: float = 0.0, book: float = 0.0,
                 tranid: int = 0, transaction: str = "", tradedate: datetime = None,
                 settledate: datetime = None, kdbegin: datetime = None, kdend: datetime = None,
                 ibor_date: datetime = None, entry_type: str = "", feeder: str = "",
                 running_balances: tuple = (0.0, 0.0, 0.0),
                 split_ratio: float = 1.0, account_key: tuple = None,
                 ):
    #     self.entries = [] # Assuming entries is a list of tuples or a similar structure
    # def __getitem__(self, key):
    #     return self.entries[key]

        # if Journals.chart_of_accounts is None:
        #     raise ValueError("Chart of Accounts not loaded.")
        if transaction == "StockSplit" or transaction == "StockDividend":
            ibor_date = tradedate

        self.portfolio = portfolio
        self.investment = investment
        self.tax_date = tax_date
        self.ls = ls
        self.location = location
        self.financial_account = financial_account
        self.quantity = quantity
        self.local = local
        self.book = book
        self.tranid = tranid
        self.transaction = transaction
        self.tradedate = tradedate
        self.settledate = settledate
        self.kdbegin = kdbegin
        self.kdend = kdend
        self.ibor_date = ibor_date
        self.entry_type = entry_type
        self.feeder = feeder
        self.running_balances = running_balances
        self.lines = []
        self.split_ratio = split_ratio
        self.account_key = account_key or (
            self.portfolio, self.investment, self.tax_date, self.ls, self.location)

    def get_tax_lot_for_report(self):
        if isinstance(self.tax_date, int):
            return 'NA'
        else:
            return str(self.tax_date)

    from datetime import datetime

    @staticmethod
    def from_json(entry):
        # Replace 'tax date' key with 'tax_date'
        if 'tax date' in entry:
            entry['tax_date'] = entry.pop('tax date')

        # Remove the 'lines' key if it exists
        entry.pop('lines', None)

        # Handling date fields
        date_fields = ['ibor_date', 'kdbegin', 'kdend', 'tradedate', 'settledate', 'tax_date']
        for date_field in date_fields:
            if date_field in entry:
                if isinstance(entry[date_field], str):
                    # Replace 'T' with a space in the date string
                    entry[date_field] = entry[date_field].replace('T', ' ')
                    try:
                        # Try to convert to datetime object
                        entry[date_field] = datetime.strptime(entry[date_field], "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        # If conversion fails, assume it's an integer and leave it as is
                        pass
                elif isinstance(entry[date_field], int):
                    # If it's already an integer, leave it as is
                    pass

        # Convert list to tuple for running_balances and account_key, if needed
        if 'running_balances' in entry:
            entry['running_balances'] = tuple(entry['running_balances'])
        if 'account_key' in entry:
            entry['account_key'] = tuple(entry['account_key'])

        return Journals(**entry)


    def to_dict(self):
        return {
            "portfolio": self.portfolio,
            "investment": self.investment,
            "tax date" : self.tax_date,
            "ls" : self.ls,
            "location" : self.location,
            "financial_account" : self.financial_account,
            "quantity" : self.quantity,
            "local" : self.local,
            "book" : self.book,
            "tranid" : self.tranid,
            "transaction" : self.transaction,
            "tradedate" : self.tradedate,
            "settledate" : self.settledate,
            "kdbegin" : self.kdbegin,
            "kdend" : self.kdend,
            "ibor_date" : self.ibor_date,
            "entry_type" : self.entry_type, # "Asset/Liability" or "Revenue/Expense/Capital" or Stat
            "feeder" : self.feeder,
            "running_balances" : self.running_balances,
            "lines" : self.lines,
            "split_ratio" : self.split_ratio

        # ... and so on for every other attribute
        }


    def items(self):
        return {
            "portfolio": self.portfolio,
            "investment": self.investment,
            "tax_date": self.tax_date,
            "ls": self.ls,
            "location": self.location,
            "financial_account": self.financial_account,
            "quantity": self.quantity,
            "local": self.local,
            "book": self.book,
            "tranid": self.tranid,
            "transaction": self.transaction,
            "tradedate": self.tradedate,
            "settledate": self.settledate,
            "kdbegin": self.kdbegin,
            "kdend": self.kdend,
            "ibor_date": self.ibor_date,
            "entry_type": self.entry_type,
            "feeder": self.feeder,
            "running_balances": self.running_balances,
            "lines": self.lines,
            "split_ratio": self.split_ratio,
            "account_key": self.account_key
        }


       # self.tax_date = tax_date if tax_date is not None else tradedate
    def __repr__(self):
        return f"Journals(portfolio={self.portfolio}, investment={self.investment}, tax_date={self.tax_date},ls={self.ls}," \
               f"tranid={self.tranid},quantity={self.quantity},local={self.local}," \
               f"book={self.book},location={self.location}, financial_account={self.financial_account})"  # add other attributes as needed

def append_if_valid_date(entry, journal_list, start_period):
    """Appends the entry to the journal list if the ibor_date is greater than or equal to the start_period."""
    if entry.ibor_date >= start_period:
        journal_list.append(entry)

class AIFEntry:
    def __init__(self, aif_id, type, subtype, data):
        self.aif_id = aif_id
        self.type = type
        self.subtype = subtype
        self.data = data

class AIFEvent:
    def __init__(self, aif_id, type, subtype, data, trade_date=None):
        self.aif_id = aif_id
        self.type = type # e.g. portgolio, investment, location, financial_account
        self.subtype = subtype # e.g. bond info, account paranters, investment paramters
        self.data = data
        self.trade_date = trade_date  # Optional: For backdating or bitemporal handling

class StatisticalRepository:
    def __init__(self):
        self.aifs = {}  # Key: AifId, Value: AIFEntry

    def add_aif(self, aif_id, type, subtype, data):
        aif_entry = AIFEntry(aif_id, type, subtype, data)
        self.aifs[aif_id] = aif_entry

    def get_aif(self, aif_id):
        return self.aifs.get(aif_id)

    def remove_aif(self, aif_id):
        if aif_id in self.aifs:
            del self.aifs[aif_id]

    def find_aifs_by_type_subtype(self, type, subtype=None):
        return [aif for aif in self.aifs.values() if aif.type == type and (subtype is None or aif.subtype == subtype)]

    # def post_aif_event(statistical_repository: StatisticalRepository, aif_event: AIFEvent):
    #     statistical_repository.add_aif(aif_event.aif_id, aif_event.type, aif_event.subtype, aif_event.data)
    #
# Example usage
# if __name__ == "__main__":
#     # Initialize the statistical repository
#     stat_repo = StatisticalRepository()
#
#     # Create an AIFEvent
#     aif_event = AIFEvent("AIF001", "Investment", "Futures Valuation Info", {"contract_size": 1000, "tick_size": 0.01})
#
#     # Post the AIFEvent to the statistical repository
#     post_aif_event(stat_repo, aif_event)
#
#     # Retrieve and print the AIF to verify
#     retrieved_aif = stat_repo.get_aif("AIF001")
#     print(f"AIF ID: {retrieved_aif.aif_id}, Type: {retrieved_aif.type}, Subtype: {retrieved_aif.subtype}, Data: {retrieved_aif.data}")

class RevenueExpenseCapitalRepository:
    def __init__(self):
        self.entries = []

    def add_entry(self, entry):
        self.entries.append(entry)

    def __iter__(self):
        return iter(self.entries)

    # Other methods specific to revenue/expense entries

class AssetLiabilityRepository:
    def __init__(self):
        self.investment_spaces_library = {}  # Maps investments to their specific AssetLiabilitySubspaces

    def get_position_space(self, investment):
        # Ensure a specific investment space exists for each investment; create if not
        if investment not in self.investment_spaces_library:
            self.investment_spaces_library[investment] = AssetLiabilitySubspace()
        return self.investment_spaces_library[investment]

    def reset_subspaces(self):
        for subspace in self.investment_spaces_library.values():
            subspace.reset_entries()  # Call a method to reset entries in each subspace


    def post_journal_entry(self, je):
        # Direct Asset/Liability entries to the appropriate investment space
        if je.entry_type == 'Asset/Liability':
            space = self.get_position_space(je.investment)
            space.post_journal_entry(je)
        # Optionally handle other logic for Asset/Liability entries not specific to an investment


class AssetLiabilitySubspace:
    def __init__(self):
        # Using a dictionary to maintain the structure of (key, values) pairs
        # This allows for efficient lookup and update operations
        self.entries = {}
    def reset_entries(self):
        self.entries = {}  # Reset the entries dictionary

    def post_journal_entry_to_subspace(self, je):
        # Construct the key based on the journal entry attributes
        key = (je.portfolio, je.investment, je.tax_date, je.ls, je.location, je.financial_account)

        # Check if an entry for this key already exists
        if key in self.entries:
            # Entry exists, update its values (quantity, local, book)
            old_values = self.entries[key]
            updated_values = (old_values[0] + je.quantity, old_values[1] + je.local, old_values[2] + je.book)
            self.entries[key] = updated_values
            if abs(updated_values[0]) < .01 and abs(updated_values[1]) < .01 and abs(updated_values[2]) < .01:
                del self.entries[key]

        else:
            # Entry does not exist, create a new one
            self.entries[key] = (je.quantity, je.local, je.book)
class BookkeepingSpace:
    _instance = None  # Class attribute to store the singleton instance

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, check_duplicates=False):
        if not hasattr(self, 'initialized'):  # Use an attribute to check if __init__ has run
            self.initialized = True
            # Your existing initialization code here
            self.journal_entries = []
            self.subspaces = {}
            self.revenue_expense_repository = RevenueExpenseCapitalRepository()
            self.asset_liability_repository = AssetLiabilityRepository()
            self.statistical_entries = []  # Assuming a list or another structure
            # Assuming a list or another structure
            self.all_assets_liabilities_accounts_list = []
            self.all_bookkeeping_accounts_list = []
            self.existing_account_keys = set()
            self.check_duplicates = check_duplicates

    # Example usage:
    def get_bookkeeping_space():
        return BookkeepingSpace()
    def reset_investment_subspaces(self):
        # Call the reset_subspaces method on the asset_liability_repository
        # to clear all entries in each investment subspace.
        self.asset_liability_repository.reset_subspaces()

    def reset_all(self):
        # Additional method to completely reset the BookkeepingSpace, including all repositories
        # and lists, for a fresh start.
        self.revenue_expense_repository.entries = []
        self.asset_liability_repository.reset_subspaces()
        self.statistical_entries = []
        self.journal_entries = []
        self.all_assets_liabilities_accounts_list = []
        self.all_bookkeeping_accounts_list = []
        self.existing_account_keys.clear()
        # Optionally, reset check_duplicates or any other stateful properties here.

    # Other methods specific to revenue/expense entries and iteration...

    def __iter__(self):
        # Assuming self.journal_entries is the list of journal entries you want to iterate over
        return iter(self.journal_entries)

    @classmethod
    def get_instance(cls):
        """Method to get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def create_new_instance(cls, *args, **kwargs):
        """Method to explicitly create a new instance bypassing the singleton behavior."""
        new_instance = super().__new__(cls)
        cls.__init__(new_instance, *args, **kwargs)
        return new_instance


    def add_account_entry(self, entry, list_type):
        account_key = entry.get("account_key")
        if account_key in self.existing_account_keys:
            raise ValueError(f"Duplicate entry for account key: {account_key}")
        else:
            self.existing_account_keys.add(account_key)
            if list_type == "assets_liabilities":
                self.all_assets_liabilities_accounts_list.append(entry)
            elif list_type == "bookkeeping":
                self.all_bookkeeping_accounts_list.append(entry)

        if self.check_duplicates and account_key in self.unique_account_keys:
            raise ValueError(f"Duplicate entry for account key: {account_key}")
        else:
            self.all_accounts_list.append(entry)
            # Update the set only if duplicate checking is enabled
            if self.check_duplicates:
                self.unique_account_keys.add(account_key)

    def reset_accounts(self):
        self.all_assets_liabilities_accounts_list = []
        self.all_bookkeeping_accounts_list = []
        self.existing_account_keys.clear()

    def enable_duplicate_check(self):
        self.check_duplicates = True

    def disable_duplicate_check(self):
        self.check_duplicates = False

    def convert_bookkeeping_objects_to_df(bookkeeping_objects):
        # Assuming 'bookkeeping_objects' is a list of custom objects (e.g., 'Bookkeeping')
        # and you want to include the six elements of 'account_key' and additional attributes like 'quantity', 'local', 'book'
        data = [{
            'portfolio': obj.account_key[0],
            'investment': obj.account_key[1],
            'tax_date': obj.account_key[2],
            'ls': obj.account_key[3],
            'location': obj.account_key[4],
            'financial_account': obj.account_key[5],
            'quantity': obj.quantity,
            'local': obj.local,
            'book': obj.book,
            # Add more attributes as necessary
        } for obj in bookkeeping_objects]

        return pd.DataFrame(data)

    import pandas as pd


    # Adjust the 'Bookkeeping' object attributes as needed
    def combined_assets_liabilities(self, initialize = True):
        aggregated_entries = []
        for subspace in self.asset_liability_repository.investment_spaces_library.values():
            # Ensure keys are included by using .items() to get key-value pairs
            aggregated_entries.extend(subspace.entries.items())
        return aggregated_entries


    def get_combined_space(self, initialize = True):
        asset_liability_space = []
        asset_liability_space = self.combined_assets_liabilities()  # Hypothetical method
        revenue_expense_space = self.get_revenue_expense_space()

        # Combine the spaces
        combined_space = asset_liability_space + revenue_expense_space

        return combined_space


    # def combined_space(self):
    #     # Similarly, ensure key-value pairs are maintained in this aggregation
    #     combined_entries = []
    #     # Combine asset and liability entries with keys
    #     combined_entries.extend(self.combined_assets_liabilities())
    #     # Include revenue/expense and statistical entries, ensuring keys are preserved
    #     # This example assumes you adjust for key-value pairing as needed
    #     combined_entries.extend(self.revenue_expense_repository.entries)  # Hypothetical example
    #     combined_entries.extend(
    #         [(key, value) for key, value in enumerate(self.statistical_entries)])  # Example for list-based structure
    #     return combined_entries

    def get_revenue_expense_entries(self):
        """Directly access revenue and expense entries."""
        return self.revenue_expense_repository.entries

    def get_revenue_expense_space(self):
        """Retrieve revenue and expense entries in a consistent format."""
        formatted_entries = []
        for entry in self.revenue_expense_repository.entries:
            # Directly construct the key and values based on the known structure
            # Assuming 'entry' has attributes or ways to access:
            # portfolio, investment, tax_lot_num, ls, location, financial_account for the key
            # and quantity, local, book for the values
            key = (
            entry.portfolio, entry.investment, entry.tax_date, entry.ls, entry.location, entry.financial_account)
            values = (entry.quantity, entry.local, entry.book)

            # Append the structured entry to the formatted_entries list
            formatted_entry = (key, values)
            formatted_entries.append(formatted_entry)

        return formatted_entries

    def get_position_space(self, investment):
        """Proxy method to simplify access to investment spaces."""
        return self.asset_liability_repository.get_position_space(investment)

    def post_journal_entry(self, je):
        # Append to journal_entries for audit trail
        self.journal_entries.append(je)

        if je.entry_type == 'Asset/Liability':
            # Direct Asset/Liability entries to their specific investment subspace
            space = self.asset_liability_repository.get_position_space(je.investment)
            # Here, we assume space.post_journal_entry(je) correctly updates or appends entries within the subspace
            space.post_journal_entry_to_subspace(je)  # This method needs to handle the logic as per your system's requirements
        elif je.entry_type == 'Revenue/Expense/Capital':
            # Handle Revenue/Expense/Capital entries via the repository
            self.revenue_expense_repository.add_entry(je)
        elif je.entry_type == 'Statistical':
            # Append Statistical entries to a list or manage via a dedicated repository if implemented
            self.statistical_entries.append(je)
        else:
            raise ValueError("Invalid entry type")

    # Threshold to remove any negligible values
    #     threshold = 0.0001
    #     if abs(new_quantity) < threshold and abs(new_local) < threshold and abs(new_book) < threshold:
    #         entries.remove((key, (new_quantity, new_local, new_book)))
    def print_sub_ledger(self):
        for key, value in self.bs:
            quantity, local, book = value
            print(f"Key: {key} Quantity: {quantity} Local: {local} Book: {book}")

    def sum_bs_quantitys(self):
        total_quantity = sum(entry[1][0] for entry in self.bs)
        return total_quantity

    def sum_bs_book(self):
        total_bv = sum(entry[1][2] for entry in self.bs)
        return total_bv

    def get_all_journal_entries(self):
        # Return combined journal entries from both spaces
        return self.asset_liability_repository.entries + self.revenue_expense_repository.entries

    def add_entry(self, entry):
        # Based on entry type, add to the appropriate space
        # Assuming entry has an attribute 'type'
        if entry.type == 'Asset/Liability':
            self.asset_liability_repository.add_entry(entry)
        elif entry.type == 'Revenue/Expense':
            self.revenue_expense_repository.add_entry(entry)

    def build_sub_ledger_from_journals(self, journals, period_end):
        import time
        bs_start_time = time.time()
        space1 = BookkeepingSpace.create_new_instance()
        # space2 = Bookkeeping()

        # Filter and process JEs for space1
        for idx, je in enumerate(journals):
            if je.ibor_date <= period_end:
                space1.post_journal_entry(je)

                #     # Optional: Print status every N entries
                #     if idx % 10 == 0:
                #         print(f"Processed {idx} journal entries for space1...")
                # else:
                #     break  # Exit loop when period_start is reached
                #
                # # Save space1's state
                # space1_state = space1.__dict__.copy()
                #
                # # Continue processing JEs for space2
                # for je in journals[idx:]:  # Start from the current index
                #     if je.ibor_date <= period_end:
                #         space2.post_journal_entry(je)

                # Optional: Print status every N entries
                if idx % 10 == 0:
                    print(f"Processed {idx} journal entries for space2...")
            else:
                break  # Exit loop when period_end is exceeded

        print("Finished processing all journal entries!")
        bs_end_time = time.time()
        fetch_time = bs_end_time - bs_start_time

        print("\nElapsed time- BS build from data: {:.6f}".format(fetch_time))

        # Return the states of space1 and space2
        return space1

    @property
    def sub_ledger(self):
        return self.asset_liability_entries + self.revenue_expense_entries

    def add_journal_entry(self, entry):
        self.journal_entries.append(entry)

    def process_stock_split(self, investment, split_ratio: float):
        split_quantities = {}
        for je in self.asset_liability_entries:
            if je[0][1] != investment:
                continue  # Skip entries that do not match the specified investment
            pos_type = je[0][3]
            additional_quantity = je[1][0] * split_ratio - je[1][0]
            split_quantities[pos_type] = additional_quantity

        return split_quantities

    def aggregate_entries(self):
        # Combine both asset/liability and revenue/expense entries into a single list
        all_entries = self.asset_liability_entries + self.revenue_expense_entries
        return all_entries

    def lot_iterator_by_custodian(self, investment, entry_type, new_shares_ratio):
        if entry_type == "dividends":
            entries = self.asset_liability_entries
        elif entry_type == "stock_splits":
            entries = self.asset_liability_entries  # Or you can use another appropriate attribute
        else:
            raise ValueError("Invalid entry_type provided")

        for entry in entries:
            key, value = entry
            # Assuming that key is in the format (portfolio, investment, lot_id, pos_type, location, financial_account)
            portfolio, inv, lot_id, pos_type, location, fa = key

            # Perform additional filtering or processing based on the specific entry_type if needed
            # For example, check the investment and new_shares_ratio

            # If the entry meets the desired conditions, yield the relevant lot information
            yield lot_id, value[0] * new_shares_ratio, location

    def query_aggregate_balances(self, query):
        query_parts = query.split('.')
        dimensions = query_parts[:-1]
        metric = query_parts[-1]
        aggregate_dict = self.aggregates
        for dimension in dimensions:
            if dimension not in aggregate_dict:
                return None
            aggregate_dict = aggregate_dict[dimension]

        if metric not in aggregate_dict:
            return None
        return aggregate_dict[metric]


    class Investment:
        def __init__(self, type, name, legs=None):
            self.type = type
            self.name = name
            self.legs = legs or []

        def get_legs_by_exposure(self, exposure_type):
            return [leg for leg in self.legs if leg.exposure_type == exposure_type]

        def report_exposure(self):
            report = {}
            for exposure_type in ExposureType:
                legs = self.get_legs_by_exposure(exposure_type)
                total_notional = sum(leg.notional_amount for leg in legs)
                total_local = sum(leg.local for leg in legs)
                total_book = sum(leg.book for leg in legs)
                report[exposure_type.value] = {
                    "Total Notional": total_notional,
                    "Total Local": total_local,
                    "Total Book": total_book
                }
            return report

    from enum import Enum

    class ExposureType(Enum):
        EQUITY = "Equity"
        FIXED_INCOME = "Fixed Income"
        COMMODITY = "Commodity"
        CURRENCY = "Currency"

    class Leg:
        def __init__(self, leg_name, notional_amount, type, quantity, local, book, exposure_type, investment,
                     day_count=None, accrual_rate=None, reset_date=None):
            self.leg_name = leg_name
            self.notional_amount = notional_amount
            self.type = type
            self.quantity = quantity
            self.local = local
            self.book = book
            self.exposure_type = exposure_type
            self.investment = investment
            self.day_count = day_count
            self.accrual_rate = accrual_rate
            self.reset_date = reset_date

def store_journals(journals):
    fieldnames = ['portfolio', 'investment', 'tax_lot_num', 'ls', 'location', 'financial_account']

    with open("journal_entries.csv", 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(fieldnames)

        for journal in journals:
            journal_tuple = (
                journal.portfolio,
                journal.investment,
                journal.tax_lot_num,
                journal.ls,
                journal.location,
                journal.financial_account
            )
            writer.writerow(journal_tuple)

def update_running_balances( jes, level_preference):
    from collections import defaultdict
    running_totals = defaultdict(lambda: [0, 0, 0])  # Default to (0, 0, 0) for (quantity, local, book)

    # We sort the journal entries to ensure we're processing them in the order they occurred.
    # If they're already in the desired order, this step can be skipped.
    sorted_jes = sorted(jes, key=lambda je:  (str(je.ibor_date),je.tranid is None, je.tranid, je.investment, je.ls,je.location, je.financial_account))
   # sorted_jes = sorted(jes, key=lambda je: je.tranid)  # sort option.

    for je in sorted_jes:
        key = tuple(getattr(je, attr) for attr in level_preference)

        # Update running totals
        running_totals[key][0] += je.quantity
        running_totals[key][1] += je.local
        running_totals[key][2] += je.book

        # Assign the current running totals to this journal entry
        je.running_balances = tuple(running_totals[key])

def parse_journal_entries(file_path):
    with open(file_path, "r") as file:
        lines = file.readlines()

    journal_entries = []
    entry_data = {}
    for line in lines:
        line = line.strip()
        if line.startswith("Entry Count"):
            if entry_data:
                journal_entry = Journals(**entry_data)
                journal_entries.append(journal_entry)
            entry_data = {}
        elif line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            entry_data[key] = value

    if entry_data:
        journal_entry = Journals(**entry_data)
        journal_entries.append(journal_entry)

    return journal_entries



import csv

import os
def close_a_period(period_name, old_je):
    # Generate the timestamp
    timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')

    # Create a CSV file with period name and timestamp in the description
    file_name = f"{period_name}_timestamp_{timestamp}.csv"
    file_name = file_name.replace(" ", "_")  # Replace whitespace with underscore
    file_path = f"C:/Users/hjmne/PycharmProjects/chest/PeriodFiles/{file_name}"

    # Check if the file already exists
    if os.path.isfile(file_path):
        print("File already exists.")
        return

    # Prepare the data to be written
    data = []
   #- data.append(['Timestamp', timestamp])
    data.append(['portfolio', 'investment', 'tax_lot_num', 'ls', 'location', 'financial_account',
                 'quantity', 'local', 'book', 'tranid', 'transaction', 'tradedate', 'settledate',
                 'kdbegin', 'kdend','ibor_date', 'running_balances', 'entry_count'])

    for record in old_je:
        data.append([
            record.portfolio,
            record.investment,
            record.tax_lot_num,
            record.ls,
            record.location,
            record.financial_account,
            record.quantity,
            record.local,
            record.book,
            record.tranid,
            record.transaction,
            record.tradedate,
            record.settledate,
            record.kdbegin,
            record.kdend,
            record.ibor_date,
            record.running_balances,
        ])

    # Write the data to the file
    with open(file_path, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerows(data)

from datetime import datetime

def check_date_format(date_str, format):
    try:
        datetime.strptime(date_str, format)
        return True
    except ValueError:
        return False

def add_leading_zero(df):
    df.index = df.index.astype(str)  # Ensures that the index is of type string
    df.index = df.index.map(lambda x: x if len(x.split('/')[0]) == 2 or x.split('/')[0] == "0" else '0'+x)
    return df

def format_date(date_string):
    date_obj = datetime.strptime(date_string, '%m/%d/%Y')
    return date_obj.strftime('%m/%d/%Y').lstrip("0").replace("/0", "/")

from dateutil.parser import parse

def parse_date(date_string):
    try:
        return parse(date_string).date()
    except ValueError:
        raise ValueError(f"Unable to parse date from string: {date_string}")

def load_price_data(price_file):
    price_data = {}
    with open(price_file, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            date = parse_date(row['date']).isoformat() # Using the ISO format
            date_obj = datetime.strptime(row['date'], '%m/%d/%Y')  # Parsing date
            date = date_obj.strftime('%m/%d/%Y').lstrip("0").replace("/0", "/")
            ticker = row['ticker']
            currency = row['currency']
            price = float(row['price'])

            if date not in price_data:
                price_data[date] = {}

            # Create a nested dictionary for each ticker containing 'price' and 'currency' fields
            price_data[date][ticker] = {
                'price': price,
                'currency': currency
            }

    return price_data
def load_fx_data(fx_file):
    fx_data = {}
    with open(fx_file, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            date = parse_date(row['date']).isoformat() # Using the ISO format
            date_obj = datetime.strptime(row['date'], '%m/%d/%Y')  # Parsing date
            date = date_obj.strftime('%m/%d/%Y').lstrip("0").replace("/0", "/")
        # Formatting date
            currency = row['currency']
            if date not in fx_data:
                fx_data[date] = {}
            fx_data[date][currency] = float(row['price'])
    return fx_data

import csv

def load_coa_from_csv():
    filename = "C:/Users/hjmne/PycharmProjects/chest/refdata/chart_of_accounts.csv"
    with open(filename, mode='r') as file:
        reader = csv.DictReader(file, delimiter='\t')
        return [row for row in reader]

def get_system_type(coa, system_name):
    for account in coa:
        if account["SystemName"] == system_name:
            return account["SystemType"]
    return None  # return None if no matching SystemName is found

def validate_bookkeeping_entry(entry):
    expected_keys = ['portfolio', 'investment', 'tax_lot', 'ls', 'location', 'financial_account', 'quantity', 'local', 'book']

    # Check if the entry has all the expected keys
    if not all(key in entry for key in expected_keys):
        return False

    # Check data types of the entry
    if not isinstance(entry['portfolio'], str) or \
            not isinstance(entry['investment'], str) or \
            not isinstance(entry['tax_lot'], int) or \
            not isinstance(entry['ls'], str) or \
            not isinstance(entry['location'], str) or \
            not isinstance(entry['financial_account'], str) or \
            not isinstance(entry['quantity'], int) or \
            not isinstance(entry['local'], float) or \
            not isinstance(entry['book'], float):
        return False

    return True

def query_income_activity(journal_entries):
    # Dictionary to hold roll-up data
    rollup_data = {}

    for je in journal_entries:
        financial_account = je.financial_account
        investment = je.investment
        feeder = je.feeder

        if financial_account in ["Income", "DividendReceipt", "PriceGainInvestment", "FXGainInvestment",
                                 "InterestReceipt", "ContributedCost", "FXGainInvestment", "PerfFee", "MgmtFee",
                                 "FXGainLossInvestment", "UnrealGLRevExp", "FXGainTradeSettle"]:
            key = (investment, financial_account, feeder)
            rollup_data.setdefault(key, {"local": 0, "book": 0})

            rollup_data[key]["local"] += je.local  # Assuming 'local' is an attribute of Journals
            rollup_data[key]["book"] += je.book    # Assuming 'book' is an attribute of Journals

    summary_list = []
    for key, values in rollup_data.items():
        investment, account, feeder = key
        summary_list.append({
            "investment": investment,
            "account": account,
            "feeder" : feeder,
            "local": values["local"],
            "book": values["book"]
        })

    return summary_list

def query_balance_sheet_activity(journal_entries):
    # Dictionary to hold roll-up data
    rollup_data = {}

    for je in journal_entries:
        financial_account = je.financial_account
        investment = je.investment
        feeder = je.feeder


        key = (investment, financial_account, feeder)
        rollup_data.setdefault(key, {"quantity": 0, "local": 0, "book": 0})

        rollup_data[key]["quantity"] += je.quantity  # Assuming 'local' is an attribute of Journals
        rollup_data[key]["local"] += je.local  # Assuming 'local' is an attribute of Journals
        rollup_data[key]["book"] += je.book    # Assuming 'book' is an attribute of Journals

    summary_list = []
    for key, values in rollup_data.items():
        investment, account, feeder = key
        summary_list.append({
            "investment": investment,
            "account": account,
            "feeder" : feeder,
            "quantity": values["quantity"],
            "local": values["local"],
            "book": values["book"]
        })

    return summary_list


import os
def parse_chart_of_accounts(filename):
    """Parses the chart of accounts and returns a dictionary."""
    chart_dict = {}
    if not isinstance(filename, str):
        raise TypeError(f"Expected a string for filename, but got {type(filename)} with value {filename}")

    with open(filename, 'r') as file:
        # Skipping the header row
        next(file)

        for line in file:
            parts = line.strip().split('\t')  # Using tab as the delimiter

            # Ensure there are 6 elements, fill in missing with empty string

            while len(parts) < 6:
                parts.append('')

            system_name, space_pref, user_description, gl_account_num, group1, group2 = parts
            chart_dict[system_name] = {
                "SpacePref": space_pref,
                "UserDescription": user_description,
                "GLAccountNum": gl_account_num,
                "Group1": group1,
                "Group2": group2
            }
    return chart_dict


def fetch_mark_records_by_account_key(account_key, all_entries):
    # First, filter the entries based on the given account_key
    filtered_entries = [entry for entry in all_entries if entry.account_key == account_key]

    # Then, filter the filtered_entries by type_name
    asset_records = [entry for entry in filtered_entries if entry.type_name == "UnrealGLAsset"]
    revexp_records = [entry for entry in filtered_entries if entry.type_name == "UnrealGLRevExp"]

    return asset_records, revexp_records


