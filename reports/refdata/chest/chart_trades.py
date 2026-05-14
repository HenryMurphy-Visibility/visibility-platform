def generate_chart(csv_file_path):
    import matplotlib.pyplot as plt
    import pandas as pd

    data = pd.read_csv(csv_file_path, header=None)
    data.columns = ['Increment', 'Elapsed Time', 'Memory Usage', 'Events Per Second']

    # Convert 'Events Per Second' to numeric, handling non-numeric values if necessary
    data['Events Per Second'] = pd.to_numeric(data['Events Per Second'], errors='coerce')

    # Plotting the chart
    plt.figure(figsize=(14, 7))
    plt.plot(data['Increment'], data['Events Per Second'], marker='o', linestyle='-', color='b')
    plt.title('Events Processed per Second per 1000 Increment')
    plt.xlabel('Increment (x1000)')
    plt.ylabel('Events Processed per Second')
    plt.grid(True)
    plt.savefig('events_per_second_chart.png')
    plt.show()


# Specify the correct path to your CSV file
csv_path = "C:/Users/hjmne/PyCharmProjects/chest/log_data.csv"
generate_chart(csv_path)
