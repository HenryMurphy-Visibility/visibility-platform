# -------------------------------------------------------------
# introspect_domain_functions.py
# -------------------------------------------------------------
# Purpose:
#   Utility to introspect callable domain functions across all
#   domain modules used by the EventScheduler.
#
#   Produces two lists:
#     1. domain_function_names  → real functions callable by scheduler
#     2. normalized_step_names  → derived step-friendly labels
#
# Usage:
#   from introspect_domain_functions import list_domain_functions
#   list_domain_functions()
#
# -------------------------------------------------------------

import inspect
import sys

# Import your domain modules here.
# Adjust these imports as needed to match your actual structure.
import equity_domain
import bond_domain
import currency_domain
import swaps_domain
import futures_domain


def list_domain_functions():
    """Introspect and list callable domain functions across all domain modules."""
    modules = {
        "equity_domain": equity_domain,
        "bond_domain": bond_domain,
        "currency_domain": currency_domain,
        "swaps_domain": swaps_domain,
        "futures_domain": futures_domain
    }

    domain_function_names = []
    normalized_step_names = []

    print("🔍 Scanning domain modules...\n")

    for module_name, module in modules.items():
        print(f"📘 {module_name}")
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            # Skip private or imported functions
            if name.startswith("_"):
                continue

            # Full qualified name (e.g. currency_domain.open_payable)
            fq_name = f"{module_name}.{name}"
            domain_function_names.append(fq_name)

            # Derive step-friendly label (UPPERCASE + underscores)
            step_name = name.upper()
            normalized_step_names.append(step_name)

            print(f"   • {name}")

        print()

    print("✅ Scan complete.")
    print(f"Total domain functions found: {len(domain_function_names)}\n")

    print("🧩 Example STEP names:")
    for s in sorted(set(normalized_step_names))[:20]:
        print(f"   {s}")

    # Return lists in case you want to use them programmatically
    return domain_function_names, normalized_step_names


if __name__ == "__main__":
    list_domain_functions()
