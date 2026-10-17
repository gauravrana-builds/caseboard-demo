"""Data-access tools for the complaint analysis agent.

All access is flat CSV via pandas, read fresh on each call (the files are small).
See IMPLEMENTATION_BRIEF.md section 4.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
POLICY_DIR = DATA_DIR / "policy"


def _read_csv(name: str) -> pd.DataFrame:
    # dtype=str / keep_default_na=False so IDs like "01" and values like "N/A" or
    # "None" survive untouched; we convert the numeric fields explicitly below.
    return pd.read_csv(DATA_DIR / name, dtype=str, keep_default_na=False)


def _clean_id(account_id) -> str:
    if account_id is None or (isinstance(account_id, float) and pd.isna(account_id)):
        return ""
    return str(account_id).strip()


def _to_float(value: str):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_account(account_id: str) -> dict:
    """Return the accounts.csv row for account_id as a dict with found=True, or
    {"found": False, "reason": ...} if the ID is blank or has no matching row.
    Never raises on a missing ID."""
    account_id = _clean_id(account_id)
    if not account_id:
        return {"found": False, "reason": "No account_id was provided."}

    accounts = _read_csv("accounts.csv")
    match = accounts[accounts["account_id"].str.strip() == account_id]
    if match.empty:
        return {"found": False, "reason": f"No account found with account_id '{account_id}'."}

    row = match.iloc[0].to_dict()
    row["loan_balance"] = _to_float(row["loan_balance"])
    row["origination_date"] = row["origination_date"] or None  # blank when no loan exists
    return {"found": True, **row}


def get_transactions(account_id: str) -> list[dict]:
    """Return all transactions for account_id sorted by date (ISO dates sort
    chronologically; placeholder rows dated "N/A" sort last). Returns an empty
    list if the ID is blank or has no transactions."""
    account_id = _clean_id(account_id)
    if not account_id:
        return []

    txns = _read_csv("transactions.csv")
    match = txns[txns["account_id"].str.strip() == account_id].copy()
    if match.empty:
        return []

    match["amount"] = match["amount"].map(_to_float)
    match["_undated"] = ~match["date"].str.match(r"^\d{4}-\d{2}-\d{2}$")
    match = match.sort_values(["_undated", "date"], kind="stable").drop(columns="_undated")
    return match.to_dict(orient="records")


def _keyword_pattern(phrase: str) -> re.Pattern:
    # whole-word/phrase match, tolerating a simple plural ("fee" matches "fees")
    return re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?:s|es)?(?!\w)", re.IGNORECASE)


def get_policy(keywords: str) -> dict:
    """Keyword-match `keywords` (free text or comma-separated) against the
    keywords column of policy_index.csv. The score is the number of index keywords
    found in the input; ties are broken by total matched characters (favoring more
    specific phrases), then by index order. Returns the best match with its full
    policy text, or {"found": False} if nothing matches."""
    text = (keywords or "").strip()
    if not text:
        return {"found": False}

    index = _read_csv("policy_index.csv")
    best = None  # (score, matched_chars, -row_position, row, matched)
    for pos, row in index.iterrows():
        phrases = [k.strip() for k in row["keywords"].split(",") if k.strip()]
        matched = [p for p in phrases if _keyword_pattern(p).search(text)]
        if not matched:
            continue
        candidate = (len(matched), sum(len(p) for p in matched), -pos, row, matched)
        if best is None or candidate[:3] > best[:3]:
            best = candidate

    if best is None:
        return {"found": False}

    _, _, _, row, matched = best
    policy_text = (POLICY_DIR / row["filename"]).read_text(encoding="utf-8")
    return {
        "found": True,
        "policy_id": row["policy_id"],
        "topic": row["topic"],
        "category": row["category"],
        "filename": row["filename"],
        "matched_keywords": matched,
        "text": policy_text,
    }


CASE_LOG_COLUMNS = [
    "complaint_id", "timestamp", "extraction_output", "verified_facts", "risk_tier", "risk_reason",
    "policy_cited", "draft_text", "verifier_result", "human_decision", "edit_severity", "override_reason",
]


def _case_log_path() -> Path:
    # COMPLAINT_AGENT_CASE_LOG lets tests and demos write to a scratch file instead of the real audit log
    override = os.environ.get("COMPLAINT_AGENT_CASE_LOG")
    return Path(override) if override else DATA_DIR / "case_log.csv"


def log_case(record: dict) -> None:
    """Append one row to the case log (full audit trail: never rewrites or edits earlier rows).

    Called when the reviewer records a decision, not when the pipeline finishes, so the log always
    reflects a human action. Dict/list values are stored as JSON text. A missing timestamp is filled
    with the current UTC time."""
    path = _case_log_path()
    row = {c: record.get(c, "") for c in CASE_LOG_COLUMNS}
    row["timestamp"] = row["timestamp"] or datetime.now(timezone.utc).isoformat(timespec="seconds")
    for key, value in row.items():
        if isinstance(value, (dict, list)):
            row[key] = json.dumps(value, ensure_ascii=False)
        elif value is None:
            row[key] = ""

    if not path.exists() or path.stat().st_size == 0:
        pd.DataFrame(columns=CASE_LOG_COLUMNS).to_csv(path, index=False)
    else:
        with open(path, "rb") as f:  # make sure the last line is terminated before appending
            f.seek(-1, os.SEEK_END)
            needs_newline = f.read(1) not in (bytes([10]), bytes([13]))  # LF, CR
        if needs_newline:
            with open(path, "ab") as f:
                f.write(bytes([10]))
    pd.DataFrame([row], columns=CASE_LOG_COLUMNS).to_csv(path, mode="a", header=False, index=False)
