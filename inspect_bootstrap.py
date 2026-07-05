# test_bootstrap.py
from process_portfolio import bootstrap_portfolio

result = bootstrap_portfolio("Portfolio1", force=True)
print(f"\nCandidates: {result['investment_count']}")
print(f"Bonds:      {result['bond_count']}")
print(f"Currencies: {sorted(result['currencies'])}")

from process_portfolio import bootstrap_portfolio, run_all_periods

# Bootstrap first
result = bootstrap_portfolio("Portfolio1")
print(f"Candidates: {result['investment_count']}")

# Run a single period
metrics = run_all_periods(
    portfolio="Portfolio1",
    calendar="Monthly",
    period_name="2021-01"
)

for m in metrics:
    print(f"\nPeriod:    {m.get('period_name')}")
    print(f"Regular:   {m.get('regular_journal_entries')}")
    print(f"Adjusting: {m.get('adjusting_journal_entries')}")
    print(f"Time:      {m.get('total_time'):.3f}s")