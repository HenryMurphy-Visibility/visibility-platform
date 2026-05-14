import os
import pandas as pd

def get_event_by_tranid(tranid, portfolio_name, portfolio_directory):
    """
    Fetches the full event row (all fields) matching the TRANID.
    """
    import os
    import pandas as pd

    path = os.path.join(portfolio_directory, f"{portfolio_name}.csv")

    if not os.path.exists(path):
        print(f"❌ Event file not found: {path}")
        return None

    try:
        # Read all columns, treat everything as strings
        df = pd.read_csv(path, dtype=str).fillna("")

        # 🧠 Normalize: force string and drop decimals for float inputs
        def normalize_tranid(value):
            try:
                f = float(value)
                if f.is_integer():
                    return str(int(f))
                return str(f)
            except Exception:
                return str(value).strip()

        df["tranid"] = df["tranid"].apply(normalize_tranid)
        tranid_normalized = normalize_tranid(tranid)

        match = df[df["tranid"] == tranid_normalized]

        if match.empty:
            print(f"⚠ No match for TRANID {tranid_normalized} in {path}")
            return None

        return match.iloc[0].to_dict()

    except Exception as e:
        print(f"❌ Failed to read event file: {e}")
        return None
