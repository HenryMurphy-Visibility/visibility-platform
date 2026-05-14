import pandas as pd
import os
import json
from datetime import datetime

# Path to the global candidate file
GLOBAL_CANDIDATE_FILE = "BASE_PATH/refdata/global_candidates.json"

# -------------------------------
# Load Candidates
# -------------------------------
def load_candidates_new(file_path=GLOBAL_CANDIDATE_FILE):
    """
    Load the global candidate list from a JSON or CSV file.

    Args:
        file_path (str): Path to the candidate file.

    Returns:
        pd.DataFrame: DataFrame containing all candidates.
    """
    try:
        if file_path.endswith(".json"):
            with open(file_path, "r") as f:
                data = json.load(f)
            return pd.DataFrame(data.get("candidates", []))
        elif file_path.endswith(".csv"):
            return pd.read_csv(file_path)
        else:
            raise ValueError("Unsupported file format. Use JSON or CSV.")
    except Exception as e:
        print(f"Error loading candidates: {e}")
        return pd.DataFrame(columns=["portfolio", "ticker"])

# -------------------------------
# Save Candidates
# -------------------------------
def save_candidates_new(candidates_df, file_path=GLOBAL_CANDIDATE_FILE):
    """
    Save the global candidate list to a JSON or CSV file.

    Args:
        candidates_df (pd.DataFrame): DataFrame containing candidates to save.
        file_path (str): Path to the candidate file.
    """
    try:
        if file_path.endswith(".json"):
            candidates = candidates_df.to_dict(orient="records")
            data = {"last_updated": datetime.now().isoformat(), "candidates": candidates}
            with open(file_path, "w") as f:
                json.dump(data, f, indent=4)
        elif file_path.endswith(".csv"):
            candidates_df.to_csv(file_path, index=False)
        else:
            raise ValueError("Unsupported file format. Use JSON or CSV.")
        print("Global candidates saved successfully.")
    except Exception as e:
        print(f"Error saving candidates: {e}")

# -------------------------------
# Add New Candidates
# -------------------------------
def add_candidates_new(new_tickers, portfolio, candidates_df):
    """
    Add new tickers to the global candidate list.

    Args:
        new_tickers (list[str]): List of new tickers to add.
        portfolio (str): Portfolio to associate with the tickers.
        candidates_df (pd.DataFrame): Existing candidates DataFrame.

    Returns:
        pd.DataFrame: Updated candidates DataFrame.
    """
    new_candidates = pd.DataFrame({"portfolio": portfolio, "ticker": new_tickers})
    updated_candidates = pd.concat([candidates_df, new_candidates]).drop_duplicates()
    print(f"Added {len(new_tickers)} new tickers to portfolio {portfolio}.")
    return updated_candidates

# -------------------------------
# Filter Candidates
# -------------------------------
def filter_candidates_new(candidates_df, portfolio=None):
    """
    Filter the global candidate list by portfolio or other criteria.

    Args:
        candidates_df (pd.DataFrame): DataFrame containing all candidates.
        portfolio (str, optional): Portfolio name to filter by.

    Returns:
        pd.DataFrame: Filtered candidates.
    """
    if portfolio:
        return candidates_df[candidates_df["portfolio"] == portfolio]
    return candidates_df

# -------------------------------
# Build Candidates
# -------------------------------
def build_candidates_new(retrieved_events_records, period_end, candidates_df):
    """
    Build a list of unique candidates and update the global candidate list.

    Args:
        retrieved_events_records (list[dict]): List of event records.
        period_end (datetime): The cutoff date for filtering events.
        candidates_df (pd.DataFrame): Existing candidates DataFrame.

    Returns:
        pd.DataFrame: Updated candidates DataFrame.
        pd.DataFrame: DataFrame containing investment details for the candidates.
    """
    # Convert events to a DataFrame for processing
    events_df = pd.DataFrame(retrieved_events_records)

    # Ensure 'tradedate' is a datetime object
    events_df["tradedate"] = pd.to_datetime(events_df["tradedate"], format="%m/%d/%Y:%H:%M:%S", errors="coerce")

    # Filter events based on `period_end`
    filtered_events = events_df[events_df["tradedate"] <= period_end]

    # Extract unique candidates from events
    new_tickers = filtered_events["investment"].unique()
    portfolio = filtered_events["portfolio"].iloc[0] if not filtered_events.empty else None

    # Update the global candidates DataFrame
    updated_candidates_df = add_candidates_new(new_tickers, portfolio, candidates_df)

    # Fetch investment details for candidates (mock or external call)
    investment_details_list = []
    for ticker in new_tickers:
        investment_info = get_security_info(ticker)  # Function to fetch investment details
        if not investment_info.empty:
            investment_details_list.append(investment_info)

    # Combine investment details into a single DataFrame
    investment_details_df = pd.concat(investment_details_list, ignore_index=True) if investment_details_list else pd.DataFrame()

    return updated_candidates_df, investment_details_df

# -------------------------------
# Mock: Fetch Security Info
# -------------------------------
def get_security_info(ticker):
    """
    Mock function to fetch security details for a given ticker.

    Args:
        ticker (str): Investment ticker.

    Returns:
        pd.DataFrame: DataFrame containing security details.
    """
    # Mock implementation for demonstration purposes
    return pd.DataFrame([{
        "ticker": ticker,
        "name": f"Security {ticker}",
        "sector": "Technology",
        "price": 100.00,
        "currency": "USD"
    }])
