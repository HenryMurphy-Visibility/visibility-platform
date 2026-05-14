# # ============================================================
# # RANGE-AWARE SHAPE EXECUTOR (PARALLEL PROTOTYPE)
# # ============================================================
#
# class RangeReportNode:
#     def __init__(self, key, level, grouping_field=None):
#         self.key = key
#         self.level = level
#         self.grouping_field = grouping_field
#         self.children = []
#
#         self.opening = {}
#         self.delta = {}
#         self.closing = {}
#
#
# # ============================================================
# # RANGE SHAPE EXECUTOR
# # ============================================================
#
# class RangeShapeExecutor:
#
#     def execute(self, shape, opening_rows, delta_rows, closing_rows):
#
#         root = RangeReportNode(
#             key=shape["name"],
#             level=0,
#             grouping_field=None
#         )
#
#         grouping_levels = shape["grouping_levels"]
#         measures_def = {m["name"]: m for m in shape["measures"]}
#
#         # --------------------------------------------------
#         # Insert rows by layer
#         # --------------------------------------------------
#         self._insert_layer(root, grouping_levels, shape, opening_rows, "opening")
#         self._insert_layer(root, grouping_levels, shape, delta_rows, "delta")
#         self._insert_layer(root, grouping_levels, shape, closing_rows, "closing")
#
#         # --------------------------------------------------
#         # Compute subtotals independently for each layer
#         # --------------------------------------------------
#         self._compute_subtotals(root, measures_def, "opening")
#         self._compute_subtotals(root, measures_def, "delta")
#         self._compute_subtotals(root, measures_def, "closing")
#
#         return root
#
#
#     # ============================================================
#     # INSERT LAYER DATA
#     # ============================================================
#
#     def _insert_layer(self, root, grouping_levels, shape, rows, layer_name):
#
#         for row in rows:
#
#             current_node = root
#
#             # Walk grouping levels
#             for depth, level_def in enumerate(grouping_levels, start=1):
#
#                 field = level_def["group_by"]
#                 value = row.get(field)
#
#                 child = self._find_child(current_node, value)
#                 if not child:
#                     child = RangeReportNode(
#                         key=value,
#                         level=depth,
#                         grouping_field=field
#                     )
#                     current_node.children.append(child)
#
#                 current_node = child
#
#             # Leaf
#             leaf_key = tuple(row[field] for field in shape["primary_row_identifier"])
#
#             leaf = self._find_child(current_node, leaf_key)
#             if not leaf:
#                 leaf = RangeReportNode(
#                     key=leaf_key,
#                     level=len(grouping_levels) + 1,
#                     grouping_field="leaf"
#                 )
#                 current_node.children.append(leaf)
#
#             # Attach measures to correct layer
#             layer_dict = getattr(leaf, layer_name)
#
#             for k, v in row.items():
#                 if k not in shape["primary_row_identifier"] \
#                    and k not in [lvl["group_by"] for lvl in grouping_levels]:
#                     layer_dict[k] = v
#
#
#     # ============================================================
#     # SUBTOTAL ENGINE (LAYER-SPECIFIC)
#     # ============================================================
#
#     def _compute_subtotals(self, node, measures_def, layer_name):
#
#         for child in node.children:
#             self._compute_subtotals(child, measures_def, layer_name)
#
#         if not node.children:
#             return
#
#         layer_dict = getattr(node, layer_name)
#
#         for measure_name, measure_def in measures_def.items():
#
#             allowed_levels = measure_def.get("allow_subtotal_levels", [])
#
#             grouping_field = node.grouping_field
#
#             if grouping_field in allowed_levels or (
#                 grouping_field is None and None in allowed_levels
#             ):
#
#                 total = 0
#                 has_value = False
#
#                 for child in node.children:
#                     child_layer = getattr(child, layer_name)
#                     val = child_layer.get(measure_name)
#                     if val is not None:
#                         total += val
#                         has_value = True
#
#                 layer_dict[measure_name] = total if has_value else None
#
#             else:
#                 layer_dict[measure_name] = None
#
#
#     # ============================================================
#     # HELPER
#     # ============================================================
#
#     def _find_child(self, node, key):
#         for child in node.children:
#             if child.key == key:
#                 return child
#         return None
#
#
# # ============================================================
# # FLATTEN FOR RENDERING
# # ============================================================
#
# def flatten_range_tree(node):
#
#     rows = []
#
#     def traverse(n, lineage):
#
#         rows.append({
#             "level": n.level,
#             "key": n.key,
#             "grouping_field": n.grouping_field,
#             "opening": n.opening.copy(),
#             "delta": n.delta.copy(),
#             "closing": n.closing.copy()
#         })
#
#         for child in n.children:
#             traverse(child, lineage + [child.key])
#
#     traverse(node, [node.key])
#
#     return rows
#
#
# # ============================================================
# # TEST MAIN
# # ============================================================
#
# if __name__ == "__main__":
#
#     shape = {
#
#         "name": "Tax Lot Range Appraisal",
#
#         "primary_row_identifier": [
#             "investment",
#             "lotid",
#             "tax_date"
#         ],
#
#         "grouping_levels": [
#             {"group_by": "investment_type"},
#             {"group_by": "investment"}
#         ],
#
#         "measures": [
#
#             {"name": "quantity",
#              "allow_subtotal_levels": ["investment"]},
#
#             {"name": "market_value_book",
#              "allow_subtotal_levels": ["investment", "investment_type", None]},
#         ]
#     }
#
#     # -----------------------------
#     # SAMPLE OPENING / DELTA / CLOSING
#     # -----------------------------
#
#     opening_rows = [
#         {
#             "investment_type": "EQUITIES",
#             "investment": "AAPL",
#             "lotid": 1001,
#             "tax_date": "2023-01-15",
#             "quantity": 100,
#             "cost_book": 15000,
#             "market_value_book": 18000,
#         },
#         {
#             "investment_type": "EQUITIES",
#             "investment": "AAPL",
#             "lotid": 1002,
#             "tax_date": "2023-02-01",
#             "quantity": 200,
#             "cost_book": 30000,
#             "market_value_book": 36000,
#         }
#     ]
#     delta_rows = [
#         {
#             "investment_type": "EQUITIES",
#             "investment": "AAPL",
#             "lotid": 1001,
#             "tax_date": "2023-01-15",
#             "quantity": -40,
#             "cost_book": -6000,
#             "market_value_book": -7200,
#         },
#         {
#             "investment_type": "EQUITIES",
#             "investment": "AAPL",
#             "lotid": 1002,
#             "tax_date": "2023-02-01",
#             "quantity": -200,
#             "cost_book": -30000,
#             "market_value_book": -36000,
#         },
#         {
#             "investment_type": "EQUITIES",
#             "investment": "AAPL",
#             "lotid": 1003,
#             "tax_date": "2023-03-01",
#             "quantity": 50,
#             "cost_book": 8000,
#             "market_value_book": 9000,
#         }
#     ]
#     closing_rows = [
#         {
#             "investment_type": "EQUITIES",
#             "investment": "AAPL",
#             "lotid": 1001,
#             "tax_date": "2023-01-15",
#             "quantity": 60,
#             "cost_book": 9000,
#             "market_value_book": 10800,
#         },
#         {
#             "investment_type": "EQUITIES",
#             "investment": "AAPL",
#             "lotid": 1003,
#             "tax_date": "2023-03-01",
#             "quantity": 50,
#             "cost_book": 8000,
#             "market_value_book": 9000,
#         }
#     ]
#
#     executor = RangeShapeExecutor()
#     tree = executor.execute(shape, opening_rows, delta_rows, closing_rows)
#
#     rows = flatten_range_tree(tree)
#
#     # Simple console output
#     for r in rows:
#         indent = "    " * r["level"]
#         print(f"{indent}{r['key']}")
#         print(f"{indent}  Opening: {r['opening']}")
#         print(f"{indent}  Delta:   {r['delta']}")
#         print(f"{indent}  Closing: {r['closing']}")
#         print()
from collections import defaultdict


# ============================================================
# Node Definition
# ============================================================

class Node:
    def __init__(self, key, level):
        self.key = key
        self.level = level  # root, type, investment, lot
        self.children = {}

        self.opening = defaultdict(float)
        self.delta = defaultdict(float)
        self.closing = defaultdict(float)

        self.journal_count = 0
        self.flags = {}

    def get_or_create_child(self, key, level):
        if key not in self.children:
            self.children[key] = Node(key, level)
        return self.children[key]


# ============================================================
# Build Hierarchy
# ============================================================

def build_tree(opening_rows, journal_rows, closing_rows):

    root = Node("Tax Lot Range Appraisal", "root")

    # Collect union of keys
    all_rows = opening_rows + journal_rows + closing_rows

    for row in all_rows:
        inv_type = row["investment_type"]
        inv = row["investment"]
        lot = row["lotid"]
        tax_date = row["tax_date"]

        type_node = root.get_or_create_child(inv_type, "type")
        inv_node = type_node.get_or_create_child(inv, "investment")
        inv_node.get_or_create_child((inv, lot, tax_date), "lot")

    return root


# ============================================================
# Apply Snapshot Layer
# ============================================================

def apply_snapshot(root, rows, layer_name):
    for row in rows:
        type_node = root.children[row["investment_type"]]
        inv_node = type_node.children[row["investment"]]
        lot_node = inv_node.children[(row["investment"], row["lotid"], row["tax_date"])]

        target = getattr(lot_node, layer_name)

        for measure in ["quantity", "cost_book", "market_value_book"]:
            value = row.get(measure)
            if value is not None:
                target[measure] += value


# ============================================================
# Apply Journal Delta
# ============================================================

def apply_journal_delta(root, journal_rows):
    for row in journal_rows:
        type_node = root.children[row["investment_type"]]
        inv_node = type_node.children[row["investment"]]
        lot_node = inv_node.children[(row["investment"], row["lotid"], row["tax_date"])]

        for measure in ["quantity", "cost_book", "market_value_book"]:
            value = row.get(measure)
            if value is not None:
                lot_node.delta[measure] += value

        lot_node.journal_count += 1


# ============================================================
# Aggregate Upwards
# ============================================================

def aggregate_up(node):

    for child in node.children.values():
        aggregate_up(child)

        for layer in ["opening", "delta", "closing"]:
            child_layer = getattr(child, layer)
            parent_layer = getattr(node, layer)

            for k, v in child_layer.items():
                parent_layer[k] += v


# ============================================================
# Reconciliation Check
# ============================================================

def reconcile(node):

    for child in node.children.values():
        reconcile(child)

    # Only reconcile if both opening and closing exist
    for measure in ["quantity", "cost_book", "market_value_book"]:
        opening = node.opening.get(measure, 0)
        delta = node.delta.get(measure, 0)
        closing = node.closing.get(measure, 0)

        if abs((opening + delta) - closing) > 1e-9:
            node.flags["reconciliation_error"] = True


# ============================================================
# Pretty Print
# ============================================================

def print_tree(node, indent=0):

    space = "  " * indent

    print(f"{space}{node.key}")

    if node.opening:
        print(f"{space}  Opening: {dict(node.opening)}")
    if node.delta:
        print(f"{space}  Delta:   {dict(node.delta)}")
    if node.closing:
        print(f"{space}  Closing: {dict(node.closing)}")

    if node.flags:
        print(f"{space}  FLAGS: {node.flags}")

    for child in node.children.values():
        print_tree(child, indent + 1)


# ============================================================
# Example Test Data
# ============================================================

def main():

    # --------------------------------------------------------
    # Opening Snapshot
    # --------------------------------------------------------
    opening_rows = [
        {
            "investment_type": "EQUITIES",
            "investment": "AAPL",
            "lotid": 1001,
            "tax_date": "2023-01-15",
            "quantity": 100,
            "cost_book": 15000,
            "market_value_book": 18000,
        },
        {
            "investment_type": "EQUITIES",
            "investment": "AAPL",
            "lotid": 1002,
            "tax_date": "2023-02-01",
            "quantity": 200,
            "cost_book": 30000,
            "market_value_book": 36000,
        }
    ]

    # --------------------------------------------------------
    # Journal Activity (Delta)
    # --------------------------------------------------------
    journal_rows = [
        # Partial exit lot 1001
        {
            "investment_type": "EQUITIES",
            "investment": "AAPL",
            "lotid": 1001,
            "tax_date": "2023-01-15",
            "quantity": -40,
            "cost_book": -6000,
            "market_value_book": -7200,
        },
        # Full exit lot 1002
        {
            "investment_type": "EQUITIES",
            "investment": "AAPL",
            "lotid": 1002,
            "tax_date": "2023-02-01",
            "quantity": -200,
            "cost_book": -30000,
            "market_value_book": -36000,
        },
        # New lot entry 1003
        {
            "investment_type": "EQUITIES",
            "investment": "AAPL",
            "lotid": 1003,
            "tax_date": "2023-03-01",
            "quantity": 50,
            "cost_book": 8000,
            "market_value_book": 9000,
        }
    ]

    # --------------------------------------------------------
    # Closing Snapshot
    # --------------------------------------------------------
    closing_rows = [
        {
            "investment_type": "EQUITIES",
            "investment": "AAPL",
            "lotid": 1001,
            "tax_date": "2023-01-15",
            "quantity": 60,
            "cost_book": 9000,
            "market_value_book": 10800,
        },
        {
            "investment_type": "EQUITIES",
            "investment": "AAPL",
            "lotid": 1003,
            "tax_date": "2023-03-01",
            "quantity": 50,
            "cost_book": 8000,
            "market_value_book": 9000,
        }
    ]

    # --------------------------------------------------------
    # Build & Run
    # --------------------------------------------------------

    root = build_tree(opening_rows, journal_rows, closing_rows)

    apply_snapshot(root, opening_rows, "opening")
    apply_journal_delta(root, journal_rows)
    apply_snapshot(root, closing_rows, "closing")

    aggregate_up(root)
    reconcile(root)

    print_tree(root)


if __name__ == "__main__":
    main()
