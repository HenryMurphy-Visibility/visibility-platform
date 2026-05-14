import os
import pandas as pd
from pandas.tseries.offsets import BDay

portfolio_groups = {
    'mygroup': ['portfolio1', 'portfolio2']
}


def create_portfolio_directories(portfolio_group, frequency, domicile, fiscal_close_date, override_start_date=None,
                                 intra_period=None):
    try:
        if portfolio_group not in portfolio_groups:
            raise ValueError(f"Portfolio group {portfolio_group} does not exist.")

        for portfolio in portfolio_groups[portfolio_group]:
            print(f"Creating directories for {portfolio} in group {portfolio_group}...")

            # Define the base directory
            base_dir = os.path.join("C:/Users/hjmne/PycharmProjects/chest/refdata", portfolio_group,
                                    portfolio) if portfolio_group else os.path.join(
                "C:/Users/hjmne/PycharmProjects/chest/refdata", portfolio)

            # Create the base directory if it doesn't exist
            if not os.path.exists(base_dir):
                os.makedirs(base_dir)
                print(f"Base directory created: {base_dir}")

            # Convert fiscal_close_date to datetime
            fiscal_close_date = pd.to_datetime(fiscal_close_date)

            # Calculate start date
            if override_start_date:
                start_date = pd.to_datetime(override_start_date)
            else:
                start_date = fiscal_close_date - pd.DateOffset(
                    days=1) if frequency == 'daily' else fiscal_close_date - pd.DateOffset(months=1)

            # Generate list of business days between start_date and fiscal_close_date
            business_days = pd.date_range(start=start_date, end=fiscal_close_date, freq=BDay())

            # Create directories for each business day
            for day in business_days:
                dir_name = day.strftime("%Y-%m-%d")
                dir_path = os.path.join(base_dir, dir_name)
                if not os.path.exists(dir_path):
                    os.makedirs(dir_path)
                    print(f"Directory created: {dir_path}")
                else:
                    print(f"Directory already exists: {dir_path}")

                # Create intra-period directories if needed
                if intra_period:
                    for i in range(intra_period):
                        intra_dir_path = os.path.join(dir_path, f'intra_{i + 1}')
                        if not os.path.exists(intra_dir_path):
                            os.makedirs(intra_dir_path)
                            print(f"Intra-period directory created: {intra_dir_path}")
                        else:
                            print(f"Intra-period directory already exists: {intra_dir_path}")

    except Exception as e:
        print(f"An error occurred: {e}")


# Example usage
create_portfolio_directories(
    portfolio_group='mygroup',
    frequency='daily',
    domicile='US',
    fiscal_close_date='2023-10-20',
    override_start_date='2023-10-15',
    intra_period=5  # Number of intra-period directories to create
)
        # from kivy.app import App
# from kivy.uix.boxlayout import BoxLayout
# from kivy.garden.matplotlib.backend_kivyagg import FigureCanvasKivyAgg
# import matplotlib.pyplot as plt
# import calendar
#
#
# class CalendarApp(App):
#
#     def build(self):
#         layout = BoxLayout()
#         fig, ax = plt.subplots(figsize=(5, 5))
#
#         # Use matplotlib to draw a calendar for a specific month and year
#         cal = calendar.month(2023, 2)
#         ax.axis('off')
#         ax.text(0.5, 0.5, cal, ha='center', va='center', size=15)
#
#         layout.add_widget(FigureCanvasKivyAgg(plt.gcf()))
#
#         return layout
#
#
# if __name__ == '__main__':
#     CalendarApp().run()
