# ============================================================
# ============================================================
# Visibility — Compute Function Registry
# compute_registry.py
#
# This is the master menu of all available compute functions.
# The GWI cockpit loader calls functions by name from here.
# The API exposes every registered function as an endpoint.
# Adding a new compute function requires:
#   1. Implement the function in its module
#   2. Import it here
#   3. Add it to COMPUTE_REGISTRY
#   Nothing else needs to change.
# ============================================================

from financial_information_gateway.fig_code.compute_accounting_ledger import (
    compute_accounting_ledger
)

# Performance and other premium modules will be added here
# as they are migrated into fig_code
# from financial_information_gateway.fig_code.compute_performance import (
#     compute_performance
# )

from financial_information_gateway.fig_code.compute_appraisal import (
    compute_appraisal
)

from financial_information_gateway.fig_code.compute_position_ledger import (
    compute_position_ledger
)
from financial_information_gateway.fig_code.compute_performance import compute_performance
from financial_information_gateway.fig_code.compute_balance_sheet import compute_balance_sheet
from financial_information_gateway.fig_code.compute_capital import compute_capital
from financial_information_gateway.fig_code.compute_income import compute_income
from financial_information_gateway.fig_code.compute_unrealized import compute_unrealized
from financial_information_gateway.fig_code.compute_recon import compute_recon
from financial_information_gateway.fig_code.compute_cost_basis import compute_cost_basis

COMPUTE_REGISTRY = {
    "compute_accounting_ledger": compute_accounting_ledger,
    "compute_appraisal": compute_appraisal,
    "compute_position_ledger": compute_position_ledger,
    "compute_performance": compute_performance,
    "compute_capital": compute_capital,
    "compute_balance_sheet": compute_balance_sheet,
    "compute_income": compute_income,
    "compute_unrealized": compute_unrealized,
    "compute_recon": compute_recon,
    "compute_cost_basis": compute_cost_basis,

}

def get_compute_function(name: str):
    """
    Resolve a compute function by name.
    Returns the function if found, raises ValueError if not.
    """
    if name not in COMPUTE_REGISTRY:
        raise ValueError(
            f"Unknown compute function: '{name}'. "
            f"Available: {list(COMPUTE_REGISTRY.keys())}"
        )
    return COMPUTE_REGISTRY[name]


def list_compute_functions():
    """
    Returns a list of all registered compute function names.
    Used by the /registry API endpoint.
    """
    return [
        {
            "name": name,
            "module": func.__module__,
            "doc": func.__doc__.strip().split("\n")[0]
                   if func.__doc__ else ""
        }
        for name, func in COMPUTE_REGISTRY.items()
    ]