# v_filter_config_loader.py

import pandas as pd

class VFilterConfigLoader:
    def __init__(self, config_path):
        self.config_path = config_path
        self.filter_config = {}
        self.load_config()

    def load_config(self):
        try:
            df = pd.read_csv(self.config_path)
            self.config = {}

            for _, row in df.iterrows():
                column = str(row["COLUMN_NAME"]).strip()

                max_values = row.get("MAX_VALUES_SHOWN")
                requires_search = str(row.get("REQUIRES_SEARCH", "")).strip().lower() == "true"
                disable_filter = str(row.get("DISABLE_FILTER", "")).strip().lower() == "true"

                try:
                    max_values = int(max_values) if pd.notna(max_values) else None
                except (ValueError, TypeError):
                    max_values = None

                self.config[column] = {
                    "max_values_shown": max_values,
                    "requires_search": requires_search,
                    "disable_filter": disable_filter
                }
            print(f"✅ Loaded VFilter config with {len(self.filter_config)} entries.")
        except Exception as e:
            print(f"❌ Error loading VFilter config: {e}")

    def get_config_for_column(self, column_name):
        return self.filter_config.get(column_name, {})

# --- Usage Example ---
# loader = VFilterConfigLoader('C:/Users/hjmne/PycharmProjects/chest/refdata/v_filter.config')
# config = loader.get_config_for_column('INVESTMENT')
# print(config)
