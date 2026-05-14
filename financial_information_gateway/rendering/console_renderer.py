# ============================================================
# shape_rendering_utility.py
# ============================================================

from typing import Dict, Any, List


def render_tree(node: Dict[str, Any], indent: int = 0):
    """
    Recursively render a structured shape tree.

    Expected node structure:
    {
        "label": str,
        "opening": dict (optional),
        "delta": dict (optional),
        "closing": dict (optional),
        "children": [node, node, ...]
    }
    """

    prefix = "  " * indent

    label = node.get("label", "")
    print(f"{prefix}{label}")

    # Render balances if present
    if "opening" in node:
        print(f"{prefix}  Opening: {_clean_dict(node.get('opening'))}")

    if "delta" in node:
        print(f"{prefix}  Delta:   {_clean_dict(node.get('delta'))}")

    if "closing" in node:
        print(f"{prefix}  Closing: {_clean_dict(node.get('closing'))}")

    # Recurse
    for child in node.get("children", []):
        render_tree(child, indent + 1)


# ------------------------------------------------------------
# Utility helpers
# ------------------------------------------------------------

def _clean_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove None values and empty dicts
    for cleaner console output.
    """
    if not d:
        return {}

    return {k: v for k, v in d.items() if v not in (None, {}, [])}


# ------------------------------------------------------------
# Optional pretty divider
# ------------------------------------------------------------

def render_header(title: str):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60 + "\n")

from typing import Any


DISPLAY_TOLERANCE = 0.0001


# ============================================================
# console_renderer.py
# ============================================================

def render_box_balance_console(structured_state):
    balances = structured_state.balances

    print("\n==============================================================")
    print("BOX BALANCE VIEW")
    print("==============================================================\n")

    for key, bal in sorted(balances.items()):

        diff_book = (
                bal["opening_book"]
                + bal["movement_book"]
                - bal["closing_book"]
        )

        diff_local = (
                bal["opening_local"]
                + bal["movement_local"]
                - bal["closing_local"]
        )

        diff_qty = (
                bal["opening_qty"]
                + bal["movement_qty"]
                - bal["closing_qty"]
        )

        print(f"KEY: {key}")
        print(
            f"  OPEN  | QTY {bal['opening_qty']:.4f} | LOCAL {bal['opening_local']:.2f} | BOOK {bal['opening_book']:.2f}")
        print(
            f"  MOVE  | QTY {bal['movement_qty']:.4f} | LOCAL {bal['movement_local']:.2f} | BOOK {bal['movement_book']:.2f}")
        print(
            f"  CLOSE | QTY {bal['closing_qty']:.4f} | LOCAL {bal['closing_local']:.2f} | BOOK {bal['closing_book']:.2f}")
        print(f"  DIFF  | QTY {diff_qty:.4f} | LOCAL {diff_local:.2f} | BOOK {diff_book:.2f}")

        if bal["je_lines"]:
            print("    JE DETAIL:")
            for line in sorted(bal["je_lines"], key=lambda x: x["sequence"]):
                print(
                    f"      {line['date']} | "
                    f"SEQ {line['sequence']} | "
                    f"TXN {line['transaction']} | "
                    f"TRANID {line['tranid']} | "
                    f"LOT {line['lotid']} | "
                    f"TAX {line['tax_date']} | "
                    f"FA {line['financial_account']} | "
                    f"QTY {line['qty']:.4f} | "
                    f"LOCAL {line['local']:.2f} | "
                    f"BOOK {line['book']:.2f}"
                )
        else:
            print("    JE DETAIL: NONE")

        print("")

# ============================================================
# Console Rollforward Renderer
# ============================================================

def render_summary_with_supporting_journal(rows, sort_by="investment"):
    """
    Renders:

    1) Aggregated summary (Open / Delta / Close)
       For qty, local, and book
    2) Supporting JE detail below (qty, local, book)

    Expects rows = list[dict] from complete perspective.
    """

    if not rows:
        print("No rows.")
        return

    # ---------------------------------------------------------
    # Aggregate summary by investment
    # ---------------------------------------------------------

    summary = {}

    for r in rows:
        inv = r["investment"]

        if inv not in summary:
            summary[inv] = {
                "opening_qty": 0.0,
                "delta_qty": 0.0,
                "closing_qty": 0.0,
                "opening_local": 0.0,
                "delta_local": 0.0,
                "closing_local": 0.0,
                "opening_book": 0.0,
                "delta_book": 0.0,
                "closing_book": 0.0,
            }

        for field in summary[inv]:
            summary[inv][field] += r.get(field, 0.0)

    # Sorting
    if sort_by == "delta":
        sorted_items = sorted(
            summary.items(),
            key=lambda x: abs(x[1]["delta_local"]),
            reverse=True,
        )
    else:
        sorted_items = sorted(summary.items(), key=lambda x: x[0])

    # ---------------------------------------------------------
    # Print SUMMARY
    # ---------------------------------------------------------

    print("\nSUMMARY\n")

    header = (
        f"{'Investment':<12}"
        f"{'Open Qty':>12}{'Δ Qty':>12}{'Close Qty':>12}"
        f"{'Open Local':>15}{'Δ Local':>15}{'Close Local':>15}"
        f"{'Open Book':>15}{'Δ Book':>15}{'Close Book':>15}"
    )
    print(header)
    print("-" * len(header))

    for inv, vals in sorted_items:
        print(
            f"{inv:<12}"
            f"{vals['opening_qty']:>12,.4f}"
            f"{vals['delta_qty']:>12,.4f}"
            f"{vals['closing_qty']:>12,.4f}"
            f"{vals['opening_local']:>15,.2f}"
            f"{vals['delta_local']:>15,.2f}"
            f"{vals['closing_local']:>15,.2f}"
            f"{vals['opening_book']:>15,.2f}"
            f"{vals['delta_book']:>15,.2f}"
            f"{vals['closing_book']:>15,.2f}"
        )

    # ---------------------------------------------------------
    # Print JE DETAIL
    # ---------------------------------------------------------

    print("\nJE DETAIL\n")

    detail_header = (
        f"{'Date':<12}"
        f"{'Tran':<15}"
        f"{'Investment':<12}"
        f"{'Qty':>12}"
        f"{'Local':>15}"
        f"{'Book':>15}"
    )
    print(detail_header)
    print("-" * len(detail_header))

    for r in rows:
        inv = r["investment"]

        for je in r.get("je_lines", []):
            print(
                f"{str(je.get('date','')):<12}"
                f"{je.get('transaction',''):<15}"
                f"{inv:<12}"
                f"{je.get('qty',0.0):>12,.4f}"
                f"{je.get('local',0.0):>15,.2f}"
                f"{je.get('book',0.0):>15,.2f}"
            )

    print()


def build_summary_with_je_flat_rows(rows):
    """
    GUI version that mimics harness behavior:

    1) Summary block (by investment)
    2) Spacer
    3) Independent JE detail block
    """

    if not rows:
        return []

    # ---------------------------------------------------------
    # 1️⃣ Build SUMMARY rows
    # ---------------------------------------------------------

    summary = {}

    for r in rows:
        inv = r["investment"]

        if inv not in summary:
            summary[inv] = {
                "opening_qty": 0.0,
                "delta_qty": 0.0,
                "closing_qty": 0.0,
                "opening_local": 0.0,
                "delta_local": 0.0,
                "closing_local": 0.0,
                "opening_book": 0.0,
                "delta_book": 0.0,
                "closing_book": 0.0,
            }

        for field in summary[inv]:
            summary[inv][field] += r.get(field, 0.0)

    flat_rows = []

    for inv in sorted(summary.keys()):
        flat_rows.append({
            "row_type": "summary",
            "level": 0,
            "label": inv,
            **summary[inv],
        })

    # ---------------------------------------------------------
    # 2️⃣ Spacer row
    # ---------------------------------------------------------

    flat_rows.append({
        "row_type": "divider",
        "level": 0,
        "label": "----- JE DETAIL -----",
    })

    # ---------------------------------------------------------
    # 3️⃣ Independent JE rows
    # ---------------------------------------------------------

    for r in rows:
        inv = r["investment"]

        for je in r.get("je_lines", []):
            flat_rows.append({
                "ibor_date": je.get("ibor_date"),
                "trade_date": je.get("trade_date"),
                "settle_date": je.get("settle_date"),
                "kkd_begin": je.get("kkd_begin"),
                "kkd_end": je.get("kkd_end"),

                "tranid": je.get("tranid"),
                "transaction": je.get("transaction"),
                "investment": r.get("investment"),
                "financial_account": je.get("financial_account"),

                "qty": je.get("qty", 0.0),
                "local": je.get("local", 0.0),
                "book": je.get("book", 0.0),
            })

    return flat_rows


