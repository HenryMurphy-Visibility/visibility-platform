from datetime import datetime, timedelta


def generate_coupon_dates(issue_date, maturity_date, payment_frequency, period_start, period_end):
    """
    Generates a list of coupon payment dates from the issue date to the maturity date.

    :param issue_date: The date when the bond was issued.
    :param maturity_date: The date when the bond matures.
    :param payment_frequency: The coupon payment frequency ('annual', 'semi-annual', 'quarterly', etc.).
    :param period_start: The start of the period for which coupons are being generated.
    :param period_end: The end of the period for which coupons are being generated.
    :return: List of coupon payment dates.
    """
    coupon_dates = []
    current_date = issue_date

    if payment_frequency == 'annual':
        increment = timedelta(days=365)
    elif payment_frequency == 'semi-annual':
        increment = timedelta(days=182)  # Approximation for simplicity
    elif payment_frequency == 'quarterly':
        increment = timedelta(days=91)
    elif payment_frequency == 'monthly':
        increment = timedelta(days=30)
    else:
        raise ValueError("Unsupported payment frequency")

    # Generate coupon dates
    while current_date < maturity_date:
        if current_date >= period_start and current_date <= period_end:
            coupon_dates.append(current_date)
        current_date += increment

    return coupon_dates


def calculate_accrued_interest(issue_date, first_coupon_date, day_count_convention, payment_frequency,
                               next_to_last_coupon_date, maturity_date, valuation_date, coupon_rate, semi_split,
                               pricing_factor, face_value=100):
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
    coupon_dates = generate_coupon_dates(issue_date, maturity_date, payment_frequency, issue_date, maturity_date)

    # Check if the valuation date is a coupon payment date
    if valuation_date in coupon_dates:
        return 0, 0, 0, 0  # Set accrued interest to 0 on coupon payment date

    # Generate coupon dates
    coupon_dates = [first_coupon_date]
    current_date = first_coupon_date

    while current_date < maturity_date:
        if payment_frequency == 'annual':
            current_date += timedelta(days=365)
        elif payment_frequency == 'semi-annual':
            current_date += timedelta(days=182)
        elif payment_frequency == 'quarterly':
            current_date += timedelta(days=91)
        elif payment_frequency == 'monthly':
            current_date += timedelta(days=30)

        if current_date <= maturity_date:
            coupon_dates.append(current_date)

    # Find the last and next coupon dates relative to valuation_date
    last_coupon_dates = [date for date in coupon_dates if date <= valuation_date]
    if last_coupon_dates:
        last_coupon_date = max(last_coupon_dates)
    else:
        last_coupon_date = issue_date

    next_coupon_date = min(date for date in coupon_dates if date > valuation_date)

    # Calculate days of accrual based on day count convention
    if day_count_convention == "30/360 Bond Basis":
        days_of_accrual = 360 * (valuation_date.year - last_coupon_date.year) + 30 * (
                valuation_date.month - last_coupon_date.month) + (min(30, valuation_date.day) - min(30, last_coupon_date.day))
    elif day_count_convention == "30/360 ISDA":
        d1 = 30 if last_coupon_date.day == 31 else last_coupon_date.day
        d2 = 30 if valuation_date.day == 31 and last_coupon_date.day in [30, 31] else valuation_date.day
        days_of_accrual = 360 * (valuation_date.year - last_coupon_date.year) + 30 * (
                valuation_date.month - last_coupon_date.month) + (d2 - d1)
    elif day_count_convention == "30E/360":
        d1 = min(30, last_coupon_date.day)
        d2 = min(30, valuation_date.day)
        days_of_accrual = 360 * (valuation_date.year - last_coupon_date.year) + 30 * (
                valuation_date.month - last_coupon_date.month) + (d2 - d1)
    elif day_count_convention == "actual/360":
        days_of_accrual = (valuation_date - last_coupon_date).days
    elif day_count_convention == "actual/365":
        days_of_accrual = (valuation_date - last_coupon_date).days
    elif day_count_convention == "actual/actual ISDA":
        days_of_accrual = (valuation_date - last_coupon_date).days
    elif day_count_convention == "actual/actual ICMA":
        num_days = (valuation_date - last_coupon_date).days
        days_in_period = (next_coupon_date - last_coupon_date).days
        days_of_accrual = num_days / days_in_period * 365
    else:
        raise ValueError("Unsupported day count convention")

    coupon_rate = float(coupon_rate)

    # Calculate the period's coupon payment
    if payment_frequency == 'annual':
        coupon_payment = coupon_rate
        days_in_period = 365 if day_count_convention == "actual/365" else 360
    elif payment_frequency == 'semi-annual':
        coupon_payment = coupon_rate / 2
        days_in_period = 182 if day_count_convention == "actual/365" else 180
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

    # Calculate the daily accrued interest per 100 face value
    daily_accrued_per_100 = accrued_interest / days_of_accrual if days_of_accrual > 0 else 0

    return accrued_interest, days_in_period, days_of_accrual, daily_accrued_per_100
#
# # Example usage
# issue_date = "01/01/2022"
# first_coupon_date = "07/01/2022"
# day_count_convention = "30/360 Bond Basis"
# payment_frequency = "semi-annual"
# next_to_last_coupon_date = "07/01/2025"
# maturity_date = "01/01/2026"
# valuation_date = "09/01/2023"
# coupon_rate = 5
# semi_split = 'A'
#
# accrued_interest, days_in_period, days_of_accrual, daily_accrued_per_100 = calculate_accrued_interest(
#     issue_date, first_coupon_date, day_count_convention, payment_frequency, next_to_last_coupon_date,
#     maturity_date, valuation_date, coupon_rate, semi_split)
#
# print(f"\nAccrued Interest: {accrued_interest}")
# print(f"Days in Period: {days_in_period}")
# print(f"Days of Accrual: {days_of_accrual}")
# print(f"Daily Accrued Interest per 100 Face Value: {daily_accrued_per_100:.4f}")
#
#
#
# import random
# from datetime import datetime, timedelta
#
#
# def random_date(start, end):
#     """Generate a random date between start and end."""
#     delta = end - start
#     random_days = random.randint(0, delta.days)
#     return start + timedelta(days=random_days)
#
#
# def random_bond_parameters():
#     """Generate random bond parameters for testing."""
#     issue_date = random_date(datetime(2015, 1, 1), datetime(2023, 1, 1))
#     maturity_date = random_date(issue_date + timedelta(days=365), issue_date + timedelta(days=365 * 10))
#     first_coupon_date = issue_date + timedelta(days=182)
#     valuation_date = random_date(issue_date, maturity_date - timedelta(days=30))
#     coupon_rate = random.uniform(1, 10)  # Random coupon rate between 1% and 10%
#     payment_frequency = random.choice(['annual', 'semi-annual', 'quarterly', 'monthly'])
#     day_count_convention = random.choice(
#         ['30/360 Bond Basis', '30/360 ISDA', '30E/360', 'actual/360', 'actual/365', 'actual/actual ISDA',
#          'actual/actual ICMA'])
#     semi_split = random.choice(['A', 'C']) if payment_frequency == 'semi-annual' else None
#
#     return {
#         "issue_date": issue_date.strftime("%m/%d/%Y"),
#         "first_coupon_date": first_coupon_date.strftime("%m/%d/%Y"),
#         "day_count_convention": day_count_convention,
#         "payment_frequency": payment_frequency,
#         "next_to_last_coupon_date": (maturity_date - timedelta(days=182)).strftime("%m/%d/%Y"),
#         "maturity_date": maturity_date.strftime("%m/%d/%Y"),
#         "valuation_date": valuation_date.strftime("%m/%d/%Y"),
#         "coupon_rate": coupon_rate,
#         "semi_split": semi_split
#     }
#
#
# def calculate_accrued_interest_for_random_bonds(num_tests):
#     """Generate random bonds and calculate accrued interest for each one."""
#     results = []
#
#     for i in range(num_tests):
#         bond_params = random_bond_parameters()
#
#         try:
#             accrued_interest, days_in_period, days_of_accrual, daily_accrued_per_100 = calculate_accrued_interest(
#                 bond_params["issue_date"],
#                 bond_params["first_coupon_date"],
#                 bond_params["day_count_convention"],
#                 bond_params["payment_frequency"],
#                 bond_params["next_to_last_coupon_date"],
#                 bond_params["maturity_date"],
#                 bond_params["valuation_date"],
#                 bond_params["coupon_rate"],
#                 bond_params["semi_split"]
#             )
#
#             results.append({
#                 "bond_parameters": bond_params,
#                 "accrued_interest": accrued_interest,
#                 "days_in_period": days_in_period,
#                 "days_of_accrual": days_of_accrual,
#                 "daily_accrued_per_100": daily_accrued_per_100
#             })
#
#         except ValueError as e:
#             # Catch unsupported day count convention or calculation issues
#             results.append({
#                 "bond_parameters": bond_params,
#                 "error": str(e)
#             })
#
#     # Print results for each random bond
#     for idx, result in enumerate(results):
#         print(f"\n--- Bond Test {idx + 1} ---")
#         if "error" in result:
#             print(f"Error: {result['error']}")
#         else:
#             print(f"Bond Parameters: {result['bond_parameters']}")
#             print(f"Accrued Interest: {result['accrued_interest']:.4f}")
#             print(f"Days in Period: {result['days_in_period']}")
#             print(f"Days of Accrual: {result['days_of_accrual']}")
#             print(f"Daily Accrued Interest per 100 Face Value: {result['daily_accrued_per_100']:.4f}")
#
#
# # Run random bond calculations for 10 tests
# calculate_accrued_interest_for_random_bonds(100)
#
#
#
