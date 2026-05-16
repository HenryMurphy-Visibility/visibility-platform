# inspect_process.py
from process_portfolio import bootstrap_portfolio, run_all_periods

# Test bootstrap — skips if already built
result = bootstrap_portfolio("Portfolio1")
print(f"Bootstrap: {result['investment_count']} investments")



# Test single period
metrics = run_all_periods("Portfolio1", "Monthly", "2021-01")
for m in metrics:
    print(f"Period: {m.get('period_name')} | "
          f"JEs: {m.get('regular_journal_entries')} | "
          f"Time: {m.get('total_time'):.3f}s")


# Test cache pass
metrics = run_all_periods("Portfolio1", "Monthly", "2021-01")
for m in metrics:
    print(f"Period: {m.get('period_name')} | "
          f"JEs: {m.get('regular_journal_entries')} | "
          f"Time: {m.get('total_time'):.3f}s")