class Journals:
    def __init__(self, portfolio, investment, tax_lot, ls, location, financial_account,
                 quantity, local, book, tranid, transaction, tradedate, settledate, ibor_date,
                 running_balances):
        self.portfolio = portfolio
        self.investment = investment
        self.tax_lot = tax_lot
        self.ls = ls
        self.location = location
        self.financial_account = financial_account
        self.quantity = quantity
        self.local = local
        self.book = book
        self.tranid = tranid
        self.transaction = transaction
        self.tradedate = tradedate
        self.settledate = settledate
        self.ibor_date = ibor_date
        self.running_balances = running_balances

    def __str__(self):
        return f"portfolio: {self.portfolio}\n" \
               f"investment: {self.investment}\n" \
               f"tax_lot: {self.tax_lot}\n" \
               f"ls: {self.ls}\n" \
               f"location: {self.location}\n" \
               f"financial_account: {self.financial_account}\n" \
               f"quantity: {self.quantity}\n" \
               f"local: {self.local}\n" \
               f"book: {self.book}\n" \
               f"tranid: {self.tranid}\n" \
               f"transaction: {self.transaction}\n" \
               f"tradedate: {self.tradedate}\n" \
               f"settledate: {self.settledate}\n" \
               f"ibor_date: {self.ibor_date}\n" \
               f"running_balances: {self.running_balances}\n"

def parse_journal_entries(file_path):
    with open(file_path, "r") as file:
        lines = file.readlines()

    journal_entries = []
    entry_data = {}
    for line in lines:
        line = line.strip()
        if line.startswith("Entry Count"):
            if entry_data:
                journal_entry = Journals(**entry_data)
                journal_entries.append(journal_entry)
            entry_data = {}
        elif line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            entry_data[key] = value

    if entry_data:
        journal_entry = Journals(**entry_data)
        journal_entries.append(journal_entry)

    return journal_entries

def main():
    file_path ="C:/Users/hjmne/PycharmProjects/chest/journal_entries.txt"
    journal_entries = parse_journal_entries(file_path)

    for entry in journal_entries:
        print(entry)

if __name__ == "__main__":
    main()
