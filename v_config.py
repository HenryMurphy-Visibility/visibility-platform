# ============================================================
# Visibility — Central Configuration
# v_config.py
# All paths live here. Nothing else imports paths directly.
# To deploy on a different machine, set the environment
# variable VISIBILITY_BASE_PATH before starting the app.
# ============================================================

import os

BASE_PATH    = os.environ.get(
                   "VISIBILITY_BASE_PATH",
                   "C:/Users/hjmne/PycharmProjects/chest"
               )

FUNDS_PATH   = os.path.join(BASE_PATH, "funds")
REFDATA_PATH = os.path.join(BASE_PATH, "refdata")
REPORTS_PATH = os.path.join(BASE_PATH, "reports")
VIEWS_PATH   = os.path.join(BASE_PATH, "views")

API_HOST     = os.environ.get("VISIBILITY_API_HOST", "127.0.0.1")
API_PORT     = int(os.environ.get("VISIBILITY_API_PORT", "8000"))