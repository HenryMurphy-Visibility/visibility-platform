
def notional_based(df):
    if 'Notional' in df.columns and 'Income_Book' in df.columns:
        df['BookToDate_Percent_Smoothed'] = (df['Income_Book'] / df['Notional']) * 100
    return df

def cap_fx_spikes(df, threshold=100):
    condition = (df['Asset_Class'] == 'Cash') & (df['BookToDate_Percent'].abs() > threshold)
    df.loc[condition, 'BookToDate_Percent_Smoothed'] = 0
    return df

def min_value_override(df, min_amt=100):
    too_small = (df['EMV_Book'].abs() < min_amt) | (df['BMV_Book'].abs() < min_amt)
    df.loc[too_small, 'BookToDate_Percent_Smoothed'] = 0
    return df

def apply_manual_overrides(df, override_path="override_return.csv"):
    import pandas as pd
    try:
        overrides = pd.read_csv(override_path, parse_dates=['ibor_date'])
        df = pd.merge(df, overrides, on=['investment', 'ibor_date'], how='left')
        df['BookToDate_Percent_Smoothed'] = df['override_ror'].combine_first(df['BookToDate_Percent_Smoothed'])
        df.drop(columns=['override_ror'], inplace=True)
    except FileNotFoundError:
        print("🔍 No overrides file found — skipping.")
    return df

SMOOTHING_RULES = {
    'notional_based': notional_based,
    'cap_fx_spikes': cap_fx_spikes,
    'min_value_override': min_value_override,
    'manual_override': apply_manual_overrides
}
