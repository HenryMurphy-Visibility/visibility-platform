# ============================================================
# Visibility — Compute Result Contract
# compute_result.py
# Every compute function returns a ComputeResult.
# The renderer consumes it. The API serializes it.
# Nothing else needs to know what produced it.
# ============================================================

from dataclasses import dataclass, field
from typing import Optional
import pandas as pd
from datetime import datetime


@dataclass
class ComputeResult:
    function:     str
    portfolio:    str
    calendar:     str
    period_start: str
    period_end:   str
    shape:        str
    data:         Optional[pd.DataFrame]
    valid:        bool = True
    errors:       list = field(default_factory=list)
    metadata:     dict = field(default_factory=dict)
    created_at:   str = field(
                      default_factory=lambda:
                      datetime.now().isoformat()
                  )