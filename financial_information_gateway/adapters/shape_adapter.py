# ============================================================
# VISIBILITY — SHAPE ADAPTER
# Thin transformation layer between FIG and GWI
# ============================================================

from typing import Dict, Any

from financial_information_gateway.fig import run_box_balance_view

from financial_information_gateway.user_specifications.shape_classifications import (
    FA_ORDER_WITHIN_CLASS,
    STATEMENT_ORDER,
    STATEMENT_CLASS,
    COA,
)

from financial_information_gateway.user_specifications.shape_definitions import SHAPES

from financial_information_gateway.projection.projection_engine import run_projection


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

def run_shape(
    portfolio: str,
    calendar: str,
    period_start: str,
    period_end: str,
    mode: str,
    report_perspective: str,
    group_by=None,
    uber_filter=None,
    include_je_detail: bool = True,
    period_chain_render_order: str = "period_first",
    shape: str = "rollover",
) -> Dict[str, Any]:

    fig_result = run_box_balance_view(
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        uber_filter=uber_filter,
        group_by=group_by,
        include_je_detail=include_je_detail,
        mode=mode,
        period_chain_render_order=period_chain_render_order,
    )

    meta = {
        "portfolio": portfolio,
        "calendar": calendar,
        "period_start": period_start,
        "period_end": period_end,
        "mode": mode,
        "report_perspective": report_perspective,
        "shape": shape,
    }

    shape_def = SHAPES.get(shape)
    if not shape_def:
        raise ValueError(f"Unknown shape: {shape}")

    # ============================================================
    # RANGE MODE
    # ============================================================

    if mode == "range":

        container = _dispatch_range_transform(report_perspective, fig_result)
        rows = container["rows"]

        # ------------------------------------------------------------
        # Attach statement_class IF required by shape grouping
        # ------------------------------------------------------------

        summary_group_by = shape_def["summary"]["group_by"]

        if summary_group_by and "statement_class" in summary_group_by:
            for row in rows:
                row["statement_class"] = STATEMENT_CLASS.get(
                    row.get("financial_account"),
                    "UNCLASSIFIED"
                )

        # ------------------------------------------------------------
        # SUMMARY FILTER
        # ------------------------------------------------------------

        summary_accounts = shape_def["summary"]["include_accounts"]

        if summary_accounts != "ALL":
            summary_rows = [
                r for r in rows
                if r["financial_account"] in summary_accounts
            ]
        else:
            summary_rows = rows

        # ------------------------------------------------------------
        # SUMMARY PROJECTION (if defined)
        # ------------------------------------------------------------

        if summary_group_by:
            summary_tree = run_projection(
                summary_rows,
                group_by=summary_group_by,
            )
        else:
            summary_tree = None

        # ------------------------------------------------------------
        # DETAIL FILTER
        # ------------------------------------------------------------

        detail_accounts = shape_def["detail"]["include_accounts"]

        if detail_accounts != "ALL":
            detail_rows = [
                r for r in rows
                if r["financial_account"] in detail_accounts
            ]
        else:
            detail_rows = rows

        # Keep original container contract intact
        return {
            "meta": meta,
            "data": {
                "type": container["type"],
                "summary_rows": summary_rows,
                "summary_tree": summary_tree,
                "detail_rows": detail_rows,
                "is_valid": container.get("is_valid"),
                "validation_failures": container.get("validation_failures"),
            }
        }

    # ============================================================
    # PERIOD CHAIN MODE
    # ============================================================

    elif mode == "period_chain":

        period_results = fig_result["period_results"]
        periods_output = []

        for period_name, state_single in period_results:

            container = _dispatch_range_transform(report_perspective, state_single)
            rows = container["rows"]

            summary_group_by = shape_def["summary"]["group_by"]

            if summary_group_by and "statement_class" in summary_group_by:
                for row in rows:
                    row["statement_class"] = STATEMENT_CLASS.get(
                        row.get("financial_account"),
                        "UNCLASSIFIED"
                    )

            summary_accounts = shape_def["summary"]["include_accounts"]

            if summary_accounts != "ALL":
                summary_rows = [
                    r for r in rows
                    if r["financial_account"] in summary_accounts
                ]
            else:
                summary_rows = rows

            if summary_group_by:
                summary_tree = run_projection(
                    summary_rows,
                    group_by=summary_group_by,
                )
            else:
                summary_tree = None

            detail_accounts = shape_def["detail"]["include_accounts"]

            if detail_accounts != "ALL":
                detail_rows = [
                    r for r in rows
                    if r["financial_account"] in detail_accounts
                ]
            else:
                detail_rows = rows

            periods_output.append({
                "period_name": period_name,
                "type": container["type"],
                "summary_rows": summary_rows,
                "summary_tree": summary_tree,
                "detail_rows": detail_rows,
                "is_valid": container.get("is_valid"),
                "validation_failures": container.get("validation_failures"),
            })

        return {
            "meta": meta,
            "data": {
                "type": report_perspective,
                "periods": periods_output
            }
        }

    else:
        raise ValueError(f"Unknown mode: {mode}")
# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

def _dispatch_range_transform(report_perspective, state):
    if report_perspective == "positions":
        return _transform_range_positions(state)

    elif report_perspective == "journals":
        return _transform_range_journals(state)

    elif report_perspective == "complete":
        return _transform_range_complete(state)

    else:
        raise ValueError(f"Unknown report_perspective: {report_perspective}")


# ============================================================
# RANGE TRANSFORMS
# ============================================================

def _transform_range_positions(state) -> Dict[str, Any]:
    rows = []

    for key, bal in state.balances.items():
        investment, location, ls, financial_account = key

        row = {
            "row_type": "position",
            "investment": investment,
            "location": location,
            "ls": ls,
            "financial_account": financial_account,
            "closing_qty": bal["closing_qty"],
            "closing_local": bal["closing_local"],
            "closing_book": bal["closing_book"],
        }

        rows.append(row)

    return {
        "type": "positions",
        "rows": rows,
        "is_valid": state.is_valid,
        "validation_failures": state.validation_failures,
    }


def _transform_range_journals(state) -> Dict[str, Any]:
    rows = []

    for key, bal in state.balances.items():

        investment, location, ls, financial_account = key

        for line in bal.get("je_lines", []):
            row = {
                "row_type": "journal",
                "investment": investment,
                "location": location,
                "ls": ls,
                "financial_account": financial_account,
                **line
            }

            rows.append(row)

    return {
        "type": "journals",
        "rows": rows,
        "is_valid": state.is_valid,
        "validation_failures": state.validation_failures,
    }


def _transform_range_complete(state) -> Dict[str, Any]:
    rows = []

    for key, bal in state.balances.items():
        investment, location, ls, financial_account = key

        opening_qty = bal["opening_qty"]
        opening_local = bal["opening_local"]
        opening_book = bal["opening_book"]

        movement_qty = bal["movement_qty"]
        movement_local = bal["movement_local"]
        movement_book = bal["movement_book"]

        closing_qty = bal["closing_qty"]
        closing_local = bal["closing_local"]
        closing_book = bal["closing_book"]

        # Delta = closing − opening
        delta_qty = closing_qty - opening_qty
        delta_local = closing_local - opening_local
        delta_book = closing_book - opening_book

        row = {
            "row_type": "complete",
            "investment": investment,
            "location": location,
            "ls": ls,
            "financial_account": financial_account,

            "opening_qty": opening_qty,
            "delta_qty": delta_qty,
            "closing_qty": closing_qty,

            "opening_local": opening_local,
            "delta_local": delta_local,
            "closing_local": closing_local,

            "opening_book": opening_book,
            "delta_book": delta_book,
            "closing_book": closing_book,

            "movement_qty": movement_qty,
            "movement_local": movement_local,
            "movement_book": movement_book,

            "je_lines": bal.get("je_lines", []),
        }

        rows.append(row)

    return {
        "type": "complete",
        "rows": rows,
        "is_valid": state.is_valid,
        "validation_failures": state.validation_failures,
    }
