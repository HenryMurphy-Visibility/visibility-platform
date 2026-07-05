"""
check_fx_dates.py
Run from chest root: python check_fx_dates.py
Checks JPY FX rate availability around period end dates.
"""
import csv
from datetime import datetime, timedelta

# Load FX index
fx_index = {}
with open('refdata/fx_master.csv', newline='') as f:
    for row in csv.DictReader(f):
        ccy  = (row.get('currency') or '').strip()
        date = row.get('date', '').strip()
        if '/' in date:
            parts = date.split('/')
            m, d, y = parts[0].zfill(2), parts[1].zfill(2), parts[2].split(':')[0]
            date = f'{y}-{m}-{d}'
        try:
            fx_index[(ccy, date)] = float(row.get('price', ''))
        except:
            pass

print(f'FX index loaded: {len(fx_index)} entries')

# Count JPY entries
jpy_entries = {k: v for k, v in fx_index.items() if k[0] == 'JPY'}
print(f'JPY entries: {len(jpy_entries)}')

# Check around each period end date
period_ends = ['2026-01-31', '2026-02-28', '2026-03-31', '2026-04-30', '2026-05-31']

print()
for target in period_ends:
    dt = datetime.strptime(target, '%Y-%m-%d')
    found = False
    for days in range(0, 6):
        for sign in [1, -1]:
            d = (dt + timedelta(days=days * sign)).strftime('%Y-%m-%d')
            if ('JPY', d) in fx_index:
                rate = fx_index[('JPY', d)]
                print(f'JPY on {target}: found {d}  gap={days}d  rate={rate}')
                found = True
                break
        if found:
            break
    if not found:
        print(f'JPY on {target}: NOT FOUND within 5 days')