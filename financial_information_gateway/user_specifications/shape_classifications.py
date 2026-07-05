# ============================================================
# VISIBILITY — SHAPE CONSTRUCTION
# Canonical Financial Statement Definitions
# ============================================================

# ============================================================
# CHART OF ACCOUNTS
# ============================================================

COA = [
    "ContributedCost",
    "Cost",
    "DividendExpense",
    "DividendReceipt",
    "DividendsPayable",
    "DividendsReceivable",
    "Expenses_Receivable",
    "ExpensesPayable",
    "ForwardFxPayable",
    "ForwardFxReceivable",
    "FXGainAccrued",
    "FXGainCurrency",
    "FXGainInvestment",
    "FXGainTradeSettle",
    "InterestExpense",
    "InterestPayable",
    "InterestReceipt",
    "InterestReceivable",
    "MgmtFee",
    "MarketVal",
    "MarketValRE",
    "OptionExpense",
    "OptionIncome",
    "PurchasedAccruedPayable",
    "SoldAccruedReceivable",
    "Payable",
    "PerfFee",
    "PriceGainInvestment",
    "Receivable",
    "SpotFxPayable",
    "SpotFxReceivable",
    "UnrealGLAsset",
    "UnrealGLRevExp",
    "AccruedInterestExpense",
    "AccruedInterestPayable",
    "AccruedInterestReceipt",
    "AccruedInterestReceivable",
    "PurchasedAccrued",
    "SoldAccrued",
    "UnrealPriceGL",
    "UnrealFXGL",
    "UnearnedIncome",
    "UnrealPriceGLOffset",
    "UnrealFXGLOffset",
]

# ============================================================
# STATEMENT CLASSIFICATION
# ============================================================

STATEMENT_CLASS = {

    # -------------------------
    # ASSETS
    # -------------------------
    "Cost": "ASSET",
    "MarketVal": "ASSET",
    "Receivable": "ASSET",
    "DividendsReceivable": "ASSET",
    "InterestReceivable": "ASSET",
    "AccruedInterestReceivable": "ASSET",
    "PurchasedAccrued": "ASSET",
    "Expenses_Receivable": "ASSET",
    "SpotFxReceivable": "ASSET",
    "ForwardFxReceivable": "ASSET",

    # -------------------------
    # LIABILITIES
    # -------------------------
    "Payable": "LIABILITY",
    "DividendsPayable": "LIABILITY",
    "InterestPayable": "LIABILITY",
    "AccruedInterestPayable": "LIABILITY",
    "SoldAccrued": "LIABILITY",
    "ExpensesPayable": "LIABILITY",
    "SpotFxPayable": "LIABILITY",
    "ForwardFxPayable": "LIABILITY",

    # -------------------------
    # REVENUE
    # -------------------------
    "DividendReceipt": "REVENUE",
    "InterestReceipt": "REVENUE",
    "PriceGainInvestment": "REVENUE",
    "FXGainAccrued": "REVENUE",
    "FXGainCurrency": "REVENUE",
    "FXGainInvestment": "REVENUE",
    "FXGainTradeSettle": "REVENUE",
    "OptionIncome": "REVENUE",
    "UnrealPriceGL": "REVENUE",
    "UnrealFXGL": "REVENUE",
    "UnrealGLRevExp": "REVENUE",

    # -------------------------
    # EXPENSE
    # -------------------------
    "DividendExpense": "EXPENSE",
    "InterestExpense": "EXPENSE",
    "MgmtFee": "EXPENSE",
    "PerfFee": "EXPENSE",
    "OptionExpense": "EXPENSE",
    "AccruedInterestExpense": "EXPENSE",

    # -------------------------
    # CAPITAL
    # -------------------------
    "ContributedCost": "CAPITAL",
    "UnearnedIncome": "CAPITAL",
}

# ============================================================
# STATEMENT ORDER
# ============================================================

STATEMENT_ORDER = [
    "ASSET",
    "LIABILITY",
    "CAPITAL",
    "REVENUE",
    "EXPENSE",
]

# ============================================================
# FINANCIAL ACCOUNT ORDER (WITHIN CLASS)
# ============================================================

FA_ORDER_WITHIN_CLASS = {
    "ASSET": [
        "Cost",
        "MarketVal",
        "Receivable",
        "InterestReceivable",
        "AccruedInterestReceivable",
        "PurchasedAccrued",
    ],
    "LIABILITY": [
        "Payable",
        "InterestPayable",
        "AccruedInterestPayable",
        "SoldAccrued",
    ],
    "REVENUE": [
        "DividendReceipt",
        "InterestReceipt",
        "PriceGainInvestment",
        "FXGainAccrued",
        "FXGainCurrency",
        "FXGainTradeSettle",
        "UnrealPriceGL",
        "UnrealFXGL",
    ],
    "EXPENSE": [
        "DividendExpense",
        "InterestExpense",
        "MgmtFee",
        "PerfFee",
    ],
    "CAPITAL": [
        "ContributedCost",
        "UnearnedIncome",
    ],
}
