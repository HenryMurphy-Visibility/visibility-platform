# ============================================================
# VISIBILITY — PROJECTION ENGINE
# Canonical financial structuring layer
# ============================================================

from typing import Dict, Any, Tuple, List
from collections import defaultdict
import copy


# ============================================================
# PUBLIC ENTRY
# ============================================================

def run_projection(rows, group_by=None, sort_by=None):
    """
    Projection Engine Contract:

    - Expects: rows → list[dict]
    - Each dict represents a flat canonical row (already transformed by adapter layer)
    - Projection performs grouping / tree-building only.
    - Adapter layer is responsible for structure normalization.

    DO NOT pass:
        - shape_result dict
        - container dict
        - meta wrappers
        - period_chain structures

    Always pass: list of row dictionaries.
    """

    if not isinstance(rows, list):
        raise TypeError("run_projection expects a list of row dictionaries")

    if group_by is None:
        group_by = ()

    return _project_rows(rows, group_by, sort_by)


# ============================================================
# CORE PROJECTION LOGIC
# ============================================================

def _project_rows(
    rows: List[Dict[str, Any]],
    group_by: Tuple[str, ...],
    sort_by: Tuple[str, ...] | None,
) -> Dict[str, Any]:

    # Work on copy to guarantee immutability
    rows = copy.deepcopy(rows)

    numeric_fields = _detect_numeric_fields(rows)

    # Build nested aggregation structure
    root = _build_tree(rows, group_by, numeric_fields)

    # Optional sorting
    if sort_by:
        _sort_tree(root, sort_by)

    return root


# ============================================================
# NUMERIC FIELD DETECTION
# ============================================================

def _detect_numeric_fields(rows: List[Dict[str, Any]]) -> List[str]:
    """
    Detect aggregatable financial numeric fields.
    Only sum fields that represent financial measures.
    """

    allowed_keywords = ("qty", "local", "book")

    numeric_fields = set()

    for row in rows:
        for k, v in row.items():
            if not isinstance(v, (int, float)):
                continue

            # Only aggregate financial measure fields
            if any(keyword in k.lower() for keyword in allowed_keywords):
                numeric_fields.add(k)

    return list(numeric_fields)

# ============================================================
# TREE BUILDER
# ============================================================

def _build_tree(
    rows: List[Dict[str, Any]],
    group_by: Tuple[str, ...],
    numeric_fields: List[str],
) -> Dict[str, Any]:

    root = {
        "label": "ROOT",
        "children": [],
        "aggregates": defaultdict(float),
    }

    for row in rows:
        _insert_row(root, row, group_by, numeric_fields)

    # Convert defaultdicts to dicts
    _finalize_aggregates(root)

    return root


def _insert_row(
    node: Dict[str, Any],
    row: Dict[str, Any],
    group_by: Tuple[str, ...],
    numeric_fields: List[str],
    level: int = 0,
):

    # Aggregate at this node
    for field in numeric_fields:
        node["aggregates"][field] += row.get(field, 0.0)

    # If no more grouping levels, attach leaf
    if level >= len(group_by):
        node.setdefault("rows", []).append(row)
        return

    key_field = group_by[level]
    key_value = row.get(key_field)

    # Find or create child
    for child in node["children"]:
        if child["label"] == key_value:
            _insert_row(child, row, group_by, numeric_fields, level + 1)
            return

    # Create new child
    new_child = {
        "label": key_value,
        "children": [],
        "aggregates": defaultdict(float),
    }

    node["children"].append(new_child)

    _insert_row(new_child, row, group_by, numeric_fields, level + 1)

def flatten_projection_tree(tree: dict) -> list[dict]:
    """
    Converts hierarchical projection tree into flat display rows
    with inline subtotals and grand total.
    """

    flat_rows = []

    numeric_fields = list(tree["aggregates"].keys())

    def recurse(node, level=0, is_root=False):

        # Traverse children first
        for child in node.get("children", []):
            recurse(child, level + 1)

            # Emit subtotal row for this child
            subtotal_row = {
                "row_type": "subtotal",
                "level": level + 1,
                "label": f"Subtotal {child['label']}",
                "investment": None,
                "location": None,
                "ls": None,
                "financial_account": child["label"],
            }

            for field in numeric_fields:
                subtotal_row[field] = child["aggregates"].get(field, 0.0)

            flat_rows.append(subtotal_row)

        # Emit data rows at leaf level
        for row in node.get("rows", []):
            data_row = {
                "row_type": "data",
                "level": level,
                "label": row.get("investment", ""),
            }

            for field in numeric_fields:
                data_row[field] = row.get(field, 0.0)

            flat_rows.append(data_row)

        # Root emits grand total at end
        if is_root:
            grand_row = {
                "row_type": "grand_total",
                "level": 0,
                "label": "Grand Total",
                "investment": None,
                "location": None,
                "ls": None,
                "financial_account": "Grand Total",
            }

            for field in numeric_fields:
                grand_row[field] = tree["aggregates"].get(field, 0.0)

            flat_rows.append(grand_row)

    recurse(tree, level=0, is_root=True)

    return flat_rows
# ============================================================
# FINALIZE AGGREGATES
# ============================================================

def _finalize_aggregates(node: Dict[str, Any]):

    node["aggregates"] = dict(node["aggregates"])

    for child in node.get("children", []):
        _finalize_aggregates(child)


# ============================================================
# OPTIONAL SORTING
# ============================================================

def _sort_tree(node: Dict[str, Any], sort_by: Tuple[str, ...]):

    if "rows" in node:
        node["rows"].sort(key=lambda r: tuple(r.get(f) for f in sort_by))

    node["children"].sort(key=lambda c: c["label"])

    for child in node.get("children", []):
        _sort_tree(child, sort_by)