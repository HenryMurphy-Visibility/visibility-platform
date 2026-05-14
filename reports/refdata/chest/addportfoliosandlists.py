import csv
import shutil

# def create_portfolio_list(filename, start, end):
#     list_path = f'C:/BASE_PATH/{filename}'
#     with open(list_path, 'w', newline='') as listfile:
#         writer = csv.writer(listfile)
#         writer.writerow(['PortfolioName'])  # Add header
#         for i in range(start, end + 1):
#             writer.writerow([f'MyPortfolio{i}'])

def copy_portfolio_files(source_portfolio, start, end):
    source_path = f'C:/BASE_PATH/{source_portfolio}'
    for i in range(start, end + 1):
        dest_path = f'C:/BASE_PATH/refdata/pooltest/MyPortfolio{i}.csv'
        shutil.copyfile(source_path, dest_path)

# Create the portfolio list file
#create_portfolio_list('portfolio_list.csv', 501, 1000)

# Copy MyPortfolio10 to create new portfolio files
copy_portfolio_files('MyPortfolio10.csv', 501, 1000)

