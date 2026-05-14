
def generate_insights(df, top_n=5):
    insights = {}

    # Top dollar contributors
    top_dollar = df.sort_values('Dollar_Contribution', ascending=False).head(top_n)
    insights['Top_Dollar_Contributors'] = top_dollar[['investment', 'Dollar_Contribution']]

    # Top BPS contributors
    top_bps = df.sort_values('BPS_Contribution', ascending=False).head(top_n)
    insights['Top_BPS_Contributors'] = top_bps[['investment', 'BPS_Contribution']]

    # Anomalies
    if 'Anomaly' in df.columns:
        anomalies = df[df['Anomaly']]
        insights['Flagged_Anomalies'] = anomalies[['investment', 'BookToDate_Percent', 'BMV_Book']]

    return insights
