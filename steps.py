# -------------------------------------------------------------
# steps_map.py
# -------------------------------------------------------------
# Declarative mapping of events → step sequence → domain function.
# Used by process_events() to schedule each function in order.
# -------------------------------------------------------------

EVENT_STEPS_SPEC = {
    # === TRADES ==========================================================
    "buy_equity": {
        "type": "TRADES",
        "steps": [
            ("OPEN_POSITION", "equity_domain.buy_equity"),
            ("OPEN_PAYABLE", "currency_domain.open_payable"),
            ("CLOSE_PR_OUT", "currency_domain.settle_single_flow_out")
        ]
    },

    "buy_bond": {
        "type": "TRADES",
        "steps": [
            ("OPEN_POSITION_ACCRUAL", "bond_domain.buy_bond"),
            ("OPEN_PAYABLE", "currency_domain.open_payable"),
            ("OPEN_PAYABLE_ACCRUED", "currency_domain.open_payable"),
            ("CLOSE_PR_BOND_OUT", "currency_domain.settle_bond_flows_out"),
            ("UPDATE_SMF", "bond_domain.schedule_update_af_record_status")
        ]
    },

    "buy_future": {
        "type": "TRADES",
        "steps": [
            ("OPEN_POSITION", "futures_domain.buy_future"),
            ("OPEN_PAYABLE", "currency_domain.open_payable"),
            ("CLOSE_PR_OUT", "currency_domain.settle_single_flow_out")
        ]
    },

    "sell_equity": {
        "type": "TRADES",
        "steps": [
            ("CLOSE_POSITION", "equity_domain.sell_equity"),
            ("OPEN_RECEIVABLE", "currency_domain.open_receivable"),
            ("CLOSE_PR_IN", "currency_domain.settle_single_flow_in")
        ]
    },

    "sell_bond": {
        "type": "TRADES",
        "steps": [
            ("CLOSE_POSITION_ACCRUED", "bond_domain.sell_bond"),
            ("OPEN_RECEIVABLE", "currency_domain.open_receivable"),
            ("OPEN_RECEIVABLE_ACCRUED", "currency_domain.open_receivable"),
            ("CLOSE_PR_BOND_IN", "currency_domain.settle_bond_flows_in"),
            ("UPDATE_SMF", "bond_domain.schedule_update_af_record_status")
        ]
    },

    "sell_future": {
        "type": "TRADES",
        "steps": [
            ("CLOSE_POSITION", "futures_domain.sell_future"),
            ("OPEN_PAYABLE", "currency_domain.open_payable"),
            ("CLOSE_PR_BY_ID", "currency_domain.settle_pay_rec_by_tranid")
        ]
    },

    "short_equity": {
        "type": "TRADES",
        "steps": [
            ("OPEN_POSITION", "equity_domain.short_equity"),
            ("OPEN_RECEIVABLE", "currency_domain.open_receivable"),
            ("CLOSE_PR_IN", "currency_domain.settle_single_flow_in")
        ]
    },

    "short_bond": {
        "type": "TRADES",
        "steps": [
            ("OPEN_POSITION_ACCRUAL", "bond_domain.short_bond"),
            ("OPEN_RECEIVABLE", "currency_domain.open_receivable"),
            ("OPEN_RECEIVABLE_ACCRUED", "currency_domain.open_receivable"),
            ("CLOSE_PR_BOND_IN", "currency_domain.settle_bond_flows_in"),
            ("UPDATE_SMF", "bond_domain.schedule_update_af_record_status")
        ]
    },

    "short_future": {
        "type": "TRADES",
        "steps": [
            ("OPEN_POSITION", "futures_domain.short_future"),
            ("OPEN_PAYABLE", "currency_domain.open_payable"),
            ("CLOSE_PR_OUT", "currency_domain.settle_single_flow_out")
        ]
    },

    "cover_equity": {
        "type": "TRADES",
        "steps": [
            ("CLOSE_POSITION", "equity_domain.cover_equity"),
            ("OPEN_PAYABLE", "currency_domain.open_payable"),
            ("CLOSE_PR_OUT", "currency_domain.settle_single_flow_out")
        ]
    },

    "cover_bond": {
        "type": "TRADES",
        "steps": [
            ("CLOSE_POSITION_ACCRUED", "bond_domain.cover_bond"),
            ("OPEN_PAYABLE", "currency_domain.open_payable"),
            ("OPEN_PAYABLE_ACCRUED", "currency_domain.open_payable"),
            ("CLOSE_PR_OUT", "currency_domain.settle_bond_flows_out"),
            ("UPDATE_SMF", "bond_domain.schedule_update_af_record_status")
        ]
    },

    "cover_future": {
        "type": "TRADES",
        "steps": [
            ("CLOSE_POSITION", "futures_domain.cover_future"),
            ("OPEN_PAYABLE", "currency_domain.open_payable"),
            ("CLOSE_PR_BY_ID", "currency_domain.settle_pay_rec_by_tranid")
        ]
    },

    # === CORPORATE ACTIONS ===============================================
    "dividend_equity": {
        "type": "CORP_ACTION",
        "steps": [
            ("CREATE_DIVIDEND", "equity_domain.dividend_equity"),
            ("CLOSE_PR_OUT", "currency_domain.settle_multiple_flows_in_out")
        ]
    },

    "bond_coupon": {
        "type": "CORP_ACTION",
        "steps": [
            ("CREATE_COUPON", "bond_domain.bond_coupon"),
            ("CLOSE_PR_OUT", "currency_domain.settle_multiple_flows_in_out")
        ]
    },

    "split_equity": {
        "type": "CORP_ACTION",
        "steps": [
            ("CREATE_SPLIT", "equity_domain.split_equity")
        ]
    },

    # === CAPITAL ACTIONS =================================================
    "deposit_currency": {
        "type": "CAPITAL_ACTION",
        "steps": [
            ("RECEIVE_CASH", "currency_domain.deposit_currency")
        ]
    },

    "withdraw_currency": {
        "type": "CAPITAL_ACTION",
        "steps": [
            ("WITHDRAW_CASH", "currency_domain.withdraw_currency")
        ]
    },

    "expense": {
        "type": "PAYMENTS",
        "steps": [
            ("EXPENSES", "currency_domain.expense")
        ]
    },

    # === SWAPS ===========================================================
    "open_equity_swap_long": {
        "type": "SWAPS",
        "steps": [
            ("OPEN_SWAP_LONG", "swaps_domain.open_equity_swap_long")
        ]
    },

    "open_equity_swap_short": {
        "type": "SWAPS",
        "steps": [
            ("OPEN_SWAP_SHORT", "swaps_domain.open_equity_swap_short")
        ]
    },

    # === FX TRADES =======================================================
    "spot_fx": {
        "type": "FX_TRADES",
        "steps": [
            ("FX_OPEN_POSITION", "currency_domain.spot_fx"),
            ("CLOSE_PRIN_IN", "currency_domain.settle_single_flow_in"),
            ("CLOSE_PRIN_OUT", "currency_domain.settle_single_flow_out")
        ]
    },

    # === OPTION ASSIGNMENTS & EXERCISES =================================
    "assign_call_long": {
        "type": "TRADES",
        "steps": [
            ("ASSIGN_CALL_LONG", "equity_domain.assign_call_long"),
            ("CLOSE_PR_BY_ID", "currency_domain.settle_pay_rec_by_tranid")
        ]
    },

    "assign_put_long": {
        "type": "TRADES",
        "steps": [
            ("ASSIGN_PUT_LONG", "equity_domain.assign_put_long"),
            ("CLOSE_PR_BY_ID", "currency_domain.settle_pay_rec_by_tranid")
        ]
    },

    "assign_call_short": {
        "type": "TRADES",
        "steps": [
            ("ASSIGN_CALL_SHORT", "equity_domain.assign_call_short"),
            ("CLOSE_PR_BY_ID", "currency_domain.settle_pay_rec_by_tranid")
        ]
    },

    "assign_put_short": {
        "type": "TRADES",
        "steps": [
            ("ASSIGN_PUT_SHORT", "equity_domain.assign_put_short"),
            ("CLOSE_PR_BY_ID", "currency_domain.settle_pay_rec_by_tranid")
        ]
    },

    "exercise_call_long": {
        "type": "TRADES",
        "steps": [
            ("EXERCISE_CALL_LONG", "equity_domain.exercise_call_long"),
            ("CLOSE_PR_BY_ID", "currency_domain.settle_pay_rec_by_tranid")
        ]
    },

    "exercise_put_long": {
        "type": "TRADES",
        "steps": [
            ("EXERCISE_PUT_LONG", "equity_domain.exercise_put_long"),
            ("CLOSE_PR_BY_ID", "currency_domain.settle_pay_rec_by_tranid")
        ]
    },

    "exercise_call_short": {
        "type": "TRADES",
        "steps": [
            ("EXERCISE_CALL_SHORT", "equity_domain.exercise_call_short"),
            ("CLOSE_PR_BY_ID", "currency_domain.settle_pay_rec_by_tranid")
        ]
    },

    "exercise_put_short": {
        "type": "TRADES",
        "steps": [
            ("EXERCISE_PUT_SHORT", "equity_domain.exercise_put_short"),
            ("CLOSE_PR_BY_ID", "currency_domain.settle_pay_rec_by_tranid")
        ]
    },
}

# -------------------------------------------------------------
# validate_steps.py   (or add to bottom of steps.py)
# -------------------------------------------------------------
# Confirms every module.function path in EVENT_STEPS_SPEC exists.
# -------------------------------------------------------------

import importlib
import inspect
from steps import EVENT_STEPS_SPEC   # same file if colocated

def validate_event_steps():
    print("🔍 Validating EVENT_STEPS_SPEC mappings...\n")

    ok_count = 0
    error_count = 0
    missing_modules = set()

    for event, spec in EVENT_STEPS_SPEC.items():
        for step_name, func_path in spec["steps"]:
            try:
                module_name, func_name = func_path.split(".")
                module = importlib.import_module(module_name)

                if not hasattr(module, func_name):
                    print(f"❌ {event}: {func_path} — function not found")
                    error_count += 1
                    continue

                func = getattr(module, func_name)
                if not inspect.isfunction(func):
                    print(f"⚠️ {event}: {func_path} exists but is not callable")
                    error_count += 1
                else:
                    ok_count += 1

            except ModuleNotFoundError:
                print(f"🚫 {event}: module '{module_name}' not found")
                missing_modules.add(module_name)
                error_count += 1

            except Exception as e:
                print(f"❗ {event}: {func_path} — {type(e).__name__}: {e}")
                error_count += 1

    print("\n✅ Validation complete.")
    print(f"   Total OK: {ok_count}")
    print(f"   Total errors: {error_count}")
    if missing_modules:
        print(f"   Missing modules: {', '.join(sorted(missing_modules))}")

if __name__ == "__main__":
    validate_event_steps()
