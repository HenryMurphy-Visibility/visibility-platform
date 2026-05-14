import os
import pickle
import copy
import sys
from pathlib import Path

# === CONFIGURATION ===
PORTFOLIO = "Portfolio1"  # <-- Change to your actual portfolio name
BASE_DIR = Path(f"C:/Users/hjmne/PycharmProjects/chest/funds/{PORTFOLIO}/Open/periods")

CLASS_SPLIT = {
    "ClassA": 0.6,
    "ClassB": 0.4
}

PARTNER_SPLIT = {
    "ClassA": [("Partner1", 0.5), ("Partner2", 0.5)],
    "ClassB": [("Partner3", 1.0)]
}


# === HELPERS ===

def load_journals(path):
    if not path.exists():
        print(f"[ERROR] Baseline journal file not found: {path}")
        return None
    with path.open("rb") as f:
        data = pickle.load(f)
        print(f"[INFO] Loaded {len(data)} Journals objects from {path}")
        return data

def save_journals(journals, path):
    os.makedirs(path.parent, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump(journals, f)
    print(f"[SAVE] {len(journals)} Journals saved to: {path}")

def scale_journals(journals_list, ratio, tag=None):
    scaled = []
    total_scaled = 0

    for jidx, journal in enumerate(copy.deepcopy(journals_list)):
        # Print debug sample for first few
        if jidx < 3:
            print(f"\n🔬 Original Journal {jidx}")
            print(f"  investment: {journal.investment}")
            print(f"  quantity: {journal.quantity}")
            print(f"  local: {journal.local}")
            print(f"  book: {journal.book}")
            print(f"  notional: {journal.notional}")
            print(f"  oface: {journal.oface}")

        # Safely scale only non-None numeric fields
        if journal.quantity is not None:
            journal.quantity *= ratio
        if journal.local is not None:
            journal.local *= ratio
        if journal.book is not None:
            journal.book *= ratio
        if journal.notional is not None:
            journal.notional *= ratio
        if journal.oface is not None:
            journal.oface *= ratio

        # Optional tagging
        if tag:
            journal.journal_type = tag  # or use a custom `source` attribute

        if jidx < 3:
            print(f"  ✅ After scaling x{ratio}:")
            print(f"     quantity: {journal.quantity}")
            print(f"     local: {journal.local}")
            print(f"     book: {journal.book}")
            print(f"     notional: {journal.notional}")
            print(f"     oface: {journal.oface}")

        scaled.append(journal)
        total_scaled += 1

    print(f"\n✅ scale_journals: scaled {total_scaled} Journals objects")
    return scaled

def summarize_journals(journals_list, label):
    total = len(journals_list)
    sums = {"quantity": 0, "local": 0, "book": 0, "notional": 0, "oface": 0}

    for journal in journals_list:
        for k in sums:
            val = getattr(journal, k, None)
            if isinstance(val, (int, float)):
                sums[k] += val

    print(f"\n📊 Summary for {label}:")
    print(f"  Total entries: {total}")
    for k, v in sums.items():
        print(f"  Sum of {k}: {v:.2f}")


# === MAIN LAYERING PROCESS ===

def perform_layering():
    baseline_path = BASE_DIR / "mqs.pkl"
    baseline = load_journals(baseline_path)

    if baseline is None:
        print("[EXIT] No baseline to layer. Please generate or copy a valid mqs.pkl.")
        sys.exit(1)

    summarize_journals(baseline, "Baseline")

    for class_name, class_ratio in CLASS_SPLIT.items():
        class_entries = scale_journals(baseline, class_ratio, tag=class_name)
        class_path = BASE_DIR / "Classes" / class_name / "mqs.pkl"
        save_journals(class_entries, class_path)
        summarize_journals(class_entries, f"Class {class_name}")

        for partner_name, partner_ratio in PARTNER_SPLIT.get(class_name, []):
            partner_entries = scale_journals(class_entries, partner_ratio, tag=partner_name)
            partner_path = BASE_DIR / "Classes" / "Partners" / partner_name / "mqs.pkl"
            save_journals(partner_entries, partner_path)
            summarize_journals(partner_entries, f"Partner {partner_name} from Class {class_name}")


# === ENTRY POINT ===

if __name__ == "__main__":
    perform_layering()
