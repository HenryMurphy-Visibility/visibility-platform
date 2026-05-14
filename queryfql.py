import re
import pandas as pd

def translate_sentence_to_query_dict(sentence: str) -> dict:
    sentence = sentence.strip().lower()
    filters = {}
    group_by = []
    sort_by = []
    period_start = None
    period_end = None
    levels = []
    mode = "PERF"
    limit = None

    # Top N performing positions between date1 and date2
    top_match = re.search(r"top (\d+) .*positions.*between (.*?) and (.*?)", sentence)
    if top_match:
        top_n = int(top_match.group(1))
        date1 = top_match.group(2).strip()
        date2 = top_match.group(3).strip()
        period_start = pd.to_datetime(date1)
        period_end = pd.to_datetime(date2)
        group_by = ["INVESTMENT"]
        sort_by = ["RETURN"]
        limit = top_n

    # Top N positions from dollars earned standpoint
    elif re.search(r"top (\d+) positions .*dollars earned", sentence):
        top_n = int(re.search(r"top (\d+)", sentence).group(1))
        group_by = ["INVESTMENT"]
        sort_by = ["BOOK_RETURN"]
        limit = top_n

    # All Google, Apple, and Microsoft info
    elif "all google, apple, and microsoft" in sentence:
        filters = {"INVESTMENT": "[GOOGLE, APPLE, MICROSOFT]"}

    # Simple pattern: VAL and (VAL or VAL)
    elif re.search(r"show.* (\w+) and \((\w+) or (\w+)\)", sentence):
        base, opt1, opt2 = re.findall(r"show.* (\w+) and \((\w+) or (\w+)\)", sentence)[0]
        filters = {"INVESTMENT": f"[{base}, {opt1}, {opt2}]"}

    # Apple's realized gains and losses history at the lot level
    elif "apple" in sentence and "realized" in sentence:
        filters = {"INVESTMENT": "==APPLE", "ENTRY_TYPE": "==REALIZED"}
        group_by = ["INVESTMENT", "LOTID", "TAX_DATE"]

    # Simple VAL or VAL or VAL pattern
    elif re.search(r"show (.+)", sentence):
        match = re.findall(r"show (.+)", sentence)[0].upper()
        if " OR " in match:
            values = [v.strip() for v in match.split(" OR ")]
            filters = {"INVESTMENT": f"[{', '.join(values)}]"}
        else:
            filters = {"INVESTMENT": f"=={match.strip()}"}

    # Top ten performers for 2nd quarter 2023
    elif "top ten performing position for 2nd qtr 2023" in sentence:
        group_by = ["INVESTMENT"]
        sort_by = ["RETURN"]
        period_start = pd.to_datetime("2023-04-01")
        period_end = pd.to_datetime("2023-06-30")
        limit = 10

    return {
        "mode": mode,
        "period_start": period_start,
        "period_end": period_end,
        "filters": filters,
        "group_by": group_by,
        "sort_by": sort_by,
        "limit": limit,
        "levels": levels
    }
