
import datetime
import pandas
pass
class ValidationError(Exception):
    pass

def invalid_date_format(date_str):
    try:
        datetime.datetime.strptime(date_str, '%m/%d/%Y:%H:%M:%S')
        return False, None  # No error
    except ValueError:
        return True, "tradedate"  # Error in conversion

def trade_date_greater_than_settle(trade_date_str, settle_date_str):
    trade_date = datetime.datetime.strptime(trade_date_str, '%m/%d/%Y:%H:%M:%S')
    settle_date = datetime.datetime.strptime(settle_date_str, '%m/%d/%Y:%H:%M:%S')
    if trade_date > settle_date:
        return True, "settledate"
    return False, None

def knowledge_begin_date_greater_or_equal_to_knowledge_end(kdbegin_str, kdend_str):
    kdbegin_date = datetime.datetime.strptime(kdbegin_str, '%m/%d/%Y:%H:%M:%S')
    kdend_date = datetime.datetime.strptime(kdend_str, '%m/%d/%Y:%H:%M:%S')
    if kdbegin_date >= kdend_date:
        return True, "kdend-"
    return False, None
def contains_whitespace(row):
    for key, value in row.items():
        if isinstance(value, str) and ' ' in value:
            return True, key
    return False, None

def numeric_required(data_obj, column_name):
    value = data_obj.get(column_name)
    if value is None:
        return False, None
    return not str(value).isdigit(), column_name
def check_duplicate_tranid(records):
    seen_tranids = set()
    for index, record in enumerate(records, start=1):
        tranid = record.get('tranid')
        if tranid in seen_tranids:
            return True, (index, 'tranid')
        seen_tranids.add(tranid)
    return False, (None, None)  # Modified this line

import pandas as pd
from collections import Counter

def validate_records(records, validations):
    # First, check for duplicate tranid
    if 'tranid' in validations and validations['tranid']:
        tranid_counts = Counter(record['tranid'] for record in records if 'tranid' in record)
        duplicate_tranids = [tranid for tranid, count in tranid_counts.items() if count > 1]
        if duplicate_tranids:
            raise ValidationError(f"Records failed validation: Duplicate tranids found - {duplicate_tranids}")

    for index, record in enumerate(records, start=1):
        for code, is_enabled in validations.items():
            if is_enabled:
                validation_data = validation_map.get(code)
                if validation_data is None:
                    print(f"Warning: No validation function found for code {code}")
                    continue

                validation_fn = validation_data["fn"]
                args = [record.get(arg_name) for arg_name in validation_data.get("args", [])]
                has_error, column_with_error = validation_fn(*args)
                if has_error:
                    raise ValidationError(f"Record {index} failed validation {code} in column {column_with_error}.")

def validate_excel(file_path, validations):
    df = pd.read_excel(file_path)

    # First, check for duplicate tranid
    if 'tranid' in validations and validations['tranid'] and 'tranid' in df.columns:
        duplicated_rows = df[df['tranid'].duplicated(keep=False)]
        if not duplicated_rows.empty:
            indices = duplicated_rows.index.tolist()
            raise ValidationError(f"Rows at indices {indices} failed validation: Duplicate tranid in column 'tranid'.")

    for index, row in df.iterrows():
        for code, is_enabled in validations.items():
            if is_enabled:
                validation_data = validation_map.get(code)
                if validation_data is None:
                    print(f"Warning: No validation function found for code {code}")
                    continue

                validation_fn = validation_data["fn"]
                args = [row[arg_name] for arg_name in validation_data.get("args", [])]
                has_error, column_with_error = validation_fn(*args)
                if has_error:
                    raise ValidationError(f"Row {index + 2} failed validation {code} in column {column_with_error}.")

validation_map = {
    "103": {"fn": invalid_date_format, "args": ["tradedate"]},
    "104": {"fn": trade_date_greater_than_settle, "args": ["tradedate", "settledate"]},
    "105": {"fn": contains_whitespace, "args": []},  # no specific column name required
    "106": {"fn": knowledge_begin_date_greater_or_equal_to_knowledge_end, "args": ["kdbegin", "kdend"]},
    "107": {"fn": numeric_required, "args": ["numeric_value"]}
    # ... other code-function mappings
}

data_obj = {
    #... other fields
}

import pandas as pd


def validate_records(records, validations):
    # First, check for duplicate tranid
    has_error, (index, column) = check_duplicate_tranid(records)
    if has_error:
        raise ValidationError(f"Record {index} failed validation: Duplicate tranid in column {column}.")
    for index, record in enumerate(records, start=1):
        for code, is_enabled in validations.items():
            if is_enabled:
                validation_data = validation_map.get(code)
                if validation_data is None:
                    print(f"Warning: No validation function found for code {code}")
                    continue

                validation_fn = validation_data["fn"]
                if code == "105":  # Whitespace check, special handling
                    has_whitespace, column_with_whitespace = validation_fn(record)
                    if has_whitespace:
                        raise ValidationError(f"Record {index + 1} failed validation {code} in column {column_with_whitespace}.")
                else:
                    args = [record.get(arg_name) for arg_name in validation_data["args"]]
                    has_error, column_with_error = validation_fn(*args)
                    if has_error:
                        raise ValidationError(f"Record {index + 1} failed validation {code} in column {column_with_error}.")


def validate_excel(file_path, validations):
    df = pd.read_excel(file_path)

    # First, check for duplicate tranid
    if 'tranid' in validations and validations['tranid'] and 'tranid' in df.columns:
        if df['tranid'].duplicated().any():
            dup_rows = df[df['tranid'].duplicated(keep=False)]
            raise ValidationError(
                f"Rows with indices {dup_rows.index.tolist()} failed validation: Duplicate tranid in column 'tranid'.")

    for index, row in df.iterrows():
        for code, is_enabled in validations.items():
            if is_enabled:
                validation_data = validation_map.get(code)
                if validation_data is None:
                    print(f"Warning: No validation function found for code {code}")
                    continue

                validation_fn = validation_data["fn"]

                # Check if the validation function is 'contains_whitespace'
                if validation_fn == contains_whitespace:
                    has_error, column_with_error = validation_fn(row)
                else:
                    args = [row[arg_name] for arg_name in validation_data["args"]]
                    has_error, column_with_error = validation_fn(*args)

                if has_error:
                    raise ValidationError(f"Row {index + 2} failed validation {code} in column {column_with_error}.")

validations_to_apply = {
    "103": True,  # Apply invalid date format check
    "104": True, # Apply tradedate > settledate check
    "105": True,  # Whitespace check
    "106": True  # Whitespace
}

# try:
#     df = pd.read_excel("C:/Users/hjmne/PycharmProjects/chest/refdata/portfolio1.xlsx")
#     records = df.to_dict(orient="records")
#     validate_records(records, validations_to_apply)
#     validate_excel("C:/Users/hjmne/PycharmProjects/chest/refdata/portfolio1.xlsx", validations_to_apply)
# except ValidationError as ve:
#     print(ve)
