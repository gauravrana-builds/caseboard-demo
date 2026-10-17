"""Offline check of eval/run_evals.py: every complaint in data/complaints.csv through the real pipeline code and
the real scoring code, with a deterministic stub standing in for the model. No API calls, no cost.

The stub is deliberately naive (Medium risk for everything, never stops on its own), so this
tests the plumbing and what the deterministic code guards alone catch - NOT model quality.

Run:  python eval/test_run_evals_offline.py
"""

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_evals as ev  # noqa: E402


class NaiveStub:
    def __init__(self):
        self.messages = self

    def create(self, model, max_tokens, system, messages):
        payload = json.loads(messages[0]["content"])
        head = system.split("\n", 1)[0]
        if head.startswith("# Prompt 1"):
            n = payload["complaint_narrative"]
            inj = ["skip the usual review"] if ("skip the usual" in n or "ignore any standard" in n) else []
            out = {"allegations": [n[:50]], "requested_outcome": None, "dollar_amounts_mentioned": [],
                   "dates_mentioned": [], "account_details_mentioned": None, "risk_signal_phrases": [],
                   "suspicious_embedded_instructions": inj, "tone_summary": "x"}
        elif head.startswith("# Prompt 2"):
            out = {"fact_verification": "confirmed_false", "fact_verification_explanation": "stub",
                   "risk_tier": "Medium", "risk_rationale": "stub", "udaap_pattern_detected": False,
                   "proceed_to_draft": True, "stop_reason": None}
        elif head.startswith("# Prompt 3"):
            out = {"draft_text": "stub draft", "policy_cited": "stub", "remedy_stated": None,
                   "allegations_addressed": []}
        else:
            out = {"overall_result": "pass", "completeness_check": "pass", "groundedness_check": "pass",
                   "policy_authorization_check": "pass", "prohibited_language_check": "pass",
                   "tone_structure_check": "pass", "specific_issues": []}
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(out))],
                               usage=SimpleNamespace(input_tokens=100, output_tokens=50))


truth = ev.load_truth()
run_dir = Path(tempfile.mkdtemp(prefix="evals_offline_"))
ev.run_all(list(truth.index), run_dir, NaiveStub(), workers=4)
packets = ev.load_packets(run_dir)
assert len(packets) == len(truth), len(packets)

card = ev.render_scorecard(run_dir, packets, truth, 0.85)
ev.finish(run_dir, truth, 0.85)

e1, e2, e3, e4 = (ev.score_eval1(packets, truth, 0.85), ev.score_eval2(packets, truth),
                  ev.score_eval3(packets, truth), ev.score_eval4(packets, truth))
n = len(truth)
assert sum(sum(m.values()) for m in e1["matrix"].values()) == n
assert e1["n"] == n and len(e4["cases"]) == 2
assert e3["n"] == (truth["fact_verification_ground_truth"] != "").sum()
assert e2["n_should"] == (truth["escalation_expected"].str.lower() == "true").sum()
assert (run_dir / "scorecard.md").exists() and (run_dir / "results.csv").exists()
assert (run_dir / "drafts_for_review.csv").exists()
# resume: nothing left to run, no model calls made
ev.run_all(list(truth.index), run_dir, None, workers=4)
# Eval 5 tabulation
import pandas as pd  # noqa: E402
rev = pd.read_csv(run_dir / "drafts_for_review.csv", dtype=str, keep_default_na=False)
rev.iloc[:6, rev.columns.get_loc(next(c for c in rev.columns if c.startswith("human_tag")))] = \
    ["Approve", "Approve", "approve as is", "Minor", "Minor edit", "Substantive"]
rev.to_csv(run_dir / "review_filled.csv", index=False)
print("\nEval 5 tabulation check:", ev.score_review(run_dir / "review_filled.csv"))
print(f"\nOffline plumbing OK. Stub-only recall (guards alone, no model): {e2['caught']}/{e2['n_should']}; "
      f"missed {e2['missed']}")
print("Results folder (temp):", run_dir)
