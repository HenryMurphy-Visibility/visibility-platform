# ============================================================
# SHAPE DEFINITIONS
# ============================================================

SHAPES = {

    # --------------------------------------------------------
    # SECURITY ROLLOVER
    # --------------------------------------------------------
    "rollover": {

        "summary": {
            # Only cost accounts appear in summary
            "include_accounts": ("Cost",),
            # How summary should be grouped
            "group_by": ("investment",),
        },

        "detail": {
            # All accounts allowed in JE detail
            "include_accounts": "ALL",
            "group_by": ("investment","financial_account"),
        }
    },

    # --------------------------------------------------------
    # RECONCILED FINANCIAL STATE
    # --------------------------------------------------------


    "reconciled_financial_state": {

        "summary": {
            # All accounts included
            "include_accounts": "ALL",
            # all accounts
            "group_by": ("investment", "financial_account"),
        },

        "detail": {
            # All JE rows allowed
            "include_accounts": "ALL",
            "group_by": ("investment"),
        }
    }

}