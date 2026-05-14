from financial_information_gateway.fig_code.compute_accounting_ledger import (
    compute_accounting_ledger
)

import pandas as pd
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)

result = compute_accounting_ledger(
    portfolio="Portfolio1",
    calendar="Monthly",
    period_start="2025-11",
    period_end="2025-11",
    ppa_ibor_date=period_start_datetime
)

print(f"Valid:        {result.valid}")
print(f"Rows:         {result.metadata['row_count']}")
print(f"Journals:     {result.metadata['journal_count']}")
print(f"Elapsed:      {result.metadata['elapsed_ms']}ms")

# Show PPAs specifically
df = result.data
ppas = df[df["is_ppa"] == True]
print(f"\nPPA rows:     {len(ppas)}")
print("\n--- FULL ZTS NOVEMBER ---")
print(result.data.to_string(index=False))