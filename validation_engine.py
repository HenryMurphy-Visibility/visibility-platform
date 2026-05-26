"""
validation_engine.py
Visibility Platform — Validation Engine

Thin orchestration layer. Reads validation_registry.json, resolves
function names to callables from validation_functions.py, runs them
in the correct sequence, and returns a structured ValidationReport.

Usage (all three lines are the same call — caller sets the line):

    from validation_engine import validate

    # Line 1 — event entry (ops_routes.py)
    report = validate("event", "buy_equity", payload, context, line=1)
    if not report.ok:
        raise HTTPException(400, detail=report.first_error)

    # Line 2 — processing (CPH)
    report = validate("event", method, payload, context, line=2)
    if report.has_errors:
        cph_log.warning(report.summary)

    # Line 3 — proof engine (VAI)
    report = validate("event", method, payload, context, line=3)
    proof.record(report)

Nothing in this file contains business logic.
All logic lives in validation_functions.py.
All rules live in validation_registry.json.
"""

import json
import os
from dataclasses import dataclass, field
from typing      import Any, Optional

from validation_functions import (
    DEFAULT_FUNCTIONS,
    COMPUTE_FUNCTIONS,
    VALIDATE_FUNCTIONS,
    GUARD_FUNCTIONS,
)


# ============================================================
# REGISTRY — loaded once at import, shared across all calls
# ============================================================

_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "validation_registry.json")

def _load_registry() -> dict:
    with open(_REGISTRY_PATH) as f:
        return json.load(f)

_REGISTRY: dict = _load_registry()


def reload_registry() -> None:
    """
    Hot-reload the registry without restarting the server.
    Call from an admin endpoint after registry edits.
    """
    global _REGISTRY
    _REGISTRY = _load_registry()
    print(">>> VALIDATION REGISTRY RELOADED")


# ============================================================
# RESULT TYPES
# ============================================================

@dataclass
class Finding:
    """Single validation finding — error, warning, or info."""
    field:    str
    rule:     str
    message:  str
    severity: str   # "error" | "warning" | "info"
    line:     int   # 1, 2, or 3


@dataclass
class ValidationReport:
    """
    Structured result returned by validate().
    Consumed identically by all three defense lines —
    caller decides what to do with findings based on severity.
    """
    context:    str
    method:     str
    line:       int
    findings:   list[Finding]        = field(default_factory=list)
    computed:   dict[str, Any]       = field(default_factory=dict)
    defaults:   dict[str, Any]       = field(default_factory=dict)
    guards:     dict[str, bool]      = field(default_factory=dict)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    @property
    def ok(self) -> bool:
        """True only if no errors. Warnings do not block."""
        return not self.has_errors

    @property
    def first_error(self) -> str:
        return self.errors[0].message if self.errors else ""

    @property
    def summary(self) -> str:
        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} error(s): " +
                         " | ".join(e.message for e in self.errors))
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s): " +
                         " | ".join(w.message for w in self.warnings))
        return " · ".join(parts) if parts else "OK"


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def validate(
    section:  str,
    method:   str,
    payload:  dict,
    context:  dict,
    line:     int = 1
) -> ValidationReport:
    """
    Run all applicable rules for a given section + method.

    Args:
        section:  Registry section — "event", "portfolio", "investment", "correction"
        method:   Method or sub-context — "buy_equity", "create", "add", "reverse" etc.
        payload:  The data being validated — field name → value dict
        context:  Runtime context — im_record, portfolio_config, portfolio_dir, etc.
        line:     Defense line — 1 (entry), 2 (processing), 3 (proof)

    Returns:
        ValidationReport with findings, computed values, and applied defaults
    """
    report = ValidationReport(context=section, method=method, line=line)

    rule_set = _get_rule_set(section, method)
    if rule_set is None:
        report.findings.append(Finding(
            field="*", rule="registry_lookup",
            message=f"No rule set found for {section}.{method}",
            severity="warning", line=line
        ))
        return report

    # Run in sequence — each phase feeds the next
    _run_defaults(rule_set, payload, context, report, line)
    _run_computed(rule_set, payload, context, report, line)

    # Write computed values back into payload so field_rules can validate
    # them and callers can read the final values from report.computed
    for field, value in report.computed.items():
        if value is not None:
            payload[field] = value

    _run_field_rules(rule_set, payload, context, report, line)
    _run_cross_field_rules(payload, context, report, line)
    _run_guards(rule_set, payload, context, report, line)
    _run_tolerance_checks(rule_set, payload, context, report, line)

    return report


# ============================================================
# PHASE RUNNERS
# ============================================================

def _run_defaults(rule_set: dict, payload: dict, context: dict,
                   report: ValidationReport, line: int) -> None:
    """
    Phase 1 — Apply IM and config defaults to any unpopulated fields.
    Only fires on line 1 (entry). Lines 2 and 3 work with what's there.
    """
    if line != 1:
        return

    # Investment-type defaults (from investment_types section)
    inv_type = _resolve_investment_type(rule_set)
    if inv_type:
        type_rules = _REGISTRY.get("investment_types", {}).get(inv_type, {})
        for default in type_rules.get("defaults", []):
            if isinstance(default, dict) and "field" in default:
                _apply_default(default, payload, context, report, line)

    # Method-level defaults — can be a list of rule dicts OR a simple {field: value} dict
    raw_defaults = rule_set.get("defaults", [])
    if isinstance(raw_defaults, dict):
        # Simple default values — apply directly if field not already set
        for field_name, value in raw_defaults.items():
            if not payload.get(field_name):
                payload[field_name] = value
                report.defaults[field_name] = value
    else:
        for default in raw_defaults:
            if isinstance(default, dict) and "field" in default:
                _apply_default(default, payload, context, report, line)


def _apply_default(default: dict, payload: dict, context: dict,
                    report: ValidationReport, line: int) -> None:
    """Apply a single default rule."""
    target   = default.get("field")
    fn_name  = default.get("default_fn")
    args     = default.get("args", {})
    override = default.get("overridable", True)

    # Skip if field already has a value and is not overridable
    if target in payload and payload[target] and not override:
        return
    # Skip if already user-supplied
    if target in payload and payload.get(f"_{target}_user_supplied"):
        return

    fn = DEFAULT_FUNCTIONS.get(fn_name)
    if fn is None:
        return

    try:
        # Build kwargs — merge args with available context
        kwargs = _build_kwargs(fn, args, payload, context)
        result = fn(**kwargs)
        if result and result.value is not None:
            report.defaults[target] = result.value
            # Only write to payload if field is empty
            if not payload.get(target):
                payload[target] = result.value
    except Exception as e:
        report.findings.append(Finding(
            field=target, rule=f"default:{fn_name}",
            message=f"Default resolution failed: {e}",
            severity="info", line=line
        ))


def _run_computed(rule_set: dict, payload: dict, context: dict,
                   report: ValidationReport, line: int) -> None:
    """
    Phase 2 — Run computed field formulas.
    On line 1: only fires if trigger fields are present and non-zero.
    On lines 2+3: always runs for verification.
    """
    inv_type  = _resolve_investment_type(rule_set)
    type_rules = _REGISTRY.get("investment_types", {}).get(inv_type, {}) if inv_type else {}

    def _norm_computed(val):
        """
        Normalise computed to a list of rule dicts.
        Handles three registry shapes:
          list of dicts  → new schema, already correct
          dict of dicts  → {field: {compute_fn, on_exit, ...}}
          dict of strings → {field: "formula string"} — legacy, no engine hook yet
        """
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            result = []
            for k, v in val.items():
                if isinstance(v, dict):
                    result.append({"field": k, **v})
                # string formulas are registry docs only — no compute_fn, skip
            return result
        return []

    computed_rules = _norm_computed(type_rules.get("computed", [])) + \
                     _norm_computed(rule_set.get("computed", []))

    for rule in computed_rules:
        target  = rule.get("field")
        fn_name = rule.get("compute_fn")
        on_exit = rule.get("on_exit", [])

        # Line 1: skip if trigger fields not all present and non-None
        if line == 1:
            if not all(payload.get(f) is not None and payload.get(f) != "" for f in on_exit):
                continue
            # Also skip if trigger field value is zero — not enough data yet
            if not all(payload.get(f) for f in on_exit if f in ("quantity", "price")):
                continue
            # Skip if user has manually overridden this field
            if payload.get(f"_{target}_user_supplied"):
                continue

        # Pre-resolve FX rate before local_times_fx runs
        if fn_name == "local_times_fx":
            if "fx_rate" not in payload:
                from validation_functions import get_file_fx_rate
                payment_ccy = payload.get("payment_currency", "USD")
                base_ccy    = context.get("base_currency", "USD")
                trade_date  = payload.get("tradedate", "")
                refdata     = context.get("refdata_path")
                rate = get_file_fx_rate(payment_ccy, base_ccy, trade_date, refdata)
                if rate is not None:
                    payload["fx_rate"] = rate
                else:
                    payload["fx_rate"] = 1.0
                    if payment_ccy != base_ccy:
                        report.findings.append(Finding(
                            field="fx_rate", rule="fx_lookup",
                            message=f"FX rate not found for {payment_ccy}/{base_ccy} on {trade_date} — using 1.0",
                            severity="warning", line=line
                        ))
            # local_times_fx expects local_amount — always map from total_amount
            payload["local_amount"] = payload.get("total_amount", 0.0)

        fn = COMPUTE_FUNCTIONS.get(fn_name)
        if fn is None:
            continue

        try:
            kwargs = _build_kwargs(fn, {}, payload, context)
            result = fn(**kwargs)
            if result:
                report.computed[target] = result.value
                # On line 1: write computed value into payload for downstream phases
                if line == 1:
                    payload[target] = result.value
        except Exception as e:
            report.findings.append(Finding(
                field=target, rule=f"compute:{fn_name}",
                message=f"Computation failed: {e}",
                severity="info", line=line
            ))


def _run_field_rules(rule_set: dict, payload: dict, context: dict,
                      report: ValidationReport, line: int) -> None:
    """
    Phase 3 — Field-level validation rules.
    Required fields, enum checks, format validation, range checks.
    """
    # Required fields
    for f in rule_set.get("required", []):
        val = payload.get(f)
        if val is None or val == "" or val == 0:
            report.findings.append(Finding(
                field=f, rule="required",
                message=f"{f} is required",
                severity="error", line=line
            ))

    # Blocked fields — should not be present or non-zero
    for f in rule_set.get("blocked", []):
        val = payload.get(f)
        if val and val != 0:
            report.findings.append(Finding(
                field=f, rule="blocked",
                message=f"{f} should not be set for {rule_set.get('label', 'this method')}",
                severity="warning", line=line
            ))

    # Named field rules — including absent fields for required_if_type checks
    for field_name, rules in rule_set.get("field_rules", {}).items():
        val = payload.get(field_name)  # may be None if field absent

        for rule_name, rule_val in rules.items():
            if rule_name in ("message", "notes", "status"):
                continue
            # Skip all rules except required_if_type when field is absent
            if val is None and rule_name != "required_if_type":
                continue
            result = _apply_field_rule(field_name, val, rule_name, rule_val, payload, rules)
            if result and not result.valid:
                report.findings.append(Finding(
                    field=field_name, rule=rule_name,
                    message=result.message,
                    severity=result.severity, line=line
                ))


def _apply_field_rule(field_name: str, value: Any, rule_name: str,
                       rule_val: Any, payload: dict, rule_dict: dict = None):
    """Dispatch a single field rule to the appropriate validate function."""
    from validation_functions import (
        validate_gt_zero, validate_enum, validate_required,
        ValidationResult
    )
    rule_dict = rule_dict or {}

    if rule_name == "gt" and rule_val == 0:
        return validate_gt_zero(value, field_name)

    if rule_name == "enum":
        return validate_enum(value, rule_val, field_name)

    if rule_name == "lte":
        if isinstance(value, (int, float)) and value > rule_val:
            sev = rule_dict.get("severity", "warning")
            msg = rule_dict.get("message", f"{field_name} {value} exceeds maximum {rule_val}")
            return ValidationResult(False, msg, severity=sev)

    if rule_name == "pattern":
        import re
        if not re.match(rule_val, str(value or "")):
            msg = rule_dict.get("message", f"{field_name} format invalid")
            return ValidationResult(False, msg)

    if rule_name == "ne_field":
        other = payload.get(rule_val)
        if other and value == other:
            msg = rule_dict.get("message", f"{field_name} cannot equal {rule_val}")
            return ValidationResult(False, msg)

    if rule_name == "required_if_type":
        inv_type = payload.get("investment_type", "")
        if inv_type == rule_val and (value is None or value == "" or value == 0):
            msg = rule_dict.get("message", f"{field_name} is required for {rule_val}")
            return ValidationResult(False, msg)

    if rule_name == "gt_if_present":
        if value is not None and value != "":
            try:
                if float(value) <= float(rule_val):
                    msg = rule_dict.get("message", f"{field_name} must be greater than {rule_val}")
                    return ValidationResult(False, msg)
            except (ValueError, TypeError):
                pass

    return None


def _run_cross_field_rules(payload: dict, context: dict,
                             report: ValidationReport, line: int) -> None:
    """
    Phase 4 — Cross-field rules from registry.cross_field_rules.
    Only runs rules whose `lines` list includes the current line.
    """
    for rule in _REGISTRY.get("cross_field_rules", {}).get("rules", []):
        rule_lines = rule.get("lines", [1, 2, 3])
        if line not in rule_lines:
            continue

        rule_id  = rule.get("id")
        fn_name  = rule.get("validate_fn")
        severity = rule.get("severity", "error")

        fn = VALIDATE_FUNCTIONS.get(fn_name)
        if fn is None:
            continue

        try:
            kwargs = _build_kwargs(fn, rule.get("args", {}), payload, context)
            result = fn(**kwargs)
            if result and not result.valid:
                report.findings.append(Finding(
                    field="*", rule=rule_id,
                    message=result.message,
                    severity=severity, line=line
                ))
        except Exception:
            # Cross-field rules are best-effort — missing context is not an error
            pass


def _run_guards(rule_set: dict, payload: dict, context: dict,
                 report: ValidationReport, line: int) -> None:
    """
    Phase 5 — Guard functions. Pre-write state checks.
    Query positions, existence, duplicates.
    Only runs on line 1 (entry) and line 2 (processing).
    Line 3 (proof) works on already-committed data.
    """
    if line == 3:
        return

    for guard in rule_set.get("guards", []):
        fn_name  = guard.get("guard_fn") or guard.get("rule")
        message  = guard.get("message", f"Guard {fn_name} failed")

        fn = GUARD_FUNCTIONS.get(fn_name)
        if fn is None:
            continue

        try:
            kwargs = _build_kwargs(fn, {}, payload, context)
            result = fn(**kwargs)
            report.guards[fn_name] = result.passed
            if not result.passed:
                report.findings.append(Finding(
                    field="*", rule=fn_name,
                    message=result.message or message,
                    severity="error", line=line
                ))
        except Exception as e:
            # Guard failed to run — treat as warning not error
            report.findings.append(Finding(
                field="*", rule=fn_name,
                message=f"Guard check skipped: {e}",
                severity="info", line=line
            ))


def _run_tolerance_checks(rule_set: dict, payload: dict, context: dict,
                            report: ValidationReport, line: int) -> None:
    """
    Phase 6 — Market tolerance checks.
    Compares user-entered values against file reference values.
    Fires on all three lines — severity response differs by caller.
    """
    tolerance_config = _REGISTRY.get("platform", {}).get("tolerance_bands", {})
    fields_config    = tolerance_config.get("fields", {})
    fn               = VALIDATE_FUNCTIONS.get("market_tolerance")

    if not fn:
        return

    for field_name, band_config in fields_config.items():
        user_value = payload.get(field_name)
        if user_value is None:
            continue

        # Only check fields that were user-supplied on line 1
        if line == 1 and not payload.get(f"_{field_name}_user_supplied"):
            continue

        # Get reference value from context
        ref_fn_name  = band_config.get("reference_fn")
        file_value   = context.get(f"file_{field_name}")  # pre-resolved by caller
        if file_value is None:
            continue

        tolerance_pct = band_config.get("tolerance_pct", 5.0)

        try:
            result = fn(
                user_value    = float(user_value),
                file_value    = float(file_value),
                field         = field_name,
                tolerance_pct = tolerance_pct,
                line          = line
            )
            if result and not result.valid:
                report.findings.append(Finding(
                    field    = field_name,
                    rule     = "market_tolerance",
                    message  = result.message,
                    severity = band_config.get("severity", "warning"),
                    line     = line
                ))
        except Exception:
            pass


# ============================================================
# HELPERS
# ============================================================

def _get_rule_set(section: str, method: str) -> Optional[dict]:
    """
    Resolve the correct rule set from the registry.
    Handles all section/method combinations.
    """
    section_map = {
        "event":       ("methods",      method),
        "portfolio":   ("portfolios",   method),
        "investment":  ("investments",  method),
        "correction":  ("corrections",  method),
        "mark":        ("marks",        method),
    }
    if section not in section_map:
        return None
    reg_section, reg_key = section_map[section]
    return _REGISTRY.get(reg_section, {}).get(reg_key)


def _resolve_investment_type(rule_set: dict) -> Optional[str]:
    """Get the investment_type for a method rule set."""
    return rule_set.get("investment_type")


def _build_kwargs(fn, args: dict, payload: dict, context: dict) -> dict:
    """
    Build kwargs for a function call by inspecting its parameter names
    and resolving them from args, payload, then context.
    Priority: args > payload > context

    Args values prefixed with $ are resolved from payload at runtime.
    e.g. {"trade_date": "$tradedate"} → kwargs["trade_date"] = payload["tradedate"]
    """
    import inspect
    sig     = inspect.signature(fn)
    kwargs  = {}

    # Resolve $-prefixed arg references from payload
    resolved_args = {}
    for k, v in args.items():
        if isinstance(v, str) and v.startswith("$"):
            resolved_args[k] = payload.get(v[1:])
        else:
            resolved_args[k] = v

    sources = {**context, **payload, **resolved_args}

    for param_name, param in sig.parameters.items():
        if param_name in sources:
            val = sources[param_name]
            # Coerce string numerics to float for compute functions
            # CSV values come through as strings — functions expect float
            ann = fn.__annotations__.get(param_name)
            if ann is float and isinstance(val, str):
                try:
                    val = float(val)
                except (ValueError, TypeError):
                    val = 0.0
            kwargs[param_name] = val
        elif param.default is not inspect.Parameter.empty:
            pass  # has a default — fine to omit

    return kwargs


# ============================================================
# CONVENIENCE WRAPPERS
# One-liner calls for the most common validation paths
# ============================================================

def validate_event(method: str, payload: dict, context: dict,
                    line: int = 1) -> ValidationReport:
    return validate("event", method, payload, context, line)


def validate_portfolio_create(payload: dict, line: int = 1) -> ValidationReport:
    return validate("portfolio", "create", payload, {}, line)


def validate_portfolio_update_method(payload: dict, context: dict,
                                      line: int = 1) -> ValidationReport:
    return validate("portfolio", "update_method", payload, context, line)


def validate_investment_add(payload: dict, context: dict,
                              line: int = 1) -> ValidationReport:
    return validate("investment", "add", payload, context, line)


def validate_correction(action: str, payload: dict, context: dict,
                         line: int = 1) -> ValidationReport:
    return validate("correction", action, payload, context, line)