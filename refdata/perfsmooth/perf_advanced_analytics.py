
def add_var_analysis(df, level, window=30, factor=2):
    df['Rolling_Std'] = df.groupby(level)['BookToDate_Percent'].transform(
        lambda x: x.rolling(window=window).std()
    )
    df['VaR'] = df['Rolling_Std'] * factor
    df['Return_to_VaR'] = df['BookToDate_Percent'] / df['VaR'].replace(0, 1)
    return df

def flag_anomalies(df, threshold=100, min_value=1000):
    df['Anomaly'] = (
        (df['BookToDate_Percent'].abs() > threshold) &
        (df['BMV_Book'] < min_value)
    )
    return df
