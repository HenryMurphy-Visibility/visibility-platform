            # bql.py

import os
import ast
import uuid
import pickle
import pandas as pd
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from business_days import get_previous_business_day
from bookkeeping import BookkeepingSpace


# ============================================================
# 🔹 DEBUG UTILITIES
# ============================================================

def debug(msg):
    print(f"🟢 {msg}")


def debug_df(df, label):
    print(f"\n🔍 [{label}] shape = {df.shape}")
    print(f"🧱 Columns: {df.columns.tolist()}")
    if df.empty:
        print(f"⚠️ [{label}] is EMPTY")
    else:
        print(f"📈 Sample rows from [{label}]:")
        print(df.head(3).to_string(index=False))


# ============================================================
# 🔹 BOOKKEEPING AGGREGATOR
# ============================================================

class BookkeepingAggregator:
    def __init__(self, portfolio=None, calendar=None, gw=None, summarize=False):
        self.portfolio = portfolio
        self.calendar = calendar
        self.gw = gw
        self.summarize = summarize
        self.journal_entries = None  # loaded later

    # ───────────────────────────────────────────────
    # LOAD JOURNALS
    # ───────────────────────────────────────────────
    def load_journals(self, period_start, period_end):
        """Load journal entries into memory for given period."""
        mqs_path = f"C:/Users/hjmne/PycharmProjects/chest/funds/{self.portfolio}/{self.calendar}/periods/mqs.pkl"
        try:
            self.journal_entries = load_journal_entries(mqs_path, self.portfolio)
            print(f"🟢 Loaded {len(self.journal_entries)} journal entries")
        except Exception as e:
            print(f"❌ Failed to load journals for {self.portfolio}: {e}")
            self.journal_entries = []

    # ───────────────────────────────────────────────
    # SNAPSHOT VIEWS
    # ───────────────────────────────────────────────
    def build_snapshot_view(self, snapshot_date):
        """Build a balance sheet snapshot at a point in time."""
        df = build_space_df(self.portfolio, snapshot_date, "SNAPSHOT", self.calendar, section=3)
        if df.empty:
            print(f"⚠️ No bookkeeping space found for {self.portfolio} @ {snapshot_date}")
            return df

        # Attach metadata
        df = merge_coa(df, "C:/Users/hjmne/PycharmProjects/chest/refdata/chart_of_accounts.csv")
        df = merge_investment_master(df, "C:/Users/hjmne/PycharmProjects/chest/refdata/investment_master.csv")
        df["SOURCE"] = f"END ({snapshot_date.date()})"

        return df

    # ───────────────────────────────────────────────
    # TRANSACTION VIEW
    # ───────────────────────────────────────────────
    def build_transaction_view(self, period_start, period_end):
        """Build JE activity between two dates."""
        if not self.journal_entries:
            print("⚠️ No journal entries loaded for JE view")
            return pd.DataFrame()

        df = build_je_activity(self.journal_entries, period_start, period_end, section=2)
        if df.empty:
            print("⚠️ No JE activity rows built")
            return df

        df = merge_coa(df, "C:/Users/hjmne/PycharmProjects/chest/refdata/chart_of_accounts.csv")
        df = merge_investment_master(df, "C:/Users/hjmne/PycharmProjects/chest/refdata/investment_master.csv")
        df["SOURCE"] = "JE ACTIVITY"

        return df

    # ───────────────────────────────────────────────
    # GENERIC AGGREGATE
    # ───────────────────────────────────────────────
    def aggregate(self, df, group_by, sum_fields):
        """Aggregate data by group_by + sum_fields."""
        if df.empty:
            return df

        if group_by and sum_fields:
            present_sums = [f for f in (sum_fields or []) if f in df.columns]
            if not present_sums:
                # If declared sum fields are missing, try numeric columns
                num_cols = df.select_dtypes(include="number").columns.tolist()
                if not num_cols:
                    return df
                agg_map = {c: "sum" for c in num_cols}
            else:
                agg_map = {field: "sum" for field in present_sums}
            present_groups = [g for g in (group_by or []) if g in df.columns]
            if not present_groups:
                return df
            df = df.groupby(present_groups, dropna=False).agg(agg_map).reset_index()

        return df


# ============================================================
# 🔹 CORE HELPERS
# ============================================================

def normalize_string(s):
    return str(s).upper().replace(" ", "").strip()


def parse_card_value(val):
    if pd.isna(val):
        return None
    try:
        return ast.literal_eval(str(val))
    except Exception:
        return str(val)


def normalize_temporal_fields(df):
    for col in ["TAX_DATE", "TRADE_DATE", "SETTLE_DATE", "IBOR_DATE"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def load_journal_entries(mqs_path, portfolio):
    with open(mqs_path, "rb") as f:
        journal_entries = pickle.load(f)
    return [je for je in journal_entries if getattr(je, "portfolio", None) == portfolio]


def merge_coa(df, coa_path):
    """
    Enrich df with BS_GROUP_NAME from COA without creating duplicates.
    Uses a one-to-one map on FINANCIAL_ACCOUNT -> BS_GROUP_NAME.
    """
    coa = pd.read_csv(coa_path)
    coa.columns = coa.columns.str.upper()
    # normalize keys
    if "SYSTEM_NAME" in coa.columns:
        coa["SYSTEM_NAME"] = coa["SYSTEM_NAME"].astype(str).str.upper().str.strip()
        key_col = "SYSTEM_NAME"
    else:
        # fallback if different column name in COA; try FINANCIAL_ACCOUNT
        key_col = "FINANCIAL_ACCOUNT"
        if key_col in coa.columns:
            coa[key_col] = coa[key_col].astype(str).str.upper().str.strip()
        else:
            return df

    if "FINANCIAL_ACCOUNT" not in df.columns:
        return df

    df["FINANCIAL_ACCOUNT"] = df["FINANCIAL_ACCOUNT"].astype(str).str.upper().str.strip()

    # de-duplicate right table on key
    dup_count = coa.duplicated(subset=[key_col]).sum()
    if dup_count:
        print(f"⚠️ COA has {dup_count} duplicate {key_col} rows; using last occurrence per key")
    coa = coa.drop_duplicates(subset=[key_col], keep="last")

    # build mapping and map (no merge)
    bs_map = dict(zip(coa[key_col], coa.get("BS_GROUP_NAME", pd.Series([None]*len(coa)))))
    if "BS_GROUP_NAME" in df.columns:
        df = df.drop(columns=["BS_GROUP_NAME"])
    df["BS_GROUP_NAME"] = df["FINANCIAL_ACCOUNT"].map(bs_map)

    return df


def merge_investment_master(df, investment_master_path):
    """
    Enrich df with investment metadata without creating duplicates.
    Maps INVESTMENT (ticker) -> selected columns via one-to-one maps.
    """
    inv_master = pd.read_csv(investment_master_path)
    inv_master.columns = inv_master.columns.str.upper()

    if "INVESTMENT" not in df.columns:
        return df

    df["INVESTMENT"] = df["INVESTMENT"].astype(str).str.upper().str.strip()
    if "TICKER" not in inv_master.columns:
        return df
    inv_master["TICKER"] = inv_master["TICKER"].astype(str).str.upper().str.strip()

    # de-duplicate right table on key
    dup_count = inv_master.duplicated(subset=["TICKER"]).sum()
    if dup_count:
        print(f"⚠️ Investment master has {dup_count} duplicate TICKER rows; using last occurrence per key")
    inv_master = inv_master.drop_duplicates(subset=["TICKER"], keep="last")

    # choose which columns to map if present
    merge_columns = [c for c in ["ANALYST", "SECTOR", "INDUSTRY"] if c in inv_master.columns]
    if not merge_columns:
        return df

    # perform per-column map (avoids row multiplication)
    im_idx = inv_master.set_index("TICKER")
    for col in merge_columns:
        df[col] = df["INVESTMENT"].map(im_idx[col])

    return df


def apply_generic_filters(df, filters, label=""):
    if not filters:
        return df
    df.columns = [c.upper().strip() for c in df.columns]

    for key, val in filters.items():
        key = key.upper().strip()
        if key not in df.columns:
            continue

        if isinstance(val, str) and val.startswith("[") and val.endswith("]"):
            try:
                comp_list = ast.literal_eval(val)
                comp_list = [normalize_string(x) for x in comp_list]
                df[key] = df[key].fillna("").astype(str).apply(normalize_string)
                df = df[df[key].isin(comp_list)]
                continue
            except Exception:
                continue

        op, comp_val = None, None
        if isinstance(val, str):
            for operator in ("==", "!=", ">=", "<=", ">", "<"):
                if val.startswith(operator):
                    op = operator
                    comp_val = val[len(operator):].strip()
                    break
        if not op:
            continue

        col_dtype = df[key].dtype
        if op in (">", "<", ">=", "<="):
            df[key] = pd.to_numeric(df[key], errors="coerce")
            comp_val = pd.to_numeric(comp_val, errors="coerce")
        elif pd.api.types.is_datetime64_any_dtype(col_dtype):
            df[key] = pd.to_datetime(df[key], errors="coerce")
            comp_val = pd.to_datetime(comp_val, errors="coerce")
        else:
            df[key] = df[key].fillna("").astype(str).apply(normalize_string)
            comp_val = normalize_string(comp_val)

        if op == "==":
            df = df[df[key] == comp_val]
        elif op == "!=":
            df = df[df[key] != comp_val]
        elif op == ">":
            df = df[df[key] > comp_val]
        elif op == "<":
            df = df[df[key] < comp_val]
        elif op == ">=":
            df = df[df[key] >= comp_val]
        elif op == "<=":
            df = df[df[key] <= comp_val]

    return df


def build_space_df(portfolio, cutoff, label, calendar, section, columns=None):
    mqs_path = f"C:/Users/hjmne/PycharmProjects/chest/funds/{portfolio}/{calendar}/periods/mqs.pkl"
    if calendar == "Current Knowledge":
        mqs_path = f"C:/Users/hjmne/PycharmProjects/chest/funds/{portfolio}/{calendar}/periods/mqs.pkl"

    try:
        journal_entries = pd.read_pickle(mqs_path)
        journal_entries = [je for je in journal_entries if getattr(je, "portfolio", None) == portfolio]
    except Exception as e:
        print(f"❌ Failed to load MQS: {e}")
        return pd.DataFrame(columns=columns if columns else [])

    space = BookkeepingSpace()
    for je in journal_entries:
        if hasattr(je, "ibor_date") and je.ibor_date <= cutoff:
            space.post_journal_entry(je)

    raw = space.all_bookkeeping_accounts_info()
    columns = columns or [
        "PORTFOLIO", "INVESTMENT", "LOTID", "TAX_DATE", "LS", "LOCATION",
        "FINANCIAL_ACCOUNT", "QUANTITY", "LOCAL", "BOOK", "NOTIONAL", "OFACE"
    ]
    df = pd.DataFrame(raw, columns=columns)
    df["SOURCE"] = f"{label} ({cutoff.date()})"
    return df


def build_je_activity(journal_entries, start, end, section, summarize=False):
    journal_entries = sorted(journal_entries, key=lambda je: getattr(je, "ibor_date", pd.Timestamp.min))
    rows = []
    for je in journal_entries:
        ibor_date = pd.to_datetime(getattr(je, "ibor_date", None), errors="coerce")
        if pd.isna(ibor_date):
            continue
        if ibor_date > end:
            break

        transaction_type = getattr(je, "transaction", None)
        is_ppa = transaction_type == "PriorPeriodAdjustment"

        if ibor_date >= start or is_ppa:
            rows.append({
                "PORTFOLIO": getattr(je, "portfolio", None),
                "INVESTMENT": getattr(je, "investment", None),
                "TRANID": getattr(je, "tranid", None),
                "LS": getattr(je, "ls", None),
                "LOCATION": getattr(je, "location", None),
                "FINANCIAL_ACCOUNT": getattr(je, "financial_account", None),
                "IBOR_DATE": ibor_date,
                "TRADE_DATE": getattr(je, "tradedate", None),
                "SETTLE_DATE": getattr(je, "settledate", None),
                "ENTRY_TYPE": getattr(je, "entry_type", None),
                "QUANTITY": getattr(je, "quantity", 0),
                "LOCAL": getattr(je, "local", 0.0),
                "BOOK": getattr(je, "book", 0.0),
                "LOTID": getattr(je, "lotid", 0),
                "TAX_DATE": getattr(je, "tax_date", None),
                "SEQUENCE_NUMBER": getattr(je, "sequence_number", None),
                "TRANSACTION": transaction_type,
                "PPA_FLAG": is_ppa,
                "SOURCE": "JE ACTIVITY"
            })
    return pd.DataFrame(rows)


# ============================================================
# 🔹 MINIMAL ADDITIONS FOR SUMMARIZE & JE DETAIL
#    (Used only by BSANDJE-VR path below)
# ============================================================

def _normalize_summarize(s):
    """
    Accepts 'YES'/'NO'/'JEDETAIL' (case/spacing tolerant) and booleans.
    """
    if isinstance(s, bool):
        return "YES" if s else "NO"
    if s is None:
        return "NO"
    s = str(s).upper().replace(" ", "").replace("-", "").strip()
    if s in ("YES", "NO", "JEDETAIL"):
        return s
    return "NO"

def _resolve_summarize_flags(summarize_mode):
    """
    YES      -> summarize BS & JE (hide JE attrs)
    NO       -> detail BS & JE (show JE attrs)
    JEDETAIL -> summarize BS, detail JE (show JE attrs)
    """
    m = _normalize_summarize(summarize_mode)
    if m == "YES":
        return dict(summarize_bs=True, summarize_je=True, include_je_attrs=False)
    if m == "NO":
        return dict(summarize_bs=False, summarize_je=False, include_je_attrs=True)
    if m == "JEDETAIL":
        return dict(summarize_bs=True, summarize_je=False, include_je_attrs=True)
    return dict(summarize_bs=False, summarize_je=False, include_je_attrs=True)

def _project_je_columns(df, keep_keys, keep_sums, include_attrs):
    """
    When include_attrs=False (YES mode), hide JE detail attrs and keep only
    grouping + sum fields (+ common meta if present). Otherwise return as-is.
    """
    if df is None or df.empty or include_attrs:
        return df
    cols = set((keep_keys or [])) | set((keep_sums or []))
    keep = [c for c in df.columns if c in cols]
    for c in ("BS_GROUP_NAME", "FINANCIAL_ACCOUNT", "PORTFOLIO", "INVESTMENT"):
        if c in df.columns and c not in keep:
            keep.append(c)
    return df.loc[:, keep] if keep else df.iloc[0:0].copy()

def _sort_je_detail(df):
    if df is None or df.empty:
        return df
    cols = [c for c in ("IBOR_DATE", "SEQUENCE_NUMBER", "SETTLE_DATE") if c in df.columns]
    return df.sort_values(by=cols, kind="mergesort") if cols else df


# ============================================================
# 🔹 MAIN FQL ENGINE
# ============================================================

def run_parallel_fql(portfolio, period_start, period_end, report_name, settings,
                     calendar, gw=None, parallel=False):
    """
    Main FQL engine entry point.

    - Unifies period anchors once (bs_start_date = previous business day of period_start; bs_end_date = period_end)
    - Applies filters/grouping consistently
    - Provides three rollforward modes:
        * BSANDJE-H  : Horizontal (three tabs side-by-side)
        * BSANDJE-V  : Vertical (stacked in a single tab with SECTION/ACTIVITY_TYPE)
        * BSANDJE-VR : Vertical + separate Reconciliation tab
    """
    import pandas as pd
    from business_days import get_previous_business_day

    print("in parallel fql")

    # -------------------------
    # Settings (strict: Mode & Summarize)
    # -------------------------
    mode = ((settings.get("mode") or settings.get("Mode") or "")).upper()

    # Summarize must be "YES"|"NO"|"JEDETAIL". We still normalize booleans but they can never become JEDETAIL.
    def _pick_summarize_raw(_s):
        for k in ("Summarize", "summarize", "SummarizeMode", "summarize_mode", "Summarization"):
            if k in _s and _s[k] is not None:
                return _s[k]
        return "NO"

    summarize_raw = _pick_summarize_raw(settings)
    if isinstance(summarize_raw, str):
        summarize_mode = _normalize_summarize(summarize_raw)  # YES/NO/JEDETAIL
    elif isinstance(summarize_raw, bool):
        summarize_mode = "YES" if summarize_raw else "NO"
        debug("⚠️ Summarize provided as boolean; if you intended JEDETAIL, set Summarize='JEDETAIL' in the QC.")
    else:
        summarize_mode = "NO"
        debug(f"⚠️ Unrecognized Summarize type ({type(summarize_raw).__name__}); defaulting to NO.")
    debug(f"Summarize raw={summarize_raw!r} -> mode={summarize_mode}")

    filters = settings.get("filters", {}) or {}
    group_by = settings.get("group_by", []) or []
    sort_by = settings.get("sort_by", []) or []
    sum_fields = settings.get("sum_fields", []) or []
    overlay_names = settings.get("overlay_names", []) or []

    coa_path = "C:/Users/hjmne/PycharmProjects/chest/refdata/chart_of_accounts.csv"
    investment_master_path = "C:/Users/hjmne/PycharmProjects/chest/refdata/investment_master.csv"
    mqs_path = f"C:/Users/hjmne/PycharmProjects/chest/funds/{portfolio}/{calendar}/periods/mqs.pkl"

    # -------------------------
    # Unified period anchors
    # -------------------------
    period_start = pd.to_datetime(period_start)
    period_end = pd.to_datetime(period_end)
    bs_start_date = get_previous_business_day(period_start)  # snapshot for "BS Start"
    bs_end_date = period_end                                 # snapshot for "BS End"

    # -------------------------
    # Aggregator
    # -------------------------
    aggregator = BookkeepingAggregator(
        portfolio=portfolio, calendar=calendar, gw=gw, summarize=(summarize_mode == "YES")
    )

    # === MODE: BS_ONLY ===
    if mode == "BS_ONLY":
        print("🟢 [BS_ONLY] Balance Sheet snapshot @ END")
        df_end = build_space_df(portfolio, bs_end_date, "END", calendar, section=3)
        df_end = merge_coa(df_end, coa_path)
        df_end = merge_investment_master(df_end, investment_master_path)
        df_end = apply_generic_filters(df_end, filters, "END")
        df_end = aggregator.aggregate(df_end, group_by, sum_fields)
        if gw:
            gw.populate_tabs(report_name, df_end)
        return df_end

    # === MODE: JE_ONLY ===
    elif mode == "JE_ONLY":
        print("🟢 [JE_ONLY] Journal Entry activity")
        try:
            journal_entries = load_journal_entries(mqs_path, portfolio)
        except Exception as e:
            print(f"❌ Failed to load MQS: {e}")
            return pd.DataFrame()

        df = build_je_activity(journal_entries, period_start, period_end, section=2)
        df = merge_coa(df, coa_path)
        df = merge_investment_master(df, investment_master_path)
        df = apply_generic_filters(df, filters, "JE")
        df = aggregator.aggregate(df, group_by, sum_fields)
        if sort_by:
            df = df.sort_values(by=sort_by)
        if gw:
            gw.populate_tabs(report_name, df)
        return df

    # === MODE: BSANDJE-H (Horizontal tabs) ===
    elif mode == "BSANDJE-H":
        print("🟢 [BSANDJE-H] Horizontal rollforward (tabs: BS Start, BS End, JE Activity)")

        aggregator.load_journals(period_start, period_end)

        bs_start = aggregator.build_snapshot_view(bs_start_date)
        bs_start = apply_generic_filters(bs_start, filters, "BS Start")
        bs_start = aggregator.aggregate(bs_start, group_by, sum_fields)

        bs_end = aggregator.build_snapshot_view(bs_end_date)
        bs_end = apply_generic_filters(bs_end, filters, "BS End")
        bs_end = aggregator.aggregate(bs_end, group_by, sum_fields)

        je_activity = aggregator.build_transaction_view(period_start, period_end)
        je_activity = apply_generic_filters(je_activity, filters, "JE Activity")
        je_activity = aggregator.aggregate(je_activity, group_by, sum_fields)
        if sort_by:
            je_activity = je_activity.sort_values(by=sort_by)

        result = {
            "BS Start": bs_start,
            "BS End": bs_end,
            "JE Activity": je_activity
        }
        if gw:
            for tab_name, sub_df in result.items():
                gw.populate_tabs(tab_name, sub_df)
        return result

    # === MODE: BSANDJE-V (Vertical Rollforward) ===
    elif mode == "BSANDJE-V":
        print("🟢 [BSANDJE-V] Vertical Rollforward")

        ba = BookkeepingAggregator(portfolio=portfolio, calendar=calendar, gw=gw)
        ba.load_journals(period_start, period_end)

        # Parse group/sum from settings (defaults)
        group_by = (settings.get("group_by") or ["BS_GROUP_NAME"])
        sum_fields = (settings.get("sum_fields") or settings.get("FieldsToSummarize") or ["BOOK"])

        # Build raw sections
        bs_start_raw = ba.build_snapshot_view(bs_start_date)  # prior business day
        bs_end_raw = ba.build_snapshot_view(bs_end_date)
        je_raw = ba.build_transaction_view(period_start, period_end)

        # Filters first (so grouping follows the visible slice)
        bs_start_raw = apply_generic_filters(bs_start_raw, filters, "BS Start")
        bs_end_raw = apply_generic_filters(bs_end_raw, filters, "BS End")
        je_raw = apply_generic_filters(je_raw, filters, "JE Activity")

        # Group each section identically
        bs_start = ba.aggregate(bs_start_raw.copy(), group_by, sum_fields)
        je_act = ba.aggregate(je_raw.copy(), group_by, sum_fields)
        bs_end = ba.aggregate(bs_end_raw.copy(), group_by, sum_fields)
        # Label sections for stacked view
        if not bs_start.empty:
            bs_start.insert(0, "SECTION", "BS Start")
            bs_start.insert(1, "ACTIVITY_TYPE", "BALANCE")
        if not je_act.empty:
            je_act.insert(0, "SECTION", "JE Activity")
            je_act.insert(1, "ACTIVITY_TYPE", "ACTIVITY")
        if not bs_end.empty:
            bs_end.insert(0, "SECTION", "BS End")
            bs_end.insert(1, "ACTIVITY_TYPE", "BALANCE")

        # Stack
        combined = pd.concat([bs_start, je_act, bs_end], ignore_index=True, sort=False)

        # Optional user sort after SECTION order
        SECTION_ORDER = {"BS Start": 1, "JE Activity": 2, "BS End": 3}
        combined["__SEC__"] = combined["SECTION"].map(SECTION_ORDER).fillna(99)
        sort_by = (settings.get("sort_by") or [])
        combined = combined.sort_values(by=["__SEC__"] + sort_by, ignore_index=True)
        combined.drop(columns="__SEC__", inplace=True, errors="ignore")

        if gw:
            gw.populate_tabs(report_name, combined)
        return combined

    # === MODE: BSANDJE-VR (Vertical Rollforward with Reconciliation) ===
    elif mode == "BSANDJE-VR":
        print("🟢 [BSANDJE-VR] Vertical Rollforward with Reconciliation")

        ba = BookkeepingAggregator(portfolio=portfolio, calendar=calendar, gw=gw)
        ba.load_journals(period_start, period_end)

        # Parse group/sum from settings (defaults)
        # For VR we’ll still read the report's group_by/sum_fields for JE or YES/NO modes,
        # but in JEDETAIL we intentionally switch BS summarization to a BS-friendly grain.
        group_by = (settings.get("group_by") or ["BS_GROUP_NAME"])
        sum_fields = (settings.get("sum_fields") or settings.get("FieldsToSummarize") or ["BOOK"])

        # Build raw sections
        bs_start_raw = ba.build_snapshot_view(bs_start_date)  # prior business day
        bs_end_raw   = ba.build_snapshot_view(bs_end_date)
        je_raw       = ba.build_transaction_view(period_start, period_end)

        # Apply filters first
        bs_start_raw = apply_generic_filters(bs_start_raw, filters, "BS Start")
        bs_end_raw   = apply_generic_filters(bs_end_raw,   filters, "BS End")
        je_raw       = apply_generic_filters(je_raw,       filters, "JE Activity")

        # === Summarize control (explicit)
        flags = _resolve_summarize_flags(summarize_mode)

        # --- BS sections ---
        if summarize_mode == "JEDETAIL":
            # Force summarized BS using a fixed BS-grain; this prevents lot/ticket-level keys from leaking in.
            bs_group_by_for_summary = settings.get("bs_summary_group_by") or ["BS_GROUP_NAME"]
            bs_sum_fields = sum_fields or ["BOOK"]
            debug(f"BSANDJE-VR JEDETAIL → BS summarized by {bs_group_by_for_summary} over {bs_sum_fields}")
            bs_start = ba.aggregate(bs_start_raw.copy(), bs_group_by_for_summary, bs_sum_fields)
            bs_end   = ba.aggregate(bs_end_raw.copy(),   bs_group_by_for_summary, bs_sum_fields)
        elif flags["summarize_bs"]:
            # YES mode (summarize BS using the report's group_by)
            bs_start = ba.aggregate(bs_start_raw.copy(), group_by, sum_fields or ["BOOK"])
            bs_end   = ba.aggregate(bs_end_raw.copy(),   group_by, sum_fields or ["BOOK"])
        else:
            # NO mode (detailed BS)
            bs_start = bs_start_raw.copy()
            bs_end   = bs_end_raw.copy()

        # --- JE section ---
        if flags["summarize_je"]:
            # YES mode (summarize JE)
            je_summed = ba.aggregate(je_raw.copy(), group_by, sum_fields or ["BOOK"])
            je_act = _project_je_columns(je_summed, group_by, sum_fields, include_attrs=flags["include_je_attrs"])
            if sort_by:
                je_act = je_act.sort_values(by=sort_by, kind="mergesort")
        else:
            # JE DETAIL (JEDETAIL or NO): keep attributes and chronological order
            je_act = _sort_je_detail(je_raw.copy())

        # --- Label sections for stacked view ---
        if not bs_start.empty:
            bs_start.insert(0, "SECTION", "BS Start")
            bs_start.insert(1, "ACTIVITY_TYPE", "BALANCE")
        if not je_act.empty:
            je_act.insert(0, "SECTION", "JE Activity")
            je_act.insert(1, "ACTIVITY_TYPE", "ACTIVITY")
        if not bs_end.empty:
            bs_end.insert(0, "SECTION", "BS End")
            bs_end.insert(1, "ACTIVITY_TYPE", "BALANCE")

        # --- Rollforward stacked view (STRICT order; preserve JE detail order) ---
        rollforward = pd.concat([bs_start, je_act, bs_end], ignore_index=True, sort=False)
        SECTION_ORDER = {"BS Start": 1, "JE Activity": 2, "BS End": 3}
        rollforward["__SEC__"] = rollforward["SECTION"].map(SECTION_ORDER).fillna(99)
        rollforward = rollforward.sort_values(by=["__SEC__"], ignore_index=True, kind="mergesort")
        rollforward.drop(columns="__SEC__", inplace=True, errors="ignore")

        # ---------------- Reconciliation (computed from RAW slices) ----------------
        TOLERANCE = 0.01  # de minimis threshold

        def _cat_sum(df):
            if df is None or df.empty or "BOOK" not in df.columns:
                return {}
            if "BS_GROUP_NAME" not in df.columns:
                df = df.copy()
                df["BS_GROUP_NAME"] = "UNCLASSIFIED"
            return df.groupby("BS_GROUP_NAME", dropna=False)["BOOK"].sum().to_dict()

        start_by_cat = _cat_sum(bs_start_raw)
        je_by_cat    = _cat_sum(je_raw)
        end_by_cat   = _cat_sum(bs_end_raw)

        categories = sorted(set(start_by_cat) | set(je_by_cat) | set(end_by_cat))
        recon_rows = []
        for cat in categories:
            s = float(start_by_cat.get(cat, 0.0))
            j = float(je_by_cat.get(cat, 0.0))
            e = float(end_by_cat.get(cat, 0.0))
            d = (s + j) - e
            recon_rows.append({
                "CATEGORY": cat,
                "BS_START": s,
                "JE_ACTIVITY": j,
                "BS_END": e,
                "DIFF": d,
                "STATUS": "✅ OK" if abs(d) <= TOLERANCE else "❌ BREAK"
            })

        # Portfolio TOTAL (exclude MV-UNREALIZEDGL from totals)
        def _exclude_from_total(cat_name: str) -> bool:
            return "MV-UNREALIZEDGL" in str(cat_name).upper()

        total_pool = [r for r in recon_rows if not _exclude_from_total(r["CATEGORY"])]
        tot_s = sum(r["BS_START"] for r in total_pool)
        tot_j = sum(r["JE_ACTIVITY"] for r in total_pool)
        tot_e = sum(r["BS_END"] for r in total_pool)
        tot_d = (tot_s + tot_j) - tot_e

        recon_rows.insert(0, {
            "CATEGORY": "TOTAL (excl MV-UNREALIZEDGL)",
            "BS_START": tot_s,
            "JE_ACTIVITY": tot_j,
            "BS_END": tot_e,
            "DIFF": tot_d,
            "STATUS": "✅ OK" if abs(tot_d) <= TOLERANCE else "❌ BREAK"
        })

        recon_df = pd.DataFrame(recon_rows)

        result = {
            "Rollforward": rollforward,
            "Reconciliation": recon_df
        }
        if gw:
            gw.populate_tabs("Rollforward", rollforward)
            gw.populate_tabs("Reconciliation", recon_df)
        return result

    # === MODE: PERF ===
    elif mode == "PERF":
        print("🟢 [PERF] Performance reporting")
        from performance import create_performance_sheets
        try:
            journal_entries = load_journal_entries(mqs_path, portfolio)
        except Exception as e:
            print(f"❌ Failed to load MQS for performance: {e}")
            return pd.DataFrame()
        results = create_performance_sheets(
            journal_entries, period_start, period_end,
            portfolio_name=portfolio, filters=filters, gw=gw
        )
        return results

    # === MODE: JETRANSFORM ===
    elif mode == "JETRANSFORM":
        print("🟢 [JETRANSFORM] Transforming JE view with mapping rules")
        try:
            journal_entries = load_journal_entries(mqs_path, portfolio)
        except Exception as e:
            print(f"❌ Failed to load MQS: {e}")
            return pd.DataFrame()

        df = build_je_activity(journal_entries, period_start, period_end, section=2)
        df = merge_investment_master(df, investment_master_path)

        # Mapping rules
        mapping_rules_path = "C:/Users/hjmne/PycharmProjects/chest/refdata/coa_mapping_rules.csv"
        rules = pd.read_csv(mapping_rules_path).to_dict(orient="records")

        mapped = []
        for _, row in df.iterrows():
            mapping = {}
            for rule in rules:
                try:
                    if (
                        rule["FINANCIAL_ACCOUNT"].upper() in [str(row.get("FINANCIAL_ACCOUNT", "")).upper(), "*"]
                        and rule["INVESTMENT_TYPE"].upper() in [str(row.get("INVESTMENT_TYPE", "")).upper(), "*"]
                        and rule["L_S_N"].upper() in [str(row.get("LS", "")).upper(), "*"]
                    ):
                        mapping = {
                            "COA_ACCOUNT": rule.get("COA_ACCOUNT", "Unmapped"),
                            "GROUP": rule.get("GROUP", "Unmapped"),
                            "CLASS": rule.get("CLASS", "Unmapped")
                        }
                        break
                except Exception:
                    continue
            if not mapping:
                mapping = {"COA_ACCOUNT": "Unmapped", "GROUP": "Unmapped", "CLASS": "Unmapped"}
            mapped.append({**row, **mapping})

        df_mapped = pd.DataFrame(mapped)
        df_mapped = apply_generic_filters(df_mapped, filters, "JETRANSFORM")
        df_mapped = df_mapped.sort_values(by=sort_by or ["INVESTMENT", "FINANCIAL_ACCOUNT"])
        if gw:
            gw.populate_tabs("JETRANSFORM", df_mapped)
        return df_mapped

    # === Unsupported ===
    else:
        print(f"❌ Unsupported mode: {mode}")
        return pd.DataFrame()
