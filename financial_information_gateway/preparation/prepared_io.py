import pickle
from pathlib import Path
from datetime import datetime


def save_prepared_view(base_path, name, payload):
    """
    Save prepared artifact to disk
    """

    base_path = Path(base_path)
    base_path.mkdir(parents=True, exist_ok=True)

    file_path = base_path / f"{name}.pkl"

    wrapper = {
        "name": name,
        "created_at": datetime.now(),
        "payload": payload,
    }

    with open(file_path, "wb") as f:
        pickle.dump(wrapper, f)

    print(f"💾 Saved prepared view → {file_path}")

    return file_path


def load_prepared_view(file_path):
    """
    Load prepared artifact from disk
    """

    with open(file_path, "rb") as f:
        data = pickle.load(f)

    print(f"⚡ Loaded prepared view → {file_path}")

    return data["payload"]

def list_prepared_views(prepared_dir):
    from pathlib import Path

    prepared_dir = Path(prepared_dir)

    if not prepared_dir.exists():
        return []

    return sorted([
        f.name for f in prepared_dir.glob("*.pkl")
    ])