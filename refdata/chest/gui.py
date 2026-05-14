
import datetime


# Set up the title and section titles
title = "FundSmart Accounting Engine"
ia_processing_section_title = "Investment Accounting Inputs"
fa_processing_section_title = "Fund Accounting Inputs"
reports_section_title = "Reports"

# Define the message for the processing section
processing_section_message = "Please enter the following details:"

# Define the choices for the reports section
reports_section_choices = [
    "Investment Accounting",
    "Fund Accounting"
    # Add more report choices as needed
]

# Default values for the date inputs
current_period_start = "05/04/2022:00:00:00"
current_period_cutoff = "05/05/2022:23:59:59"
current_knowledge_cutoff = "05/05/2029:10:00:00"
prior_period_start = "05/04/2022:00:00:00"
prior_period_cutoff = "05/05/2022:23:59:59"
prior_knowledge_cutoff = "05/06/2022:10:00:00"

# Function to display the processing inputs section
def display_ia_processing_inputs():
    ia_processing_inputs = easygui.multenterbox(
        processing_section_message,
        title,
        ["Current Period Start", "Current Period Cutoff", "Current Knowledge Cutoff", "Prior Period Start",
         "Prior Period Cutoff", "Prior Knowledge Cutoff", "Process Prior?", "Process Current?", "Report Adjustments?",
         "Post Adjustments", "TPS Check", "Number of Portfolios", "Prior Period Name", "Current Period Name"],
        values=[current_period_start, current_period_cutoff, current_knowledge_cutoff,
                prior_period_start, prior_period_cutoff, prior_knowledge_cutoff,
                "Yes", "Yes", "No", "No", "No", 1, "NA", "NA"],  # Set default values
    )

    if ia_processing_inputs is None:
        # User closed the dialog without providing input, handle this case
        easygui.msgbox("Error: Please provide the required inputs.", title="Input Error")
        return None

    return ia_processing_inputs

def display_fa_processing_inputs():
    fa_processing_inputs = easygui.multenterbox(
        processing_section_message,
        title,
        ["Current Period Start", "Current Period Cutoff", "Current Knowledge Cutoff","Prior Period Start", "Prior Period Cutoff", "Prior Knowledge Cutoff", "Process Prior?", "Process Current?", "Report Adjustments?", "Post Adjustments","TPS Check", "Number of Portfolios", "Prior Period Name", "Current Period Name"],
        values=[current_period_start, current_period_cutoff, current_knowledge_cutoff,
                prior_period_start, prior_period_cutoff, prior_knowledge_cutoff,
                "Yes","Yes", "No", "Yes", "No", 1, "2022-05-04", "2022-05-05"],  # Set default values
    )

    if fa_processing_inputs is None:
        # User closed the dialog without providing input, handle this case
        easygui.msgbox("Error: Please provide the required inputs.", title="Input Error")
        return None

    return fa_processing_inputs

# Function to display the reports section
def display_high_level_section():
    reports_selected = easygui.choicebox(
        "Select:",
        title,
        reports_section_choices,
    )
    return reports_selected

# GUI function
def display_gui():
    choice = display_high_level_section()

    if choice == "Investment Accounting":
        processing_inputs = display_ia_processing_inputs()
    else:
        processing_inputs = display_fa_processing_inputs()

    if processing_inputs is None:
        # Handle the case when inputs are not provided
        easygui.msgbox("Error: Please provide the required inputs.", title="Input Error")
        return None

    # Extract the captured input values
    current_period_start_str = processing_inputs[0] if processing_inputs[0] else current_period_start
    current_period_cutoff_str = processing_inputs[1] if processing_inputs[1] else current_period_cutoff
    current_knowledge_cutoff_str = processing_inputs[2] if processing_inputs[2] else current_knowledge_cutoff
    prior_period_start_str = processing_inputs[3] if processing_inputs[3] else prior_period_start
    prior_period_cutoff_str = processing_inputs[4] if processing_inputs[4] else prior_period_cut+off
    prior_knowledge_cutoff_str = processing_inputs[5] if processing_inputs[5] else prior_knowledge_cutoff
    process_base = processing_inputs[6]
    process_current = processing_inputs[7]
    report_adjustments = processing_inputs[8]
    post_adjustments = processing_inputs[9]
    run_time = processing_inputs[10]
    numport = processing_inputs[11]
    prior_period_name = processing_inputs[12]
    current_period_name = processing_inputs[13]

    # Convert the string inputs to datetime objects
    current_period_start = datetime.datetime.strptime(current_period_start_str, "%m/%d/%Y:%H:%M:%S")
    current_period_cutoff = datetime.datetime.strptime(current_period_cutoff_str, "%m/%d/%Y:%H:%M:%S")
    current_knowledge_cutoff = datetime.datetime.strptime(current_knowledge_cutoff_str, "%m/%d/%Y:%H:%M:%S")
    prior_period_start = datetime.datetime.strptime(prior_period_start_str, "%m/%d/%Y:%H:%M:%S")
    prior_period_cutoff = datetime.datetime.strptime(prior_period_cutoff_str, "%m/%d/%Y:%H:%M:%S")
    prior_knowledge_cutoff = datetime.datetime.strptime(prior_knowledge_cutoff_str, "%m/%d/%Y:%H:%M:%S")
    numport = int(numport)

    return current_period_start, current_period_cutoff, current_knowledge_cutoff, prior_period_start, prior_period_cutoff, \
        prior_knowledge_cutoff,process_current, process_base, report_adjustments, post_adjustments, run_time, numport, prior_period_name, current_period_name
# import easygui
# import datetime
#
# # Set up the title and section titles
# title = "FundSmart Accounting Engine"
# processing_section_message = "Please enter the following details:"
#
# # Default values for the date inputs
# currentperiod_start = "05/04/2022:00:00:00"
# currentperiod_cutoff = "05/04/2022:23:59:59"
# currentknowledge_cutoff = "05/05/2022:23:59:59"
#
# # Function to display the processing inputs section
# def display_processing_inputs():
#     processing_inputs = easygui.multenterbox(
#         processing_section_message,
#         title,
#         ["Period_Start", "Period Cutoff", "Knowledge Cutoff", "Process Base?", "Process Current?", "Report Adjustments?", "TPS Check", "Number of Portfolios", "Period Start"],
#         values=[currentperiod_start, currentperiod_cutoff, currentknowledge_cutoff, "Yes", "Yes", "Yes", "No", 1, "2022-05-04"]
#     )
#
#     if processing_inputs is None:
#         # User closed the dialog without providing input
#         easygui.msgbox("Error: Please provide the required inputs.", title="Input Error")
#         return None
#
#     return processing_inputs
#
# def main_menu():
#     choices = ["Fund Accounting", "Investment Accounting"]
#     user_choice = easygui.buttonbox("Choose a processing type:", title=title, choices=choices)
#
#     if user_choice == "Fund Accounting":
#         processing_inputs = display_processing_inputs()
#         if processing_inputs is None:
#             return None
#         return processing_inputs
#
#     elif user_choice == "Investment Accounting":
#         processing_inputs = display_processing_inputs()
#         if processing_inputs is None:
#             return None
#         return processing_inputs
#
#     else:
#         # If the user closes the menu without selecting
#         return None
#
# if __name__ == '__main__':
#     result = main_menu()
#     if result:
#         print(result)
#     else:
#         print("No input received.")
