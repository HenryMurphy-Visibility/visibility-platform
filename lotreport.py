# ----------------------------------------
# Node Structure
# ----------------------------------------

class ReportNode:
    def __init__(self, key, level, grouping_field=None):
        self.key = key
        self.level = level
        self.grouping_field = grouping_field
        self.measures = {}
        self.children = []

    def __repr__(self):
        return f"ReportNode(key={self.key}, level={self.level})"


# ----------------------------------------
# Shape Executor
# ----------------------------------------

class ShapeExecutor:

    def execute(self, shape, flat_rows):

        root = ReportNode(key=shape["name"], level=0, grouping_field=None)

        grouping_levels = shape["grouping_levels"]
        measures_def = {m["name"]: m for m in shape["measures"]}

        # ----------------------------------------
        # 1️⃣ Insert rows
        # ----------------------------------------
        for row in flat_rows:

            current_node = root

            for depth, level_def in enumerate(grouping_levels, start=1):

                field = level_def["group_by"]
                value = row.get(field)

                child = self._find_child(current_node, value)
                if not child:
                    child = ReportNode(
                        key=value,
                        level=depth,
                        grouping_field=field
                    )
                    current_node.children.append(child)

                current_node = child

            # Leaf
            leaf_key = tuple(row[field] for field in shape["primary_row_identifier"])

            leaf = self._find_child(current_node, leaf_key)
            if not leaf:
                leaf = ReportNode(
                    key=leaf_key,
                    level=len(grouping_levels) + 1,
                    grouping_field="leaf"
                )
                current_node.children.append(leaf)

            # Attach measures
            for measure_name in measures_def:
                if measure_name != "percent_weight_book":
                    leaf.measures[measure_name] = row.get(measure_name)

        # ----------------------------------------
        # 2️⃣ Compute sum-based subtotals
        # ----------------------------------------
        self._compute_subtotals(root, measures_def)

        # ----------------------------------------
        # 3️⃣ Compute derived weights
        # ----------------------------------------
        total_mv_book = root.measures.get("market_value_book")

        if total_mv_book:
            self._compute_weights(root, total_mv_book)

        return root

    def _find_child(self, node, key):
        for child in node.children:
            if child.key == key:
                return child
        return None

    def _compute_subtotals(self, node, measures_def):

        for child in node.children:
            self._compute_subtotals(child, measures_def)

        if not node.children:
            return  # leaf

        for measure_name, measure_def in measures_def.items():

            if measure_name == "percent_weight_book":
                continue  # derived later

            allowed_levels = measure_def.get("allow_subtotal_levels", [])

            # ROOT behaves like investment_type level
            grouping_field = node.grouping_field

            if grouping_field in allowed_levels or (
                grouping_field is None and None in allowed_levels
            ):

                total = 0
                has_value = False

                for child in node.children:
                    val = child.measures.get(measure_name)
                    if val is not None:
                        total += val
                        has_value = True

                node.measures[measure_name] = total if has_value else None

            else:
                node.measures[measure_name] = None

    def _compute_weights(self, node, total_mv_book):

        # Skip ROOT
        if node.grouping_field is not None:

            mv = node.measures.get("market_value_book")

            if mv is not None and total_mv_book != 0:
                node.measures["percent_weight_book"] = mv / total_mv_book
            else:
                node.measures["percent_weight_book"] = None

        for child in node.children:
            self._compute_weights(child, total_mv_book)


# ----------------------------------------
# Pretty Print
# ----------------------------------------

def print_tree(node, indent=0):
    print(" " * indent + f"{node.key} | {node.measures}")
    for child in node.children:
        print_tree(child, indent + 4)


# ----------------------------------------
# MAIN
# ----------------------------------------

if __name__ == "__main__":

    shape = {

        "name": "Tax Lot Appraisal",

        "primary_row_identifier": [
            "investment",
            "lotid",
            "tax_date"
        ],

        "grouping_levels": [
            {"group_by": "investment_type"},
            {"group_by": "investment"}
        ],

        "measures": [

            {"name": "quantity",
             "allow_subtotal_levels": ["investment"]},

            {"name": "cost_local",
             "allow_subtotal_levels": ["investment"]},

            {"name": "cost_book",
             "allow_subtotal_levels": ["investment", "investment_type", None]},

            {"name": "market_value_local",
             "allow_subtotal_levels": ["investment"]},

            {"name": "market_value_book",
             "allow_subtotal_levels": ["investment", "investment_type", None]},

            {"name": "unreal_price_local",
             "allow_subtotal_levels": ["investment"]},

            {"name": "unreal_price_book",
             "allow_subtotal_levels": ["investment", "investment_type", None]},

            {"name": "unreal_fx_book",
             "allow_subtotal_levels": ["investment", "investment_type", None]},

            {"name": "total_unreal_local",
             "allow_subtotal_levels": ["investment"]},

            {"name": "total_unreal_book",
             "allow_subtotal_levels": ["investment", "investment_type", None]},

            {"name": "percent_weight_book"}  # derived
        ]
    }
    flat_rows = [

        # --------------------------------------------------
        # AAPL - Lot 1
        # --------------------------------------------------
        {
            "investment_type": "EQUITIES",
            "investment": "AAPL",
            "lotid": 1001,
            "tax_date": "2023-01-15",

            "quantity": 100,
            "cost_local": 15000,
            "cost_book": 15000,
            "market_value_local": 18000,
            "market_value_book": 18000,
            "unreal_price_local": 3000,
            "unreal_price_book": 3000,
            "unreal_fx_book": 0,
            "total_unreal_local": 3000,
            "total_unreal_book": 3000,
        },

        # --------------------------------------------------
        # AAPL - Lot 2
        # --------------------------------------------------
        {
            "investment_type": "EQUITIES",
            "investment": "AAPL",
            "lotid": 1002,
            "tax_date": "2023-03-10",

            "quantity": 50,
            "cost_local": 7000,
            "cost_book": 7000,
            "market_value_local": 9000,
            "market_value_book": 9000,
            "unreal_price_local": 2000,
            "unreal_price_book": 2000,
            "unreal_fx_book": 0,
            "total_unreal_local": 2000,
            "total_unreal_book": 2000,
        },

        # --------------------------------------------------
        # BMW Bond - Lot 1
        # --------------------------------------------------
        {
            "investment_type": "BONDS",
            "investment": "BMW_2028",
            "lotid": 2001,
            "tax_date": "2022-06-01",

            "quantity": 100000,
            "cost_local": 98000,
            "cost_book": 105000,
            "market_value_local": 99000,
            "market_value_book": 110000,
            "unreal_price_local": 1000,
            "unreal_price_book": 2000,
            "unreal_fx_book": 3000,
            "total_unreal_local": 1000,
            "total_unreal_book": 5000,
        },

        # --------------------------------------------------
        # BMW Bond - Lot 2
        # --------------------------------------------------
        {
            "investment_type": "BONDS",
            "investment": "BMW_2028",
            "lotid": 2002,
            "tax_date": "2022-09-01",

            "quantity": 50000,
            "cost_local": 49000,
            "cost_book": 52000,
            "market_value_local": 50500,
            "market_value_book": 55000,
            "unreal_price_local": 1500,
            "unreal_price_book": 2500,
            "unreal_fx_book": 2000,
            "total_unreal_local": 1500,
            "total_unreal_book": 4500,
        }

    ]

    executor = ShapeExecutor()
    tree = executor.execute(shape, flat_rows)

    print_tree(tree)
