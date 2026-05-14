import pandas as pd

# Define sample journal entries
sample_journal_entries = [
    # Lot opened today (no previous entries)
    {'portfolio': 'Portfolio1', 'transaction': 'T1', 'investment': 'Inv1', 'ibor_date': '2024-01-01',
     'tradedate': '2024-01-01', 'settledate': '2024-01-01', 'lotid': 'L1', 'tranid': 'TR1', 'tax_date': '2024-01-01',
     'ls': 'L', 'location': 'Loc1', 'financial_account': 'Cost', 'quantity': 100, 'local': 1000, 'book': 1000,
     'notional': 1000, 'oface': 1000},
    {'portfolio': 'Portfolio1', 'transaction': 'T2', 'investment': 'Inv1', 'ibor_date': '2024-01-02',
     'tradedate': '2024-01-02', 'settledate': '2024-01-02', 'lotid': 'L1', 'tranid': 'TR2', 'tax_date': '2024-01-02',
     'ls': 'L', 'location': 'Loc1', 'financial_account': 'MarketVal', 'quantity': 100, 'local': 1100, 'book': 1100,
     'notional': 1100, 'oface': 1100},
    {'portfolio': 'Portfolio1', 'transaction': 'T3', 'investment': 'Inv1', 'ibor_date': '2024-01-03',
     'tradedate': '2024-01-03', 'settledate': '2024-01-03', 'lotid': 'L1', 'tranid': 'TR3', 'tax_date': '2024-01-03',
     'ls': 'L', 'location': 'Loc1', 'financial_account': 'MarketVal', 'quantity': 0, 'local': 1200, 'book': 1200,
     'notional': 1200, 'oface': 1200},

    # Lot entirely disposed of today
    {'portfolio': 'Portfolio1', 'transaction': 'T4', 'investment': 'Inv2', 'ibor_date': '2024-01-02',
     'tradedate': '2024-01-02', 'settledate': '2024-01-02', 'lotid': 'L2', 'tranid': 'TR4', 'tax_date': '2024-01-02',
     'ls': 'L', 'location': 'Loc1', 'financial_account': 'Cost', 'quantity': 50, 'local': 500, 'book': 500,
     'notional': 500, 'oface': 500},
    {'portfolio': 'Portfolio1', 'transaction': 'T5', 'investment': 'Inv2', 'ibor_date': '2024-01-02',
     'tradedate': '2024-01-02', 'settledate': '2024-01-02', 'lotid': 'L2', 'tranid': 'TR5', 'tax_date': '2024-01-02',
     'ls': 'L', 'location': 'Loc1', 'financial_account': 'MarketVal', 'quantity': 0, 'local': 0, 'book': 0,
     'notional': 0, 'oface': 0},
]

# Convert the sample data to a DataFrame
df = pd.DataFrame(sample_journal_entries)


# Define the function to flatten market value and cost entries
def flatten_entries(df):
    # Separate Cost and MarketVal entries
    cost_entries = df[df['financial_account'] == 'Cost']
    market_val_entries = df[df['financial_account'] == 'MarketVal']

    # Merge Cost and MarketVal entries on common columns
    flattened_df = pd.merge(
        market_val_entries,
        cost_entries,
        on=['portfolio', 'investment', 'lotid', 'ls', 'location'],
        suffixes=('_marketval', '_cost')
    )

    return flattened_df


# Define the function to calculate changes in unrealized gains
def calculate_unrealized_gains(flattened_df):
    # Initialize columns for UnrealGLPrice and UnrealGLPriceChange
    flattened_df['UnrealGLPrice'] = flattened_df['book_marketval'] - flattened_df['book_cost']
    flattened_df['UnrealGLPriceChange'] = flattened_df['UnrealGLPrice'].diff().fillna(flattened_df['UnrealGLPrice'])

    # Handle the case where positions are closed
    for idx, row in flattened_df.iterrows():
        if row['quantity_marketval'] == 0:
            previous_idx = idx - 1
            if previous_idx >= 0:
                flattened_df.at[idx, 'UnrealGLPriceChange'] = -flattened_df.at[previous_idx, 'UnrealGLPrice']

    return flattened_df


# Flatten the entries
flattened_df = flatten_entries(df)
print("Flattened DataFrame:\n", flattened_df)

# Calculate unrealized gains
flattened_df = calculate_unrealized_gains(flattened_df)
print("Flattened DataFrame with Unrealized Gains:\n", flattened_df)

# Print the final DataFrame with Unrealized Gains
final_df = flattened_df[
    ['portfolio', 'investment', 'lotid', 'tranid_marketval', 'ibor_date_marketval', 'book_marketval', 'book_cost',
     'UnrealGLPrice', 'UnrealGLPriceChange']]
final_df = final_df.rename(
    columns={'ibor_date_marketval': 'ibor_date', 'book_marketval': 'market_value', 'book_cost': 'cost',
             'tranid_marketval': 'tranid'})
print("Final DataFrame:\n", final_df)
