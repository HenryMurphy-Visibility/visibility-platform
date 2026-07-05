# inspect_cph_status.py
import json
from pathlib import Path
from v_config import FUNDS_PATH

portfolio = "Portfolio1"

candidates_path = Path(FUNDS_PATH) / portfolio / "Candidates" / "candidates.json"

if not candidates_path.exists():
    print(f"Not bootstrapped — {candidates_path} not found")
else:
    with open(candidates_path) as f:
        data = json.load(f)
    print(f"Portfolio:    {data.get('portfolio')}")
    print(f"Bootstrapped: True")
    print(f"Candidates:   {data.get('count')}")
    print(f"Currencies:   {data.get('currencies')}")
    print(f"Last updated: {data.get('last_updated')}")