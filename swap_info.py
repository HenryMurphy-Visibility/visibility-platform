import csv

rows = [
    {
        "Investment": "IRSSWAP",
        "Contract_Type": "INTEREST_RATE_SWAP",
        "Pay_Leg_Type": "Fixed",
        "Pay_Index": "",
        "Pay_Rate": "0.035",
        "Pay_Spread": "0.000",
        "Pay_Frequency": "SemiAnnual",
        "Pay_DayCount": "30/360",
        "Pay_Currency": "USD",
        "Pay_Curve_Ref": "USD_SOFR_3M",
        "Receive_Leg_Type": "Float",
        "Receive_Index": "SOFR_3M",
        "Receive_Rate": "",
        "Receive_Spread": "0.002",
        "Receive_Frequency": "Quarterly",
        "Receive_DayCount": "ACT/360",
        "Receive_Currency": "USD",
        "Receive_Curve_Ref": "USD_SOFR_3M",
        "Effective_Date": "2025-10-10",
        "Maturity_Date": "2029-10-10",
        "Notional": "10000000",
        "Business_Day_Convention": "ModifiedFollowing",
        "Reset_Lag": "2",
        "Counterparty": "GSCO",
        "Settlement_Type": "Cash",
        "Entry_Type": "OffBalanceSheet"
    },
    {
        "Investment": "EQUITYSWAP",
        "Contract_Type": "EQUITY_TOTAL_RETURN_SWAP",
        "Pay_Leg_Type": "Float",
        "Pay_Index": "SOFR_3M",
        "Pay_Rate": "",
        "Pay_Spread": "0.002",
        "Pay_Frequency": "Quarterly",
        "Pay_DayCount": "ACT/360",
        "Pay_Currency": "USD",
        "Pay_Curve_Ref": "USD_SOFR_3M",
        "Receive_Leg_Type": "EquityTotalReturn",
        "Receive_Index": "SPX",
        "Receive_Rate": "",
        "Receive_Spread": "0.000",
        "Receive_Frequency": "Quarterly",
        "Receive_DayCount": "ACT/360",
        "Receive_Currency": "USD",
        "Receive_Curve_Ref": "",
        "Effective_Date": "2025-10-10",
        "Maturity_Date": "2026-10-10",
        "Notional": "5000000",
        "Business_Day_Convention": "ModifiedFollowing",
        "Reset_Lag": "2",
        "Counterparty": "MSCO",
        "Settlement_Type": "Cash",
        "Entry_Type": "OffBalanceSheet"
    }
]

with open("C:/BASE_PATH/refdata/swap_info.csv", "w", newline='') as f:
    writer = csv.DictWriter(
        f,
        fieldnames=rows[0].keys(),
        quoting=csv.QUOTE_ALL  # 🟢 ensures all values are enclosed in quotes
    )
    writer.writeheader()
    writer.writerows(rows)

print("✅ swap_info.csv created safely with quotes around all fields")
