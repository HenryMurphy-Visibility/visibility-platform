import pandas as pd
import os
import json

def build_candidate_list_from_events(events_dir, output_file):
    """
    Build a global candidate list from portfolio-specific Events JSON files.

    Args:
        events_dir (str): Directory containing Events JSON files.
        output_file (str): Path to save the global candidate list.

    Returns:
        pd.DataFrame: DataFrame containing the global candidate list.
    """
    all_candidates = []

    # Iterate over all JSON files in the Events directory
    for file_name in os.listdir(events_dir):
        if file_name.endswith(".json"):
            portfolio_name = file_name.replace(".json", "")  # Extract portfolio name from file name
            file_path = os.path.join(events_dir, file_name)

            try:
                # Load the Events file
                events_data = pd.read_json(file_path)

                # Extract unique investments
                if "investment" in events_data.columns:
                    investments = events_data["investment"].unique()
                    for investment in investments:
                        all_candidates.append({"portfolio": portfolio_name, "ticker": investment})

            except Exception as e:
                print(f"Error processing {file_name}: {e}")

    # Create a DataFrame and remove duplicates
    candidates_df = pd.DataFrame(all_candidates).drop_duplicates()

    # Save to JSON
    candidates = {"last_updated": pd.Timestamp.now().isoformat(), "candidates": candidates_df.to_dict(orient="records")}
    with open(output_file, "w") as f:
        json.dump(candidates, f, indent=4)

    print(f"Global candidate list saved to {output_file}")
    return candidates_df

# Example Usage
events_directory = "BASE_PATH/refdata/pooltest"
output_candidates_file = "BASE_PATH/refdata/global_candidates.json"

build_candidate_list_from_events(events_directory, output_candidates_file)
