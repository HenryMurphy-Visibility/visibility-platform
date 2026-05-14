
funds_root = "C:/Users/hjmne/PycharmProjects/chest/funds"
from load_core_defs import build_default_composite

composite = build_default_composite(funds_root)

print(composite)
print(composite.get_portfolio_names())

for p in composite.get_portfolios()[:5]:
    print(p, p.supports_calendar("Operational"))