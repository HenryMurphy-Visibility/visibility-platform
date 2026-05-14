from financial_information_gateway.fig_code.compute_appraisal import (
    compute_appraisal
)

result = compute_appraisal(
    portfolio="Portfolio1",
    calendar="Monthly",
    period_start="2025-12",
    period_end="2025-12",
    mode="period_close",
    uber_filter={"investment": "AAPL"}
)

print(f"Valid:        {result.valid}")
print(f"Mode:         {result.metadata['mode']}")
print(f"Investments:  {result.metadata['investments']}")
print(f"Lots:         {result.metadata['detail_rows']}")
print(f"Elapsed:      {result.metadata['elapsed_ms']}ms")
print(result.data.to_string(index=False))