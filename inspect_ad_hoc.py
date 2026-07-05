"""
check_im.py
Run from chest root: python check_im.py Portfolio3
"""
import csv, sys

portfolio = sys.argv[1] if len(sys.argv) > 1 else "Portfolio3"
path = f"funds/{portfolio}/RefData/investment_master.csv"

with open(path, newline="") as f:
    reader = csv.DictReader(f)
    print(f"Columns: {reader.fieldnames}\n")
    for row in reader:
        print(dict(row))