# ============================================================
# TEST — SHAPE ADAPTER CONSOLE
# ============================================================

from financial_information_gateway.adapters.shape_adapter import run_shape
from financial_information_gateway.projection.projection_engine import run_projection
from financial_information_gateway.rendering.console_renderer import (
    render_summary_with_supporting_journal
)

def filter_rows_by_investment(rows, investment):
    return [r for r in rows if r.get("investment") == investment]

def render_console_table(rows, columns, max_rows=30):
    """
    Simple fixed-width console renderer.
    """

    if not rows:
        print("No rows.")
        return

    # Limit output for sanity
    rows = rows[:max_rows]

    # Determine column widths
    col_widths = {}

    for col in columns:
        max_len = len(col)
        for r in rows:
            val = r.get(col, "")
            val_str = f"{val:,.2f}" if isinstance(val, (int, float)) else str(val)
            max_len = max(max_len, len(val_str))
        col_widths[col] = max_len + 2

    # Header
    header = ""
    for col in columns:
        header += col.ljust(col_widths[col])
    print(header)

    print("-" * len(header))

    # Rows
    for r in rows:
        line = ""
        for col in columns:
            val = r.get(col, "")
            if isinstance(val, (int, float)):
                val_str = f"{val:,.2f}"
            else:
                val_str = str(val)
            line += val_str.ljust(col_widths[col])
        print(line)

    print(f"\nDisplayed {len(rows)} rows\n")

def main():
    portfolio = "Portfolio1"
    calendar = "Monthly"
    period_start = "2024-04"
    period_end = "2024-04"

    mode = "range"  # or "range"
    report_perspective = "complete"

    result = run_shape(
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        mode=mode,
        report_perspective=report_perspective,
        group_by=None,
        uber_filter=None,
        include_je_detail=True,
    )
    # import pprint
    # pprint.pprint(result)
    # print("\n================ META ================")
    # for k, v in result["meta"].items():
    #     print(f"{k}: {v}")
    #
    # print("\n================ DATA TYPE ================")
    # print(result["data"]["type"])

    # ------------------------------------------------------------
    # RANGE MODE
    # ------------------------------------------------------------

    if mode == "range":
        rows = result["data"]["rows"]

        rows = filter_rows_by_investment(rows, "AAPL")

        render_summary_with_supporting_journal(
            rows,
            sort_by="investment"  # or "delta"
        )


    # ------------------------------------------------------------
    # PERIOD_CHAIN MODE
    # ------------------------------------------------------------
    elif mode == "period_chain":

        for p in result["data"]["periods"]:
            print(f"\n=== PERIOD {p['period_name']} ===")

            rows = p["data"]["rows"]

            rows = filter_rows_by_investment(rows, "AAPL")

            render_summary_with_supporting_journal(
                rows,
                sort_by="investment"  # or "delta"
            )

if __name__ == "__main__":
    main()