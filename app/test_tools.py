"""Standalone check of app/tools.py against the real CSVs in data/.

Run from anywhere:  python app/test_tools.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools import DATA_DIR, get_account, get_policy, get_transactions  # noqa: E402

complaints = pd.read_csv(DATA_DIR / "complaints.csv", dtype=str, keep_default_na=False)


def complaint(cid: str) -> pd.Series:
    return complaints[complaints["complaint_id"] == cid].iloc[0]


def show(title, obj):
    print(f"\n--- {title}")
    print(json.dumps(obj, indent=2, default=str))


def section(title):
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


# 1. Purpose-built evidence: ACC-F01 (confirmed false) and ACC-B04 (missing window)
for cid in ["SYN-F01", "SYN-B04"]:
    c = complaint(cid)
    section(f"{cid}  account={c['account_id']}  [{c['demo_case_type']}]  "
            f"{c['issue']} / {c['sub_issue'] or '(no sub_issue)'}")
    print("Narrative:", c["narrative"][:220], "...")
    acct = get_account(c["account_id"])
    txns = get_transactions(c["account_id"])
    show("get_account", acct)
    show(f"get_transactions ({len(txns)} rows)", txns)
    assert acct["found"] and acct["account_id"] == c["account_id"]
    assert isinstance(acct["loan_balance"], float)
    assert all(t["account_id"] == c["account_id"] for t in txns)

# 2. A 'core' complaint with generic (not individually verified) evidence
generic = complaints[(complaints["demo_case_type"] == "core")
                     & ~complaints["account_id"].str.match(r"^ACC-[FPB]\d\d$")].iloc[0]
section(f"{generic['complaint_id']}  account={generic['account_id']}  [core, generic evidence]  "
        f"{generic['issue']} / {generic['sub_issue'] or '(no sub_issue)'}")
acct = get_account(generic["account_id"])
txns = get_transactions(generic["account_id"])
show("get_account", acct)
show(f"get_transactions ({len(txns)} rows)", txns)
dates = [t["date"] for t in txns]
assert dates == sorted(dates), "transactions not sorted by date"

# 3. Edge cases: unknown / blank / None ID, placeholder 'N/A' rows
section("Edge cases")
show("get_account('ACC-NOPE')", get_account("ACC-NOPE"))
show("get_account('')", get_account(""))
show("get_account(None)", get_account(None))
print("\nget_transactions('ACC-NOPE') ->", get_transactions("ACC-NOPE"))
print("get_transactions('') ->", get_transactions(""))
show("get_account('ACC-F02')  (no loan on file)", get_account("ACC-F02"))
show("get_transactions('ACC-F02')  (N/A placeholder row)", get_transactions("ACC-F02"))

# 4. Policy lookup: keywords built from real complaints' issue/sub_issue, plus direct queries
section("get_policy")
queries = [
    ("SYN-F01 issue + sub_issue", f"{complaint('SYN-F01')['issue']} {complaint('SYN-F01')['sub_issue']}"),
    ("SYN-B04 issue + sub_issue", f"{complaint('SYN-B04')['issue']} {complaint('SYN-B04')['sub_issue']}"),
    (f"{generic['complaint_id']} issue + sub_issue", f"{generic['issue']} {generic['sub_issue']}"),
    ("direct: late fee waiver", "late fee, waive, goodwill"),
    ("direct: collection calls", "frequent collection calls at workplace"),
    ("direct: no match", "zebra pineapple"),
    ("direct: blank", ""),
]
for label, q in queries:
    p = get_policy(q)
    if p["found"]:
        print(f"\n[{label}] query={q!r}\n  -> policy {p['policy_id']} | {p['topic']} | {p['category']}"
              f"\n     matched={p['matched_keywords']}  text_chars={len(p['text'])}"
              f"\n     text starts: {p['text'][:90]!r}")
    else:
        print(f"\n[{label}] query={q!r}\n  -> {p}")

assert get_policy("late fee, waive, goodwill")["policy_id"] == "06"
assert get_policy("zebra pineapple") == {"found": False}
assert get_policy("") == {"found": False}
print("\nAll assertions passed.")
