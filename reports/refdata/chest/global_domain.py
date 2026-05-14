import equity_domain
from bookkeeping import Journals
import equity_domain
from bookkeeping import Journals

def mark_event(portfolio, investment, mark_date, stat_repo, sub_ledger, price, fx_rate):
    from bookkeeping import Journals
    aggregated_values = {}
    # Fetch the subspace for the given investment
    investment_space = sub_ledger.get_position_space(investment)
    currency = sub_ledger.get_information_field(investment, 'AIF', 'Currency')
    is_currency = sub_ledger.get_information_field(investment, 'AIF', 'IsCurrency')

    # Ensure currencies are priced at 1
    if is_currency:
        price = 1

    # Check if the subspace is valid and contains entries
    if not investment_space or not currency:
        print(f"No subspace found or subspace is empty for investment {investment}")
        return

    # First Loop: Compute and post Market Values at the tax lot level
    lots_returned = equity_domain.lot_iterator(investment, sub_ledger)
    for lot_info in lots_returned:
        account_key, lot_qty, lot_local, lot_book = lot_info
        mktval_local = lot_qty * float(price)
        mktval_book = mktval_local * float(fx_rate)
        lot_portfolio = account_key[0]
        lot_investment = account_key[1]
        lot_lotid = account_key[2]
        lot_tax_date = account_key[3]
        lot_ls = account_key[4]
        lot_location = account_key[5]

        # Post the MarketVal journal entry to sub_ledger at the tax lot level
        mark_value_entry = Journals(
            lot_portfolio, lot_investment, lot_lotid, lot_tax_date, lot_ls, lot_location, 'MarketVal',
            lot_qty, mktval_local, mktval_book, None, None,
            lot_lotid, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
            "Revenue/Expense/Capital"
        )
        sub_ledger.post_journal_entry(mark_value_entry)

    # Second Loop: Aggregate and post Unrealized GL entries
    aggregated_values = {}

    # Aggregate values by key (investment, ls, location, financial_account) ignoring lotid and tax_date
    for lot_info in lots_returned:
        account_key, lot_qty, lot_local, lot_book = lot_info  # Ensure cost basis is correctly included
        mktval_local = lot_qty * float(price)
        mktval_book = mktval_local * float(fx_rate)
        lot_portfolio = account_key[0]
        lot_investment = account_key[1]
        lot_ls = account_key[4]
        lot_location = account_key[5]

        # Define the financial account names for statistical accounts
        price_stat_account = 'UnrealPriceGL'
        fx_stat_account = 'UnrealFXGL'

        # Set keys for price and FX unrealized gain/loss
        price_key = (lot_portfolio, lot_investment, lot_ls, lot_location, price_stat_account)
        fx_key = (lot_portfolio, lot_investment, lot_ls, lot_location, fx_stat_account)

        # Initialize aggregation dictionaries if not already present
        if price_key not in aggregated_values:
            aggregated_values[price_key] = {'local_value': 0, 'book_value': 0, 'local_cost': 0, 'book_cost': 0}

        aggregated_values[price_key]['local_value'] += mktval_local
        aggregated_values[price_key]['book_value'] += mktval_book
        aggregated_values[price_key]['local_cost'] += lot_local
        aggregated_values[price_key]['book_cost'] += lot_book

    # Post aggregated Unrealized GL entries
    for (agg_portfolio, agg_investment, agg_ls, agg_location, stat_account_name), agg_values in aggregated_values.items():
        agg_local_value = agg_values['local_value']
        agg_book_value = agg_values['book_value']
        agg_local_cost = agg_values['local_cost']
        agg_book_cost = agg_values['book_cost']

        # Retrieve previous unrealized GL values using explicit names for statistical accounts
        print(f"Getting entry from stat_repo for: Portfolio={agg_portfolio}, Investment={agg_investment}, "
              f"LS={agg_ls}, Location={agg_location}, Account=UnrealPriceGL")
        previous_unrealized_price_local, previous_unrealized_price_book = stat_repo.get_entry(
            None, agg_portfolio, agg_investment, 0, 0, 'UnrealPriceGL', agg_ls, agg_location, stat_repo
        )
        print(f"Retrieved values: Local={previous_unrealized_price_local}, Book={previous_unrealized_price_book}")

        print(f"Getting entry from stat_repo for: Portfolio={agg_portfolio}, Investment={agg_investment}, "
              f"LS={agg_ls}, Location={agg_location}, Account=UnrealFXGL")
        _, previous_unrealized_fx_book = stat_repo.get_entry(
            None, agg_portfolio, agg_investment, 0, 0, 'UnrealFXGL', agg_ls, agg_location, stat_repo
        )
        print(f"Retrieved values: Book={previous_unrealized_fx_book}")

        # Initialize values if None
        previous_unrealized_price_local = previous_unrealized_price_local or 0
        previous_unrealized_price_book = previous_unrealized_price_book or 0
        previous_unrealized_fx_book = previous_unrealized_fx_book or 0
        previous_total_gain_book = previous_unrealized_price_book + previous_unrealized_fx_book

        # Correct calculation for Unrealized GL values
        unrealized_price_local = agg_local_value - agg_local_cost
        unrealized_price_book = unrealized_price_local * fx_rate
        unrealized_fx_book = agg_book_value - agg_book_cost - unrealized_price_book

        # Calculate the net change in Unrealized GL
        net_unrealized_price_local = unrealized_price_local - previous_unrealized_price_local
        net_unrealized_price_book = unrealized_price_book - previous_unrealized_price_book
        net_unrealized_fx_book = agg_book_value - agg_book_cost - previous_total_gain_book - net_unrealized_price_book

        # Calculate the net change in Unrealized FX GL
        # Based on the structure of unrealized_fx_book, calculate the net change using the same logic
        # net_unrealized_fx_book = (agg_book_value - agg_book_cost) - (
        #             previous_unrealized_price_book + previous_unrealized_fx_book)
        # Explanation: Current book gain less previous gains sums up the net unrealized FX impact

        # Store the new unrealized values in the statistical repository
        print(f"Adding entry to stat_repo for UnrealPriceGL: Portfolio={agg_portfolio}, Investment={agg_investment}, "
              f"LS={agg_ls}, Location={agg_location}, Local={unrealized_price_local}, Book={unrealized_price_book}")
        stat_repo.add_entry(
            None, agg_portfolio, agg_investment, 0, 0, 'UnrealPriceGL', agg_ls, agg_location, stat_repo, unrealized_price_local, unrealized_price_book
        )

        print(f"Adding entry to stat_repo for UnrealFXGL: Portfolio={agg_portfolio}, Investment={agg_investment}, "
              f"LS={agg_ls}, Location={agg_location}, Book={unrealized_fx_book}")
        stat_repo.add_entry(
            None, agg_portfolio, agg_investment, 0, 0, 'UnrealFXGL', agg_ls, agg_location, stat_repo, 0, unrealized_fx_book
        )

        # Post the UnrealGLPrice journal entry to sub_ledger
        unreal_gl_price_entry = Journals(
            agg_portfolio, agg_investment, 0, 0, agg_ls, agg_location, 'UnrealPriceGL',
            None, net_unrealized_price_local, net_unrealized_price_book, None, None,
            0, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
            "Revenue/Expense/Capital"
        )
        sub_ledger.post_journal_entry(unreal_gl_price_entry)

        # Post the UnrealGLFX journal entry to sub_ledger
        unreal_gl_fx_entry = Journals(
            agg_portfolio, agg_investment, 0, 0, agg_ls, agg_location, 'UnrealFXGL',
            None, 0, net_unrealized_fx_book, None, None,
            0, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
            "Revenue/Expense/Capital"
        )
        sub_ledger.post_journal_entry(unreal_gl_fx_entry)

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
