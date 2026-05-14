import openpyxl


wb = openpyxl.load_workbook("C:/Users/hjmne/PycharmProjects/chest/refdata/portfolio1bak.xlsx")
ws = wb.active

# Create a new workbook and worksheet for output
new_wb = openpyxl.Workbook()
new_ws = new_wb.active

# Copy data from input to output
for row in ws:
    for cell in row:
        new_ws[cell.coordinate].value = cell.value

# Save the new workbook to the output filename
new_wb.save("C:/Users/hjmne/PycharmProjects/chest/refdata/portfolio1.xlsx")
