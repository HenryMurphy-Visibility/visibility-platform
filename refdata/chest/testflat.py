import pandas as pd

def tax_lot_appraisal(bookkeeping_space, edate, fname):
    # Step 1: Create the DataFrame from the list of entries
    bookkeeping_space_list = []
    for entry in bookkeeping_space:
        bookkeeping_space_list.append(entry)

    df = pd.DataFrame(bookkeeping_space_list, columns=[
        'Portfolio', 'Investment', 'Lot_Id', 'Tax_Date', 'Ls', 'Location',
        'Financial_Account', 'Quantity', 'Local', 'Book', 'Notional', 'OFace'
    ])

    print("Initial DataFrame:\n", df.head())

    # Define account links
    account_links = {
        'Cost': {
            'MarketVal': {'Local': 'MktValLocal', 'Book': 'MktValBook'},
            'PriceGL': {'Local': 'PriceGLLocal', 'Book': 'PriceGLBook'},
            'FXGL': {'Book': 'FXGLBook'}
        },
        'Payable': {
            'MarketVal': {'Local': 'MktValLocal', 'Book': 'MktValBook'},
            'PriceGL': {'Local': 'PriceGLLocal', 'Book': 'PriceGLBook'},
            'FXGL': {'Book': 'FXGLBook'}
        },
        'Receivable': {
            'MarketVal': {'Local': 'MktValLocal', 'Book': 'MktValBook'},
            'PriceGL': {'Local': 'PriceGLLocal', 'Book': 'PriceGLBook'},
            'FXGL': {'Book': 'FXGLBook'}
        },
        # Add more account links as needed
    }

    # Simplified Direct Mapping
    direct_mapped_records = []
    for entry in bookkeeping_space_list:
        portfolio, investment, lotid, tax_date, ls, location, financial_account, quantity, local, book, notional, oface = entry

        # Initialize secondary data with zero values
        secondary_data = {
            'MktValLocal': 0.0,
            'MktValBook': 0.0,
            'PriceGLLocal': 0.0,
            'PriceGLBook': 0.0,
            'FXGLBook': 0.0
        }

        # Directly map and add values
        if financial_account in account_links:
            links = account_links[financial_account]
            if 'MarketVal' in links:
                secondary_data['MktValLocal'] = local
                secondary_data['MktValBook'] = book
            if 'PriceGL' in links:
                secondary_data['PriceGLLocal'] = local
                secondary_data['PriceGLBook'] = book
            if 'FXGL' in links:
                secondary_data['FXGLBook'] = book

        # Append the mapped record
        direct_mapped_records.append({
            'Portfolio': portfolio,
            'Investment': investment,
            'Lot_ID': lotid,
            'Tax_Date': tax_date,
            'Ls': ls,
            'Location': location,
            'Financial_Account': financial_account,
            'Quantity': quantity,
            'Local': local,
            'Book': book,
            'MktValLocal': secondary_data['MktValLocal'],
            'MktValBook': secondary_data['MktValBook'],
            'PriceGLLocal': secondary_data['PriceGLLocal'],
            'PriceGLBook': secondary_data['PriceGLBook'],
            'FXGLBook': secondary_data['FXGLBook'],
        })

    # Create DataFrame from directly mapped records
    direct_mapped_df = pd.DataFrame(direct_mapped_records)

    print("Directly Mapped DataFrame:\n", direct_mapped_df.head())

    # Save the DataFrame to an Excel file for verification
    fnamechoice = f"C:/Users/hjmne/PycharmProjects/chest/reports/TaxLotHoldingsDirectMap{fname}.xlsx"
    direct_mapped_df.to_excel(fnamechoice, index=False)

    # Add title to the Excel file
    report_title = f"Tax Lot Holdings Direct Map {fname}"
    unique_portfolios = direct_mapped_df[~direct_mapped_df['Portfolio'].isin(['Subtotal', 'Grand Totals'])]['Portfolio'].unique()
    portfolio_name = unique_portfolios[0] if len(unique_portfolios) > 0 else "Unknown Portfolio"
    period_end_date = edate.strftime('%Y-%m-%d')
    full_title = f"{report_title} for {portfolio_name} ({period_end_date})"
    add_title(fnamechoice, "Sheet1", full_title)

    # Apply standard formatting to the saved Excel file
    apply_standard_formatting(fnamechoice, "Sheet1")

# Dummy functions for the example to work
def fetch_and_map_groupings(df, inv_master_path, coa_path):
    # Placeholder function
    return df

def calculate_grand_totals(df, total_columns):
    # Placeholder function
    return df

def subtotal_data(df, subtotal_columns, group_by_columns):
    # Placeholder function
    return df

def insert_subtotals(df, group_by_columns, subtotal_columns):
    # Placeholder function
    return df

def add_title(fname, sheet_name, title):
    # Placeholder function
    pass

def apply_standard_formatting(fname, sheet_name):
    # Placeholder function
    pass

# Example usage with dummy data
bookkeeping_space = [
    ['ATestPortfolio120', 'UUU', '314', pd.to_datetime('2022-01-03'), 'l', 'Goldman', 'Cost', 4900.0, 407662.076411205, 300647.7830200845, None, None],
    ['ATestPortfolio120', 'UUU', '4676', pd.to_datetime('2022-01-03'), 'l', 'Goldman', 'Cost', 67900.0, 6600820.607, 5062934.625, None, None],
    ['ATestPortfolio120', 'UUU', '327', pd.to_datetime('2022-01-03'), 'l', 'Goldman', 'Cost', 28800.0, 2604486.765, 3466623.655, None, None],
    ['ATestPortfolio120', 'UUU', '4674', pd.to_datetime('2022-01-03'), 'l', 'Goldman', 'Cost', 70400.0, 6278888.405, 5953996.232, None, None],
    ['ATestPortfolio120', 'UUU', '253', pd.to_datetime('2022-01-04'), 'l', 'Goldman', 'Cost', 34600.0, 2577815.868, 4449302.684, None, None]
]

edate = pd.to_datetime('2022-01-31')
fname = 'test'

tax_lot_appraisal(bookkeeping_space, edate, fname)
