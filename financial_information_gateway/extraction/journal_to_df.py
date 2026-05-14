import pandas as pd

def build_positions_df(journal_df):

    RELEVANT_ACCOUNTS = [
        "Cost",
        "MarketVal"
    ]

    df = journal_df[
        journal_df["financial_account"].isin(RELEVANT_ACCOUNTS)
    ].copy()

    df["lotid"] = df["lotid"].fillna(0)
    df["tax_date"] = df["tax_date"].fillna(0)

    group_cols = [
        "investment",
        "lotid",
        "tax_date",
        "is_adjustment"
    ]

    positions = (
        df.groupby(group_cols, as_index=False)
          .agg({
              "local": "sum",
              "book": "sum"
          })
    )

    positions["entry_type"] = positions["is_adjustment"].map({
        False: "current",
        True: "adjustment"
    })

    return positions

# ============================================================
# journal_to_df.py
# Convert Journal Entries → DataFrame for FIG
# ============================================================


def build_journal_df(journal_entries):
    """
    Convert journal entry objects into a normalized DataFrame

    Required output columns:
        investment
        lotid
        tax_date
        financial_account
        local
        book
        is_adjustment
    """
    import pandas as pd
    rows = []

    for je in journal_entries:

        # -----------------------------------
        # SAFE ATTRIBUTE ACCESS
        # -----------------------------------
        investment = getattr(je, "investment", None)
        lotid = getattr(je, "lotid", 0)
        tax_date = getattr(je, "tax_date", 0)
        financial_account = getattr(je, "financial_account", None)
        local = getattr(je, "local", 0.0)
        book = getattr(je, "book", 0.0)

        # -----------------------------------
        # 🔥 CRITICAL: adjustment flag
        # -----------------------------------
        # Try multiple possible indicators safely

        is_adjustment = False

        # Option 1: explicit flag on JE
        if hasattr(je, "is_adjustment"):
            is_adjustment = bool(getattr(je, "is_adjustment"))

        # Option 2: source attribute (common pattern)
        elif hasattr(je, "source"):
            is_adjustment = (getattr(je, "source") == "adjusting")

        # Option 3: filename or tag (fallback)
        elif hasattr(je, "file_type"):
            is_adjustment = (getattr(je, "file_type") == "adjusting")

        # -----------------------------------
        # BUILD ROW
        # -----------------------------------
        rows.append({
            "investment": investment,
            "lotid": lotid if lotid is not None else 0,
            "tax_date": tax_date if tax_date is not None else 0,
            "financial_account": financial_account,
            "local": local if local is not None else 0.0,
            "book": book if book is not None else 0.0,
            "is_adjustment": is_adjustment,
        })

    # -----------------------------------
    # BUILD DATAFRAME
    # -----------------------------------
    df = pd.DataFrame(rows)

    if df.empty:
        return df

    # -----------------------------------
    # CLEANUP / NORMALIZATION
    # -----------------------------------
    df["lotid"] = df["lotid"].fillna(0)
    import pandas as pd

    df["tax_date"] = pd.to_datetime(df["tax_date"], errors="coerce")
    df["tax_date"] = df["tax_date"].fillna(pd.Timestamp("1900-01-01"))
    df["local"] = df["local"].fillna(0.0)
    df["book"] = df["book"].fillna(0.0)

    return df