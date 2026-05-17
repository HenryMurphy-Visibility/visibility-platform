# ============================================================
# oversight_routes.py
# Visibility — Oversight Console REST API Routes
#
# Authority-gated endpoints for governance operations.
# Registered in app.py via:
#   from oversight_routes import oversight_router
#   app.include_router(oversight_router)
#
# Endpoints:
#   GET  /api/v1/oversight/dashboard
#   GET  /api/v1/oversight/calendar/{portfolio}/{calendar}
#   POST /api/v1/oversight/calendar/{portfolio}/{calendar}/{period}/close
#   POST /api/v1/oversight/calendar/{portfolio}/{calendar}/{period}/reopen
#   POST /api/v1/oversight/calendar/{portfolio}/{calendar}/{period}/restate
#   POST /api/v1/oversight/signoff
#   POST /api/v1/oversight/validate
#   GET  /api/v1/oversight/audit
#
# All mutating actions are permanently logged to:
#   funds/{portfolio}/Oversight/audit.jsonl
#
# Henry J. Murphy — Chest Financial Systems
# ============================================================

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
from datetime import datetime, date
from calendar import monthrange
import traceback
import json

from v_config import FUNDS_PATH

oversight_router = APIRouter(prefix="/api/v1/oversight", tags=["Oversight"])

# ============================================================
# MODELS
# ============================================================

class CloseRequest(BaseModel):
    knowledge_end: str        # YYYY-MM-DD
    note:          str = ""
    actor:         str = "unknown"

class ReopenRequest(BaseModel):
    reason: str
    actor:  str = "unknown"

class RestateRequest(BaseModel):
    reason: str
    actor:  str = "unknown"

class SignoffRequest(BaseModel):
    type:      str            # ops | fa | perf
    portfolio: str
    calendar:  str
    period:    str
    note:      str = ""
    actor:     str = "unknown"

class ValidateRequest(BaseModel):
    portfolio: str
    calendar:  str
    period:    str
    suite:     str = "standard"
    actor:     str = "unknown"


# ============================================================
# PATHS
# ============================================================

def _portfolio_dir(portfolio: str) -> Path:
    return Path(FUNDS_PATH) / portfolio

def _calendar_path(portfolio: str, calendar: str) -> Path:
    return _portfolio_dir(portfolio) / "Calendars" / calendar / f"{calendar}.txt"

def _oversight_dir(portfolio: str) -> Path:
    d = _portfolio_dir(portfolio) / "Oversight"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _audit_path(portfolio: str) -> Path:
    return _oversight_dir(portfolio) / "audit.jsonl"


# ============================================================
# AUDIT LOGGING
# ============================================================

def write_audit(portfolio: str, action_type: str, action: str,
                detail: str, actor: str, extra: dict = None):
    """
    Append a permanent audit entry to funds/{portfolio}/Oversight/audit.jsonl
    One JSON record per line. Never deleted, never modified.
    """
    entry = {
        "ts":          datetime.now().isoformat(),
        "portfolio":   portfolio,
        "actor":       actor,
        "action_type": action_type,
        "action":      action,
        "detail":      detail,
    }
    if extra:
        entry.update(extra)

    with open(_audit_path(portfolio), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    print(f">>> AUDIT | {portfolio} | {actor} | {action} | {detail}")


# ============================================================
# CALENDAR HELPERS
# ============================================================

def load_calendar(portfolio: str, calendar: str) -> list:
    """Load all period records from a calendar file."""
    cal_path = _calendar_path(portfolio, calendar)
    if not cal_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Calendar not found: {portfolio}/{calendar}"
        )
    records = []
    with open(cal_path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln and ln.startswith("{"):
                try:
                    records.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue
    return records


def save_calendar(portfolio: str, calendar: str, records: list):
    """Write all period records back to the calendar file."""
    cal_path = _calendar_path(portfolio, calendar)
    with open(cal_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def find_period(records: list, period_name: str) -> tuple[Optional[dict], int]:
    """Return (record, index) or (None, -1)."""
    for i, r in enumerate(records):
        if r.get("period_name") == period_name:
            return r, i
    return None, -1


def _next_period_name(calendar: str, current_name: str,
                      current_cutoff_str: str) -> str:
    """
    Derive the next period name from the calendar type and current cutoff.
    current_cutoff_str: YYYY-MM-DD:HH:MM:SS
    """
    cutoff_date = datetime.strptime(
        current_cutoff_str[:10], "%Y-%m-%d"
    ).date()

    # Advance one day past the cutoff to get next period start
    from datetime import timedelta
    next_start = cutoff_date + timedelta(days=1)

    if calendar == "Monthly":
        return f"{next_start.year}-{next_start.month:02d}"
    elif calendar == "Quarterly":
        q = (next_start.month - 1) // 3 + 1
        return f"{next_start.year}-Q{q}"
    elif calendar == "Yearly":
        return str(next_start.year)
    else:
        # Daily
        return next_start.strftime("%Y-%m-%d")


def _period_cutoff_for(calendar: str, period_name: str) -> str:
    """
    Given a period name, return its natural cutoff date as YYYY-MM-DD:23:59:59
    """
    if calendar == "Monthly":
        # period_name = YYYY-MM
        year, month = int(period_name[:4]), int(period_name[5:7])
        last_day = monthrange(year, month)[1]
        return f"{year}-{month:02d}-{last_day:02d}:23:59:59"
    elif calendar == "Quarterly":
        # period_name = YYYY-QN
        year = int(period_name[:4])
        q    = int(period_name[6])
        ends = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
        return f"{year}-{ends[q]}:23:59:59"
    elif calendar == "Yearly":
        return f"{period_name}-12-31:23:59:59"
    else:
        # Daily — period_name IS the date
        return f"{period_name}:23:59:59"


# ============================================================
# DASHBOARD
# ============================================================

@oversight_router.get("/dashboard")
def get_dashboard():
    """
    Summary stats across all portfolios for the Oversight dashboard.
    """
    try:
        funds_dir = Path(FUNDS_PATH)
        open_periods     = 0
        closed_this_month = 0
        pending_signoff  = 0
        active_restatements = 0
        this_month = datetime.now().strftime("%Y-%m")

        for portfolio_dir in sorted(funds_dir.iterdir()):
            if not portfolio_dir.is_dir():
                continue
            cal_root = portfolio_dir / "Calendars"
            if not cal_root.exists():
                continue
            for cal_dir in cal_root.iterdir():
                if not cal_dir.is_dir():
                    continue
                cal_name = cal_dir.name
                cal_file = cal_dir / f"{cal_name}.txt"
                if not cal_file.exists():
                    continue
                with open(cal_file, "r", encoding="utf-8") as f:
                    for ln in f:
                        ln = ln.strip()
                        if not ln.startswith("{"):
                            continue
                        try:
                            rec = json.loads(ln)
                        except Exception:
                            continue
                        status = rec.get("period_status", "")
                        if status in ("Open", "Pending"):
                            open_periods += 1
                        if status == "Closed":
                            closed_at = rec.get("closed_at", "")
                            if closed_at.startswith(this_month):
                                closed_this_month += 1
                        if status == "Needs Restatement":
                            active_restatements += 1

        return {
            "open_periods":         open_periods,
            "closed_this_month":    closed_this_month,
            "pending_signoff":      pending_signoff,
            "active_restatements":  active_restatements,
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# CALENDAR OVERVIEW
# ============================================================

@oversight_router.get("/calendar/{portfolio}/{calendar}")
def get_calendar_periods(portfolio: str, calendar: str):
    """Return all periods for a portfolio/calendar with status."""
    try:
        records = load_calendar(portfolio, calendar)
        return {
            "portfolio": portfolio,
            "calendar":  calendar,
            "periods":   records,
            "count":     len(records),
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# CLOSE PERIOD
# ============================================================

@oversight_router.post("/calendar/{portfolio}/{calendar}/{period}/close")
def close_period(portfolio: str, calendar: str, period: str,
                 req: CloseRequest):
    """
    Close a period.

    - Stamps knowledge_end on the period
    - Sets period_status = "Closed"
    - Creates the next contiguous period if it doesn't exist
    - Writes permanent audit entry
    """
    try:
        records = load_calendar(portfolio, calendar)
        rec, idx = find_period(records, period)

        if rec is None:
            raise HTTPException(
                status_code=404,
                detail=f"Period '{period}' not found in {portfolio}/{calendar}"
            )

        if rec.get("period_status") == "Closed":
            raise HTTPException(
                status_code=409,
                detail=f"Period '{period}' is already closed"
            )

        now = datetime.now().isoformat()

        # ── STAMP CLOSE ───────────────────────────────────────────
        records[idx]["period_status"]            = "Closed"
        records[idx]["current_period_knowledge"] = f"{req.knowledge_end}:23:59:59"
        records[idx]["closed_at"]                = now
        records[idx]["closed_by"]                = req.actor
        records[idx]["close_note"]               = req.note

        # ── CREATE NEXT PERIOD IF NEEDED ──────────────────────────
        next_name   = _next_period_name(
            calendar,
            period,
            rec.get("current_period_cutoff", "")
        )
        _, next_idx = find_period(records, next_name)
        next_period_created = None

        if next_idx == -1:
            cutoff_str = rec.get("current_period_cutoff", "")
            next_cutoff = _period_cutoff_for(calendar, next_name)

            from datetime import timedelta
            cutoff_date = datetime.strptime(cutoff_str[:10], "%Y-%m-%d").date()
            next_start  = cutoff_date + timedelta(days=1)

            new_rec = {
                "period_name":              next_name,
                "period_status":            "Pending",
                "current_period_start":     f"{next_start.strftime('%Y-%m-%d')}:00:00:00",
                "current_period_cutoff":    next_cutoff,
                "current_period_knowledge": now[:19].replace("T", " ") + ":00",
                "prior_period_start":       rec.get("current_period_start"),
                "prior_period_cutoff":      rec.get("current_period_cutoff"),
                "prior_period_knowledge":   f"{req.knowledge_end}:23:59:59",
            }
            records.append(new_rec)
            next_period_created = next_name

        save_calendar(portfolio, calendar, records)

        write_audit(
            portfolio  = portfolio,
            action_type = "close",
            action     = f"CLOSE {period}",
            detail     = req.note or "no note",
            actor      = req.actor,
            extra      = {
                "calendar":             calendar,
                "period":               period,
                "knowledge_end":        req.knowledge_end,
                "next_period_created":  next_period_created,
            }
        )

        print(f">>> PERIOD CLOSED | {portfolio} | {calendar} | {period} "
              f"| by {req.actor}")

        return {
            "status":               "closed",
            "portfolio":            portfolio,
            "calendar":             calendar,
            "period":               period,
            "knowledge_end":        req.knowledge_end,
            "next_period":          next_period_created,
            "closed_by":            req.actor,
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# REOPEN PERIOD
# ============================================================

@oversight_router.post("/calendar/{portfolio}/{calendar}/{period}/reopen")
def reopen_period(portfolio: str, calendar: str, period: str,
                  req: ReopenRequest):
    """
    Reopen a closed period. Senior authority action.

    - Sets period_status back to Open
    - Marks all subsequent periods as Needs Restatement
    - Writes permanent audit entry with mandatory justification
    """
    try:
        if not req.reason or not req.reason.strip():
            raise HTTPException(
                status_code=400,
                detail="Justification is required to reopen a period"
            )

        records = load_calendar(portfolio, calendar)
        rec, idx = find_period(records, period)

        if rec is None:
            raise HTTPException(
                status_code=404,
                detail=f"Period '{period}' not found in {portfolio}/{calendar}"
            )

        if rec.get("period_status") != "Closed":
            raise HTTPException(
                status_code=409,
                detail=f"Period '{period}' is not closed (status: "
                       f"{rec.get('period_status')})"
            )

        now = datetime.now().isoformat()

        # ── REOPEN TARGET PERIOD ──────────────────────────────────
        records[idx]["period_status"] = "Open"
        records[idx]["reopened_at"]   = now
        records[idx]["reopened_by"]   = req.actor
        records[idx]["reopen_reason"] = req.reason

        # ── MARK SUBSEQUENT PERIODS ───────────────────────────────
        affected = []
        for i in range(idx + 1, len(records)):
            if records[i].get("period_status") == "Closed":
                records[i]["period_status"]        = "Needs Restatement"
                records[i]["restatement_triggered"] = now
                records[i]["restatement_reason"]    = f"Prior period {period} reopened"
                affected.append(records[i]["period_name"])

        save_calendar(portfolio, calendar, records)

        write_audit(
            portfolio   = portfolio,
            action_type = "reopen",
            action      = f"REOPEN {period}",
            detail      = req.reason,
            actor       = req.actor,
            extra       = {
                "calendar":          calendar,
                "period":            period,
                "periods_affected":  affected,
            }
        )

        print(f">>> PERIOD REOPENED | {portfolio} | {calendar} | {period} "
              f"| by {req.actor} | {len(affected)} subsequent affected")

        return {
            "status":           "reopened",
            "portfolio":        portfolio,
            "calendar":         calendar,
            "period":           period,
            "reopened_by":      req.actor,
            "reason":           req.reason,
            "periods_affected": affected,
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# RESTATEMENT
# ============================================================

@oversight_router.post("/calendar/{portfolio}/{calendar}/{period}/restate")
def restate_from_period(portfolio: str, calendar: str, period: str,
                        req: RestateRequest):
    """
    Initiate restatement from a given period.
    Senior authority action — cascades to all subsequent periods.

    Marks the target period AND all subsequent periods as
    Needs Restatement. Each must be reprocessed and re-closed.
    """
    try:
        if not req.reason or not req.reason.strip():
            raise HTTPException(
                status_code=400,
                detail="Reason is required for restatement"
            )

        records = load_calendar(portfolio, calendar)
        rec, idx = find_period(records, period)

        if rec is None:
            raise HTTPException(
                status_code=404,
                detail=f"Period '{period}' not found in {portfolio}/{calendar}"
            )

        now     = datetime.now().isoformat()
        affected = []

        # ── MARK TARGET AND ALL SUBSEQUENT ────────────────────────
        for i in range(idx, len(records)):
            records[i]["period_status"]          = "Needs Restatement"
            records[i]["restatement_initiated"]  = now
            records[i]["restatement_by"]         = req.actor
            records[i]["restatement_reason"]     = req.reason
            affected.append(records[i]["period_name"])

        save_calendar(portfolio, calendar, records)

        write_audit(
            portfolio   = portfolio,
            action_type = "restate",
            action      = f"RESTATE from {period}",
            detail      = req.reason,
            actor       = req.actor,
            extra       = {
                "calendar":         calendar,
                "from_period":      period,
                "periods_affected": affected,
                "count":            len(affected),
            }
        )

        print(f">>> RESTATEMENT | {portfolio} | {calendar} | from {period} "
              f"| {len(affected)} periods | by {req.actor}")

        return {
            "status":           "restatement_initiated",
            "portfolio":        portfolio,
            "calendar":         calendar,
            "from_period":      period,
            "periods_affected": affected,
            "count":            len(affected),
            "initiated_by":     req.actor,
            "reason":           req.reason,
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# SIGN-OFF
# ============================================================

@oversight_router.post("/signoff")
def record_signoff(req: SignoffRequest):
    """
    Record an OPS, FA, or PERF sign-off for a period.
    Writes to portfolio audit log and to portfolio.json signoffs section.
    """
    try:
        valid_types = {"ops", "fa", "perf"}
        if req.type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"type must be one of: {sorted(valid_types)}"
            )

        portfolio_dir = _portfolio_dir(req.portfolio)
        if not portfolio_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Portfolio '{req.portfolio}' not found"
            )

        # Load and update portfolio config
        config_path = portfolio_dir / "portfolio.json"
        with open(config_path) as f:
            config = json.load(f)

        if "signoffs" not in config:
            config["signoffs"] = []

        config["signoffs"].append({
            "type":      req.type,
            "calendar":  req.calendar,
            "period":    req.period,
            "note":      req.note,
            "actor":     req.actor,
            "timestamp": datetime.now().isoformat(),
        })

        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        write_audit(
            portfolio   = req.portfolio,
            action_type = "signoff",
            action      = f"{req.type.upper()} SIGNOFF {req.period}",
            detail      = req.note or "no note",
            actor       = req.actor,
            extra       = {
                "calendar": req.calendar,
                "period":   req.period,
                "type":     req.type,
            }
        )

        print(f">>> SIGNOFF | {req.portfolio} | {req.type.upper()} | "
              f"{req.period} | by {req.actor}")

        return {
            "status":    "recorded",
            "portfolio": req.portfolio,
            "type":      req.type,
            "period":    req.period,
            "actor":     req.actor,
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# VALIDATION
# ============================================================

@oversight_router.post("/validate")
def run_validation(req: ValidateRequest):
    """
    Run a validation suite against a portfolio period.

    Suites:
      standard — positions, cash, income
      ops      — custodian reconciliation
      fa       — income allocation checks
      perf     — returns verification
      full     — all checks
    """
    try:
        portfolio_dir = _portfolio_dir(req.portfolio)
        if not portfolio_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Portfolio '{req.portfolio}' not found"
            )

        # ── RUN CHECKS ────────────────────────────────────────────
        checks_passed = []
        checks_failed = []

        def check(name: str, condition: bool, detail: str = ""):
            if condition:
                checks_passed.append(f"✓ {name}" + (f" — {detail}" if detail else ""))
            else:
                checks_failed.append(f"✗ {name}" + (f" — {detail}" if detail else ""))

        # Standard checks — file existence and basic integrity
        events_file = portfolio_dir / "Events" / f"{req.portfolio}.csv"
        im_file     = portfolio_dir / "RefData" / "investment_master.csv"
        cal_path    = _calendar_path(req.portfolio, req.calendar)

        check("Events file exists",    events_file.exists())
        check("Investment master exists", im_file.exists())
        check("Calendar file exists",  cal_path.exists())

        if cal_path.exists():
            records = load_calendar(req.portfolio, req.calendar)
            _, idx  = find_period(records, req.period)
            check("Period exists in calendar", idx != -1)
            if idx != -1:
                status = records[idx].get("period_status", "")
                check("Period not already closed",
                      status != "Closed",
                      f"status={status}")

        suite = req.suite
        if suite in ("ops", "full"):
            # OPS-specific — marks file
            marks_file = portfolio_dir / "Events" / f"{req.portfolio}_marks.csv"
            check("Marks file exists", marks_file.exists())

        if suite in ("fa", "full"):
            # FA-specific — signoffs recorded
            config_path = portfolio_dir / "portfolio.json"
            if config_path.exists():
                with open(config_path) as f:
                    config = json.load(f)
                ops_signed = any(
                    s.get("type") == "ops" and s.get("period") == req.period
                    for s in config.get("signoffs", [])
                )
                check("OPS sign-off recorded for period", ops_signed)

        if suite in ("perf", "full"):
            # PERF-specific — snapshots exist
            snapshots_dir = (
                portfolio_dir / "Calendars" / req.calendar / "Snapshots"
            )
            has_snapshots = snapshots_dir.exists() and any(
                snapshots_dir.iterdir()
            ) if snapshots_dir.exists() else False
            check("Snapshots directory exists",  snapshots_dir.exists())
            check("Snapshots present for period", has_snapshots)

        write_audit(
            portfolio   = req.portfolio,
            action_type = "signoff",
            action      = f"VALIDATION {req.period}",
            detail      = f"suite={req.suite} passed={len(checks_passed)} failed={len(checks_failed)}",
            actor       = req.actor,
            extra       = {
                "calendar":       req.calendar,
                "period":         req.period,
                "suite":          req.suite,
                "checks_passed":  len(checks_passed),
                "checks_failed":  len(checks_failed),
            }
        )

        return {
            "status":         "complete",
            "portfolio":      req.portfolio,
            "calendar":       req.calendar,
            "period":         req.period,
            "suite":          req.suite,
            "checks_passed":  len(checks_passed),
            "checks_failed":  len(checks_failed),
            "details":        checks_passed + checks_failed,
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# AUDIT LOG RETRIEVAL
# ============================================================

@oversight_router.get("/audit")
def get_audit(
    portfolio:   str,
    action_type: Optional[str] = None,
    limit:       int = 100,
):
    """Return audit log entries for a portfolio."""
    try:
        audit_file = _audit_path(portfolio)
        if not audit_file.exists():
            return {"entries": [], "count": 0}

        entries = []
        with open(audit_file, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    entry = json.loads(ln)
                    if action_type and entry.get("action_type") != action_type:
                        continue
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue

        # Most recent first
        entries.reverse()
        entries = entries[:limit]

        return {"entries": entries, "count": len(entries)}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# SERVE OVERSIGHT HTML
# ============================================================

@oversight_router.get("/ui", include_in_schema=False)
def oversight_ui():
    """Serve the Oversight Console HTML."""
    html_path = Path(__file__).parent / "api" / "oversight.html"
    if not html_path.exists():
        # Fallback — same directory as this file
        html_path = Path(__file__).parent / "oversight.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="oversight.html not found")
    return FileResponse(str(html_path))