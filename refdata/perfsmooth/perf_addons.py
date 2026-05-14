
def dollar_contribution(df):
    df['Dollar_Contribution'] = (df['BookToDate_Percent'] / 100) * df['BMV_Book']
    return df

def bps_contribution(df, total_bmv=None):
    if total_bmv is None:
        total_bmv = df['BMV_Book'].sum()
    df['BPS_Contribution'] = (df['BookToDate_Percent'] * df['BMV_Book']) / total_bmv
    return df
