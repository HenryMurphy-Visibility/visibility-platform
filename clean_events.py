# -*- coding: utf-8 -*-
"""
clean_events_csv.py
Removes reversal_of and correction_reason columns from events CSV files.
These columns were added incorrectly — correction metadata belongs in audit file.

Run from chest root: python clean_events_csv.py Portfolio3
"""
import csv
import os
import shutil
import sys
from pathlib import Path

ROGUE_COLUMNS = {"reversal_of", "correction_reason"}

def clean_events_csv(portfolio: str, funds_path: str = "funds"):
    events_file = Path(funds_path) / portfolio / "Events" / f"{portfolio}.csv"

    if not events_file.exists():
        print(f"Events file not found: {events_file}")
        return

    # Read existing
    with open(events_file, newline="", encoding="utf-8") as f:
        reader     = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows       = list(reader)

    # Check if rogue columns exist
    found = [c for c in ROGUE_COLUMNS if c in fieldnames]
    if not found:
        print(f"No rogue columns found in {events_file} — nothing to do")
        return

    print(f"Found rogue columns: {found}")

    # Backup first
    backup = str(events_file) + ".bak"
    shutil.copy(events_file, backup)
    print(f"Backup saved: {backup}")

    # Remove rogue columns
    clean_fieldnames = [c for c in fieldnames if c not in ROGUE_COLUMNS]

    # Write clean file
    with open(events_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=clean_fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Cleaned {events_file}")
    print(f"Columns removed: {found}")
    print(f"Rows preserved: {len(rows)}")
    print(f"Clean columns: {clean_fieldnames}")

if __name__ == "__main__":
    portfolio = sys.argv[1] if len(sys.argv) > 1 else "Portfolio3"
    clean_events_csv(portfolio)