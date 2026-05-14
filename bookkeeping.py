print("IMPORTING BOOKKEEPING")

import bond_calc
import utilities
from collections import OrderedDict
import logging
import datetime


from datetime import datetime




# ============================================================
# SYSTEM / OS-LEVEL FUND INTERNALS
# ============================================================

class CadenceStyle:
    """
    Defines the allowed calendars for a group of portfolios.
    Purely declarative — no processing logic.
    """

    def __init__(self, name, calendars):
        self.name = name
        self.calendars = set(calendars)

    def supports_calendar(self, calendar_name):
        return calendar_name in self.calendars

    def __repr__(self):
        return f"CadenceStyle(name={self.name}, calendars={sorted(self.calendars)})"


import os


class Portfolio:
    """
    Represents a single accounting portfolio.
    """

    def __init__(self, name, root_path, base_currency=None):
        self.name = name
        self.root_path = root_path
        self.base_currency = base_currency  # optional, no enforcement
        self._composite = None

    def _set_composite(self, composite):
        if not hasattr(self, "_composites"):
            self._composites = set()

        self._composites.add(composite)

    @property
    def composites(self):
        return getattr(self, "_composites", set())

    def get_calendars_path(self):
        import os
        return os.path.join(self.root_path, "Calendars")

    def list_calendars(self):
        import os
        path = self.get_calendars_path()
        if not os.path.exists(path):
            return []

        return [
            name for name in os.listdir(path)
            if os.path.isdir(os.path.join(path, name))
        ]

    def supports_calendar(self, calendar_name):
        if not self._composite:
            raise ValueError(f"Portfolio '{self.name}' is not assigned to a composite")

        return self._composite.supports_calendar(calendar_name)

    def __repr__(self):
        comp = self._composite.name if self._composite else None
        return f"Portfolio(name={self.name}, base_currency={self.base_currency}, composite={comp})"

class PortfolioComposite:
    """
    Logical grouping of portfolios.
    Carries a cadence style that governs calendar usage.
    """

    def __init__(self, name, cadence_style):
        self.name = name
        self.cadence_style = cadence_style
        self._portfolios = {}

    def add_portfolio(self, portfolio):
        if portfolio.name in self._portfolios:
            raise ValueError(f"Duplicate portfolio '{portfolio.name}' in composite '{self.name}'")

        self._portfolios[portfolio.name] = portfolio
        portfolio._set_composite(self)

    def get_portfolios(self):
        return list(self._portfolios.values())

    def get_portfolio_names(self):
        return list(self._portfolios.keys())

    def supports_calendar(self, calendar_name):
        return self.cadence_style.supports_calendar(calendar_name)

    def __repr__(self):
        return f"PortfolioComposite(name={self.name}, cadence_style={self.cadence_style.name})"

# NOTE: Precedence is assigned to individual event functions, not just event types.
# This ensures granular control over execution order, particularly for multi-stage events.

# In EventScheduler class
from collections import OrderedDict

class EventScheduler:
    def __init__(self, ctx):
        """
        Scheduler binds a single KernelExecutionContext
        for the entire run.
        """
        self.ctx = ctx
        self.events = OrderedDict()

        self._sorted = False
        self._executed = False

        self.event_type_precedence = {
            'open_payable': 1073, 'open_receivable': 1074,
             'buy_equity': 1075, 'sell_equity': 1111,
            'short_equity': 1076, 'cover_equity': 1111,
            'buy_bond': 1075, 'sell_bond': 1111,
            'short_bond': 1111, 'cover_bond': 1111,
            'buy_future': 1075, 'sell_future': 1111,
            'short_future': 1076, 'cover_future': 1111,
            'open_swap': 1075, 'reset_swap': 1111,
            'spot_fx': 1111, 'forward_fx': 1111,
            'deposit_currency': 1090, 'withdraw_currency': 1090,
            'split_equity': 1065, 'dividend_equity': 1068,
            'mark_prices': 9000, 'perf_mark': 9000,
            'allocate': 9500,
            'settle_bond_flows_in': 1050,
            'settle_bond_flows_out': 1053,
            'settle_single_flow_in': 1051,
            'settle_single_flow_out': 1054,
            'settle_multiple_flows_in_out': 1055,
            'settle_pay_rec_by_tranid': 1056,
            'mark_bond_accruals': 1060,
            'bond_coupon': 1061,
            'assign_call_long': 1113,
            'assign_put_short': 1114,
            'write_option': 1111
        }

    def schedule_event(self, tradedate, event_function, *args):

        # --------------------------------------------------
        # Extract tranid from args (authoritative)
        # --------------------------------------------------
        tranid = None

        for a in args:
            if isinstance(a, int):
                tranid = a
                break

        if tranid is None:
            raise RuntimeError(
                f"Scheduled event {event_function.__name__} missing tranid"
            )

        if not callable(event_function):
            raise ValueError("event_function must be callable")

        # 🔥 Derive event_type from the function name AUTOMATICALLY
        event_type = event_function.__name__

        if event_type not in self.event_type_precedence:
            raise ValueError(f"Unrecognized event function: {event_type}")

        event_id = len(self.events) + 1

        self.events[event_id] = {
            "tradedate": tradedate,
            "event_function": event_function,
            "args": args,
            "event_type": event_type,
            "tranid": tranid  # 👈 STEP 2 IS RIGHT HERE
        }

    def sort_events(self):
        """
        Sort events by tradedate and event precedence, then rebuild the OrderedDict
        so that popitem(last=False) processes them in correct order.
        """
        assert not self._executed, (
            "Scheduler.sort_events() called AFTER execution started. "
            "Schedulers must be sorted BEFORE any events run."
        )

        try:
            # 1. Convert to list and sort by (tradedate, precedence)
            sorted_items = sorted(
                self.events.items(),
                key=lambda x: (
                    x[1]["tradedate"],
                    self.event_type_precedence[x[1]["event_type"]]
                )
            )

            # 2. Rebuild the OrderedDict in sorted order
            new_events = OrderedDict()
            for key, value in sorted_items:
                new_events[key] = value

            self.events = new_events
            self._sorted = True

        except Exception as e:
            print(f"❌ Sort failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()


    def run_next_event(self):
        if not self.events:
            return 0

        assert self._sorted, (
            "Scheduler.run_next_event() called before scheduler.sort_events(). "
            "Execution order is undefined without sorting."
        )

        self._executed = True
        event_key, event = self.events.popitem(last=False)
        func = event['event_function']
        args = event['args']
        func(*args)
        return 1

def accrue_interest(space, smf, portfolio, investment, current_date, fx_rates_df):
    investment_cache = {}

    # Cache investment types and subspaces to minimize redundant accesses
    for investment in space.asset_liability_repository.investment_spaces_library.keys():
        if investment not in investment_cache:
            subspace = space.asset_liability_repository.get_position_space(investment)
            investment_type = subspace.get_attribute_field("AIF", "investment_type")
            if investment_type:
                investment_type = investment_type.strip()
                investment_cache[investment] = (investment_type, subspace)
            else:
                #print(f"Investment type for {investment} is None, skipping this investment.")
                continue

    # Process only BOND investments
    for investment, (investment_type, subspace) in investment_cache.items():
        if investment_type == "BOND":
            print(f"Processing BOND investment: {investment}")

            net_positions = smf.calculate_net_positions(portfolio=portfolio, investment=investment, date=current_date)
            print(f"Net Positions for {investment}: {net_positions}")

            for location, positions in net_positions.items():
                for position_type, qty in positions.items():
                    ls = 'l' if 'long' in position_type else 's'
                    if ls == 's':
                        qty = -qty

                    issue_date_str = subspace.get_attribute_field('AIF', 'issue_date')
                    first_coupon_date_str = subspace.get_attribute_field('AIF', 'first_coupon_date')
                    next_to_last_coupon_date_str = subspace.get_attribute_field('AIF', 'next_to_last_coupon_date')
                    maturity_date_str = subspace.get_attribute_field('AIF', 'maturity_date')
                    coupon_rate = float(subspace.get_attribute_field('AIF', 'coupon_rate'))
                    day_count_convention = 'actual/365'
                    payment_frequency = 'semi-annual'
                    semi_split = "C"

                    issue_date = datetime.strptime(issue_date_str, '%m/%d/%Y')
                    first_coupon_date = datetime.strptime(first_coupon_date_str, '%m/%d/%Y')
                    next_to_last_coupon_date = datetime.strptime(next_to_last_coupon_date_str, '%m/%d/%Y')
                    maturity_date = datetime.strptime(maturity_date_str, '%m/%d/%Y')
                    valuation_date = current_date

                    accrued_interest, days_in_period, days_of_accrual = bond_calc.calculate_accrued_interest(
                        issue_date, first_coupon_date, day_count_convention, payment_frequency,
                        next_to_last_coupon_date, maturity_date, valuation_date, coupon_rate, semi_split
                    )

                    coupon = qty * accrued_interest

                    if coupon > 0:
                        faal = "InterestReceivable"
                        faie = "InterestReceipt"
                    else:
                        faal = "InterestPayable"
                        faie = "InterestExpense"

                    payment_currency = subspace.get_attribute_field('AIF', 'payment_currency')
                    fx_rate = 1  # Example placeholder
                    coupon_in_book_terms = coupon * fx_rate

                    bcoup = Journals(portfolio, payment_currency, 0, ls, location, faal, coupon_in_book_terms,
                                     coupon_in_book_terms, coupon_in_book_terms, 0,
                                     "Accrual", valuation_date, valuation_date, valuation_date,
                                     valuation_date, valuation_date, "Asset/Liability")
                    space.post_journal_entry(bcoup)

                    bcoupRE = Journals(portfolio, investment, 0, ls, location, faie, 0, -coupon_in_book_terms,
                                       -coupon_in_book_terms, 0,
                                       "Accrual", valuation_date, valuation_date, valuation_date, valuation_date,
                                       valuation_date,
                                       "Revenue/Expense/Capital")
                    space.post_journal_entry(bcoupRE)
        else:
            print(f"Skipping non-BOND investment: {investment}, Type: {investment_type}")

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
from datetime import datetime
from typing import Optional, Tuple

class Journals:
    sequence_counter = 0
    def __init__(self, portfolio: str = "", investment: str = "", lotid: int = 0, tax_date: Optional[datetime] = None,
                 ls: str = "", location: str = "", financial_account: str = "",
                 quantity: float = 0.0, local: float = 0.0, book: float = 0.0,
                 notional: float = None, oface: Optional[float] = None, tranid: Optional[int] = 0, transaction: str = "",
                 tradedate: Optional[datetime] = None, settledate: Optional[datetime] = None,
                 kdbegin: Optional[datetime] = None, kdend: Optional[datetime] = None,
                 ibor_date: Optional[datetime] = None, entry_type: str = "", feeder: str = "",
                 running_balances: Tuple[float, float, float] = (0.0, 0.0, 0.0),
                 split_ratio: float = 1.0, account_key: Optional[Tuple[str, str, int, datetime, str, str, str]] = None,
                 period: str = "", journal_type: str = "", sequence_number: Optional[int] = None):

        # Assign values to attributes
        self.portfolio = portfolio
        self.investment = investment
        self.lotid = lotid
        self.tax_date = datetime.fromisoformat(tax_date) if isinstance(tax_date, str) else tax_date
        self.ls = ls
        self.location = location
        self.financial_account = financial_account
        self.quantity = quantity
        self.local = local
        self.book = book
        # Handle None for notional and set to 0 if needed
        self.notional = notional if notional is not None else 0.0  # Focused change for `notional`
        self.oface = oface
        self.tranid = tranid
        self.transaction = transaction
        self.tradedate = datetime.fromisoformat(tradedate) if isinstance(tradedate, str) else tradedate
        self.settledate = datetime.fromisoformat(settledate) if isinstance(settledate, str) else settledate
        self.kdbegin = datetime.fromisoformat(kdbegin) if isinstance(kdbegin, str) else kdbegin
        self.kdend = datetime.fromisoformat(kdend) if isinstance(kdend, str) else kdend
        self.ibor_date = datetime.fromisoformat(ibor_date) if isinstance(ibor_date, str) else ibor_date
        self.entry_type = entry_type
        self.feeder = feeder
        self.running_balances = running_balances
        self.split_ratio = split_ratio

        # If `account_key` is not provided, construct it from existing attributes
        self.account_key = account_key or (
            self.portfolio, self.investment, self.lotid, self.tax_date, self.ls, self.location, self.financial_account
        )


        # Assign period and journal type
        self.period = period
        self.journal_type = journal_type

        # Assign a sequence number if not provided
        if sequence_number is None:
            self.sequence_number = Journals.sequence_counter
            Journals.sequence_counter += 1
        else:
            self.sequence_number = sequence_number

        self.entries = []

    def __str__(self):
        return (f"JournalEntry(portfolio={self.portfolio}, investment={self.investment}, lotid={self.lotid}, "
                f"tax_date={self.tax_date}, ls={self.ls}, location={self.location}, "
                f"financial_account={self.financial_account}, quantity={self.quantity}, "
                f"local={self.local}, book={self.book}, notional={self.notional}, oface={self.oface})")


    @classmethod
    def fetch_market_values(cls, journal_entries, edate, portfolio, investment, lotid, location, financial_account="MarketVal"):
        """
        Fetch market values from the journal entries based on the given criteria.
        """
        # Truncate time from edate
        edate = edate.date() if isinstance(edate, datetime) else edate

        for entry in journal_entries:
            # Truncate time from entry.tradedate
            entry_date = entry.tradedate.date() if isinstance(entry.tradedate, datetime) else entry.tradedate

            if (entry.financial_account == financial_account and
                    entry.investment == investment and
                    entry.lotid == lotid and
                    entry.location == location and
                    entry_date == edate and
                    entry.entry_type == "Revenue/Expense/Capital"):
                # Return the market values if a match is found
                return entry.local, entry.book

        # Return None if no match is found
        return None, None

        # Method to add a journal entry

    def add_entry(self, entry):
        self.entries.append(entry)

        # Method to get all entries

    def get_entries(self):
        return self.entries

    def to_dict(self):
        def format_date(date_value):
            if isinstance(date_value, str):
                try:
                    date_value = datetime.fromisoformat(date_value)
                except ValueError:
                    return date_value
            return date_value.strftime("%Y-%m-%dT%H:%M:%S") if isinstance(date_value, datetime) else date_value

        return {
            # Other fields...
            "portfolio": self.portfolio,
            "investment": self.investment,
            "lotid": self.lotid,
            "tax_date": self.tax_date.strftime("%Y-%m-%dT%H:%M:%S") if self.tax_date else None,
            "ls": self.ls,
            "location": self.location,
            "financial_account": self.financial_account,
            "quantity": self.quantity,
            "local": self.local,
            "book": self.book,
            "notional": self.notional,
            "oface": self.oface,
            "tranid": self.tranid,
            "transaction": self.transaction,
            "tradedate": self.tradedate.strftime("%Y-%m-%dT%H:%M:%S") if self.tradedate else None,
            "settledate": self.settledate.strftime("%Y-%m-%dT%H:%M:%S") if self.settledate else None,
            "kdbegin": self.kdbegin.strftime("%Y-%m-%dT%H:%M:%S") if self.kdbegin else None,
            "kdend": self.kdend.strftime("%Y-%m-%dT%H:%M:%S") if self.kdend else None,
            "ibor_date": self.ibor_date.strftime("%Y-%m-%dT%H:%M:%S") if self.ibor_date else None,
            "entry_type": self.entry_type,
            "feeder": self.feeder,
            "running_balances": self.running_balances,
            "split_ratio": self.split_ratio,
            "account_key": self.account_key,
            # Uncomment and handle default values if these fields are needed:
            # "asset_class": self.asset_class if hasattr(self, 'asset_class') else None,
            # "currency": self.currency if hasattr(self, 'currency') else None,
            # "country": self.country if hasattr(self, 'country') else None,
            # "sector": self.sector if hasattr(self, 'sector') else None,
            # "system_type": self.system_type if hasattr(self, 'system_type') else None,
            # "group1": self.group1 if hasattr(self, 'group1') else None,
            # "bsgroup": self.bsgroup if hasattr(self, 'bsgroup') else None,
            # "performance_category": self.performance_category if hasattr(self, 'performance_category') else None,
        }

    @classmethod
    def from_dict(cls, data):
        # Normalize tax_date, default to January 1, 1970, if empty or invalid
        if 'tax_date' in data and data['tax_date']:
            tax_date = datetime.strptime(data['tax_date'], "%Y-%m-%dT%H:%M:%S").replace(hour=0, minute=0, second=0)
        else:
            tax_date = datetime(1970, 1, 1, 0, 0, 0)

        return cls(
            portfolio=data['portfolio'],
            investment=data['investment'],
            lotid=data['lotid'],
            tax_date=tax_date,
            ls=data['ls'],
            location=data['location'],
            financial_account=data['financial_account'],
            transaction=data['transaction'],
            quantity=data['quantity'],
            local=data['local'],
            book=data['book'],
            notional=data['notional'],
            oface=data['oface'],
            tradedate=datetime.strptime(data['tradedate'], "%Y-%m-%dT%H:%M:%S"),
            settledate=datetime.strptime(data['settledate'], "%Y-%m-%dT%H:%M:%S"),
            ibor_date=datetime.strptime(data['ibor_date'], "%Y-%m-%dT%H:%M:%S"),
            kdbegin=data['kdbegin'],
            kdend=data['kdend'],
            entry_type=data['entry_type'],
            feeder=data['feeder'],
            running_balances=data['running_balances'],
            split_ratio=data['split_ratio'],
            account_key=data['account_key']
        )
@staticmethod
def from_json(entry):
    if 'tax date' in entry:
        entry['tax_date'] = entry.pop('tax date')

    entry.pop('lines', None)

    date_fields = ['ibor_date', 'kdbegin', 'kdend', 'tradedate', 'settledate', 'tax_date']
    for date_field in date_fields:
        if date_field in entry:
            if isinstance(entry[date_field], str):
                entry[date_field] = entry[date_field].replace('T', ' ')
                try:
                    entry[date_field] = datetime.strptime(entry[date_field], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass
            elif isinstance(entry[date_field], int):
                pass

    if 'running_balances' in entry:
        entry['running_balances'] = tuple(entry['running_balances'])
    if 'account_key' in entry:
        entry['account_key'] = tuple(entry['account_key'])

    return Journals(**entry)

class StatisticalRepository:
    def __init__(self):
        # Use a dictionary to store data keyed by a tuple of all relevant identifiers
        self.data = {}

    def add_entry(self, mark_date, portfolio, investment, lotid, tax_date, stat_account_name, ls, location, stat_repo,
                  local_value, book_value, notional):
        # Construct the key including 'lotid' and 'tax_date' to ensure uniqueness
        key = (mark_date, portfolio, investment, lotid, tax_date, stat_account_name, ls, location)
        self.data[key] = {'local': local_value, 'book': book_value, 'notional': notional}
      #  print(f"Added entry: {key} -> {self.data[key]}")  # Debugging print statement to verify key addition

    def clear(self):
        """Clears all data in the StatisticalRepository safely."""
        print("Clearing repository...")

        import pandas as pd
        import gc

        print(f"🧭 Type before clear: {type(self.data)}")

        try:
            if isinstance(self.data, pd.DataFrame):
                self.data.drop(index=self.data.index, inplace=True)
            elif isinstance(self.data, pd.Series):
                # Handle Series safely
                self.data = pd.Series(dtype=self.data.dtype)
            elif isinstance(self.data, (dict, list, set)):
                self.data.clear()
            else:
                self.data = {}
        except Exception as e:
            print(f"⚠️ Safe clear fallback: {e}")
            self.data = {}

        gc.collect()
        print("Repository cleared.")

    def remove_stats_for(self, investment, location, ls):
        """
        Remove all statistical accounts for this investment/location/ls triple.
        """
        keys_to_delete = []

        for key in self.entries:
            inv, loc, long_short, stat_name = key
            if inv == investment and loc == location and long_short == ls:
                keys_to_delete.append(key)

        for k in keys_to_delete:
            del self.entries[k]

    def delete_investment(self, portfolio, investment):
        keys_to_delete = [k for k in list(self.data.keys())
                          if k[1] == portfolio and k[2] == investment]
        for k in keys_to_delete:
            del self.data[k]

    def reset(self):
        """Resets the entire statistical repository to its initial state."""
        print("Resetting repository...")  # Debug statement to confirm reset operation
        self.data = {}
        import gc
        gc.collect()  # Force garbage collection
        print("Repository reset.")

    def get_entry(self, mark_date, portfolio, investment, lotid, tax_date, stat_account_name, ls, location, stat_repo):
        # Construct the key using all relevant dimensions
        key = (mark_date, portfolio, investment, lotid, tax_date, stat_account_name, ls, location)
      #  print(f"Getting entry for key: {key}")  # Debug statement to verify key retrieval

        # Check if the key exists in the data
        if key in self.data:
            entry = self.data[key]
       #     print(f"Found entry: {entry}")  # Debugging print statement

            # Return local, book, and handle notional if it's present
            local_value = entry.get('local')
            book_value = entry.get('book')
            notional_value = entry.get('notional', None)  # Default to None if not present

            return local_value, book_value, notional_value

        # If the key doesn't exist, return None for all fields
     #   print("Entry not found.")
        return None, None, None


class QuantityTracker:
    def __init__(self):
        self.lot_quantities = {}

    def update_quantity(self, lot_id, quantity_change):
        """ Update the quantity for a given lot_id """
        if lot_id in self.lot_quantities:
            self.lot_quantities[lot_id] += quantity_change
        else:
            self.lot_quantities[lot_id] = quantity_change

    def get_quantity(self, lot_id):
        """ Retrieve the current quantity for a given lot_id """
        return self.lot_quantities.get(lot_id, 0)


class RevenueExpenseCapitalRepository:
    def __init__(self):
        self.entries = []
        self.entries.clear()
        self.investment_spaces_library = {}
        self.balance_spaces_library = {}

    def add_entry(self, entry):
        self.entries.append(entry)

    def __iter__(self):
        return iter(self.entries)

    def get_balance_space(self, investment):

        if investment not in self.balance_spaces_library:
            self.balance_spaces_library[investment] = {
                "entries": {},
                "position_state": {},
            }

        return self.balance_spaces_library[investment]

    def post_journal_entry_to_balance_space(self, balance_space, je):

        entries = balance_space["entries"]
        position_state = balance_space["position_state"]

        # ------------------------------------------------------------
        # Normalize journal values (Rev/Exp may not carry quantity)
        # ------------------------------------------------------------
        qty = je.quantity or 0.0
        local = je.local or 0.0
        book = je.book or 0.0
        notional = je.notional or 0.0
        oface = je.oface or 0.0

        key = (
            je.portfolio,
            je.investment,
            je.lotid,
            je.tax_date,
            je.ls,
            je.location,
            je.financial_account,
        )

        # ------------------------------------------------------------
        # Lot-level accumulation
        # ------------------------------------------------------------
        if key in entries:
            old_qty, old_local, old_book, old_notional, old_oface = entries[key]

            new_qty = old_qty + qty
            new_local = old_local + local
            new_book = old_book + book
            new_notional = (old_notional or 0.0) + notional
            new_oface = (old_oface or 0.0) + oface

            # Auto-delete collapsed lots (qty-driven collapse only)
            # Collapse only if FULL economic zero
            if (
                    abs(new_qty) < 0.01
                    and abs(new_local) < 0.01
                    and abs(new_book) < 0.01
            ):
                del entries[key]
                return

            entries[key] = (
                new_qty,
                new_local,
                new_book,
                new_notional,
                new_oface,
            )

        else:
            entries[key] = (
                qty,
                local,
                book,
                notional,
                oface,
            )

        # ------------------------------------------------------------
        # Derived runtime position state (optional symmetry)
        # ------------------------------------------------------------
        pos_key = (je.location, je.ls)

        if pos_key not in position_state:
            position_state[pos_key] = {
                "position_qty": 0.0,
                "local_cost": 0.0,
                "book_cost": 0.0,
                "notional": 0.0,
            }

        position_state[pos_key]["position_qty"] += qty
        position_state[pos_key]["local_cost"] += local
        position_state[pos_key]["book_cost"] += book
        position_state[pos_key]["notional"] += notional

        # Drop zero positions
        if abs(position_state[pos_key]["position_qty"]) < 0.01:
            del position_state[pos_key]

    def clear_balances(self):
        self.balances = {}

    def add_balance(self, key, quantity, local, book):
        self.balances[key] = (quantity, local, book)

    from collections import defaultdict


    def reset(self):
        """Reset the repository by clearing all entries and subspaces."""
        self.entries.clear()
        self.investment_spaces_library.clear()  # Clear subspaces if they exist

    def get_position_space(self, investment):
        if investment not in self.investment_spaces_library:
            self.investment_spaces_library[investment] = AssetLiabilitySubspace()
        return self.investment_spaces_library[investment]

    def query_balance(self, tranid, account_type, investment):
        subspace = self.get_position_space(investment)
        return subspace.query_balance(tranid, account_type)


    def find_most_recent_entry(entries, portfolio, investment, lotid, tax_date, ls, location, financial_account):
        """
        Find the most recent entry in the list of entries that matches the given parameters.

        Args:
            entries (list): List of journal entry objects.
            portfolio (str): The portfolio identifier.
            investment (str): The investment identifier.
            lotid (str): The lot identifier.
            tax_date (str): The tax date.
            ls (str): The LS (long/short) identifier.
            location (str): The location identifier.
            financial_account (str): The financial account identifier.

        Returns:
            tuple: A tuple containing the local and book values of the most recent matching entry,
                   or (None, None) if no matching entry is found.
        """
        # Iterate over the list in reverse order to find the most recent entry
        for entry in reversed(entries):
            if (entry.portfolio == portfolio and entry.investment == investment and
                    entry.lotid == lotid and entry.ls == ls and entry.location == location and
                    entry.financial_account == financial_account):
                # Extract the local and book values
                local_value = entry.local
                book_value = entry.book

                # Print debug information
                print(
                    f"Record found: Investment: {investment}, Lot ID: {lotid}, Local Value: {local_value}, Book Value: {book_value}")

                return local_value, book_value

        # Print debug information if no record is found
        print(f"No matching record found for Investment: {investment}, Lot ID: {lotid}")

        # Return None if no matching entry is found
        return None, None

    def get_journal_value(self, portfolio, investment, lotid, tax_date, ls, location, financial_account):
        # Check if the investment sub-space exists
        if investment not in self.investment_spaces_library:
            return None

        subspace = self.investment_spaces_library[investment]

        # Retrieve the entry if it exists
        entry_key = (portfolio, investment, lotid, tax_date, ls, location, financial_account)
        if entry_key in subspace.entries:
            return subspace.entries[entry_key]
        else:
            return None

class SecurityInformationRepository:
    """
    SIR = Security Information Repository.
    - Wraps existing AIF fields (static fundamental and descriptive data).
    - Provides compatibility methods so no existing code breaks.
    - Adds empty containers for price and FX history.
    - Future temporal extensions will attach cleanly here.
    """

    def __init__(self, **aif_fields):
        # Static / fundamental fields (your original AIF)
        self.fields = dict(aif_fields)

        # Temporal containers (empty for now)
        self.price_history = []  # will be filled later
        self.fx_history = []     # will be filled later


    # Future: safe method for adding price entries
    def add_price_record(self, record):
        self.price_history.append(record)

    # Future: safe method for adding fx entries
    def add_fx_record(self, record):
        self.fx_history.append(record)

    def __repr__(self):
        return f"<SIR {self.fields}>"

class SettlementChores:

    def __init__(self):
        # Track flows by tranid
        self.flow_tracker = {}
        self.records = {}  # Manages records by transaction ID
        self.position_cache = {}  # Caching mechanism

    def reset(self):
        """
        Execution-safe reset.
        Restores SettlementChores to a pristine state.
        """
        self.__init__()

    def __iter__(self):
        # This allows the object to be iterable over its records
        return iter(self.records.values())

    def add_record(self, tranid, portfolio, investment, position, position_effect, location, currency, qty,
                   currency_amount, status):
        new_record = {
            'tranid': tranid,
            'portfolio': portfolio,
            'investment': investment,
            'position': position,
            'position_effect': position_effect,
            'location': location,
            'currency': currency,
            'qty': qty,
            'currency_amount': currency_amount,
            'status': status
        }
        self.records[tranid] = new_record
        print(f"Record for TranID {tranid} added to SMF.")

    def update_record_status(self, tranid, new_status, portfolio):
        record = self.records.get(tranid, {})
        if record and record.get('portfolio') == portfolio:
            self.records[tranid]['status'] = new_status
            print(f"Status of record {tranid} updated to {new_status}.")
        else:
            print(f"Record not found for TranID {tranid} with portfolio {portfolio}.")

    def query_records(self, portfolio, **filters):
        return [record for record in self if record.get('portfolio', '').strip().lower() == portfolio.lower() and
                all(record.get(k, '').strip().lower() == v.lower() for k, v in filters.items())]

    def calculate_net_positions(self, portfolio, investment, date, status='Settled'):
        cache_key = (portfolio, investment, date)
        if cache_key in self.position_cache:
            return self.position_cache[cache_key]

        net_positions = {}
        for record in self.query_records(portfolio, investment=investment, status=status):
            location = record['location']
            position_key = f"{record['position']}_{record['position_effect']}"
            if location not in net_positions:
                net_positions[location] = {}
            if position_key not in net_positions[location]:
                net_positions[location][position_key] = 0
            effect_multiplier = 1 if record['position_effect'] == 'open' else -1
            net_positions[location][position_key] += record['qty'] * effect_multiplier

        self.position_cache[cache_key] = net_positions
        return net_positions

    def cleanup_records(self, retention_period_days=365):
        """ Clean up records that have been fully settled and net to zero, and are older than the retention period. """
        today = datetime.now()
        keys_to_remove = []
        for tranid, record in self.records.items():
            record_date = datetime.strptime(record['settled_date'], '%Y-%m-%d')
            if (today - record_date).days > retention_period_days and self.is_fully_settled_and_netted(tranid):
                keys_to_remove.append(tranid)

        for tranid in keys_to_remove:
            del self.records[tranid]
            print(f"Record {tranid} removed from SMF due to cleanup policy.")

    def is_fully_settled_and_netted(self, tranid):
        """ Determine if a transaction is fully settled and netted to zero. """
        record = self.records[tranid]
        # Assuming there's a way to check if the position is netted to zero (simplified here)
        return record['status'] == 'Settled' and record['net_position'] == 0


class BookkeepingSpace:
    """
    BOOKKEEPING SPACE (CONDUCTOR)

    Responsibilities:
      - Event routing
      - Snapshot control
      - Query façades
      - Aggregation / assembly for reporting & appraisal

    Does NOT:
      - Own accounting truth
      - Own accounting state
      - Compute balances
    """

    def __init__(self):
        # --------------------------------------------------
        # Authoritative truth
        # --------------------------------------------------
        self.journal_entries = []

        # --------------------------------------------------
        # Core repositories (derived state)
        # --------------------------------------------------

        self.asset_liability_repository = AssetLiabilityRepository()
        self.revenue_expense_repository = RevenueExpenseCapitalRepository()
        self.stat_repo = StatisticalRepository()
        self.chores = SettlementChores()



        # --------------------------------------------------
        # Snapshot metadata
        # --------------------------------------------------
        self.snapshots = []

        # --------------------------------------------------
        # Journal sequencing
        # --------------------------------------------------
        self.sequence_counter = 0

    def reset(self):
        self.asset_liability_repository.reset()
        self.revenue_expense_repository.reset()
        self.stat_repo.reset()
        self.chores.reset()

    """
    BOOKKEEPING SPACE (CONDUCTOR)

    Responsibilities:
      - Owns authoritative JOURNALS
      - Routes events to repositories
      - Controls snapshot save / restore
      - Provides rebuild hooks for validation & audit
      - Acts as the execution surface for CPH

    Does NOT:
      - Decide what events to run
      - Schedule events
      - Perform ingestion
      - Determine accounting policy
    """



    def load_journals(self, journal_path, portfolio):
        import pickle

        if not journal_path.exists():
            return []

        with open(journal_path, "rb") as f:
            container = pickle.load(f)

        if isinstance(container, dict) and "journals" in container:
            journal_list = container["journals"]
        elif isinstance(container, list):
            journal_list = container
        else:
            raise RuntimeError(
                f"Unexpected journal container format in {journal_path}"
            )

        return [
            je for je in journal_list
            if getattr(je, "portfolio", None) == portfolio
        ]

    # ============================================================
    # SNAPSHOT METADATA
    # ============================================================

    class SnapshotRecord:
        def __init__(self, kd, state):
            self.kd = kd  # knowledge date
            self.state = state  # serialized bookkeeping state

    # ============================================================
    # SNAPSHOT SAVE
    # ============================================================

    def save_snapshot(self, knowledge_date):
        """
        Save a FULL snapshot (journals + repositories).

        This is an optimization snapshot.
        Journals remain the ultimate truth.
        """
        import copy

        snapshot_state = {
            "journal_entries": copy.deepcopy(self.journal_entries),
            "asset_liability_repository": copy.deepcopy(
                self.asset_liability_repository
            ),
            "statistical_repository": copy.deepcopy(
                self.statistical_repository
            ),
            "revenue_expense_repository": copy.deepcopy(
                self.revenue_expense_repository
            ),
            "settlement_chores": copy.deepcopy(
                self.settlement_chores
            ),
            "sequence_counter": self.sequence_counter,
        }

        snap = BookkeepingSpace.SnapshotRecord(
            kd=knowledge_date,
            state=snapshot_state
        )

        self.snapshots.append(snap)
        return snap

    # ============================================================
    # SNAPSHOT RESTORE (SNAPSHOT-FIRST)
    # ============================================================

    def restore_from_snapshot(self, snapshot_state):
        """
        Restore bookkeeping state from an authoritative snapshot.

        Rules:
          - Snapshot is trusted
          - No validation
          - No scheduling
          - No ingestion
          - Pure state replacement
        """

        if snapshot_state is None:
            raise ValueError("Snapshot state is None")

        # --------------------------------------------------
        # Restore journals
        # --------------------------------------------------
        self.journal_entries = snapshot_state["journal_entries"]

        # --------------------------------------------------
        # Restore repositories
        # --------------------------------------------------
        self.asset_liability_repository = snapshot_state[
            "asset_liability_repository"
        ]
        self.statistical_repository = snapshot_state[
            "statistical_repository"
        ]
        self.revenue_expense_repository = snapshot_state[
            "revenue_expense_repository"
        ]

        # --------------------------------------------------
        # Restore settlement chores
        # --------------------------------------------------
        self.settlement_chores = snapshot_state.get(
            "settlement_chores",
            SettlementChores()
        )

        # --------------------------------------------------
        # Restore sequencing
        # --------------------------------------------------
        self.sequence_counter = snapshot_state.get(
            "sequence_counter",
            len(self.journal_entries)
        )

        print(
            f"🔁 Snapshot restored "
            f"({len(self.journal_entries):,} journals)"
        )

    # ============================================================
    # OPTIONAL: REBUILD FROM JOURNALS (NOT ACTIVE YET)
    # ============================================================

    def rebuild_from_journals(self):
        """
        OPTIONAL / FUTURE USE

        Rebuild entire bookkeeping state from journals ONLY.

        This is the truth-anchor path used for:
          - Validation
          - Audit
          - AI analysis
          - Snapshot verification

        Not used in production execution yet.
        """
        # self.asset_liability_repository = AssetLiabilityRepository()
        # self.statistical_repository = StatisticalRepository()
        # self.revenue_expense_repository = RevenueExpenseCapitalRepository()
        # self.settlement_chores = SettlementChores()

        self.sequence_counter = 0

        for je in self.journal_entries:
            je.sequence_number = self.sequence_counter
            self.sequence_counter += 1
            je.post(self)

        print(
            f"♻️ Rebuilt from journals "
            f"({len(self.journal_entries):,} journals)"
        )

    # ============================================================
    # SNAPSHOT DELETE
    # ============================================================

    def delete_snapshot(self, snapshot):
        if snapshot in self.snapshots:
            self.snapshots.remove(snapshot)

    # ============================================================
    # FULL RESET
    # ============================================================
    def reset(self):
        """
        Execution-safe reset.
        Restores BookkeepingSpace to a pristine, runnable state.
        """
        self.__init__()

    def set_investment_attribute(self, investment, field_type, attribute, value):
        """
        Authoritative setter for investment attributes.
        """
        return self.asset_liability_repository.apply_investment_reference_data(
            investment=investment,
            field_type=field_type,
            attribute=attribute,
            value=value,
        )


    # ============================================================
    # SUBSPACE MANAGEMENT
    # ============================================================

    def create_investment_subspaces(self, candidate_investments):
        """
        Create subspaces only for held investments.
        """
        repo = self.asset_liability_repository

        for investment in candidate_investments:
            repo.get_position_space(investment)

        # Remove unheld
        unheld = [
            inv for inv in repo.investment_positions
            if inv not in candidate_investments
        ]
        for inv in unheld:
            del repo.investment_positions[inv]


    # ============================================================
    # CORE POSTING
    # ============================================================

    def post_journal_entry(self, je):

        from business_days import is_non_business_day, get_next_business_day
        from datetime import datetime

        # 1️⃣ Validate IBOR date
        if not isinstance(je.ibor_date, datetime):
            raise TypeError("Journal entry IBOR date must be datetime")

        # 2️⃣ Business-day adjustment
        if is_non_business_day(je.ibor_date):
            je.ibor_date = get_next_business_day(je.ibor_date)

        # 3️⃣ Assign canonical creation sequence (ONCE)
        if je.sequence_number is None:
            self.sequence_counter += 1
            je.sequence_number = self.sequence_counter

        # 4️⃣ PASS SCRATCHPAD ONLY (NOT AUTHORITATIVE TRUTH)
        # Lives only until the period is materialized, then flushed by space.reset().
        self.journal_entries.append(je)


        # 5️⃣ Route entry
        if je.entry_type in ("Asset/Liability", "Asset/Liability-OBS"):
            subspace = self.asset_liability_repository.get_position_space(
                je.investment
            )
            subspace.post_journal_entry_to_subspace(je)
            return

        elif je.entry_type in ("Revenue/Expense/Capital", "Revenue/Expense/Capital-OBS"):
            repo = self.revenue_expense_repository
            balance_space = repo.get_balance_space(je.investment)
            repo.post_journal_entry_to_balance_space(balance_space, je)
            return

        else:
            raise ValueError(f"Invalid entry type: {je.entry_type}")


    # ============================================================
    # GIVE FUNCTIONS — TRUTH ACCESS ONLY
    # ============================================================

    def get_attribute_field(self, investment, field_type, attribute):
        """
        LEGACY-COMPATIBLE READ ACCESSOR.

        BookkeepingSpace does NOT store semantic metadata.
        This method exists solely to preserve existing call sites.

        All reads delegate to the AssetLiabilityRepository,
        which is the authoritative metadata source.
        """

        if not hasattr(self, "asset_liability_repository"):
            raise RuntimeError(
                "BookkeepingSpace missing asset_liability_repository "
                "(cannot retrieve investment metadata)"
            )

        return self.asset_liability_repository.get_attribute_field(
            investment,
            field_type,
            attribute,
        )

    def get_position_space(self, investment):
        """
        Routing accessor.
        """
        return self.asset_liability_repository.get_position_space(investment)

    # ============================================================
    # COMBINED VIEWS (CRITICAL DOMAIN FUNCTIONS)
    # ============================================================

    def combined_assets_liabilities(self):
        """
        Flat list of all AL entries across all subspaces.
        """
        return self.asset_liability_repository.combined_assets_liabilities()


    def get_all_asset_liability_bookkeeping_info(self):
        """
        Flatten AL entries into rows for appraisal / reporting.
        """
        rows = []
        for key, values in self.combined_assets_liabilities():
            (
                portfolio, investment, lotid, tax_date,
                ls, location, financial_account
            ) = key
            quantity, local, book, notional, oface = values

            rows.append([
                portfolio, investment, lotid, tax_date,
                ls, location, financial_account,
                quantity, local, book, notional, oface
            ])

        return rows

    def get_revenue_expense_space(self):
        formatted = []
        for entry in self.revenue_expense_repository.entries:
            key = (
                entry.portfolio, entry.investment, entry.lotid, entry.tax_date,
                entry.ls, entry.location, entry.financial_account
            )
            values = (entry.quantity, entry.local, entry.book)
            formatted.append((key, values))
        return formatted


    def get_combined_space(self):
        """
        Combined AL + RE view.
        """
        return (
            self.combined_assets_liabilities()
            + self.get_revenue_expense_space()
        )


    def get_all_entries(self):
        """
        Unified AL + RE + STAT view with integrity checks.
        """

        all_entries = []

        # AL
        for inv, subspace in self.asset_liability_repository.investment_positions.items():
            for key, value in subspace.entries.items():
                all_entries.append((key, value))

        # RE
        for entry in getattr(self.revenue_expense_repository, "entries", []):
            key = (
                entry.portfolio, entry.investment, entry.lotid, entry.tax_date,
                entry.ls, entry.location, entry.financial_account
            )
            value = (entry.quantity, entry.local, entry.book)
            all_entries.append((key, value))

        # STAT
        if hasattr(self.statistical_repository, "data"):
            for key, value in self.statistical_repository.data.items():
                all_entries.append((key, value))

        return all_entries

# ============================================================
# Asset / Liability Core
# ============================================================
# This file is SELF-CONTAINED for the AL layer.
# No accounting state is stored outside AssetLiabilitySubspace.
# Repository ONLY combines subspaces.
# ============================================================

class AssetLiabilityRepository:
    """
    ASSET / LIABILITY REPOSITORY

    ROLE:
      - Portfolio-level registry of subspaces
      - Authoritative 'give me' access
      - Schema authority for semantic truth (AIFs)

    FORBIDDEN ZONE:
      - NO accounting state
      - NO balances
      - NO posting logic
      - NO derivation
    """

    def __init__(self):
        self.investment_attributes = {}
        self.investment_positions = {}


        print("🔥 AssetLiabilityRepository CONSTRUCTED")


        # ----------------------------------------------------
        # AUTHORITATIVE AIF SCHEMA
        # ----------------------------------------------------
        # This defines what AIFs are allowed to exist.
        # It is a CONTRACT, not logic.
        # ----------------------------------------------------
        self.allowed_aifs = {
            # General
            "investment",
            "ticker",
            "issuer",
            "investment_type",
            "asset_class",
            "currency",
            "is_currency",
            "country",
            "contract_size",
            "pricing_factor",
            "underlying",
            "put_call",
            "strike",
            "pricing_method",

            # Credit / bond-specific
            "index",
            "issue_date",
            "first_coupon_date",
            "day_count_convention",
            "payment_frequency",
            "next_to_last_coupon_date",
            "maturity_date",
            "coupon_rate",
            "face_value",
            "semi_split",
        }

    def reset(self):
        """
        Reset all derived, run-scoped state.
        Delegates to constructor logic.
        """
        self.__init__()

    # ========================================================
    # SUBSPACE REGISTRY
    # ========================================================

    def get_position_space(self, investment):
        if investment not in self.investment_positions:
            self.investment_positions[investment] = AssetLiabilitySubspace(investment)
        return self.investment_positions[investment]

    def get_attribute_space(self, investment):
        if investment not in self.investment_attributes:
            self.investment_attributes[investment] = AssetLiabilitySubspace(investment)
        return self.investment_attributes[investment]

    # ========================================================
    # METADATA WRITE (SCHEMA-GUARDED)
    # ========================================================

    def apply_investment_reference_data(self, investment, field_type, attribute, value):
        """
        SINGLE AUTHORITATIVE MUTATION OF INVESTMENT REFERENCE DATA
        """

        if field_type == "AIF" and attribute not in self.allowed_aifs:
            raise KeyError(f"Invalid AIF attribute: {attribute}")

        # ✅ Use the SAME subspace used for accounting state
        sub = self.get_attribute_space(investment)

        # Ensure AIF container exists
        if "AIF" not in sub.investment_attributes:
            sub.investment_attributes["AIF"] = {}

        sub.investment_attributes["AIF"][attribute] = value

    # ========================================================
    # METADATA READ (GIVE ME)
    # ========================================================

    def get_position_entries(self, investment):
        """
        Authoritative read of investment accounting entries.*
        """
        sub = self.get_position_space(investment)
        return sub.entries

    def get_attribute_field(self, investment, attribute):
        sub = self.get_attribute_space(investment)
        return sub.investment_attributes.get("AIF", {}).get(attribute)

    # ========================================================
    # AGGREGATION
    # ========================================================

    def combined_assets_liabilities(self):
        aggregated = []
        for subspace in self.investment_positions.values():
            aggregated.extend(subspace.entries.items())
        return aggregated

class AssetLiabilitySubspace:
    """
    ASSET / LIABILITY SUBSPACE

    Responsibility:
      - Store accounting STATE for a single investment
      - Maintain lot-level balances
      - Maintain derived runtime position state

    Does NOT:
      - Decide semantic truth
      - Interpret metadata across investments
      - Query other subspaces
      - Perform portfolio-level aggregation

    This is the UNIT OF SPEED.
    """

    def __init__(self, investment):
        self.investment = investment
        self.investment_attributes = {
            "AIF": {}
        }

        # ----------------------------------------------------
        # Lot-level accounting state
        # ----------------------------------------------------
        self.entries = {}

        # ----------------------------------------------------
        # Reference fields (structural investment attributes)
        # ----------------------------------------------------

        # ----------------------------------------------------
        # Derived runtime position state (per location, ls)
        # ----------------------------------------------------
        self.position_state = {}

        # Optional downstream hook
        self.statistical_repository = None


    # ========================================================
    # REFERENCE FIELD STORAGE
    # ========================================================

    # ========================================================
    # POSITION STATE ACCESS
    # ========================================================

    def get_position_state(self):
        """
        Return maintained runtime position state keyed by (location, ls).

        Returns:
            {
                (location, ls): {
                    "position_qty": float,
                    "local_cost": float,
                    "book_cost": float,
                    "notional": float
                }
            }
        """
        # Shallow copy (values are primitives)
        return {
            key: {
                "position_qty": vals["position_qty"],
                "local_cost": vals["local_cost"],
                "book_cost": vals["book_cost"],
                "notional": vals.get("notional", 0),
            }
            for key, vals in self.position_state.items()
        }


    # ========================================================
    # RESET
    # ========================================================

    def reset(self):
        """
        Fully reset accounting STATE for this investment.
        Reference fields remain intact.
        """
        self.entries.clear()
        self.position_state.clear()


    # ========================================================
    # CORE POSTING LOGIC
    # ========================================================

    def post_journal_entry_to_subspace(self, je):
        """
        Apply a journal entry to accounting state.

        This function:
          - Accumulates lot-level balances
          - Deletes collapsed lots
          - Updates derived runtime position state
        """

        key = (
            je.portfolio,
            je.investment,
            je.lotid,
            je.tax_date,
            je.ls,
            je.location,
            je.financial_account,
        )

        # ----------------------------
        # Lot-level accumulation
        # ----------------------------
        if key in self.entries:
            old_qty, old_local, old_book, old_notional, old_oface = self.entries[key]

            new_qty = old_qty + je.quantity
            new_local = old_local + je.local
            new_book = old_book + je.book
            new_notional = (old_notional or 0) + (je.notional or 0)
            new_oface = (old_oface or 0) + (je.oface or 0)

            # Auto-delete collapsed lots
            if abs(new_qty) < 0.01:
                del self.entries[key]
                return

            self.entries[key] = (
                new_qty,
                new_local,
                new_book,
                new_notional,
                new_oface,
            )
        else:
            self.entries[key] = (
                je.quantity,
                je.local,
                je.book,
                je.notional or 0,
                je.oface or 0,
            )

        # ----------------------------
        # Derived runtime position update
        # ----------------------------
        pos_key = (je.location, je.ls)

        if pos_key not in self.position_state:
            self.position_state[pos_key] = {
                "position_qty": 0,
                "local_cost": 0,
                "book_cost": 0,
                "notional": 0,
            }

        self.position_state[pos_key]["position_qty"] += je.quantity
        self.position_state[pos_key]["local_cost"] += je.local
        self.position_state[pos_key]["book_cost"] += je.book
        self.position_state[pos_key]["notional"] += je.notional or 0

        # Drop zero positions
        if abs(self.position_state[pos_key]["position_qty"]) < 0.01:
            del self.position_state[pos_key]

            if self.statistical_repository:
                self.statistical_repository.remove_stats_for(
                    investment=je.investment,
                    location=je.location,
                    ls=je.ls,
                )

class CurrencyReclassifier:
    def __init__(self, space):
        self.space = space

    def get_combined_cash_quantity(self, investment):
        account_types = ['Cost', 'Receivable', 'Payable', 'InterestReceivable', 'InterestPayable', 'AccruedInterestReceivable',
                         'AccruedInterestPayable', 'DividendsReceivable', 'DividendsPayable', 'ExpensesPayable']
        return self._get_combined_quantity(investment, account_types)

    def get_separated_cash_quantities(self, investment):
        cost_quantity = self._get_quantity(investment, 'Cost')
        receivable_quantity = self._get_quantity(investment, 'Receivable')
        payable_quantity = self._get_quantity(investment, 'Payable')
        dividends_receivable_quantity = self._get_quantity(investment, 'DividendsReceivable')
        dividends_payable_quantity = self._get_quantity(investment, 'DividendsPayable')
        accrued_interest_receivable_quantity = self._get_quantity(investment, 'AccruedInterestReceivable')
        accrued_interest_payable_quantity = self._get_quantity(investment, 'AccruedInterestPayable')
        expenses_payable_quantity = self._get_quantity(investment, 'ExpensesPayable')
        return (cost_quantity, receivable_quantity, payable_quantity, dividends_payable_quantity, dividends_receivable_quantity,
                accrued_interest_receivable_quantity, accrued_interest_payable_quantity, expenses_payable_quantity, )

    def _get_combined_quantity(self, investment, account_types):
        combined_quantity = 0
        for record in self.space.get_journal_entries():
            if record['investment'] == investment and record['financial_account'] in account_types:
                combined_quantity += record['quantity']
        return combined_quantity

    def _get_quantity(self, investment, account_type):
        quantity = 0
        for record in self.space.get_journal_entries():
            if record['investment'] == investment and record['financial_account'] == account_type:
                quantity += record['quantity']
        return quantity

    class Leg:
        def __init__(self, leg_name, notional_amount, type, quantity, local, book, notional, oface, exposure_type, investment,
                     day_count=None, accrual_rate=None, reset_date=None):
            self.leg_name = leg_name
            self.notional_amount = notional_amount
            self.type = type
            self.quantity = quantity
            self.local = local
            self.book = book
            self.notional = notional
            self.oface = oface
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
                journal.lotid,
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
    sorted_jes = sorted(jes, key=lambda je: (
    je.ibor_date, je.tranid is None, je.tranid, je.investment,  je.ls, je.location, je.financial_account))
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
    expected_keys = ['portfolio', 'investment', 'lotid', 'tax_lot', 'ls', 'location', 'financial_account', 'quantity', 'local', 'book', 'notional', 'oface']

    # Check if the entry has all the expected keys
    if not all(key in entry for key in expected_keys):
        return False

    # Check data types of the entry
    if not isinstance(entry['portfolio'], str) or \
            not isinstance(entry['investment'], str) or \
            not isinstance(entry['lotid'], str) or \
            not isinstance(entry['tax_lot'], int) or \
            not isinstance(entry['ls'], str) or \
            not isinstance(entry['location'], str) or \
            not isinstance(entry['financial_account'], str) or \
            not isinstance(entry['quantity'], int) or \
            not isinstance(entry['local'], float) or \
            not isinstance(entry['book'], float) or \
            not isinstance(entry['notional'], float) or \
            not isinstance(entry['oface'], float):
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
        rollup_data[key]["notional"] += je.notional  # Assuming 'book' is an attribute of Journals
        rollup_data[key]["oface"] += je.oface  # Assuming 'book' is an attribute of Journals

    summary_list = []
    for key, values in rollup_data.items():
        investment, account, feeder = key
        summary_list.append({
            "investment": investment,
            "account": account,
            "feeder" : feeder,
            "quantity": values["quantity"],
            "local": values["local"],
            "book": values["book"],
            "notional": values["notional"],
            "oface": values["oface"],
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

print("<<< EXIT bookkeeping.py")
