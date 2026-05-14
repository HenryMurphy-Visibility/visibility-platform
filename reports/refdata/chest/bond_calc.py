from datetime import datetime, timedelta


import datetime

from datetime import datetime, timedelta

def calculate_accrued_interest(issue_date, first_coupon_date, day_count_convention, payment_frequency,
                               next_to_last_coupon_date, maturity_date, valuation_date, coupon_rate, semi_split):
    # Convert dates to datetime objects if they are strings
    if isinstance(issue_date, str):
        issue_date = datetime.strptime(issue_date, "%m/%d/%Y")
    if isinstance(first_coupon_date, str):
        first_coupon_date = datetime.strptime(first_coupon_date, "%m/%d/%Y")
    if isinstance(next_to_last_coupon_date, str):
        next_to_last_coupon_date = datetime.strptime(next_to_last_coupon_date, "%m/%d/%Y")
    if isinstance(maturity_date, str):
        maturity_date = datetime.strptime(maturity_date, "%m/%d/%Y")
    if isinstance(valuation_date, str):
        valuation_date = datetime.strptime(valuation_date, "%m/%d/%Y")

    # Generate coupon dates
    coupon_dates = [first_coupon_date]
    current_date = valuation_date

    while current_date < maturity_date:
        if payment_frequency == 'annual':
            current_date += timedelta(days=365)
        elif payment_frequency == 'semi-annual':
            if semi_split == 'A':
                current_date += timedelta(days=365 // 2)
            elif semi_split == 'C':
                if current_date.month <= 6:
                    current_date += timedelta(days=182)
                else:
                    current_date += timedelta(days=183)
        elif payment_frequency == 'quarterly':
            current_date += timedelta(days=91)
        elif payment_frequency == 'monthly':
            current_date += timedelta(days=30)
        coupon_dates.append(current_date)

    # Find the last and next coupon dates relative to valuation_date
    last_coupon_dates = [date for date in coupon_dates if date <= valuation_date]
    if last_coupon_dates:
        last_coupon_date = max(last_coupon_dates)
    else:
        last_coupon_date = issue_date

    next_coupon_date = min(date for date in coupon_dates if date > valuation_date)


    # Calculate days of accrual based on day count convention
    if day_count_convention == "30/360":
        days_of_accrual = 360 * (valuation_date.year - last_coupon_date.year) + 30 * (
                valuation_date.month - last_coupon_date.month) + (valuation_date.day - last_coupon_date.day)
    elif day_count_convention == "actual/360":
        days_of_accrual = (valuation_date - last_coupon_date).days
    elif day_count_convention == "actual/365":
        days_of_accrual = (valuation_date - last_coupon_date).days
    elif day_count_convention == "actual/actual":
        days_of_accrual = (valuation_date - last_coupon_date).days
    elif day_count_convention == "30E/360":
        d1 = last_coupon_date.day
        d2 = valuation_date.day
        if d1 == 31: d1 = 30
        if d2 == 31: d2 = 30
        days_of_accrual = 360 * (valuation_date.year - last_coupon_date.year) + 30 * (
                valuation_date.month - last_coupon_date.month) + (d2 - d1)
    else:
        raise ValueError("Unsupported day count convention")

    # Calculate the period's coupon payment
    if payment_frequency == 'annual':
        coupon_payment = coupon_rate
        days_in_period = 365 if day_count_convention == "actual/365" else 360
    elif payment_frequency == 'semi-annual':
        if semi_split == 'A':
            coupon_payment = coupon_rate / 2
            days_in_period = 182 if day_count_convention == "actual/365" else 180
        elif semi_split == 'C':
            coupon_payment = coupon_rate / 2
            days_in_period = (next_coupon_date - last_coupon_date).days
    elif payment_frequency == 'quarterly':
        coupon_payment = coupon_rate / 4
        days_in_period = 91 if day_count_convention == "actual/365" else 90
    elif payment_frequency == 'monthly':
        coupon_payment = coupon_rate / 12
        days_in_period = 30 if day_count_convention == "actual/365" else 30
    else:
        raise ValueError("Unsupported payment frequency")

    # Calculate accrued interest
    accrued_interest = coupon_payment * days_of_accrual / days_in_period

    return accrued_interest, days_in_period, days_of_accrual
