"""Check log_case() against a scratch file (never touches data/case_log.csv).  Run: python app/test_log_case.py"""
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
scratch = Path(tempfile.mkdtemp(prefix="caselog_")) / "case_log.csv"
os.environ["COMPLAINT_AGENT_CASE_LOG"] = str(scratch)
from tools import CASE_LOG_COLUMNS, log_case  # noqa: E402

# 1. missing file is created with the header
log_case({"complaint_id": "A1", "human_decision": "approve", "risk_tier": "Low", "draft_text": "Hello,\n\n\"quoted\", commas, and newlines",
          "extraction_output": {"allegations": ["a, b"]}})
# 2. a second decision on the same complaint is a NEW row, the first is untouched (audit trail)
log_case({"complaint_id": "A1", "human_decision": "edit", "edit_severity": "Minor", "draft_text": "edited"})
# 3. file with no trailing newline: the next append must not glue onto the last line
raw = scratch.read_bytes().rstrip(b"\n")
scratch.write_bytes(raw)
log_case({"complaint_id": "B2", "human_decision": "downgrade", "override_reason": "false positive"})

df = pd.read_csv(scratch, dtype=str, keep_default_na=False)
assert list(df.columns) == CASE_LOG_COLUMNS
assert df.complaint_id.tolist() == ["A1", "A1", "B2"], df.complaint_id.tolist()
assert df.human_decision.tolist() == ["approve", "edit", "downgrade"]
assert df.loc[0, "draft_text"] == "Hello,\n\n\"quoted\", commas, and newlines"
assert df.loc[0, "extraction_output"] == '{"allegations": ["a, b"]}'
assert df.loc[1, "edit_severity"] == "Minor" and df.loc[2, "override_reason"] == "false positive"
assert all(df.timestamp.str.len() > 10)
print("log_case OK:", len(df), "rows, columns intact, JSON/newlines/commas round-trip, no-newline file handled")
