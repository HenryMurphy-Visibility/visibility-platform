from openpyxl import load_workbook

# workbook = load_workbook('C:/Users/hjmne/PycharmProjects/chest/refdata/Performance_asset_class.xlsx')
# workbook.active = 0  # Set the first sheet as active
# workbook.save('C:/Users/hjmne/PycharmProjects/chest/reports/Performance_asset_class.xlsx')

import pandas as pd

# Sample data
data = {
    'Column1': [1, 2, 3],
    'Column2': ['A', 'B', 'C']
}

# Convert the data to a DataFrame
df = pd.DataFrame(data)

# Path to save the Excel file
output_file = 'C:/Users/hjmne/PycharmProjects/chest/reports/test_output.xlsx'

# Create and save an Excel workbook
with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name='Sheet1', index=False)

print(f"Workbook saved to {output_file}")
