
def build_sub_ledger_from_journals(self, journals, period_end_date):
    # Filter the journals by the period_end_date
    journals = [je for je in journals if je.ibor_date <= period_end_date]
    for idx, je in enumerate(journals):
        self.post_journal_entry(je)

        # Print the status every 10 entries for example:
        if idx % 10 == 0:
            print(f"Processed {idx} journal entries...")

    print("Finished processing all journal entries!")

    # Return the current state of the bookkeeping space
    return {
        "asset_liability": self.asset_liability_entries,
        "revenue_expense": self.revenue_expense_entries,
        "statistical": self.statistical_entries,
        "aggregates": self.aggregates,
        "bs": self.bs,
        "balance_sheet": self.balance_sheet,
        "journal_entries": self.journal_entries,
        "entries": self.entries
    }

