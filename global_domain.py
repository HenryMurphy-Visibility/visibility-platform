
from bookkeeping import Journals
from itertools import groupby

from utilities import round_to_precision





def execute_rule_event(event, space, stat_repo, smf, sir):
    """
    Execute a single rule invocation event.
    Domain logic remains untouched.
    """
    import pandas as pd
    method = event["method"]

    portfolio  = event["portfolio"]
    investment = event["investment"]

    # Core temporal reference
    mark_date = pd.to_datetime(event["tradedate"]).to_pydatetime()

    # Optional payload
    price   = event.get("price")
    fx_rate = event.get("fx_rate")

    accrued_interest_per_100fv = event.get("accrued_interest_per_100fv", 0.0)

    # -------------------------------
    # Rule dispatch
    # -------------------------------
    if method == "mark_prices":
        mark_prices(
            portfolio,
            investment,
            mark_date,
            space,
            price,
            fx_rate,
            accrued_interest_per_100fv,
        )

    elif method == "mark_bond_accruals":
        mark_bond_accruals(
            portfolio,
            investment,
            mark_date,
            space,
            price,
            fx_rate,
            None,  # settledate (unchanged)
            accrued_interest_per_100fv,
        )

    else:
        raise ValueError(f"Unknown rule method: {method}")

# Define the lot iterator by location and long/short (ls)
def global_lot_iterator_by_location_ls(investment, space):
    lots = global_lot_iterator(investment, space)

    # Instead of sorting, iterate over lots directly grouped by ls and location
    # Assuming account_key is a tuple and location and ls are part of the account_key
    lots_sorted = sorted(lots, key=lambda x: (x[0][4], x[0][5]))  # Sorting by long/short (ls) and location

    # Group by long/short and location
    for (lot_ls, lot_location), grouped_lots in groupby(lots_sorted, key=lambda x: (x[0][4], x[0][5])):
        yield (lot_ls, lot_location), list(grouped_lots)

def global_lot_iterator(investment, space):
    # Get the entries from the investment subspace
    investment_space = space.get_position_space(investment)

    if investment_space:
        bs_entries = investment_space.entries  # Assuming 'entries' is a dictionary

        # Filter the entries based on the investment
        matching_lots = [entry for entry in bs_entries.items() if entry[0][1] == investment]

        # Extract relevant lot information (account key, lot quantity, local, and book values)
        # Assuming entry[1][0] is the lot quantity, entry[1][1] is local, and entry[1][2] is book
        return [(entry[0], entry[1][0], entry[1][1], entry[1][2], entry[1][3]) for entry in matching_lots]
    else:
        return []

def mark_prices(
    portfolio, investment, mark_date,
    space, tranid,
    mark_price, mark_fx, per_100FV_accrue, per_100FV_amort
):
    from business_days import is_non_business_day

    stat_repo = space.stat_repo
    repo = space.asset_liability_repository

    # --------------------------------------------------------------
    # 1. GET SUBSPACE (POSITION STATE ONLY)
    # --------------------------------------------------------------
    subspace = repo.get_position_space(investment)
    if subspace is None:
        print(f"⚠️ No subspace for {investment}; skipping mark.")
        return

    # --------------------------------------------------------------
    # 2. SKIP NON-BUSINESS DAYS
    # --------------------------------------------------------------
    if is_non_business_day(mark_date):
        return

    # --------------------------------------------------------------
    # 3. GET INVESTMENT ATTRIBUTES (CANONICAL LOCATION)
    # --------------------------------------------------------------
   # print("DEBUG KEYS:", list(repo.investment_attributes.keys())[:10])

    sub = repo.investment_attributes.get(investment)

    if not sub:
        raise RuntimeError(
            f"No investment attributes loaded for {investment}"
        )

    attributes = sub.investment_attributes.get("AIF", {})



    MARK_PRICE_ACCOUNTS = {"Cost",
                           "Receivable",
                           "Payable",
                           "DividendsReceivable", "DividendsPayable",
                           "AccruedInterestReceivable", "AccruedInterestPayable",
                           "SpotFXReceivable", "SpotFXPayable"
                           "SoldAccruedReceivable", "PurchasedAccruedPayable",
                           "ForwardFXReceivable", "ForwardFXPayable"}

    position_data = {}
    for key, (qty, local, book, notional, oface) in subspace.entries.items():
        (_, inv, lotid, tax_date, ls, loc, fa) = key
        if fa not in MARK_PRICE_ACCOUNTS:
            continue
        pos_key = (loc, ls)
        if pos_key not in position_data:
            position_data[pos_key] = {
                "position_qty": 0.0,
                "local_cost": 0.0,
                "book_cost": 0.0,
                "notional": 0.0,
                "oface": 0.0,
            }
        position_data[pos_key]["position_qty"] += qty
        position_data[pos_key]["local_cost"] += local
        position_data[pos_key]["book_cost"] += book
        position_data[pos_key]["notional"] += notional
        position_data[pos_key]["oface"] += oface

#    position_data = subspace.position_state

    # --------------------------------------------------------------
    # 4. PRICE / FX — FROM EVENT (NOT LOOKUP)
    # --------------------------------------------------------------
    if mark_price is None:
        raise ValueError(f"Missing mark_price for {investment} on {mark_date}")

    if mark_fx is None:
        raise ValueError(f"Missing mark_fx for {investment} on {mark_date}")

    price = mark_price
    fx_rate = mark_fx

    if price is None or fx_rate is None:
        print(f"❌ Mark missing price/FX: {investment} {mark_date}")
        return

    pricing_factor = attributes.get("pricing_factor", 1)
    contract_size = attributes.get("contract_size", 1)

    # --------------------------------------------------------------
    # 5. PROCESS EACH POSITION
    # --------------------------------------------------------------
    for (location, ls), pos_fields in position_data.items():
        process_position(
            portfolio, investment, mark_date,
            stat_repo, space,
            price, fx_rate,
            location, ls, pos_fields,
            pricing_factor,
            contract_size
        )

def process_position(portfolio, investment, mark_date, stat_repo, space,
                     price, fx_rate, location, ls, position_data, pricing_factor, contract_size):
    """
    Processes a single position during mark pricing with safe numeric conversions.
    Preserves original valuation and posting logic; eliminates float('') crashes.
    """
    from bookkeeping import Journals  # ensure available here


    # ---- Safe numeric conversion helper ----
    def safe_float(val, default=0.0):
        try:
            if val in (None, '', 'NA'):
                return default
            return float(val)
        except (TypeError, ValueError):
            return default

    # ---- Extract + normalize inputs ----
    position_qty = safe_float(position_data.get('position_qty'), 0.0)
    position_local_cost = safe_float(position_data.get('local_cost'), 0.0)
    position_book_cost  = safe_float(position_data.get('book_cost'), 0.0)
    position_notional   = safe_float(position_data.get('notional'), 0.0)

    px        = safe_float(price, 0.0)
    fx_rate_f = safe_float(fx_rate, 1.0)
    cs = safe_float(contract_size, 1.0) or 1.0
    pf = safe_float(pricing_factor, 1.0) or 1.0


    # ---- Skip if no quantity ----
    if position_qty == 0.0:
        return

    # ---- Market values (preserve your formulae) ----
    mktval_local = position_qty * px * pf * cs - position_notional
    mktval_book  = mktval_local * fx_rate_f

    # ---- Post current market value ----
    mark_value_entry = Journals(
        portfolio, investment, 0, 0, ls, location, 'MarketVal',
        position_qty, mktval_local, mktval_book, position_notional, None,
        0, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
        "Revenue/Expense/Capital"
    )
    space.post_journal_entry(mark_value_entry)

    # ---- Unrealized GL calculations (preserve original accounts/flow) ----
    price_stat_account = 'UnrealPriceGL'
    fx_stat_account    = 'UnrealFXGL'

    prev_price_local, prev_price_book, prev_unrl_notional = stat_repo.get_entry(
        None, portfolio, investment, 0, 0, price_stat_account, ls, location, stat_repo
    )
    _, prev_fx_book, _ = stat_repo.get_entry(
        None, portfolio, investment, 0, 0, fx_stat_account, ls, location, stat_repo
    )

    prev_price_local     = safe_float(prev_price_local, 0.0)
    prev_price_book      = safe_float(prev_price_book, 0.0)
    prev_fx_book         = safe_float(prev_fx_book, 0.0)
    prev_unrl_notional   = safe_float(prev_unrl_notional, 0.0)
    prev_total_gain_book = prev_price_book + prev_fx_book

    unrealized_price_local = mktval_local - position_local_cost
    unrealized_price_book  = unrealized_price_local * fx_rate_f
    unrealized_fx_book     = mktval_book - position_book_cost - unrealized_price_book
    unrealized_notional    = position_notional - prev_unrl_notional

    net_unrealized_price_local = unrealized_price_local - prev_price_local
    net_unrealized_price_book  = unrealized_price_book  - prev_price_book
    net_unrealized_fx_book     = mktval_book - position_book_cost - prev_total_gain_book - net_unrealized_price_book
    net_unrealized_notional    = unrealized_notional - prev_unrl_notional

    # ---- Store new unrealized values ----
    stat_repo.add_entry(
        None, portfolio, investment, 0, 0, 'UnrealPriceGL', ls, location, stat_repo,
        unrealized_price_local, unrealized_price_book, unrealized_notional
    )
    stat_repo.add_entry(
        None, portfolio, investment, 0, 0, 'UnrealFXGL', ls, location, stat_repo,
        0, unrealized_fx_book, 0
    )

    # ---- Post Unrealized GL journals and offsets (preserve your entries) ----
    unreal_gl_price_entry = Journals(
        portfolio, investment, 0, 0, ls, location, 'UnrealPriceGL',
        None, net_unrealized_price_local, net_unrealized_price_book, net_unrealized_notional, None,
        0, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
        "Revenue/Expense/Capital"
    )
    space.post_journal_entry(unreal_gl_price_entry)

    unreal_gl_fx_entry = Journals(
        portfolio, investment, 0, 0, ls, location, 'UnrealFXGL',
        None, 0, net_unrealized_fx_book, 0, None,
        0, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
        "Revenue/Expense/Capital"
    )
    space.post_journal_entry(unreal_gl_fx_entry)

    unreal_gl_price_entry = Journals(
        portfolio, investment, 0, 0, ls, location, 'UnrealPriceGLOffset',
        None, -net_unrealized_price_local, -net_unrealized_price_book, net_unrealized_notional, None,
        0, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
        "Revenue/Expense/Capital"
    )
    space.post_journal_entry(unreal_gl_price_entry)

    unreal_gl_fx_entry = Journals(
        portfolio, investment, 0, 0, ls, location, 'UnrealFXGLOffset',
        None, 0, -net_unrealized_fx_book, 0, None,
        0, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
        "Revenue/Expense/Capital"
    )
    space.post_journal_entry(unreal_gl_fx_entry)

def calculate_net_long_qty(self, portfolio, investment, date, status='Settled'):
    net_positions = self.calculate_net_positions(portfolio, investment, date, status)
    total = 0
    for location, positions in net_positions.items():
        total += positions.get('long_open', 0)
        total -= positions.get('long_close', 0)
        total -= positions.get('short_open', 0)
        total += positions.get('short_close', 0)
    return total

def mark_bond_accruals(portfolio, investment, mark_date,
    space, tranid, mark_price, mark_fx, per_100FV_accrue, mark_100FV_amort, smf):
    from bookkeeping import Journals
    from business_days import is_non_business_day

    # Skip non-business days
    if is_non_business_day(mark_date):
        print(f"Skipping bond marking for {investment} on {mark_date} as it is a non-business day.")
        return

    # Only process bonds
    repo = space.asset_liability_repository
    sub = repo.investment_attributes.get(investment)
    if not sub:
        return
    attributes = sub.investment_attributes.get("AIF", {})
    investment_type = attributes.get("investment_type")
    currency = attributes.get("currency")

    if investment_type != "BOND":
        return

    # ── NET SETTLED QUANTITY ──────────────────────────────────
    # Accounts for long opens, long closes, short opens, short covers
    # Zero or negative = no accrual entitlement
    net_qty = smf.calculate_net_long_qty(
        portfolio=portfolio,
        investment=investment,
        date=mark_date,
        status="Settled"
    )

    if net_qty <= 0:
        print(
            f"Net position is zero or short for portfolio {portfolio}, "
            f"investment {investment} on {mark_date}. Skipping bond mark event."
        )
        return

    # Use the accrued interest per 100 FV for bonds
    accrued_interest_per_100fv = per_100FV_accrue
    fx_rate = mark_fx

    if accrued_interest_per_100fv > 0:
        # Iterate through lots for this investment
        lots_grouped = global_lot_iterator_by_location_ls(investment, space)

        for (lot_ls, lot_location), lots in lots_grouped:
            for lot_info in lots:
                account_key, lot_qty, lot_local, lot_book, lot_notional = lot_info

                # Calculate accrued interest for this lot
                accrued_interest_local = lot_qty * accrued_interest_per_100fv
                accrued_interest_book  = accrued_interest_local * float(fx_rate)

                # AccruedInterestReceivable
                space.post_journal_entry(Journals(
                    portfolio, currency, 0, None, lot_ls, lot_location,
                    'AccruedInterestReceivable',
                    accrued_interest_local, accrued_interest_local, accrued_interest_book,
                    None, None, tranid, "BondAccrual",
                    mark_date, mark_date, mark_date, mark_date, mark_date,
                    "Asset/Liability"
                ))

                # InterestIncome
                space.post_journal_entry(Journals(
                    portfolio, investment, 0, 0, lot_ls, lot_location,
                    'InterestIncome',
                    0, -accrued_interest_local, -accrued_interest_book,
                    None, None, tranid, "BondAccrual",
                    mark_date, mark_date, mark_date, mark_date, mark_date,
                    "Revenue/Expense/Capital"
                ))

    print(f"Bond accruals processed for portfolio {portfolio}, investment {investment} on {mark_date}.")
def allocate(portfolio,  investment, location, quantity, local, book, fund_structures_space_journal_entries,
            tranid, transaction, tradedate, settledate, kdbegin, kdend, period_start,
            period_cutoff, investment_accounting_space, fund_structures_space, allocation_entities, allocation_currency, allocation_percents):
    print(id(investment_accounting_space.journal_entries))
    print(id(fund_structures_space.journal_entries))

    # Splitting the allocation entities and percentages
    entities = allocation_entities.split(',')
    currency = allocation_currency.split(',')
    percents = [float(p) for p in allocation_percents.split(',')]

    # Ensure entities and percentages match in length
    if len(entities) != len(currency) != len(percents):
        raise ValueError("Mismatch in number of allocation entities and percentages")

    # 1) Fetch all journal entries from investment_accounting_space
    # Make a copy to avoid conflict in spaces

    import copy
    journal_entries_copy = copy.deepcopy(investment_accounting_space.journal_entries)
    manager = bookkeeping.SpaceManager()

    investment_accounting_space.journal_entries.clear()
    investment_accounting_space.asset_liability_entries.clear()
    investment_accounting_space.revenue_expense_entries.clear()
    investment_accounting_space.journal_entries.clear()



    for entry in journal_entries_copy:
        ibor_date = entry.tradedate
        portfolio = entry.portfolio
        investment = entry.investment
        financial_account = entry.financial_account
        quantity = entry.quantity
        local_amount = entry.local
        book_amount = entry.book
        tranid = entry.tranid
        transaction = entry.transaction
        tradedate = entry.tradedate
        settledate = entry.settledate
        kdend = entry.kdend
        entry_type = entry.entry_type
        ls = entry.ls
        tax_date = entry.tax_date
        feeder = entry.feeder


        handled = False  # Add this flag

        # Determine allocation based on feeder
        if entry.feeder and entry.feeder in entities:
            entity_alloc = entry.feeder
            allocated_quantity = quantity
            allocated_local = local_amount
            allocated_book = book_amount

            if feeder == "":
                feeder = entity_alloc

            je = Journals(entity_alloc, investment, tax_date, ls, portfolio, financial_account,
                              allocated_quantity, allocated_local, allocated_book, tranid, transaction, tradedate,
                              settledate, ibor_date, kdend, ibor_date, entry_type, feeder)

            # Add the Journals to fund_structures_space's journal entries
            fund_structures_space.post_journal_entry(je)
            handled = True  # Mark it as handled

        if not handled:  # Only continue if it hasn't been handled already
            # General allocation logic
            for entity_alloc, currency_item, percent in zip(entities, currency, percents):
                allocated_quantity = quantity * (percent / 100)
                allocated_local = local_amount * (percent / 100)
                allocated_book = book_amount * (percent / 100)

                if allocated_local == 0 and allocated_book == 0:
                    continue

                je = Journals(entity_alloc, investment, tax_date, ls, portfolio, financial_account,
                                  allocated_quantity, allocated_local, allocated_book, tranid, transaction, tradedate,
                                  settledate, ibor_date, kdend, ibor_date, entry_type, feeder)

                # Log details of the journal entry
                print(f"Posting entry to fund_structures_space:")
                print(
                    f"Entity: {entity_alloc}, Investment: {investment}, Trade Date: {tradedate}, Transaction: {transaction}")
                # ... Add more details as required ...

                # Add the Journals to fund_structures_space's journal entries
                fund_structures_space.post_journal_entry(je)

    investment_accounting_space.journal_entries = journal_entries_copy
