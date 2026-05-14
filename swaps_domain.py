# ============================================================
# swaps_domain.py
# Core swap event posting logic
# ============================================================

import datetime
import heapq
import equity_domain
import bond_domain
from bookkeeping import (
    Journals,
    Event,
    RevenueExpenseCapitalRepository,
    load_coa_from_csv
)

# ============================================================
# 🔹 GLOBALS / INITIALIZATION
# ============================================================

revenue_expense_repository = RevenueExpenseCapitalRepository()
coa = load_coa_from_csv()
journal_entries = []
event = Event()
events = []  # priority queue for event scheduling


# ============================================================
# 🔹 EQUITY SWAP (LONG)
# ============================================================

def open_equity_swap_long(
    portfolio, investment, location, quantity, local, book, notional,
    journal_entries, space, tranid, transaction,
    tradedate, settledate, kdbegin, kdend,
    payment_currency, tdate_fx, smf, legin, legout
):
    """
    Post an equity swap long:
    - Books the swap contract itself (1 unit, zero local/book)
    - Books the equity leg (legin)
    - Books the financing leg (legout, negative mirror)
    """

    # 1️⃣ Book the swap contract (the contract record)
    ls = "n"
    financial_account = "Cost"
    entry_type = "Asset/Liability"
    ibor_date = tradedate
    tax_date = tradedate

    je = Journals(
        portfolio, investment, tranid, tax_date, ls, location, financial_account,
        1, 0, 0, 0, 0, tranid, transaction,
        tradedate, settledate, kdbegin, kdend, ibor_date, entry_type
    )
    space.post_journal_entry(je)

    # 2️⃣ Book the underlying equity leg — off-balance-sheet
    equity_domain.buy_equity(
        portfolio, legin, location, financial_account, quantity, local, book, 0,0,
        space, tranid, transaction,
        tradedate, settledate, kdbegin, kdend,
        tdate_fx,
        entry_type="Asset/Liability-OBS"   # 👈 override here
    )

    # 3️⃣ Book the financing leg (mirror image)
    bond_domain.short_bond(
        portfolio, legout, location,
        local, local, book,
        journal_entries, space,
        tranid, transaction,
        tradedate, settledate, kdbegin, kdend,
        payment_currency,
        smf=None, accrued_local=None, accrued_book=None,
        entry_type="Asset/Liability-OBS"
    )

    return
