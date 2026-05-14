import pandas as pd

def modify_and_insert_record(csv_file, tranid, new_date, new_quantity, output_file):
    # Load the CSV file into a DataFrame
    df = pd.read_csv(csv_file)

    # Find the row that matches the tranid
    matching_row = df[df['tranid'] == tranid]

    if matching_row.empty:
        print(f"No record found with tranid = {tranid}")
        return

    # Create a copy of the matching row
    new_record = matching_row.copy()

    # Update the new record with the new date and quantity
    new_record['kdend'] = new_date
    new_record['quantity'] = new_quantity

    # Append the new record to the DataFrame
    df = pd.concat([df, new_record], ignore_index=True)

    # Save the updated DataFrame back to a CSV file
    df.to_csv(output_file, index=False)
    print(f"New record inserted and saved to {output_file}")

# Example usage
csv_file = 'input.csv'  # Path to your input CSV file
tranid = 12345  # Transaction ID to match
new_date = '01/04/2022:00:00:00'  # New date to update in the record
new_quantity = 500  # New quantity to update in the record
output_file = 'output.csv'  # Path to save the updated CSV file

modify_and_insert_record(csv_file, tranid, new_date, new_quantity, output_file)
