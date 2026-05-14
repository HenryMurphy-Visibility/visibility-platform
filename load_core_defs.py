import os

from bookkeeping import Portfolio, PortfolioComposite, CadenceStyle
from v_config import BASE_PATH, FUNDS_PATH, REFDATA_PATH, REPORTS_PATH, VIEWS_PATH
import re

def natural_key(s):
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', s)]

def load_portfolios_from_funds(funds_root):
    portfolios = []

    for name in os.listdir(funds_root):
        path = os.path.join(funds_root, name)

        if not os.path.isdir(path):
            continue

        # 🚫 Skip known non-portfolio folders
        if name == "Composites":
            continue

        if name.startswith("ZLIST"):
            continue

        p = Portfolio(name=name, root_path=path)
        portfolios.append(p)

    return portfolios


def build_default_composite(funds_root):
    """
    Minimal working setup:
    - One cadence style (Operational + Quarterly)
    - One composite
    - All portfolios assigned
    """

    # 1. Cadence Style
    op_qtr = CadenceStyle(
        name="OP_QTR",
        calendars=["Operational", "Quarterly"]
    )

    # 2. Composite
    composite = PortfolioComposite(
        name="DEFAULT_COMPOSITE",
        cadence_style=op_qtr
    )

    # 3. Load portfolios
    portfolios = load_portfolios_from_funds(funds_root)

    # 4. Assign
    for p in portfolios:
        composite.add_portfolio(p)

    return composite

import csv

from bookkeeping import PortfolioComposite


def load_composites_from_csv(csv_path, portfolios_by_name, cadence_styles):
    """
    Loads composites from composite_master.csv
    """

    composites = {}

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        print("FIELDNAMES:", reader.fieldnames)

        for row in reader:
            comp_name = row["composite_name"]
            cadence_name = row["cadence_style"]
            portfolio_name = row["portfolio_name"]

            # Validate cadence
            if cadence_name not in cadence_styles:
                raise ValueError(f"Unknown cadence_style '{cadence_name}'")

            cadence_style = cadence_styles[cadence_name]

            # Create composite if not exists
            if comp_name not in composites:
                composites[comp_name] = PortfolioComposite(
                    name=comp_name,
                    cadence_style=cadence_style
                )

            comp = composites[comp_name]

            # Validate portfolio exists
            if portfolio_name not in portfolios_by_name:
                raise ValueError(
                    f"Portfolio '{portfolio_name}' not found for composite '{comp_name}'"
                )

            comp.add_portfolio(portfolios_by_name[portfolio_name])

    return list(composites.values())
