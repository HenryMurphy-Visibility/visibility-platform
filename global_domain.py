
from bookkeeping import Journals
from itertools import groupby

from utilities import round_to_precision

import json
import os

# Module-level cache: portfolio.json read once per portfolio per process,
# not once per accrual event.
import json
import os

# Module-level: config cache and a record of which file each
# portfolio's config was loaded from (for diagnostics).
_PORTFOLIO_CONFIG_CACHE = {}
_PORTFOLIO_CONFIG_PATHS = {}


def get_portfolio_config(portfolio):
    """
    Load and cache the portfolio configuration (portfolio.json).
    Cached per process: config edits require a process restart.
    Every log line carries the absolute path so config staleness
    and wrong-file ambiguity are visible facts, not mysteries.
    """
    if portfolio in _PORTFOLIO_CONFIG_CACHE:
        print(f"PORTFOLIO CONFIG: {portfolio} from CACHE (loaded this "
              f"process from {_PORTFOLIO_CONFIG_PATHS.get(portfolio, '?')})")
        return _PORTFOLIO_CONFIG_CACHE[portfolio]

    config_path = os.path.join("funds", portfolio, "portfolio.json")
    abs_path = os.path.abspath(config_path)
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        print(f"PORTFOLIO CONFIG: {portfolio} loaded from {abs_path}")
    except FileNotFoundError:
        print(f"PORTFOLIO CONFIG: {portfolio} NOT FOUND at {abs_path} "
              f"-- defaulting empty")
        config = {}
    except json.JSONDecodeError as e:
        print(f"PORTFOLIO CONFIG: {portfolio} JSON ERROR at {abs_path}: "
              f"{e} -- defaulting empty")
        config = {}

    _PORTFOLIO_CONFIG_CACHE[portfolio] = config
    _PORTFOLIO_CONFIG_PATHS[portfolio] = abs_path
    return config


def get_accrual_posting_policy(portfolio, as_of_date):
    """
    Resolve the fund's accrual posting policy from
    accrual_method_history, effective-dated: the entry with the
    latest effective_from <= as_of_date governs.

    Values (industry verbiage, per ICI operations guidance):
      single_day_factor   -- each calendar day posts dated itself.
                             DEFAULT when no election exists.
      multiday_preceding  -- weekend/holiday stamped on the prior
                             business day (Friday carries Fri+Sat+Sun).
      multiday_following  -- weekend/holiday stamped on the next
                             business day (Monday carries Sat+Sun+Mon).
    """
    config = get_portfolio_config(portfolio)
    history = config.get("accrual_method_history", [])
    effective = None
    for entry in history:
        eff_from = entry.get("effective_from")
        if eff_from and str(eff_from) <= str(as_of_date)[:10]:
            if effective is None or eff_from > effective["effective_from"]:
                effective = entry

    resolved = effective["value"] if effective else "single_day_factor"
    print(f"POLICY RESOLVE: portfolio={portfolio} as_of={str(as_of_date)[:10]} "
          f"history={history} -> '{resolved}'")
    return resolved


def execute_rule_event(event, space, stat_repo, af, sir):
    """
    Execute a single rule invocation event.
    Domain logic remains untouched.
    """
    import pandas as pd
    method = event["method"]

    portfolio  = event["portfolio"]
    investment = event["investment"]

    # Core temporal reference
    mark_date = pd.to_datetime(event["tradedate"]).to_pydatetime()

    # Optional payload
    price   = event.get("price")
    fx_rate = event.get("fx_rate")

    accrued_interest_per_100fv = event.get("accrued_interest_per_100fv", 0.0)

    # -------------------------------
    # Rule dispatch
    # -------------------------------
    if method == "mark_prices":
        mark_prices(
            portfolio,
            investment,
            mark_date,
            space,
            price,
            fx_rate,
            accrued_interest_per_100fv,
        )

    elif method == "mark_bond_accruals":
        mark_bond_accruals(
            portfolio,
            investment,
            mark_date,
            space,
            price,
            fx_rate,
            None,  # settledate (unchanged)
            accrued_interest_per_100fv,
        )

    else:
        raise ValueError(f"Unknown rule method: {method}")

# Define the lot iterator by location and long/short (ls)
def global_lot_iterator_by_location_ls(investment, space):
    lots = global_lot_iterator(investment, space)

    # Instead of sorting, iterate over lots directly grouped by ls and location
    # Assuming account_key is a tuple and location and ls are part of the account_key
    lots_sorted = sorted(lots, key=lambda x: (x[0][4], x[0][5]))  # Sorting by long/short (ls) and location

    # Group by long/short and location
    for (lot_ls, lot_location), grouped_lots in groupby(lots_sorted, key=lambda x: (x[0][4], x[0][5])):
        yield (lot_ls, lot_location), list(grouped_lots)

def global_lot_iterator(investment, space):
    # Get the entries from the investment subspace
    investment_space = space.get_position_space(investment)

    if investment_space:
        bs_entries = investment_space.entries  # Assuming 'entries' is a dictionary

        # Filter the entries based on the investment
        matching_lots = [entry for entry in bs_entries.items() if entry[0][1] == investment]

        # Extract relevant lot information (account key, lot quantity, local, and book values)
        # Assuming entry[1][0] is the lot quantity, entry[1][1] is local, and entry[1][2] is book
        return [(entry[0], entry[1][0], entry[1][1], entry[1][2], entry[1][3]) for entry in matching_lots]
    else:
        return []


def mark_prices(
        portfolio, investment, mark_date,
        space, tranid,
        mark_price, mark_fx, per_100FV_accrue, per_100FV_amort
):
    from business_days import is_non_business_day
    from bookkeeping import Journals

    stat_repo = space.stat_repo
    repo = space.asset_liability_repository

    # --------------------------------------------------------------
    # 1. GET SUBSPACE (POSITION STATE ONLY)
    # --------------------------------------------------------------
    subspace = repo.get_position_space(investment)
    if subspace is None:
        print(f"⚠️ No subspace for {investment}; skipping mark.")
        return

    # --------------------------------------------------------------
    # 2. SKIP NON-BUSINESS DAYS
    # --------------------------------------------------------------
    if is_non_business_day(mark_date):
        return

    # --------------------------------------------------------------
    # 3. GET INVESTMENT ATTRIBUTES (CANONICAL LOCATION)
    # --------------------------------------------------------------
    sub = repo.investment_attributes.get(investment)

    if not sub:
        raise RuntimeError(
            f"No investment attributes loaded for {investment}"
        )

    attributes = sub.investment_attributes.get("AIF", {})

    # --------------------------------------------------------------
    # ACCOUNT CLASSIFICATION
    # --------------------------------------------------------------
    # MARK_PRICE_ACCOUNTS aggregate into a single price-driven MV per
    # (location, ls). Works correctly when the investment is a currency
    # (all balances are par-natured) AND when the investment is a
    # security (Cost is the dominant balance and accrued/receivable
    # currency-natured balances are tagged to a CURRENCY investment,
    # not the security).
    MARK_PRICE_ACCOUNTS = {
        "Cost",
        "Receivable",
        "Payable",
        "DividendsReceivable", "DividendsPayable",
        "InterestReceivable", "InterestPayable",  # coupon with lag
        "SpotFXReceivable", "SpotFXPayable",
    }

    # PAR_PRICED_ACCOUNTS are currency-natured balances that happen to
    # be tagged to a non-currency investment (a bond, in current scope).
    # They mark at par: MV = book balance, no Unreal G/L from price
    # movement. Each account posts its own MV entry; not aggregated
    # into the standard MV per (location, ls).
    #
    # Tactical: when the proper pricing-method assignment is built
    # (see HOUSEKEEPING in issue log), this list becomes a pricing-
    # method classification on the account / investment configuration
    # rather than a hardcoded list here.
    PAR_PRICED_ACCOUNTS = {"PurchasedInterest", "SoldInterest","AccruedInterestReceivable", "AccruedInterestPayable"}


    # --------------------------------------------------------------
    # 4. BUILD POSITION DATA — TWO TRACKS
    # --------------------------------------------------------------
    position_data = {}  # (location, ls) -> aggregated for price-mark
    par_data = {}  # (location, ls, fa) -> per-account for par-mark

    for key, (qty, local, book, notional, oface) in subspace.entries.items():
        (_, inv, lotid, tax_date, ls, loc, fa) = key

        if fa in MARK_PRICE_ACCOUNTS:
            pos_key = (loc, ls)
            if pos_key not in position_data:
                position_data[pos_key] = {
                    "position_qty": 0.0,
                    "local_cost": 0.0,
                    "book_cost": 0.0,
                    "notional": 0.0,
                    "oface": 0.0,
                }
            position_data[pos_key]["position_qty"] += qty
            position_data[pos_key]["local_cost"] += local
            position_data[pos_key]["book_cost"] += book
            position_data[pos_key]["notional"] += notional
            position_data[pos_key]["oface"] += oface

        elif fa in PAR_PRICED_ACCOUNTS:
            # Track separately; each par-priced account posts its own
            # MV entry. Not aggregated with anything.
            par_key = (loc, ls, fa)
            if par_key not in par_data:
                par_data[par_key] = {
                    "position_qty": 0.0,
                    "local": 0.0,
                    "book": 0.0,
                }
            par_data[par_key]["position_qty"] += qty
            par_data[par_key]["local"] += local
            par_data[par_key]["book"] += book

    # --------------------------------------------------------------
    # 5. PRICE / FX — FROM EVENT (NOT LOOKUP)
    # --------------------------------------------------------------
    if mark_price is None:
        raise ValueError(f"Missing mark_price for {investment} on {mark_date}")

    if mark_fx is None:
        raise ValueError(f"Missing mark_fx for {investment} on {mark_date}")

    price = mark_price
    fx_rate = mark_fx

    if price is None or fx_rate is None:
        print(f"❌ Mark missing price/FX: {investment} {mark_date}")
        return

    pricing_factor = attributes.get("pricing_factor", 1)
    contract_size = attributes.get("contract_size", 1)

    # --------------------------------------------------------------
    # 6. PROCESS PRICE-MARKED POSITIONS
    # --------------------------------------------------------------
    for (location, ls), pos_fields in position_data.items():
        process_position(
            portfolio, investment, mark_date,
            stat_repo, space,
            price, fx_rate,
            location, ls, pos_fields,
            pricing_factor,
            contract_size
        )

    # --------------------------------------------------------------
    # 7. PROCESS PAR-MARKED POSITIONS (PurchasedInterest, SoldInterest)
    # --------------------------------------------------------------
    # MV = book balance. No price lookup, no Unreal G/L from price
    # movement. Each (location, ls, fa) posts its own MV entry.
    for (location, ls, fa), par_fields in par_data.items():
        # Skip zero balances (e.g. closed-out PurchasedInterest after
        # settlement reclassed it into AccruedInterestReceivable)
        if par_fields["position_qty"] == 0.0 and par_fields["book"] == 0.0:
            continue

        par_mv_entry = Journals(
            portfolio, investment, 0, 0, ls, location, "MarketVal",
            par_fields["position_qty"],
            par_fields["local"],
            par_fields["book"],
            0, None,
            0, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
            "Revenue/Expense/Capital"
        )
        space.post_journal_entry(par_mv_entry)

def process_position(portfolio, investment, mark_date, stat_repo, space,
                     price, fx_rate, location, ls, position_data, pricing_factor, contract_size):
    """
    Processes a single position during mark pricing with safe numeric conversions.
    Preserves original valuation and posting logic; eliminates float('') crashes.
    """
    from bookkeeping import Journals  # ensure available here


    # ---- Safe numeric conversion helper ----
    def safe_float(val, default=0.0):
        try:
            if val in (None, '', 'NA'):
                return default
            return float(val)
        except (TypeError, ValueError):
            return default

    # ---- Extract + normalize inputs ----
    position_qty = safe_float(position_data.get('position_qty'), 0.0)
    position_local_cost = safe_float(position_data.get('local_cost'), 0.0)
    position_book_cost  = safe_float(position_data.get('book_cost'), 0.0)
    position_notional   = safe_float(position_data.get('notional'), 0.0)

    px        = safe_float(price, 0.0)
    fx_rate_f = safe_float(fx_rate, 1.0)
    cs = safe_float(contract_size, 1.0) or 1.0
    pf = safe_float(pricing_factor, 1.0) or 1.0


    # ---- Skip if no quantity ----
    if position_qty == 0.0:
        return

    # ---- Market values (preserve your formulae) ----
    mktval_local = position_qty * px * pf * cs - position_notional
    mktval_book  = mktval_local * fx_rate_f

    # ---- Post current market value ----
    mark_value_entry = Journals(
        portfolio, investment, 0, 0, ls, location, 'MarketVal',
        position_qty, mktval_local, mktval_book, mktval_local + position_notional, None,
        0, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
        "Revenue/Expense/Capital"
    )
    space.post_journal_entry(mark_value_entry)

    # ---- Unrealized GL calculations (preserve original accounts/flow) ----
    price_stat_account = 'UnrealPriceGL'
    fx_stat_account    = 'UnrealFXGL'

    prev_price_local, prev_price_book, prev_unrl_notional = stat_repo.get_entry(
        None, portfolio, investment, 0, 0, price_stat_account, ls, location, stat_repo
    )
    _, prev_fx_book, _ = stat_repo.get_entry(
        None, portfolio, investment, 0, 0, fx_stat_account, ls, location, stat_repo
    )

    prev_price_local     = safe_float(prev_price_local, 0.0)
    prev_price_book      = safe_float(prev_price_book, 0.0)
    prev_fx_book         = safe_float(prev_fx_book, 0.0)
    prev_unrl_notional   = safe_float(prev_unrl_notional, 0.0)
    prev_total_gain_book = prev_price_book + prev_fx_book

    unrealized_price_local = mktval_local - position_local_cost
    unrealized_price_book  = unrealized_price_local * fx_rate_f
    unrealized_fx_book     = mktval_book - position_book_cost - unrealized_price_book
    unrealized_notional    = position_notional - prev_unrl_notional

    net_unrealized_price_local = unrealized_price_local - prev_price_local
    net_unrealized_price_book  = unrealized_price_book  - prev_price_book
    net_unrealized_fx_book     = mktval_book - position_book_cost - prev_total_gain_book - net_unrealized_price_book
    # carry over just the unrealized price gain in local for notional
    net_unrealized_notional    = net_unrealized_price_local

    # ---- Store new unrealized values ----
    stat_repo.add_entry(
        None, portfolio, investment, 0, 0, 'UnrealPriceGL', ls, location, stat_repo,
        unrealized_price_local, unrealized_price_book, unrealized_notional
    )
    stat_repo.add_entry(
        None, portfolio, investment, 0, 0, 'UnrealFXGL', ls, location, stat_repo,
        0, unrealized_fx_book, 0
    )

    # ---- Post Unrealized GL journals and offsets (preserve your entries) ----
    unreal_gl_price_entry = Journals(
        portfolio, investment, 0, 0, ls, location, 'UnrealPriceGL',
        None, net_unrealized_price_local, net_unrealized_price_book, net_unrealized_notional, None,
        0, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
        "Revenue/Expense/Capital"
    )
    space.post_journal_entry(unreal_gl_price_entry)

    unreal_gl_fx_entry = Journals(
        portfolio, investment, 0, 0, ls, location, 'UnrealFXGL',
        None, 0, net_unrealized_fx_book, 0, None,
        0, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
        "Revenue/Expense/Capital"
    )
    space.post_journal_entry(unreal_gl_fx_entry)

    unreal_gl_price_entry = Journals(
        portfolio, investment, 0, 0, ls, location, 'UnrealPriceGLOffset',
        None, -net_unrealized_price_local, -net_unrealized_price_book, -net_unrealized_notional, None,
        0, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
        "Revenue/Expense/Capital"
    )
    space.post_journal_entry(unreal_gl_price_entry)

    unreal_gl_fx_entry = Journals(
        portfolio, investment, 0, 0, ls, location, 'UnrealFXGLOffset',
        None, 0, -net_unrealized_fx_book, 0, None,
        0, "Valuation", mark_date, mark_date, mark_date, mark_date, mark_date,
        "Revenue/Expense/Capital"
    )
    space.post_journal_entry(unreal_gl_fx_entry)


def mark_bond_accruals(portfolio, investment, mark_date,
                       space, tranid, mark_price, mark_fx, per_100FV_accrue, mark_100FV_amort, af):
    """
    Daily bond accrual, basis-true, policy-aware.
    Fires BEFORE mark_settled (precedence 1040 < 1045): the ordering
    encodes through-settle-inclusive ownership -- on a disposal-settle
    day the final owned day posts while the AF still shows the
    position entitled.

    AMOUNT: instrument's basis (per_100FV_accrue daily rate).
    OWNERSHIP: trade terms, via AF settled entitlement.
    RECOGNITION: fund policy from portfolio.json accrual_method_history.

    Transaction naming (bifurcated): own-day entries are normal
    accruals (BondAccrual) under every policy; only non-business-day
    treatment carries the election's name:
      single_day_factor  -- gap days post EACH dated themselves,
                            named SingleDayFactor
      multiday_preceding -- gap days post as ONE entry dated the
                            PRIOR business day, named MultiDayPreceding
                            (computed in this run: today's pre-settlement
                            AF state equals that day's post-settlement
                            state, since nothing settles over a gap)
      multiday_following -- gap days post as ONE entry dated TODAY,
                            named MultiDayFollowing
    """
    from bookkeeping import Journals
    from business_days import is_non_business_day
    from datetime import timedelta

    if is_non_business_day(mark_date):
        return

    repo = space.asset_liability_repository
    sub = repo.investment_attributes.get(investment)
    if not sub:
        return
    attributes = sub.investment_attributes.get("AIF", {})
    if attributes.get("investment_type") != "BOND":
        return
    if per_100FV_accrue is None or per_100FV_accrue == 0:
        return

    rate = float(per_100FV_accrue)
    pf = float(attributes.get("pricing_factor", 1))
    fx = float(mark_fx)

    # ── RESOLVE FUND POLICY (effective-dated) ─────────────────────
    policy = get_accrual_posting_policy(portfolio, mark_date)

    # ── COVERAGE, STAMPING, AND TRANSACTION NAME PER POLICY ──────
    # postings: list of (posting_date, n_days_covered, txn_name)
    if policy == "single_day_factor":
        postings = [(mark_date, 1, "BondAccrual")]
        probe = mark_date - timedelta(days=1)
        while is_non_business_day(probe):
            postings.insert(0, (probe, 1, "SingleDayFactor"))
            probe -= timedelta(days=1)

    elif policy == "multiday_preceding":
        postings = [(mark_date, 1, "BondAccrual")]
        n = 0
        probe = mark_date - timedelta(days=1)
        while is_non_business_day(probe):
            n += 1
            probe -= timedelta(days=1)
        if n:
            # probe is now the business day preceding the gap;
            # the gap's accrual stamps onto it, named for the election.
            postings.insert(0, (probe, n, "MultiDayPreceding"))

    elif policy == "multiday_following":
        postings = [(mark_date, 1, "BondAccrual")]
        n = 0
        probe = mark_date - timedelta(days=1)
        while is_non_business_day(probe):
            n += 1
            probe -= timedelta(days=1)
        if n:
            postings.append((mark_date, n, "MultiDayFollowing"))

    else:
        raise ValueError(f"Unknown accrual posting policy '{policy}' "
                         f"for portfolio {portfolio}")


    # ── ENTITLEMENT: PRE-SETTLEMENT AF STATE ──────────────────────
    positions = af.entitled_position(portfolio=portfolio,
                                     investment=investment)

    # (B) at the TOP of mark_bond_accruals, right after entitled_position is read,
    #     the first time it fires in Feb:
    print(f"[ACCRUAL-GATE] {investment} {mark_date:%Y-%m-%d} positions={positions}")

    if not positions:
        print(f"Bond accruals: {portfolio}/{investment} "
              f"{mark_date:%Y-%m-%d} policy={policy} -- no AF "
              f"positions, skipping.")
        return

    posted_any = False

    for (location, ls_key), entitled_qty in positions.items():
        if entitled_qty == 0:
            continue
        economic_direction = entitled_qty * rate
        if economic_direction == 0:
            continue
        if economic_direction > 0:
            al_account, re_account, ls = ("AccruedInterestReceivable",
                                          "InterestIncome", "l")
        else:
            al_account, re_account, ls = ("AccruedInterestPayable",
                                          "InterestExpense", "s")

        daily_local = entitled_qty * rate * pf

        for posting_date, n_days, txn in postings:
            accrued_local = daily_local * n_days
            accrued_book = accrued_local * fx

            space.post_journal_entry(Journals(
                portfolio, investment, 0, None, ls, location,
                al_account,
                accrued_local, accrued_local, accrued_book,
                None, None, tranid, txn,
                posting_date, posting_date, posting_date,
                posting_date, posting_date,
                "Asset/Liability"
            ))
            space.post_journal_entry(Journals(
                portfolio, investment, 0, 0, ls, location,
                re_account,
                0, -accrued_local, -accrued_book,
                None, None, tranid, txn,
                posting_date, posting_date, posting_date,
                posting_date, posting_date,
                "Revenue/Expense/Capital"
            ))
            posted_any = True

    if posted_any:
        print(f"Bond accruals: {portfolio}/{investment} "
              f"{mark_date:%Y-%m-%d} policy={policy} postings="
              f"{[(f'{d:%m-%d}', n, t) for d, n, t in postings]}")
    else:
        print(f"Bond accruals: {portfolio}/{investment} "
              f"{mark_date:%Y-%m-%d} policy={policy} -- entitled "
              f"positions all zero, nothing posted.")


def bond_coupon(portfolio, investment, space, tranid, transaction, tradedate, settledate, kdbegin, kdend,
                payment_currency, per_share, af, fx_ex):
    """
    Coupon ex-date posting. No NEW income beyond one day -- income
    was recognized daily by the accrual engine through ex-1. This
    rule:

      1. Relieves the accrued claim at its READ book cost (what the
         daily accrual actually carried it at -- historical rates).
      2. Recognizes the FINAL day (ex-date) as income, at the
         ex-date rate. That day = coupon_local - accrued_local.
      3. Collects the coupon: cash today if ex == pay (same-day),
         else opens a due claim (InterestReceivable) booked at the
         ex-date rate, to be washed at pay date.
      4. Books FXGainAccrued for the residual: coupon at ex-rate vs
         (accrued at historical book + ex-day at ex-rate). Zero for
         base currency; realized FX on income across a moving rate
         otherwise.

    Sign convention: debits +, credits -. Direction follows signed
    entitled qty -- long relieves a Receivable and earns Income;
    short relieves a Payable and books Expense; cash_payment_same_day
    takes +local for a receipt, -local for a payment.

    Relief is posted at the READ balance plus the constructed
    ex-day, so the accrued account zeroes by construction. A gap
    beyond one day surfaces in the eps check (and Pillar 7), never
    silently absorbed.
    """
    ibor_date = tradedate
    repo = space.asset_liability_repository
    import currency_domain

    positions = af.entitled_position(portfolio=portfolio,
                                     investment=investment)

    # ── READ accrued balances at book cost, per (location, ls) ───
    accrued_bal = {}  # (location, ls) -> [local, book]
    subspace = repo.get_position_space(investment)
    if subspace is not None:
        for key, (qty, local, book, notional, oface) in subspace.entries.items():
            (_, inv, lotid, tax_date, ls_k, loc_k, fa) = key
            if fa in ("AccruedInterestReceivable", "AccruedInterestPayable"):
                k = (loc_k, ls_k)
                if k not in accrued_bal:
                    accrued_bal[k] = [0.0, 0.0]
                accrued_bal[k][0] += local
                accrued_bal[k][1] += book

    for (location, ls), entitled_qty in positions.items():
        if entitled_qty == 0:
            continue
        # Missing location => structural default, made VISIBLE (not
        # silently inferred). Users may add semantic validation
        # (e.g. "must be one of our desks") on top.
        if not location:
            location = "Default"

        coupon_local = entitled_qty * per_share / 100
        coupon_book = coupon_local * fx_ex

        # Account names follow position direction (debit+/credit-).
        if coupon_local >= 0:
            faal_accr = "AccruedInterestReceivable"
            faal_inc = "InterestIncome"
            faal_due = "InterestReceivable"
        else:
            faal_accr = "AccruedInterestPayable"
            faal_inc = "InterestExpense"
            faal_due = "InterestPayable"

        bal_local, bal_book = accrued_bal.get((location, ls), [0.0, 0.0])

        # The read accrued carries through ex-1; the ex-date day is
        # the missing piece, by construction the coupon/accrued gap.
        exday_local = coupon_local - bal_local
        exday_book = exday_local * fx_ex

        # 1. Relieve accrued at READ book cost (historical rates).
        #    coupon_local >= 0 (long): accrued was a debit balance,
        #    relief is a credit -> -bal. Mirror for short.
        relief = Journals(portfolio, investment, 0, 0,
                          ls, location, faal_accr,
                          -bal_local, -bal_local, -bal_book,
                          None, None, tranid,
                          "Coupon", tradedate, settledate,
                          kdbegin, kdend, ibor_date, "Asset/Liability")
        space.post_journal_entry(relief)

        # 2. Ex-date day recognized as income at the ex-date rate.
        #    Income is a credit (long) -> -exday. Expense a debit
        #    (short) -> faal_inc flips and the sign mirrors naturally
        #    since exday_local is negative for short.
        if exday_local != 0:
            income = Journals(portfolio, investment, 0, 0,
                              ls, location, faal_inc,
                              0, -exday_local, -exday_book,
                              None, None, tranid,
                              "Coupon", tradedate, settledate,
                              kdbegin, kdend, ibor_date,
                              "Revenue/Expense/Capital")
            space.post_journal_entry(income)

        # 3. Collect: cash today if same-day, else open due claim.
        if tradedate == settledate:
            # cash_payment_same_day: +local receipt (long coupon),
            # -local payment (short coupon). coupon_local already
            # carries the right sign; book at ex-date rate.
            currency_domain.cash_payment_same_day(
                portfolio, payment_currency, location, 0,
                coupon_local, coupon_book, space, tranid, "Coupon",
                tradedate, settledate, kdbegin, kdend)
        else:
            # Due claim at the ex-date rate, washed at pay date.
            due = Journals(portfolio, payment_currency, tranid, 0,
                           ls, location, faal_due,
                           coupon_local, coupon_local, coupon_book,
                           None, None, tranid,
                           "Coupon", tradedate, settledate,
                           kdbegin, kdend, ibor_date, "Asset/Liability")
            space.post_journal_entry(due)

        # 4. FXGainAccrued: coupon at ex-rate vs accrued (historical
        #    book) + ex-day (ex-rate). Zero for base by construction.
        fxgl = coupon_book - (bal_book + exday_book)
        if fxgl != 0:
            fxje = Journals(portfolio, payment_currency, 0, 0,
                            ls, location, "FXGainAccrued",
                            0, 0, -fxgl, None, None,
                            tranid, "Coupon", tradedate, settledate,
                            kdbegin, kdend, ibor_date,
                            "Revenue/Expense/Capital")
            space.post_journal_entry(fxje)

        # Local sanity: relief + ex-day must equal the coupon. A
        # residual beyond one day's rounding is an upstream accrual
        # defect -- surfaced, never absorbed.
        eps = coupon_local - (bal_local + exday_local)
        if abs(eps) > 0.02:
            print(f"COUPON WARNING: {portfolio}/{investment} "
                  f"{location}/{ls} coupon {coupon_local:.2f} vs "
                  f"accrued+exday {(bal_local + exday_local):.2f} "
                  f"(eps={eps:.2f}) -- upstream mismatch, Pillar 7 "
                  f"will report.")

    return

def allocate(portfolio,  investment, location, quantity, local, book, fund_structures_space_journal_entries,
            tranid, transaction, tradedate, settledate, kdbegin, kdend, period_start,
            period_cutoff, investment_accounting_space, fund_structures_space, allocation_entities, allocation_currency, allocation_percents):
    print(id(investment_accounting_space.journal_entries))
    print(id(fund_structures_space.journal_entries))

    # Splitting the allocation entities and percentages
    entities = allocation_entities.split(',')
    currency = allocation_currency.split(',')
    percents = [float(p) for p in allocation_percents.split(',')]

    # Ensure entities and percentages match in length
    if len(entities) != len(currency) != len(percents):
        raise ValueError("Mismatch in number of allocation entities and percentages")

    # 1) Fetch all journal entries from investment_accounting_space
    # Make a copy to avoid conflict in spaces

    import copy
    journal_entries_copy = copy.deepcopy(investment_accounting_space.journal_entries)
    manager = bookkeeping.SpaceManager()

    investment_accounting_space.journal_entries.clear()
    investment_accounting_space.asset_liability_entries.clear()
    investment_accounting_space.revenue_expense_entries.clear()
    investment_accounting_space.journal_entries.clear()



    for entry in journal_entries_copy:
        ibor_date = entry.tradedate
        portfolio = entry.portfolio
        investment = entry.investment
        financial_account = entry.financial_account
        quantity = entry.quantity
        local_amount = entry.local
        book_amount = entry.book
        tranid = entry.tranid
        transaction = entry.transaction
        tradedate = entry.tradedate
        settledate = entry.settledate
        kdend = entry.kdend
        entry_type = entry.entry_type
        ls = entry.ls
        tax_date = entry.tax_date
        feeder = entry.feeder


        handled = False  # Add this flag

        # Determine allocation based on feeder
        if entry.feeder and entry.feeder in entities:
            entity_alloc = entry.feeder
            allocated_quantity = quantity
            allocated_local = local_amount
            allocated_book = book_amount

            if feeder == "":
                feeder = entity_alloc

            je = Journals(entity_alloc, investment, tax_date, ls, portfolio, financial_account,
                              allocated_quantity, allocated_local, allocated_book, tranid, transaction, tradedate,
                              settledate, ibor_date, kdend, ibor_date, entry_type, feeder)

            # Add the Journals to fund_structures_space's journal entries
            fund_structures_space.post_journal_entry(je)
            handled = True  # Mark it as handled

        if not handled:  # Only continue if it hasn't been handled already
            # General allocation logic
            for entity_alloc, currency_item, percent in zip(entities, currency, percents):
                allocated_quantity = quantity * (percent / 100)
                allocated_local = local_amount * (percent / 100)
                allocated_book = book_amount * (percent / 100)

                if allocated_local == 0 and allocated_book == 0:
                    continue

                je = Journals(entity_alloc, investment, tax_date, ls, portfolio, financial_account,
                                  allocated_quantity, allocated_local, allocated_book, tranid, transaction, tradedate,
                                  settledate, ibor_date, kdend, ibor_date, entry_type, feeder)

                # Log details of the journal entry
                print(f"Posting entry to fund_structures_space:")
                print(
                    f"Entity: {entity_alloc}, Investment: {investment}, Trade Date: {tradedate}, Transaction: {transaction}")
                # ... Add more details as required ...

                # Add the Journals to fund_structures_space's journal entries
                fund_structures_space.post_journal_entry(je)

    investment_accounting_space.journal_entries = journal_entries_copy
