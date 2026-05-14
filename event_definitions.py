# ============================================================
# event_definitions.py — Visibility Platform v1.0
# Core event schema for the accounting engine
# ============================================================

class BaseEvent:
    """
    Core structure shared by all event types.
    Used for all processing in the accounting engine.
    """

    def __init__(
        self,
        last_updated,
        portfolio,
        investment,
        location,
        method,
        event_type,
        tradedate,
        settledate,
        kdbegin,
        kdend,
        tranid,
        transaction=None,
        source=None,
        actual_settlement=None,
        tdate_fx=None,
        strategy=None,
        quantity=None,
        notional=None,
        oface=None,              # ✅ correct field name
        **kwargs
    ):
        self.last_updated = last_updated
        self.portfolio = portfolio
        self.investment = investment
        self.location = location
        self.method = method
        self.event_type = event_type
        self.tradedate = tradedate
        self.settledate = settledate
        self.actual_settlement = actual_settlement
        self.kdbegin = kdbegin
        self.kdend = kdend
        self.tranid = tranid
        self.transaction = transaction
        self.source = source

        # Optional fields (directly from event file)
        self.tdate_fx = tdate_fx
        self.strategy = strategy
        self.quantity = quantity
        self.notional = notional
        self.oface = oface        # ✅ matches your event file exactly

class TradeEvent(BaseEvent):
    """Trade-related events (equities, bonds, futures)."""

    def __init__(
        self,
        quantity,
        price,
        local=None,
        book=None,
        payment_currency=None,
        fx_rate=None,
        closing_method=None,
        space=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.quantity = quantity
        self.price = price
        self.local = local
        self.book = book
        self.payment_currency = payment_currency
        self.fx_rate = fx_rate
        self.closing_method = closing_method
        self.space = space


class IncomeEvent(BaseEvent):
    """Dividend or coupon income events."""

    def __init__(self, per_share=None, local=None, book=None, payment_currency=None, **kwargs):
        super().__init__(**kwargs)
        self.per_share = per_share
        self.local = local
        self.book = book
        self.payment_currency = payment_currency


class BondAccrualEvent(BaseEvent):
    """Represents bond interest accruals."""

    def __init__(self, accrued_local=None, accrued_book=None, per_100fv=None, payment_currency=None, **kwargs):
        super().__init__(**kwargs)
        self.accrued_local = accrued_local
        self.accrued_book = accrued_book
        self.per_100fv = per_100fv
        self.payment_currency = payment_currency


class SpinOffEvent(BaseEvent):
    """Represents a spin-off from a parent investment into one or more new entities."""

    def __init__(self, parent_investment, child_entities, **kwargs):
        super().__init__(**kwargs)
        self.parent_investment = parent_investment
        self.child_entities = [
            {
                "investment": c.get("investment"),
                "new_shares": c.get("new_shares"),
                "old_shares": c.get("old_shares"),
                "allocation_pct": c.get("allocation_pct"),
                "mark_price": c.get("mark_price"),
            }
            for c in child_entities or []
        ]

    def __repr__(self):
        return f"<SpinOffEvent parent={self.parent_investment} children={len(self.child_entities)}>"


class PriceMarkEvent(BaseEvent):
    """Price or FX mark for valuation."""

    def __init__(self, price, currency, fx_rate=None, **kwargs):
        super().__init__(**kwargs)
        self.price = price
        self.currency = currency
        self.fx_rate = fx_rate


class ExpenseEvent(BaseEvent):
    """Represents trade-level or operational expenses."""

    def __init__(
        self,
        amount_local,
        amount_book,
        payment_currency,
        expense_type,
        linked_tranid=None,
        capitalized=False,
        description=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.amount_local = amount_local
        self.amount_book = amount_book
        self.payment_currency = payment_currency
        self.expense_type = expense_type
        self.linked_tranid = linked_tranid
        self.capitalized = capitalized
        self.description = description


class FxContractEvent(BaseEvent):
    """Represents a spot or forward FX trade."""

    def __init__(
        self,
        buy_currency,
        sell_currency,
        buy_amt,
        sell_amt,
        rate=None,
        notional=None,
        fx_type="SPOT",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.buy_currency = buy_currency
        self.sell_currency = sell_currency
        self.buy_amt = buy_amt
        self.sell_amt = sell_amt
        self.rate = rate
        self.notional = notional
        self.fx_type = fx_type


class SwapContractEvent(BaseEvent):
    """Represents a swap contract or reset."""

    def __init__(
        self,
        legin,
        legout,
        maturity_date,
        early_termination_date=None,
        fixing_lag_days=None,
        payment_lag_days=None,
        reset_frequency=None,
        notional=None,
        rate=None,
        payment_currency=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.legin = legin
        self.legout = legout
        self.maturity_date = maturity_date
        self.early_termination_date = early_termination_date
        self.fixing_lag_days = fixing_lag_days
        self.payment_lag_days = payment_lag_days
        self.reset_frequency = reset_frequency
        self.notional = notional
        self.rate = rate
        self.payment_currency = payment_currency


class CapitalEvent(BaseEvent):
    """Represents capital additions or withdrawals."""

    def __init__(
        self,
        amount_local=None,
        amount_book=None,
        currency=None,
        investment=None,
        quantity=None,
        fx_rate=None,
        direction=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.amount_local = amount_local
        self.amount_book = amount_book
        self.currency = currency
        self.investment = investment
        self.quantity = quantity
        self.fx_rate = fx_rate
        self.direction = direction


class SplitEvent(BaseEvent):
    """Represents a share split or reverse split."""

    def __init__(
        self,
        old_shares=None,
        new_shares=None,
        split_ratio=None,
        fractional_policy=None,
        mark_price=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.old_shares = old_shares
        self.new_shares = new_shares
        self.split_ratio = split_ratio
        self.fractional_policy = fractional_policy
        self.mark_price = mark_price


# ============================================================
# METHOD TO EVENT CLASS MAP
# ============================================================

METHOD_EVENT_CLASS_MAP = {
    # Bond domain
    "bond_domain.buy_bond": "TradeEvent",
    "bond_domain.bond_coupon": "IncomeEvent",
    "bond_domain.cover_bond": "TradeEvent",
    "bond_domain.sell_bond": "TradeEvent",
    "bond_domain.short_bond": "TradeEvent",

    # Currency domain
    "currency_domain.deposit_currency": "CapitalEvent",
    "currency_domain.expense": "ExpenseEvent",
    "currency_domain.spot_fx": "FxContractEvent",
    "currency_domain.forward_fx": "FxContractEvent",
    "currency_domain.withdraw_currency": "CapitalEvent",

    # Equity domain
    "equity_domain.assign_call_long": "TradeEvent",
    "equity_domain.assign_call_short": "TradeEvent",
    "equity_domain.assign_put_long": "TradeEvent",
    "equity_domain.assign_put_short": "TradeEvent",
    "equity_domain.buy_equity": "TradeEvent",
    "equity_domain.cover_equity": "TradeEvent",
    "equity_domain.dividend_equity": "IncomeEvent",
    "equity_domain.exercise_call_long": "TradeEvent",
    "equity_domain.exercise_call_short": "TradeEvent",
    "equity_domain.exercise_put_long": "TradeEvent",
    "equity_domain.exercise_put_short": "TradeEvent",
    "equity_domain.sell_equity": "TradeEvent",
    "equity_domain.short_equity": "TradeEvent",
    "equity_domain.split_equity": "SplitEvent",
    "equity_domain.spin_off_equity": "SpinOffEvent",

    # Futures domain
    "futures_domain.buy_future": "TradeEvent",
    "futures_domain.cover_future": "TradeEvent",
    "futures_domain.sell_future": "TradeEvent",
    "futures_domain.short_future": "TradeEvent",

    # Swaps domain
    "swaps_domain.open_equity_swap_long": "SwapContractEvent",
    "swaps_domain.open_equity_swap_short": "SwapContractEvent",
}

# ============================================================
# TRANSACTION TO RULE MAP
# ============================================================

TRANSACTION_TO_RULE_MAP = {
    # Equity Trades
    "Equity Purchase": "equity_domain.buy_equity",
    "Equity Sale": "equity_domain.sell_equity",
    "Equity Short Sale": "equity_domain.short_equity",
    "Equity Cover Short": "equity_domain.cover_equity",

    # Bond Trades
    "Bond Purchase": "bond_domain.buy_bond",
    "Bond Sale": "bond_domain.sell_bond",
    "Bond Short Sale": "bond_domain.short_bond",
    "Bond Cover Short": "bond_domain.cover_bond",

    # Futures Trades
    "Futures Purchase": "futures_domain.buy_future",
    "Futures Sale": "futures_domain.sell_future",
    "Futures Short Sale": "futures_domain.short_future",
    "Futures Cover Short": "futures_domain.cover_future",

    # Corporate Actions
    "Equity Dividend": "equity_domain.dividend_equity",
    "Bond Coupon": "bond_domain.bond_coupon",
    "Equity Split": "equity_domain.split_equity",
    "Equity Spin-Off": "equity_domain.spin_off_equity",

    # FX Contracts
    "Spot FX": "currency_domain.spot_fx",
    "Forward FX": "currency_domain.forward_fx",

    # Capital Movements
    "Capital Deposit": "currency_domain.deposit_currency",
    "Capital Withdrawal": "currency_domain.withdraw_currency",

    # Swaps
    "Open Equity Swap (Long)": "swaps_domain.open_equity_swap_long",
    "Open Equity Swap (Short)": "swaps_domain.open_equity_swap_short",

    # Expenses
    "Expense": "currency_domain.expense",
}
