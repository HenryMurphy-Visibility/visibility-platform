# =====================================================================
#      CPU — CLOSED PERIOD UTILITIES (FULL FILE, NO SNIPPETS)
# =====================================================================
# This is the “front door” of closed-period processing.
# It:
#   • Loads the calendar
#   • Locates selected_record and preceding_record
#   • Builds the CPU payload
#   • Calls the CPH (Central Processing Hub)
#
# NOTHING ELSE. 100% orchestration.
# =====================================================================

import json
import os

from datetime import datetime



# =====================================================================
#             PUBLIC ENTRY: CPU (Closed Period Utilities)
# =====================================================================

# CPU.py  (simple, correct, final)

from central_processing_hub import do_processing

def CPU(portfolio, calendar, period_name, mode):
    """
    CPU is the unified entrypoint for ALL workflows:
    - GWI workflows
    - API calls
    - Command line
    - Batch automation

    It simply forwards the four key arguments directly into do_processing.
    Nothing more. Nothing less.
    """
    return do_processing(
        portfolio_name=portfolio,
        calendar=calendar,
        period_name=period_name,
        mode=mode
    )


if __name__ == "__main__":
    CPU(
        portfolio="Portfolio1",
        calendar="Current Knowledge",
        period_name="Current Knowledge",
        mode="Snapshot"    # or "Snapshot"
    )
