import csv

# Define the file path for the portfolio list CSV
portfolio_list_file = 'C:/BASE_PATH/manyportfolios20000.csv'

# Create the portfolio names
portfolio_names = [f"manyportfolios{i}" for i in range(1, 20001)]

# Write the portfolio names to the CSV file
with open(portfolio_list_file, mode='w', encoding='utf-8', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['PortfolioName'])  # Write header
    for name in portfolio_names:
        writer.writerow([name])

print(f'Portfolio list written to {portfolio_list_file}')