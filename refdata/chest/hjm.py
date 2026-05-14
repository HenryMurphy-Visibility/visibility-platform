import equity_domain
from bookkeeping import Journals
from kivygui import ld

def mark_event(portfolio, investment, mark_date, stat_repo, sub_ledger, price, fx_rate):
    stat_repo.clear()

    # Fetch the subspace for the given investment
    investment_space = sub_ledger.get_position_space(investment)

    currency = sub_ledger.get_attribute_field(investment, 'AIF', 'Currency')
    is_currency = sub_ledger.get_attribute_field(investment, 'AIF', 'IsCurrency')

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

        # Set the market value mark date
        mv_mark_date = mark_date.replace(hour=23, minute=59, second=59)

        # Store the market value directly in the statistical repository at the lot level
        stat_repo.add_entry(mv_mark_date, lot_portfolio, lot_investment, lot_lotid, lot_tax_date, 'MarketVal', mktval_local, mktval_book)

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

    # Aggregate values by key (investment, ls, location) ignoring lotid and tax_date
    for lot_info in lots_returned:
        account_key, lot_qty, lot_local, lot_book = lot_info
        mktval_local = lot_qty * float(price)
        mktval_book = mktval_local * float(fx_rate)
        lot_portfolio = account_key[0]
        lot_investment = account_key[1]
        lot_ls = account_key[4]
        lot_location = account_key[5]

        # Use aggregate key
        agg_key = (lot_portfolio, lot_investment, lot_ls, lot_location)
        if agg_key not in aggregated_values:
            aggregated_values[agg_key] = {'local_value': 0, 'book_value': 0}

        aggregated_values[agg_key]['local_value'] += mktval_local
        aggregated_values[agg_key]['book_value'] += mktval_book

    # Post Unrealized GL and UnearnedIncome using aggregated values
    for (agg_portfolio, agg_investment, agg_ls, agg_location), values in aggregated_values.items():
        agg_local_value = values['local_value']
        agg_book_value = values['book_value']

        # Retrieve previous unrealized GL values including ls and location
        previous_unrealized_price_local, previous_unrealized_price_book = stat_repo.get_entry(None, agg_portfolio, agg_investment, 0, 0, 'UnrealGLPrice', agg_ls, agg_location)
        _, previous_unrealized_fx_book = stat_repo.get_entry(None, agg_portfolio, agg_investment, 0, 0, 'UnrealGLFX', agg_ls, agg_location)

        # Initialize if no previous values found
        if previous_unrealized_price_local is None:
            previous_unrealized_price_local = 0
        if previous_unrealized_price_book is None:
            previous_unrealized_price_book = 0
        if previous_unrealized_fx_book is None:
            previous_unrealized_fx_book = 0

        # Calculate the new Unrealized GL values
        unrealized_price_local = agg_local_value - previous_unrealized_price_local
        unrealized_price_book = unrealized_price_local * fx_rate
        unrealized_fx_gain_book = agg_book_value - previous_unrealized_fx_book - unrealized_price_book

        # Calculate net change in Unrealized GL
        net_unrealized_price_local = unrealized_price_local - previous_unrealized_price_local
        net_unrealized_price_book = unrealized_price_book - previous_unrealized_price_book
        net_unrealized_fx_gain_book = unrealized_fx_gain_book - previous_unrealized_fx_book

        # Post the UnrealGLPrice journal entry to sub_ledger (as Asset/Liability)
        unreal_gl_price_entry = Journals(
            agg_portfolio, agg_investment, 0, 0, agg_ls, agg_location, 'UnrealGLPrice',
            None, net_unrealized_price_local, net_unrealized_price_book, None, None,
            0, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
            "Asset/Liability"
        )
        sub_ledger.post_journal_entry(unreal_gl_price_entry)

        # Post the UnrealGLFX journal entry to sub_ledger (as Asset/Liability)
        unreal_gl_fx_entry = Journals(
            agg_portfolio, agg_investment, 0, 0, agg_ls, agg_location, 'UnrealGLFX',
            None, 0, net_unrealized_fx_gain_book, None, None,
            0, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
            "Asset/Liability"
        )
        sub_ledger.post_journal_entry(unreal_gl_fx_entry)

        # Offset Unrealized GL with UnearnedIncome
        unearned_income_local = -net_unrealized_price_local
        unearned_income_book = -(net_unrealized_price_book + net_unrealized_fx_gain_book)

        unearned_income_entry = Journals(
            agg_portfolio, agg_investment, 0, 0, agg_ls, agg_location, 'UnearnedIncome',
            None, unearned_income_local, unearned_income_book, None, None,
            0, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
            "Revenue/Expense/Capital"
        )
        sub_ledger.post_journal_entry(unearned_income_entry)
