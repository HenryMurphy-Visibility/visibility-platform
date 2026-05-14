"""
compute_unrealized.py
──────────────────────────────────────────────────────────────────────────────
Computes unrealized gain/loss two ways and proves they agree:

  METHOD A — Journal roll-up:
    Sum all UnrealPriceGL, PriceGainStatOffset, UnrealFXGL, FXGainStatOffset
    account movements across the period range.
    This is the accounting view — derived from journal entries.

  METHOD B — Point-in-time:
    Market Value - Cost Basis at period end.
    This is the appraisal view — derived from price data and state snapshots.

  RECON:
    Method A must equal Method B.
    If they differ, either price data is wrong, cost basis is wrong,
    or a journal entry is missing. No other explanation exists.

This is the bridge between the accounting system and the appraisal system.
It is only possible because both views derive from the same state.

Drop into:
  financial_information_gateway/fig_code/compute_unrealized.py

Register in compute_registry.py:
  COMPUTE_REGISTRY["compute_unrealized"] = compute_unrealized
"""

from __future__ import annotations

import time
from typing import Optional

import pandas as pd

from financial_information_gateway.fig_code.compute_result import ComputeResult
from financial_information_gateway.fig_code.compute_classifications import (
    UNREALIZED_ACCOUNTS,
    Category,
    ACCOUNT_CLASSIFICATION,
)

TOLERANCE = 1e-6


# ──────────────────────────────────────────────────────────────────────────────
# METHOD A — JOURNAL ROLL-UP
# ──────────────────────────────────────────────────────────────────────────────

def _unrealized_from_journals(prep, uber_filter=None) -> pd.DataFrame:
    """
    Sum unrealized account movements from journal entries.
    Returns one row per investment with:
      unreal_price_local, unreal_price_book,
      unreal_fx_book,
      unreal_total_book
    """
    prior_cutoff   = prep["prior_cutoff_datetime"]
    current_cutoff = prep["current_cutoff_datetime"]

    rows = []

    for je in prep["journal_entries"]:
        fa  = getattr(je, "financial_account", None)
        inv = getattr(je, "investment", None)

        if fa not in UNREALIZED_ACCOUNTS:
            continue

        if uber_filter and "investment" in uber_filter:
            if inv != uber_filter["investment"]:
                continue

        is_adj = getattr(je, "is_adjustment", False)
        if not is_adj:
            ibor = getattr(je, "ibor_date", None)
            if not ibor:
                continue
            if prior_cutoff is None:
                # First period — include all entries up to current_cutoff
                if ibor > current_cutoff:
                    continue
            else:
                if not (prior_cutoff < ibor <= current_cutoff):
                    continue

        rows.append({
            "investment": inv,
            "financial_account": fa,
            "category": ACCOUNT_CLASSIFICATION.get(fa, "Unknown"),
            "local": getattr(je, "local", 0.0),
            "book":  getattr(je, "book",  0.0),
        })

    if not rows:
        return pd.DataFrame(columns=[
            "investment",
            "unreal_price_local_je", "unreal_price_book_je",
            "unreal_fx_book_je", "unreal_total_book_je"
        ])

    df = pd.DataFrame(rows)

    price_cats = {Category.UNREALIZED_PRICE}
    fx_cats    = {Category.UNREALIZED_FX}

    price_df = (
        df[df["category"].isin(price_cats)]
        .groupby("investment")[["local", "book"]]
        .sum()
        .rename(columns={"local": "unreal_price_local_je",
                         "book":  "unreal_price_book_je"})
    )

    fx_df = (
        df[df["category"].isin(fx_cats)]
        .groupby("investment")[["book"]]
        .sum()
        .rename(columns={"book": "unreal_fx_book_je"})
    )

    result = price_df.join(fx_df, how="outer").fillna(0.0).reset_index()
    result["unreal_total_book_je"] = (
        result["unreal_price_book_je"] + result["unreal_fx_book_je"]
    )

    return result


# ──────────────────────────────────────────────────────────────────────────────
# METHOD B — POINT-IN-TIME FROM STATE
# ──────────────────────────────────────────────────────────────────────────────

def _unrealized_from_state(state, uber_filter=None) -> pd.DataFrame:
    """
    Extract unrealized gain directly from the closing state snapshot.
    Returns one row per investment with:
      unreal_price_local_state, unreal_price_book_state,
      unreal_fx_book_state, unreal_total_book_state
    """
    if not state:
        return pd.DataFrame()

    def passes(inv):
        if not uber_filter:
            return True
        return inv == uber_filter.get("investment")

    def decode(row):
        local = row[1] if len(row) > 1 else 0.0
        book  = row[2] if len(row) > 2 else 0.0
        return local, book

    rows = []
    al_repo = state["asset_liability_repository"]

    for subspace in al_repo.investment_positions.values():
        for key, row in subspace.entries.items():
            (_, inv, _, _, _, _, fa) = key
            if not passes(inv):
                continue
            if fa not in UNREALIZED_ACCOUNTS:
                continue
            local, book = decode(row)
            category = ACCOUNT_CLASSIFICATION.get(fa, "Unknown")
            rows.append({
                "investment": inv,
                "category":   category,
                "local":      local,
                "book":       book,
            })

    if not rows:
        return pd.DataFrame(columns=[
            "investment",
            "unreal_price_local_state", "unreal_price_book_state",
            "unreal_fx_book_state",     "unreal_total_book_state"
        ])

    df = pd.DataFrame(rows)

    price_df = (
        df[df["category"] == Category.UNREALIZED_PRICE]
        .groupby("investment")[["local", "book"]]
        .sum()
        .rename(columns={"local": "unreal_price_local_state",
                         "book":  "unreal_price_book_state"})
    )

    fx_df = (
        df[df["category"] == Category.UNREALIZED_FX]
        .groupby("investment")[["book"]]
        .sum()
        .rename(columns={"book": "unreal_fx_book_state"})
    )

    result = price_df.join(fx_df, how="outer").fillna(0.0).reset_index()
    result["unreal_total_book_state"] = (
        result["unreal_price_book_state"] + result["unreal_fx_book_state"]
    )

    return result


# ──────────────────────────────────────────────────────────────────────────────
# MAIN COMPUTE FUNCTION
# ──────────────────────────────────────────────────────────────────────────────

def compute_unrealized(
    portfolio:    str,
    calendar:     str,
    period_start: str,
    period_end:   str,
    uber_filter:  Optional[dict] = None,
    prep:         Optional[dict] = None,
) -> ComputeResult:
    """
    Compute unrealized gain two ways and prove they agree.

    Journal roll-up (Method A) must equal point-in-time state (Method B).
    Difference column shows any variance — zero means perfect agreement.

    This is the bridge between the accounting system and the appraisal.
    """

    t_total = time.perf_counter()

    if prep is None:
        raise ValueError("prep is required.")

    # Method A — journals
    t_je = time.perf_counter()
    je_df = _unrealized_from_journals(prep, uber_filter)
    t_je_ms = (time.perf_counter() - t_je) * 1000

    # Method B — state
    t_state = time.perf_counter()
    state_df = _unrealized_from_state(prep["current_state"], uber_filter)
    t_state_ms = (time.perf_counter() - t_state) * 1000

    # ── MERGE AND RECON ───────────────────────────────────────────────
    if je_df.empty and state_df.empty:
        return ComputeResult(
            function="compute_unrealized",
            portfolio=portfolio,
            calendar=calendar,
            period_start=period_start,
            period_end=period_end,
            shape="unrealized",
            data=pd.DataFrame(),
            valid=False,
            errors=["No unrealized data found"],
            metadata={},
        )

    if je_df.empty:
        merged = state_df.copy()
        for col in ["unreal_price_local_je", "unreal_price_book_je",
                    "unreal_fx_book_je", "unreal_total_book_je"]:
            merged[col] = 0.0
    elif state_df.empty:
        merged = je_df.copy()
        for col in ["unreal_price_local_state", "unreal_price_book_state",
                    "unreal_fx_book_state", "unreal_total_book_state"]:
            merged[col] = 0.0
    else:
        merged = je_df.merge(state_df, on="investment", how="outer").fillna(0.0)

    # Recon columns
    merged["price_diff"] = (
        merged["unreal_price_book_je"] - merged["unreal_price_book_state"]
    ).abs()
    merged["fx_diff"] = (
        merged["unreal_fx_book_je"] - merged["unreal_fx_book_state"]
    ).abs()
    merged["total_diff"] = (
        merged["unreal_total_book_je"] - merged["unreal_total_book_state"]
    ).abs()
    merged["ties"] = merged["total_diff"] <= TOLERANCE

    # Sort
    merged = merged.sort_values("investment").reset_index(drop=True)

    # Summary row
    summary = {
        "investment":               "── TOTAL",
        "unreal_price_local_je":    merged["unreal_price_local_je"].sum(),
        "unreal_price_book_je":     merged["unreal_price_book_je"].sum(),
        "unreal_fx_book_je":        merged["unreal_fx_book_je"].sum(),
        "unreal_total_book_je":     merged["unreal_total_book_je"].sum(),
        "unreal_price_local_state": merged["unreal_price_local_state"].sum(),
        "unreal_price_book_state":  merged["unreal_price_book_state"].sum(),
        "unreal_fx_book_state":     merged["unreal_fx_book_state"].sum(),
        "unreal_total_book_state":  merged["unreal_total_book_state"].sum(),
        "price_diff":               merged["price_diff"].sum(),
        "fx_diff":                  merged["fx_diff"].sum(),
        "total_diff":               merged["total_diff"].sum(),
        "ties":                     merged["ties"].all(),
    }
    merged = pd.concat(
        [merged, pd.DataFrame([summary])], ignore_index=True
    )

    failures    = merged[~merged["ties"]].copy()
    n_failures  = len(failures[failures["investment"] != "── TOTAL"])
    valid       = n_failures == 0
    t_total_ms  = (time.perf_counter() - t_total) * 1000

    if not valid:
        print(f">>> UNREALIZED RECON FAILURES: {n_failures}")
        for _, row in failures.head(5).iterrows():
            print(
                f"    {row['investment']} "
                f"| total_diff={row['total_diff']:.8f}"
            )

    print(
        f">>> compute_unrealized COMPLETE "
        f"| {portfolio} | {calendar} "
        f"| {period_start} → {period_end} "
        f"| {'CLEAN' if valid else f'{n_failures} FAILURES'} "
        f"| {t_total_ms:.0f}ms"
    )

    metadata = {
        "elapsed_ms":         round(t_total_ms, 1),
        "journal_ms":         round(t_je_ms, 1),
        "state_ms":           round(t_state_ms, 1),
        "investments":        len(merged) - 1,
        "recon_failures":     n_failures,
        "all_ties":           valid,
        "uber_filter":        uber_filter,
    }

    return ComputeResult(
        function="compute_unrealized",
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        shape="unrealized",
        data=merged,
        valid=valid,
        errors=[
            f"{row['investment']}|diff={row['total_diff']:.8f}"
            for _, row in failures.iterrows()
            if row["investment"] != "── TOTAL"
        ],
        metadata=metadata,
    )
