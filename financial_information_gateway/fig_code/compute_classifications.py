"""
compute_classifications.py
──────────────────────────────────────────────────────────────────────────────
Single source of truth for account classification in Visibility.

Every financial account maps to exactly one economic category.
Every compute function that needs to classify accounts imports from here.
Adding a new account is one line — every report picks it up automatically.

Chart of accounts is the authoritative source for account definitions.
This module translates that into Python constants for compute functions.

Five reporting categories:
  1. Cost Basis   — position accounts (AL repo)
  2. Income       — revenue and expense accounts (RE repo)
  3. Realized     — realized gain/loss on disposition (RE repo)
  4. Unrealized   — unrealized mark-to-market (RE repo)
  5. Capital      — external capital flows (RE repo)

Stat-only accounts are excluded from all reports and recon.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations


# ──────────────────────────────────────────────────────────────────────────────
# STAT-ONLY ACCOUNTS
# Excluded from all balance sheet, recon, and NAV calculations.
# These are derived measurement accounts — they do not carry
# independent economic value.
# ──────────────────────────────────────────────────────────────────────────────

STAT_ONLY_ACCOUNTS = frozenset({
    "MarketVal",            # Daily Price × Quantity — not an accumulated balance
    "MarketValRE",          # RE repo variant of MarketVal
    "UnrealPriceGLOffset",  # Cancels out UnrealPriceGL — stat only
    "UnrealFXGLOffset",     # Cancels out UnrealFXGL — stat only
    "PriceGainStatOffset",  # Legacy offset name
    "FXGainStatOffset",     # Legacy offset name
})


# ──────────────────────────────────────────────────────────────────────────────
# ECONOMIC CATEGORIES
# ──────────────────────────────────────────────────────────────────────────────

class Category:
    # ── COST BASIS (Asset / Liability repo) ──────────────────────────
    COST                = "Cost"
    RECEIVABLE          = "Receivable"
    PAYABLE             = "Payable"
    ACCRUED_INTEREST    = "AccruedInterest"

    # ── UNREALIZED (Revenue / Expense repo) ──────────────────────────
    UNREALIZED_PRICE    = "UnrealizedPrice"
    UNREALIZED_FX       = "UnrealizedFX"

    # ── STAT (excluded from all reports) ─────────────────────────────
    MARKET_VAL          = "MarketVal"

    # ── REALIZED GAINS (Revenue / Expense repo) ──────────────────────
    REALIZED_PRICE      = "RealizedPrice"
    REALIZED_FX         = "RealizedFX"

    # ── INCOME / EXPENSE (Revenue / Expense repo) ─────────────────────
    INCOME              = "Income"
    EXPENSE             = "Expense"

    # ── CAPITAL (Revenue / Expense repo) ─────────────────────────────
    CAPITAL             = "Capital"


# ──────────────────────────────────────────────────────────────────────────────
# ACCOUNT CLASSIFICATION
# Maps every financial_account to its economic category.
# Derived directly from chart of accounts.
# ──────────────────────────────────────────────────────────────────────────────

ACCOUNT_CLASSIFICATION: dict[str, str] = {

    # ── COST BASIS ────────────────────────────────────────────────────
    "Cost":                         Category.COST,

    # ── RECEIVABLES ───────────────────────────────────────────────────
    "Receivable":                   Category.RECEIVABLE,
    "DividendsReceivable":          Category.RECEIVABLE,
    "SpotFxReceivable":             Category.RECEIVABLE,
    "ForwardFxReceivable":          Category.RECEIVABLE,
    "SoldAccruedReceivable":        Category.RECEIVABLE,
    "PurchasedInterest":            Category.RECEIVABLE,
    "SoldInterest":                 Category.RECEIVABLE,
    "InterestReceivable":           Category.RECEIVABLE,
    "Expenses_Receivable":          Category.RECEIVABLE,
    "SoldAccrued":                  Category.RECEIVABLE,

    # ── PAYABLES ──────────────────────────────────────────────────────
    "Payable":                      Category.PAYABLE,
    "DividendsPayable":             Category.PAYABLE,
    "SpotFxPayable":                Category.PAYABLE,
    "ForwardFxPayable":             Category.PAYABLE,
    "PurchasedAccruedPayable":      Category.PAYABLE,
    "InterestPayable":              Category.PAYABLE,
    "ExpensesPayable":              Category.PAYABLE,
    "PurchasedAccrued":             Category.PAYABLE,

    # ── ACCRUED INTEREST ──────────────────────────────────────────────
    "AccruedInterestReceivable":    Category.ACCRUED_INTEREST,
    "AccruedInterestPayable":       Category.ACCRUED_INTEREST,

    # ── UNREALIZED ────────────────────────────────────────────────────
    "UnrealPriceGL":                Category.UNREALIZED_PRICE,
    "UnrealFXGL":                   Category.UNREALIZED_FX,

    # ── STAT ONLY (excluded from reports) ────────────────────────────
    "MarketVal":                    Category.MARKET_VAL,
    "MarketValRE":                  Category.MARKET_VAL,
    "UnrealPriceGLOffset":          Category.MARKET_VAL,
    "UnrealFXGLOffset":             Category.MARKET_VAL,
    "PriceGainStatOffset":          Category.MARKET_VAL,
    "FXGainStatOffset":             Category.MARKET_VAL,

    # ── REALIZED GAINS ────────────────────────────────────────────────
    "PriceGainInvestment":          Category.REALIZED_PRICE,
    "FXGainInvestment":             Category.REALIZED_FX,
    "FXGainCurrency":               Category.REALIZED_FX,
    "FXGainTradeSettle":            Category.REALIZED_FX,

    # ── INCOME ────────────────────────────────────────────────────────
    "DividendReceipt":              Category.INCOME,
    "InterestIncome":               Category.INCOME,
    "InterestReceipt":              Category.INCOME,
    "AccruedInterestIncome":        Category.INCOME,
    "AccruedInterestReceipt":       Category.INCOME,
    "UnearnedIncome":               Category.INCOME,
    "OptionIncome":                 Category.INCOME,
    "SoldInterestIncome":           Category.INCOME,

    # ── EXPENSE ───────────────────────────────────────────────────────
    "DividendExpense":              Category.EXPENSE,
    "InterestExpense":              Category.EXPENSE,
    "AccruedInterestExpense":       Category.EXPENSE,
    "PurchasedInterestExpense":     Category.EXPENSE,
    "OptionExpense":                Category.EXPENSE,
    "MgmtFee":                      Category.EXPENSE,
    "PerfFee":                      Category.EXPENSE,

    # ── CAPITAL FLOWS ─────────────────────────────────────────────────
    "ContributedCost":              Category.CAPITAL,
}


# ──────────────────────────────────────────────────────────────────────────────
# ACCOUNT SETS
# Pre-built frozensets for fast membership testing.
# Always derived from ACCOUNT_CLASSIFICATION — never defined independently.
# ──────────────────────────────────────────────────────────────────────────────

def _accounts_for(*categories: str) -> frozenset[str]:
    """Return frozenset of all accounts belonging to given categories."""
    return frozenset(
        acct for acct, cat in ACCOUNT_CLASSIFICATION.items()
        if cat in categories
    )


# ── FIVE REPORTING CATEGORIES ─────────────────────────────────────────────────

COST_BASIS_ACCOUNTS = _accounts_for(
    Category.COST,
    Category.RECEIVABLE,
    Category.PAYABLE,
    Category.ACCRUED_INTEREST,
)

INCOME_ACCOUNTS = _accounts_for(
    Category.INCOME,
    Category.EXPENSE,
)

EXPENSE_ACCOUNTS = _accounts_for(
    Category.EXPENSE,
)

REALIZED_ACCOUNTS = _accounts_for(
    Category.REALIZED_PRICE,
    Category.REALIZED_FX,
)

UNREALIZED_ACCOUNTS = _accounts_for(
    Category.UNREALIZED_PRICE,
    Category.UNREALIZED_FX,
)

CAPITAL_ACCOUNTS = _accounts_for(
    Category.CAPITAL,
)

# ── COMBINED SETS ─────────────────────────────────────────────────────────────

# All accounts that appear in reports (excludes stat-only)
ALL_REPORT_ACCOUNTS = (
    COST_BASIS_ACCOUNTS |
    INCOME_ACCOUNTS |
    REALIZED_ACCOUNTS |
    UNREALIZED_ACCOUNTS |
    CAPITAL_ACCOUNTS
)

# Position accounts — AL repo (cost basis layer)
POSITION_ACCOUNTS = _accounts_for(
    Category.COST,
    Category.RECEIVABLE,
    Category.PAYABLE,
    Category.ACCRUED_INTEREST,
    Category.UNREALIZED_PRICE,
    Category.UNREALIZED_FX,
)

# Revenue / Expense accounts — RE repo
REVENUE_EXPENSE_ACCOUNTS = _accounts_for(
    Category.INCOME,
    Category.EXPENSE,
    Category.REALIZED_PRICE,
    Category.REALIZED_FX,
    Category.CAPITAL,
    Category.UNREALIZED_PRICE,
    Category.UNREALIZED_FX,
)

# Cash flow accounts for TWR performance
CASH_FLOW_ACCOUNTS = _accounts_for(
    Category.CAPITAL,
    Category.COST,
    Category.RECEIVABLE,
    Category.PAYABLE,
)

# Mark price accounts — used by mark_prices() to derive position_data
MARK_PRICE_ACCOUNTS = frozenset({
    "Cost",
    "Receivable",
    "Payable",
    "SpotFxReceivable",
    "SpotFxPayable",
    "ForwardFxReceivable",
    "ForwardFxPayable",
})


# ──────────────────────────────────────────────────────────────────────────────
# BALANCE SHEET DISPLAY GROUPINGS
# For report ordering and section headers
# ──────────────────────────────────────────────────────────────────────────────

BS_GROUP_ORDER = [
    # Section          Category                      Display label
    ("Assets",         Category.COST,                "Cost Basis"),
    ("Assets",         Category.RECEIVABLE,          "Receivables"),
    ("Assets",         Category.ACCRUED_INTEREST,    "Accrued Interest"),
    ("Assets",         Category.UNREALIZED_PRICE,    "Unrealized Price Gain"),
    ("Assets",         Category.UNREALIZED_FX,       "Unrealized FX Gain"),
    ("Liabilities",    Category.PAYABLE,             "Payables"),
    ("Revenue",        Category.INCOME,              "Income"),
    ("Revenue",        Category.REALIZED_PRICE,      "Realized Price Gain"),
    ("Revenue",        Category.REALIZED_FX,         "Realized FX Gain"),
    ("Expenses",       Category.EXPENSE,             "Expenses"),
    ("Capital",        Category.CAPITAL,             "Capital Flows"),
]

BS_SECTION_ORDER = ["Assets", "Liabilities", "Revenue", "Expenses", "Capital"]


# ──────────────────────────────────────────────────────────────────────────────
# COLUMN MAPPING
# Maps financial_account → 13-column position in comprehensive report
# Positions: 0=qty 1=local 2=book 3=unrealgl_local 4=unrealgl_book
#            5=unrealfx_book 6=realized_local 7=realized_book
#            8=income_local 9=income_book 10=capital_shares
#            11=capital_local 12=capital_book
# ──────────────────────────────────────────────────────────────────────────────

COLUMN_MAPPING: dict[str, tuple] = {
    "Cost":                         (0, 1, 2),
    "Receivable":                   (0, 1, 2),
    "Payable":                      (0, 1, 2),
    "AccruedInterestReceivable":    (0, 1, 2),
    "AccruedInterestPayable":       (0, 1, 2),
    "SoldAccruedReceivable":        (0, 1, 2),
    "PurchasedAccruedPayable":      (0, 1, 2),
    "PurchasedInterest":            (0, 1, 2),
    "SoldInterest":                 (0, 1, 2),
    "DividendsReceivable":          (0, 1, 2),
    "DividendsPayable":             (0, 1, 2),
    "SpotFxReceivable":             (0, 1, 2),
    "SpotFxPayable":                (0, 1, 2),
    "ForwardFxReceivable":          (0, 1, 2),
    "ForwardFxPayable":             (0, 1, 2),
    "InterestReceivable":           (0, 1, 2),
    "InterestPayable":              (0, 1, 2),
    "Expenses_Receivable":          (0, 1, 2),
    "ExpensesPayable":              (0, 1, 2),
    "SoldAccrued":                  (0, 1, 2),
    "PurchasedAccrued":             (0, 1, 2),
    "UnrealPriceGL":                (0, 3, 4),
    "UnrealFXGL":                   (0, "skip", 5),
    "PriceGainStatOffset":          (0, 3, 4),
    "FXGainStatOffset":             (0, "skip", 5),
    "PriceGainInvestment":          (0, 6, 7),
    "FXGainInvestment":             (0, 6, 7),
    "FXGainCurrency":               (0, 6, 7),
    "FXGainTradeSettle":            (0, 6, 7),
    "DividendReceipt":              (0, 8, 9),
    "DividendExpense":              (0, 8, 9),
    "UnearnedIncome":               (0, 8, 9),
    "InterestIncome":               (0, 8, 9),
    "InterestReceipt":              (0, 8, 9),
    "InterestExpense":              (0, 8, 9),
    "AccruedInterestIncome":        (0, 8, 9),
    "AccruedInterestReceipt":       (0, 8, 9),
    "AccruedInterestExpense":       (0, 8, 9),
    "PurchasedInterestExpense":     (0, 8, 9),
    "SoldInterestIncome":           (0, 8, 9),
    "OptionIncome":                 (0, 8, 9),
    "OptionExpense":                (0, 8, 9),
    "MgmtFee":                      (0, 8, 9),
    "PerfFee":                      (0, 8, 9),
    "ContributedCost":              (10, 11, 12),
}

COLUMN_NAMES = [
    "quantity",
    "local",
    "book",
    "unrealgl_local",
    "unrealgl_book",
    "unrealfx_book",
    "realized_local",
    "realized_book",
    "income_local",
    "income_book",
    "capital_shares",
    "capital_local",
    "capital_book",
]


# ──────────────────────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def classify_account(financial_account: str) -> str:
    """Return the economic category for a financial account."""
    return ACCOUNT_CLASSIFICATION.get(financial_account, "Unknown")


def is_stat_only(financial_account: str) -> bool:
    """True if account is stat-only and should be excluded from reports."""
    return financial_account in STAT_ONLY_ACCOUNTS


def is_position_account(financial_account: str) -> bool:
    """True if account is an asset/liability position account."""
    return financial_account in POSITION_ACCOUNTS


def is_cost_basis_account(financial_account: str) -> bool:
    """True if account belongs to the cost basis reporting category."""
    return financial_account in COST_BASIS_ACCOUNTS


def is_income_account(financial_account: str) -> bool:
    """True if account is an income or expense account."""
    return financial_account in INCOME_ACCOUNTS


def is_realized_account(financial_account: str) -> bool:
    """True if account is a realized gain/loss account."""
    return financial_account in REALIZED_ACCOUNTS


def is_unrealized_account(financial_account: str) -> bool:
    """True if account is an unrealized gain/loss account."""
    return financial_account in UNREALIZED_ACCOUNTS


def is_capital_account(financial_account: str) -> bool:
    """True if account is a capital flow account."""
    return financial_account in CAPITAL_ACCOUNTS


def unknown_accounts(df) -> list[str]:
    """
    Return list of financial_account values in df that are not
    in ACCOUNT_CLASSIFICATION. Use to detect new accounts needing
    classification.
    """
    if "financial_account" not in df.columns:
        return []
    all_accounts = df["financial_account"].dropna().unique()
    return [
        a for a in all_accounts
        if a not in ACCOUNT_CLASSIFICATION
        and a not in STAT_ONLY_ACCOUNTS
    ]