 # ======================================================================
#  central_processing_hub.py
# ======================================================================

import copy
from datetime import datetime, timedelta
#
# from core_ingest import remove_violated_snapshots, select_best_snapshot,derive_candidates_from_events, build_portfolio_bond_info, build_portfolio_investment_master,  build_interpretation_ctx
# from core_scheduling import core_schedule_events
from kernel_utilities import load_snapshot_into_space
from datetime import datetime
from core_ingest import load_snapshot_state
MIN_DT = datetime.min

def _norm_dt(v):
    """
    Normalize ordering value.
    - datetime → itself
    - None / 0 / int → MIN_DT
    """
    if isinstance(v, datetime):
        return v
    return MIN_DT

QTY_TOL = 0.0005        # quantities rounded to 3 decimals
LOCAL_TOL = 0.005      # half-cent
BOOK_TOL = 0.005       # half-cent

def interpretation_context_per_pass(
    interpretation_ctx,
    period_name,
    pass_type,
):
    all_events = interpretation_ctx.all_events

    prior_period_start      = interpretation_ctx.prior_period_start
    prior_period_cutoff     = interpretation_ctx.prior_period_cutoff
    prior_period_knowledge  = interpretation_ctx.prior_period_knowledge

    current_period_start    = interpretation_ctx.current_period_start
    current_period_cutoff   = interpretation_ctx.current_period_cutoff
    current_period_knowledge = interpretation_ctx.current_period_knowledge

    replay_start = interpretation_ctx.replay_start

    if pass_type == "PASS1_FILE1":
        trade_window_start = prior_period_start
        trade_window_cutoff = prior_period_cutoff
        effective_knowledge_date = prior_period_knowledge

    elif pass_type == "PASS1_FILE2":
        trade_window_start = prior_period_start
        trade_window_cutoff = prior_period_cutoff
        effective_knowledge_date = current_period_knowledge

    elif pass_type == "PASS2":
        trade_window_start = current_period_start
        trade_window_cutoff = current_period_cutoff
        effective_knowledge_date = current_period_knowledge

    else:
        raise RuntimeError(f"Unknown pass_type: {pass_type}")

    from datetime import timedelta

    qualifying_events = [
        e for e in all_events
        if (
                (replay_start - timedelta(seconds=1)) < e["kdbegin"] <= effective_knowledge_date
                and trade_window_start <= e["tradedate"] <= trade_window_cutoff
        )
    ]

    if not qualifying_events:
        return {"no_events": True, "events": [], "interpretation_ctx": None}

    return {
        "no_events": False,
        "events": qualifying_events,
        "interpretation_ctx": {
            "period_name": period_name,
            "pass_type": pass_type,
            "replay_start": replay_start,
            "effective_knowledge_date": effective_knowledge_date,
            "trade_window_start": trade_window_start,
            "trade_window_cutoff": trade_window_cutoff,
        },
    }




def economically_material(adj):
    """
    Returns True if the adjustment represents a real economic change.
    """
    return (
        abs(adj.quantity or 0) >= QTY_TOL or
        abs(adj.local or 0) >= LOCAL_TOL or
        abs(adj.book or 0) >= BOOK_TOL
    )

def canonical_resequence(journals):
    journals.sort(
        key=lambda je: (
            _norm_dt(je.ibor_date),
            _norm_dt(je.tradedate),
            _norm_dt(je.settledate),
            _norm_dt(je.kdbegin),
            je.portfolio,
            je.investment,
            _norm_dt(je.tax_date),        # 🔑 FIX IS HERE
            je.financial_account,
            je.tranid,
        )
    )

    from bookkeeping import Journals
    Journals.sequence_counter = 0
    for je in journals:
        je.sequence_number = Journals.sequence_counter
        Journals.sequence_counter += 1


# ============================================================
# CPH EXECUTION ENTRY — SNAPSHOT / REPLAY CONTROL
# ============================================================
# CANONICAL RULES:
#
# 1) BookkeepingSpace MUST start each period in exactly one of:
#    a) cold state (no snapshot)
#    b) snapshot-seeded state (prior period end)
#
# 2) A snapshot, if used, MUST be:
#    - loaded exactly once
#    - applied exactly once
#
# 3) Journals are per-period artifacts:
#    - they MUST be cleared before replay
#    - they MUST NOT be carried across periods
#
# 4) Knowledge cutoffs filter economic truth ONLY.
#    They MUST NOT control lifecycle, clearing, or state reuse.
#
# If you think you need more than one snapshot load per period,
# the design is wrong.
# ============================================================

def prepare_space_for_replay(space, interpretation_ctx):
    """
    Prepare bookkeeping space for replay.

    Guarantees:
    - Cold start OR snapshot-seeded start
    - Snapshot loaded exactly once
    - Journals cleared
    """

    snap = interpretation_ctx.selected_snapshot

    if snap is None:
        print("[SNAPSHOT] ❌ No snapshot selected — cold replay")
        space.reset()                      # ✅ reset ONLY here
        space.journal_entries.clear()
        return

    # --------------------------------------------------
    # SNAPSHOT-SEEDED START — DO NOT RESET
    # --------------------------------------------------
    snap_path = snap["path"]
    snap_kd   = snap["kd"]

    print("[SNAPSHOT] ▶ Loading snapshot")
    print(f"           path = {snap_path}")
    print(f"           kd   = {snap_kd}")

    snap_state = load_snapshot_state(snap_path)

    # Validate payload
    assert "asset_liability_repository" in snap_state
    assert "revenue_expense_repository" in snap_state
    assert "stat_repo" in snap_state
    assert "chores" in snap_state

    # 🔑 APPLY SNAPSHOT STATE
    space.asset_liability_repository = snap_state["asset_liability_repository"]
    space.revenue_expense_repository = snap_state["revenue_expense_repository"]
    space.stat_repo                  = snap_state["stat_repo"]
    space.chores                     = snap_state["chores"]

    # Journals must be empty for replay
    space.journal_entries.clear()

    print("[SNAPSHOT] ✅ Snapshot applied")



# ======================================================================
# PURE EXECUTION LOOP
# ======================================================================

def execute_scheduled_events(scheduled_events):
    for ev in scheduled_events:
        ev.func(*ev.args)

# ======================================================================
# COMBINE JOURNALS — PROCESSING UTILITY (NOT ASSEMBLER)
# NEW PERIOD CONTAINER AWARE



def combine_je_files(
    portfolio,
    calendar,
    period_name,
    *,
    upto_kd=None,
):
    """
    Combine journals from Accounting Containers.

    Reads:
      chest/funds/{portfolio}/Calendars/{calendar}/Periods/*/Outputs/Journals/*.pkl

    Used ONLY for:
      - baseline reconstruction
      - adjustment diffing

    Rules:
      - Filesystem structure is NOT economic truth
      - Economic truth is enforced via upto_kd
      - No inference about prior/current periods
    """

    base_path = (
        Path("C:/Users/hjmne/PycharmProjects/chest/funds")
        / portfolio
        / "Calendars"
        / calendar
        / "Periods"
    )

    if not base_path.exists():
        return []

    period_dirs = sorted(
        [p for p in base_path.iterdir() if p.is_dir()],
        key=lambda p: p.name
    )

    from bookkeeping import Journals
    combined = []

    for period_dir in period_dirs:
        journals_dir = period_dir / "Outputs" / "Journals"

        if not journals_dir.exists():
            continue

        for file in sorted(journals_dir.iterdir()):
            if file.suffix != ".pkl":
                continue

            with open(file, "rb") as f:
                jes = pickle.load(f)

            for je in jes:

                # --------------------------------------------------
                # EXCLUDE VALUATION JOURNALS
                # --------------------------------------------------
                if getattr(je, "transaction", None) == "Valuation":
                    continue

                if upto_kd is not None and je.ibor_date > upto_kd:
                    continue

                combined.append(je)

    # 🔒 Canonical resequencing
    Journals.sequence_counter = 0
    for je in combined:
        je.sequence_number = Journals.sequence_counter
        Journals.sequence_counter += 1

    return combined


# ======================================================================
# ADJUSTMENT DIFF ENGINE (ECONOMICALLY CORRECT)
# ======================================================================

import copy

# ----------------------------------------------------------------------
# ECONOMIC TOLERANCES
# ----------------------------------------------------------------------

# Amount tolerance is currency-safe (<< 1 cent)
EPSILON_AMT = 1e-8


# ======================================================================
# ADJUSTMENT DIFF ENGINE — CANONICAL (NO NOISE)
# ======================================================================

import copy

ADJUSTMENT_EPS = 1e-8


def _is_effectively_zero(v):
    return v is None or abs(v) < ADJUSTMENT_EPS


def _is_noise_adjustment(e):
    return (
        (e.quantity or 0) == 0
        and _is_effectively_zero(e.local or 0)
        and _is_effectively_zero(e.book or 0)
    )


import copy

# ======================================================================
# WRITE CURRENT JOURNALS
# ======================================================================

def write_journals(space, portfolio, calendar, period_name):

    out_dir = (
        Path("C:/Users/hjmne/PycharmProjects/chest/funds")
        / portfolio
        /"Calendars"
        / calendar
        / "Periods"
        / period_name
        / "Outputs"
        / "Journals"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    file_path = out_dir / "period_journals.pkl"

    with open(file_path, "wb") as f:
        pickle.dump(space.journal_entries, f)

    return True, str(file_path.resolve())


def create_adjustment_records(journals_A, journals_B):
    """Create adjustment records from two sets of journals."""
    adjustments = []

    # Helper function to get a unique identifier for an entry based on account keys.
    def get_key(entry):
        return (entry.portfolio, entry.investment, entry.lotid, entry.tax_date,
                entry.ls, entry.location, entry.financial_account, entry.tranid, get_sign(entry.local))

    def get_sign(amount):
        return 'positive' if amount >= 0 else 'negative'

    # Create dictionaries for each journal set for easy access.
    dict_A = {(get_key(entry)): entry for entry in journals_A}
    dict_B = {(get_key(entry)): entry for entry in journals_B}

    keys_only_in_A = set(dict_A.keys()) - set(dict_B.keys())
    keys_only_in_B = set(dict_B.keys()) - set(dict_A.keys())
    common_keys = set(dict_A.keys()).intersection(set(dict_B.keys()))

    # Handle keys present in A but missing in B.
    for key in keys_only_in_A:
        adjusted_entry = copy.copy(dict_A[key])
        # Adding checks for None
        adjusted_entry.quantity = -dict_A[key].quantity if dict_A[key].quantity is not None else None
        adjusted_entry.local = -dict_A[key].local if dict_A[key].local is not None else None
        adjusted_entry.book = -dict_A[key].book if dict_A[key].book is not None else None
        adjustments.append(adjusted_entry)

    # Handle keys present in B but missing in A.
    for key in keys_only_in_B:
        adjustments.append(dict_B[key])

    # Process common keys to determine changes.
    for key in common_keys:
        entry_from = dict_A[key]
        entry_to = dict_B[key]

        # Check differences and handle None cases.
        if (entry_from.quantity != entry_to.quantity or
                entry_from.local != entry_to.local or
                entry_from.book != entry_to.book):
            delta_record = copy.copy(entry_from)
            delta_record.quantity = (entry_to.quantity or 0) - (entry_from.quantity or 0)
            delta_record.local = (entry_to.local or 0) - (entry_from.local or 0)
            delta_record.book = (entry_to.book or 0) - (entry_from.book or 0)
            adjustments.append(delta_record)

    return adjustments


import json
from datetime import datetime

import time
import pickle
from pathlib import Path

def cph_run_and_materialize(
    *,
    portfolio,
    calendar,
    per_period_ctx,
    snapshot_path,
    replay_start,
    events,
    is_first_calendar_period,
    smf
):
    """
    CENTRAL PROCESSING HUB — PURE EXECUTION
    WITH FULL PROFILING INSTRUMENTATION
    """

    import time
    import copy
    import gc
    import sys

    from bookkeeping import EventScheduler, BookkeepingSpace
    from core_scheduling import core_schedule_events
    from kernel_utilities import (
        materialize_period_outputs,
        load_snapshot_into_space,
    )

    # ------------------------------------------------------------
    # PROFILING CONTAINER
    # ------------------------------------------------------------
    profile = {}
    t0_total = time.perf_counter()

    def mark(label):
        profile[label] = time.perf_counter()

    # ------------------------------------------------------------
    # INIT SPACE
    # ------------------------------------------------------------
    mark("t_space_init_start")
    space = BookkeepingSpace()
    mark("t_space_init_end")

    metrics = {
        "period_name": per_period_ctx["period_name"],
        "passes_executed": [],
        "regular_journal_entries": 0,
        "adjusting_journal_entries": 0,
        "total_time": 0.0,
        "profile": {},
        "state_sizes": {},
    }

    # ============================================================
    # PASS 1A + PASS 1B
    # ============================================================
    if not is_first_calendar_period:

        # ---------------- PASS 1A ----------------
        mark("t_pass1a_reset_start")
        space.reset()
        mark("t_pass1a_reset_end")

        mark("t_pass1a_load_start")
        if snapshot_path is not None:
            load_snapshot_into_space(space, snapshot_path)
        else:
            from kernel_utilities import bootstrap_investment_attributes
            bootstrap_investment_attributes(space, portfolio)
        mark("t_pass1a_load_end")

        scheduler = EventScheduler(space)

        mark("t_pass1a_schedule_start")
        core_schedule_events(
            interpretation_ctx={
                "replay_start": replay_start,
                "trade_window_cutoff": per_period_ctx["prior_period_cutoff"],
                "effective_knowledge_date": per_period_ctx["prior_period_knowledge"],
            },
            qualifying_events=events,
            space=space,
            scheduler=scheduler,
            smf=smf
        )
        mark("t_pass1a_schedule_end")

        mark("t_pass1a_sort_start")
        scheduler.sort_events()
        mark("t_pass1a_sort_end")

        mark("t_pass1a_exec_start")
        while scheduler.run_next_event():
            pass
        mark("t_pass1a_exec_end")

        mark("t_pass1a_copy_start")
        pass1_file1_journals = [copy.copy(j) for j in space.journal_entries]
        mark("t_pass1a_copy_end")

        metrics["passes_executed"].append("PASS1_FILE1")

        # ---------------- PASS 1B ----------------
        mark("t_pass1b_reset_start")
        space.reset()
        mark("t_pass1b_reset_end")

        mark("t_pass1b_load_start")
        if snapshot_path is not None:
            load_snapshot_into_space(space, snapshot_path)
        else:
            from kernel_utilities import bootstrap_investment_attributes
            bootstrap_investment_attributes(space, portfolio)
        mark("t_pass1b_load_end")

        scheduler = EventScheduler(space)

        mark("t_pass1b_schedule_start")
        core_schedule_events(
            interpretation_ctx={
                "replay_start": replay_start,
                "trade_window_cutoff": per_period_ctx["prior_period_cutoff"],
                "effective_knowledge_date": per_period_ctx["current_period_knowledge"],
            },
            qualifying_events=events,
            space=space,
            scheduler=scheduler,
            smf=smf
        )
        mark("t_pass1b_schedule_end")

        mark("t_pass1b_sort_start")
        scheduler.sort_events()
        mark("t_pass1b_sort_end")

        mark("t_pass1b_exec_start")
        while scheduler.run_next_event():
            pass
        mark("t_pass1b_exec_end")

        mark("t_pass1b_copy_start")
        pass1_file2_journals = [copy.copy(j) for j in space.journal_entries]
        mark("t_pass1b_copy_end")

        metrics["passes_executed"].append("PASS1_FILE2")

        # ---------------- ADJUSTMENTS ----------------
        mark("t_adjust_start")
        adjusting_journals = create_adjustment_records(
            pass1_file1_journals,
            pass1_file2_journals,
        )
        mark("t_adjust_end")

        pass1_file1_journals = None
        pass1_file2_journals = None
        gc.collect()

    else:
        adjusting_journals = []

    # ============================================================
    # PASS 2
    # ============================================================
    mark("t_pass2_reset_start")
    space.reset()
    mark("t_pass2_reset_end")

    mark("t_pass2_load_start")
    if snapshot_path is not None:
        load_snapshot_into_space(space, snapshot_path)
    else:
        from kernel_utilities import bootstrap_investment_attributes
        bootstrap_investment_attributes(space, portfolio)
    mark("t_pass2_load_end")

    scheduler = EventScheduler(space)

    mark("t_pass2_schedule_start")
    core_schedule_events(
        interpretation_ctx={
            "replay_start": replay_start,
            "trade_window_cutoff": per_period_ctx["current_period_cutoff"],
            "effective_knowledge_date": per_period_ctx["current_period_knowledge"],
        },
        qualifying_events=events,
        space=space,
        scheduler=scheduler,
        smf=smf
    )
    mark("t_pass2_schedule_end")

    mark("t_pass2_sort_start")
    scheduler.sort_events()
    mark("t_pass2_sort_end")

    mark("t_pass2_exec_start")
    while scheduler.run_next_event():
        pass
    mark("t_pass2_exec_end")

    mark("t_pass2_copy_start")
    final_regular_journals = [copy.copy(j) for j in space.journal_entries]
    mark("t_pass2_copy_end")

    metrics["passes_executed"].append("PASS2")

    # ============================================================
    # STATE SIZE METRICS
    # ============================================================
    try:
        al_repo = space.asset_liability_repository
        re_repo = space.revenue_expense_repository

        al_investments = len(al_repo.investment_spaces_library)
        al_entries = sum(
            len(sub.entries)
            for sub in al_repo.investment_spaces_library.values()
        )

        re_entries = len(re_repo.entries)

        metrics["state_sizes"] = {
            "al_investments": al_investments,
            "al_entries": al_entries,
            "re_entries": re_entries,
        }
    except Exception:
        metrics["state_sizes"] = {"error": "state size capture failed"}

    # ============================================================
    # MATERIALIZE
    # ============================================================
    space.chores = smf
    mark("t_materialize_start")
    materialize_period_outputs(
        space=space,
        regular_journals=final_regular_journals,
        adjusting_journals=adjusting_journals,
        portfolio=portfolio,
        calendar=calendar,
        period_name=per_period_ctx["period_name"],
        snapshot_kd=per_period_ctx["current_period_cutoff"],
    )
    mark("t_materialize_end")

    # ------------------------------------------------------------
    # METRICS FINALIZATION
    # ------------------------------------------------------------
    metrics["regular_journal_entries"] = len(final_regular_journals)
    metrics["adjusting_journal_entries"] = len(adjusting_journals)

    t1_total = time.perf_counter()
    metrics["total_time"] = t1_total - t0_total

    # ------------------------------------------------------------
    # BUILD TIME DELTAS
    # -------------------- ----------------------------------------
    ordered_keys = sorted(profile.keys(), key=lambda x: profile[x])
    timing = {}

    prev_time = t0_total
    for key in ordered_keys:
        timing[key] = profile[key] - prev_time
        prev_time = profile[key]

    metrics["profile"] = timing

    # ------------------------------------------------------------
    # PRINT PROFILE METRICS (DIRECTLY HERE)
    # ------------------------------------------------------------
    print("\n🔎 STATE SIZES")
    for k, v in metrics.get("state_sizes", {}).items():
        print(f"   {k}: {v}")

    print("\n⏱ PROFILE BREAKDOWN")
    for k, v in metrics.get("profile", {}).items():
        print(f"   {k}: {v:.6f}s")

    print(f"\n⏱ TOTAL CPH TIME: {metrics['total_time']:.6f}s\n")

    # ------------------------------------------------------------
    # CLEANUP
    # ------------------------------------------------------------
    space.reset()
    gc.collect()

    return metrics
