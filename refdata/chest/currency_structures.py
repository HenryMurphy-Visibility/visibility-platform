class Investment:
    def __init__(self, name, amount, aif):
        self.name = name
        self.amount = amount
        self.investment_type = aif.get_investment_type(name)  # Retrieve Investment_Type via AIF

    def __repr__(self):
        return f"Investment({self.name}, {self.amount}, {self.investment_type})"

class Currency(Investment):
    def __init__(self, name, amount, financial_account, aif):
        super().__init__(name, amount, aif)

        # Ensure the investment is of type "CURRENCY"
        if self.investment_type != "CURRENCY":
            raise ValueError(f"Investment {name} is not of type 'CURRENCY'")

        self.financial_account = financial_account
        self.currency_type = self.determine_currency_type()

    def determine_currency_type(self):
        # Determine the currency type based on the financial account
        if self.financial_account == "Cost":
            return "CurrencyOnHand"
        elif self.financial_account == "Payable":
            return "CurrencyPayable"
        elif self.financial_account == "Receivable":
            return "CurrencyReceivable"
        else:
            return "Unknown"

    def __repr__(self):
        return f"Currency({self.name}, {self.amount}, {self.currency_type}, {self.financial_account})"

class JournalEntry:
    def __init__(self, portfolio, investment, transaction_type, amount, financial_account, local_currency_amount, book_currency_amount):
        self.portfolio = portfolio
        self.investment = investment
        self.transaction_type = transaction_type  # e.g., 'Deposit', 'Withdrawal', 'Purchase', 'Sale'
        self.amount = amount
        self.financial_account = financial_account
        self.local_currency_amount = local_currency_amount
        self.book_currency_amount = book_currency_amount

    def __repr__(self):
        return (f"JournalEntry({self.portfolio}, {self.investment.name}, {self.transaction_type}, {self.amount}, "
                f"{self.financial_account}, {self.local_currency_amount}, {self.book_currency_amount})")

# Example: Mock AIF system to simulate Investment_Type retrieval
class MockAIF:
    def __init__(self):
        self.investment_data = {
            "USD": "CURRENCY",
            "EUR": "CURRENCY",
            "IBM": "STOCK"
        }

    def get_investment_type(self, name):
        return self.investment_data.get(name, "UNKNOWN")

# Example: Using the AIF to create a Currency instance and post a journal entry
aif = MockAIF()  # In reality, this would be your system's AIF

currency = Currency("USD", 1000, "Cost", aif)
journal_entry = JournalEntry(
    portfolio="Portfolio1",
    investment=currency,
    transaction_type="Deposit",
    amount=1000,
    financial_account="Payable",
    local_currency_amount=1000,
    book_currency_amount=1000
)

print(journal_entry)
