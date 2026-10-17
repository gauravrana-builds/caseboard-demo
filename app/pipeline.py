"""Complaint analysis pipeline: one complaint in, one reviewable packet out.

Extract -> fetch evidence -> verify/classify risk -> (stop & escalate | retrieve policy ->
draft -> independent verifier, one retry). The agent never sends anything, never
initiates an escalation, and never logs: the packet goes to Maya, and log_case() runs
only when she records a decision. See IMPLEMENTATION_BRIEF.md section 5.

Usage:  python app/pipeline.py SYN-F01 [--json]
"""

import copy
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools import DATA_DIR, POLICY_DIR, get_account, get_policy, get_transactions  # noqa: E402

PROMPTS_DIR = DATA_DIR.parent / "prompts"
MODEL = os.environ.get("COMPLAINT_AGENT_MODEL", "claude-sonnet-5-5")
MAX_TOKENS = 16000

PROMPT_FILES = {
    "extraction": "01_extraction.md",
    "verify_and_classify": "02_verify_and_classify.md",
    "drafting": "03_drafting.md",
    "verifier": "04_verifier.md",
}

# Deterministic backstop for the mandatory stop rule (PRD section 10): attorney / legal
# action / regulator mentions. Matches the triggers Prompt 2 defines, so a model miss
# can never let one of these through to drafting.
ATTORNEY_REGULATOR_RE = re.compile(
    r"\b(attorneys?|lawyers?|legal counsel|legal action|lawsuit|sue|suing|sued"
    r"|cfpb|consumer financial protection bureau|attorney general|regulators?"
    r"|state banking|department of financial)\b",
    re.IGNORECASE,
)

FACT_VERDICTS = {"confirmed_true", "confirmed_false", "partially_true", "unverifiable"}
GENERAL_DISPUTE_FALLBACK = "general dispute, process, timeline, acknowledge, investigate, respond"


class PipelineLLMError(RuntimeError):
    """An LLM call failed, was refused, or returned unusable output."""


# --------------------------------------------------------------------------- helpers

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_prompt(key: str) -> str:
    return (PROMPTS_DIR / PROMPT_FILES[key]).read_text(encoding="utf-8")


def _load_complaint(complaint_id: str) -> dict:
    df = pd.read_csv(DATA_DIR / "complaints.csv", dtype=str, keep_default_na=False)
    match = df[df["complaint_id"].str.strip() == str(complaint_id).strip()]
    if match.empty:
        raise ValueError(f"Complaint '{complaint_id}' not found in complaints.csv")
    return match.iloc[0].to_dict()


def _policy_by_id(policy_id: str) -> dict:
    """Full policy text by policy_id (used for the always-included policies 09/10/11)."""
    index = pd.read_csv(DATA_DIR / "policy_index.csv", dtype=str, keep_default_na=False)
    row = index[index["policy_id"] == policy_id].iloc[0]
    return {
        "found": True,
        "policy_id": row["policy_id"],
        "topic": row["topic"],
        "category": row["category"],
        "filename": row["filename"],
        "text": (POLICY_DIR / row["filename"]).read_text(encoding="utf-8"),
    }


def _parse_json(text: str) -> dict:
    text = text.strip()
    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())
    if "{" in text and "}" in text:
        candidates.append(text[text.index("{"): text.rindex("}") + 1])
    for cand in candidates:
        try:
            parsed = json.loads(cand)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    raise ValueError("no JSON object found in model output")


def _call_llm(client, name: str, payload: dict, calls: list) -> dict:
    """One stateless LLM call: the prompt file is the system prompt, payload is the user
    message. Retries once on unparseable output; refusals and truncation raise."""
    system = _load_prompt(name)
    user = json.dumps(payload, indent=2, default=str)
    last_err = None
    for attempt in (1, 2):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        calls.append({
            "step": name, "attempt": attempt, "stop_reason": resp.stop_reason,
            "input_tokens": getattr(resp.usage, "input_tokens", None),
            "output_tokens": getattr(resp.usage, "output_tokens", None),
        })
        if resp.stop_reason == "refusal":
            raise PipelineLLMError(f"{name}: model declined the request (refusal)")
        if resp.stop_reason == "max_tokens":
            raise PipelineLLMError(f"{name}: output truncated at max_tokens")
        text = "".join(b.text for b in resp.content if b.type == "text")
        try:
            return _parse_json(text)
        except ValueError as err:
            last_err = err
    raise PipelineLLMError(f"{name}: could not parse JSON after 2 attempts ({last_err})")


def _require(obj: dict, keys: list, name: str) -> None:
    missing = [k for k in keys if k not in obj]
    if missing:
        raise PipelineLLMError(f"{name}: output missing required fields {missing}")


# ------------------------------------------------------------------ stop-rule logic

def _find_triggers(complaint: dict, extraction: dict) -> list[dict]:
    """Deterministic stop triggers that do not depend on the model's judgment."""
    triggers = []
    hits = sorted({m.group(0) for m in ATTORNEY_REGULATOR_RE.finditer(complaint["narrative"])},
                  key=str.lower)
    if hits or complaint.get("attorney_regulator_flag", "").strip().upper() == "TRUE":
        triggers.append({
            "type": "attorney_regulator",
            "detail": ("Attorney/regulator reference in narrative: " + ", ".join(f"'{h}'" for h in hits))
            if hits else "attorney_regulator_flag is TRUE on the complaint record",
            "stop_reason": "Attorney or regulator mention detected - mandatory escalation per "
                           "policy 09; no draft may be prepared.",
        })
    injected = extraction.get("suspicious_embedded_instructions") or []
    if injected:
        triggers.append({
            "type": "prompt_injection",
            "detail": "Narrative contains embedded instructions: " + "; ".join(f"'{i}'" for i in injected),
            "stop_reason": "Suspected prompt injection - the narrative contains instructions aimed at "
                           "the system. They were not followed; flagged for human review.",
        })
    return triggers


def _decide(verification: dict, triggers: list[dict]) -> dict:
    """Combine the model's stop decision with deterministic triggers. Either can stop
    the run; nothing can override a stop."""
    verification = dict(verification)
    if verification.get("fact_verification") not in FACT_VERDICTS:
        # e.g. the model's own few-shot uses "unresolved"; treat anything off-enum as unverifiable
        verification["fact_verification_raw"] = verification.get("fact_verification")
        verification["fact_verification"] = "unverifiable"

    proceed = verification.get("proceed_to_draft") is True
    stop_reason = verification.get("stop_reason")
    overrides = []

    if triggers:
        proceed = False
        # Only attorney/regulator is an automatic High (Prompt 2). Injection stops the run but
        # leaves the model's own tier alone, so Eval 1 reflects what the model actually judged.
        if any(t["type"] == "attorney_regulator" for t in triggers) and verification.get("risk_tier") != "High":
            overrides.append(f"risk_tier raised from {verification.get('risk_tier')} to High by attorney_regulator trigger")
            verification["risk_tier"] = "High"
        if verification.get("proceed_to_draft") is True:
            overrides.append("proceed_to_draft forced to false by deterministic trigger")
        stop_reason = triggers[0]["stop_reason"]  # attorney/regulator is listed first
    if verification.get("risk_tier") == "High" and proceed:
        proceed = False
        overrides.append("proceed_to_draft forced to false: risk tier is High")
    if not proceed and not stop_reason:
        stop_reason = "Model decided not to proceed to draft without stating a reason; review required."

    verification["proceed_to_draft"] = proceed
    verification["stop_reason"] = None if proceed else stop_reason
    verification["triggers"] = triggers
    verification["code_overrides"] = overrides
    return verification


# ---------------------------------------------------------------- policy + drafting

def _retrieve_policy(complaint: dict, extraction: dict) -> dict:
    parts = [complaint["issue"], complaint["sub_issue"], extraction.get("requested_outcome") or ""]
    parts += extraction.get("allegations") or []
    policy = get_policy(" ".join(p for p in parts if p))
    fallback = False
    if not policy["found"]:
        policy = get_policy(GENERAL_DISPUTE_FALLBACK)  # policy 08, so the draft is never un-cited
        fallback = True
    policy["fallback_used"] = fallback
    return policy


def _verifier_failed(result: dict) -> bool:
    checks = [v for k, v in result.items() if k.endswith("_check")]
    return result.get("overall_result") != "pass" or any(str(c).strip().lower().startswith("fail") for c in checks)


def _draft_and_verify(client, extraction, verification, policy, case_reference, calls, analyst_note=None) -> tuple[list[dict], str]:
    """Draft, verify, and (once) regenerate with verifier feedback. Returns the attempts
    and the final status. Never loops beyond two attempts."""
    p10, p11 = _policy_by_id("10"), _policy_by_id("11")
    attempts, feedback = [], None
    for n in (1, 2):
        context = {
            "extraction": extraction,
            "verification": {k: verification[k] for k in
                             ("fact_verification", "fact_verification_explanation", "risk_tier", "risk_rationale")},
            "retrieved_policy": {k: policy[k] for k in ("policy_id", "topic", "text")},
            "policy_10_prohibited_language": p10["text"],
            "policy_11_response_tone_format": p11["text"],
            "case_reference": case_reference,
        }
        if analyst_note:
            context["analyst_override"] = analyst_note
        if feedback:
            context["verifier_feedback_on_previous_draft"] = feedback
        draft = _call_llm(client, "drafting", context, calls)
        _require(draft, ["draft_text", "policy_cited", "allegations_addressed"], "drafting")

        result = _call_llm(client, "verifier", {
            "allegations": extraction.get("allegations") or [],
            "case_reference": case_reference,  # the drafter is given this, so the verifier must be too
            "verification": context["verification"],
            "draft_text": draft["draft_text"],
            "remedy_stated": draft.get("remedy_stated"),
            "referral_stated": draft.get("referral_stated"),
            "policy_cited_by_draft": draft["policy_cited"],
            "cited_policy_text": policy["text"],
            "policy_10_prohibited_language": p10["text"],
            "policy_11_response_tone_format": p11["text"],
        }, calls)
        _require(result, ["overall_result"], "verifier")
        result["overall_result"] = "fail" if _verifier_failed(result) else "pass"
        attempts.append({"attempt": n, "draft": draft, "verifier": result})
        if result["overall_result"] == "pass":
            return attempts, "draft_ready"
        feedback = result.get("specific_issues") or [str(result)]
    return attempts, "draft_failed_verification"


# ------------------------------------------------------------------------ main entry

def run_pipeline(complaint_id: str, client=None) -> dict:
    """Run one complaint through the full loop and return the review packet.

    Each run is stateless: nothing from another complaint is visible to any call."""
    complaint = _load_complaint(complaint_id)
    packet = {
        "complaint_id": complaint["complaint_id"],
        "run_started": _now(),
        "model": MODEL,
        "complaint": {k: complaint[k] for k in
                      ("complaint_id", "date_received", "product", "sub_product", "issue",
                       "sub_issue", "state", "narrative", "account_id", "attorney_regulator_flag")},
        "llm_calls": [],
    }
    calls = packet["llm_calls"]

    if client is None:
        import anthropic
        client = anthropic.Anthropic()

    try:
        # Step 2: extraction. The narrative is data only; nothing else about the complaint
        # (ground truth, labeler notes) is ever shown to a model.
        extraction = _call_llm(client, "extraction", {
            "complaint_narrative": complaint["narrative"],
            "cfpb_tags": {k: complaint[k] for k in ("product", "sub_product", "issue", "sub_issue")},
        }, calls)
        _require(extraction, ["allegations", "risk_signal_phrases", "suspicious_embedded_instructions"], "extraction")
        packet["extraction"] = extraction

        # Step 3: evidence
        account = get_account(complaint["account_id"])
        transactions = get_transactions(complaint["account_id"])
        packet["evidence"] = {"account": account, "transactions": transactions}

        # Step 4: verification + risk + stop decision (model), then deterministic guards
        raw = _call_llm(client, "verify_and_classify", {
            "extraction": extraction,
            "account": account,
            "transactions": transactions,
            "attorney_regulator_flag": complaint["attorney_regulator_flag"],
        }, calls)
        _require(raw, ["fact_verification", "risk_tier", "proceed_to_draft"], "verify_and_classify")
        verification = _decide(raw, _find_triggers(complaint, extraction))
        packet["verification"] = verification
        packet["risk_tier"] = verification["risk_tier"]

        # Step 5: branch
        if not verification["proceed_to_draft"]:
            packet["status"] = "escalated"
            packet["escalation_package"] = _escalation_package(complaint, extraction, verification, account, transactions)
        else:
            # Step 6-7: policy, draft, verify (one regeneration)
            policy = _retrieve_policy(complaint, extraction)
            packet["policy"] = {k: policy[k] for k in ("policy_id", "topic", "category", "matched_keywords", "fallback_used", "text")}
            attempts, status = _draft_and_verify(
                client, extraction, verification, policy, complaint["complaint_id"], calls)
            packet["status"] = status
            packet["attempts"] = attempts
            packet["draft"] = attempts[-1]["draft"]
            # A draft that says something is being referred needs a human to make that referral before sending.
            packet["action_required_before_sending"] = packet["draft"].get("referral_stated") or None
            packet["verifier"] = attempts[-1]["verifier"]
    except PipelineLLMError as err:
        # Fail closed: if the pipeline can't complete safely, hand the case to a human.
        packet["status"] = "escalated"
        packet["pipeline_error"] = str(err)
        packet["escalation_package"] = {
            "complaint_text": complaint["narrative"],
            "extraction": packet.get("extraction"),
            "verification": packet.get("verification"),
            "evidence": packet.get("evidence"),
            "stop_reason": f"Pipeline could not complete safely: {err}",
            "agent_actions_taken": "Analysis only. No draft prepared, nothing sent, no escalation initiated.",
        }

    packet["summary"] = _summary(packet)
    packet["run_finished"] = _now()
    return packet  # Step 8: caller shows Maya; log_case() is called on her decision, not here


def draft_after_override(packet: dict, reason: str, client=None) -> dict:
    """A human analyst downgraded the agent's stop as a false alarm: draft a reply for human review.

    Reuses the earlier extraction and verification, then runs the normal steps 6-7 (policy lookup, draft,
    independent check with one retry). The original stop reason stays on the packet; the analyst's reason is
    recorded as analyst_override. Nothing is sent; the new draft goes back to the analyst for a decision."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    complaint = packet["complaint"]
    extraction = copy.deepcopy(packet["extraction"])
    verification = dict(packet["verification"])
    calls: list = []
    policy = _retrieve_policy(complaint, extraction)
    note = ("A human analyst reviewed the agent's stop on this complaint and downgraded it as a false alarm "
            f"(the analyst's reason: {reason}). Draft the normal reply for the analyst to review.")
    attempts, status = _draft_and_verify(client, extraction, verification, policy, packet["complaint_id"], calls, analyst_note=note)
    out = copy.deepcopy(packet)
    out["status"] = status
    out["policy"] = {k: policy[k] for k in ("policy_id", "topic", "category", "matched_keywords", "fallback_used", "text")}
    out["attempts"] = attempts
    out["draft"] = attempts[-1]["draft"]
    out["verifier"] = attempts[-1]["verifier"]
    out["action_required_before_sending"] = out["draft"].get("referral_stated") or None
    out["analyst_override"] = {"reason": reason, "original_stop_reason": verification.get("stop_reason"), "at": _now()}
    out["llm_calls"] = list(packet.get("llm_calls", [])) + calls
    out["summary"] = _summary(out)
    out["run_finished"] = _now()
    return out


def _escalation_package(complaint, extraction, verification, account, transactions) -> dict:
    p09 = _policy_by_id("09")
    return {
        "complaint_text": complaint["narrative"],
        "extraction": extraction,
        "verification": {k: verification.get(k) for k in
                         ("fact_verification", "fact_verification_explanation", "risk_tier", "risk_rationale",
                          "udaap_pattern_detected")},
        "evidence": {"account": account, "transactions": transactions},
        "trigger": verification["triggers"] or "Model-determined stop (see stop_reason)",
        "stop_reason": verification["stop_reason"],
        "unresolved": verification.get("fact_verification_explanation")
        if verification.get("fact_verification") == "unverifiable" else None,
        "policy_reference": {"policy_id": p09["policy_id"], "topic": p09["topic"], "text": p09["text"]},
        "agent_actions_taken": "Analysis only. No draft prepared, nothing sent, no escalation initiated - "
                               "Maya decides whether to route this case.",
    }


def _summary(packet: dict) -> str:
    c = packet["complaint"]
    v = packet.get("verification") or {}
    fact = v.get("fact_verification", "not assessed")
    tier = v.get("risk_tier", "unknown")
    tail = {"draft_ready": "draft ready for review",
            "draft_failed_verification": "draft failed verification twice - needs manual drafting",
            "escalated": "ESCALATED - no draft"}[packet["status"]]
    return f"{c['issue']} - {fact} - {tier} risk - {tail}"


# --------------------------------------------------------------------------------- CLI

def _print_packet(p: dict) -> None:
    line = "=" * 78
    print(f"{line}\n{p['complaint_id']}  |  {p['summary']}\n{line}")
    if p.get("pipeline_error"):
        print("PIPELINE ERROR:", p["pipeline_error"])
    ex = p.get("extraction")
    if ex:
        print("\nAllegations:", *[f"\n  - {a}" for a in ex.get("allegations", [])])
        print("Requested outcome:", ex.get("requested_outcome"))
        print("Risk-signal phrases:", ex.get("risk_signal_phrases"))
        print("Embedded instructions:", ex.get("suspicious_embedded_instructions"))
    v = p.get("verification")
    if v:
        print(f"\nFact verification: {v['fact_verification']}\n  {v.get('fact_verification_explanation')}")
        print(f"Risk tier: {v['risk_tier']}\n  {v.get('risk_rationale')}")
        if v.get("code_overrides"):
            print("Guard overrides:", v["code_overrides"])
    if p["status"] == "escalated":
        pkg = p["escalation_package"]
        print(f"\n*** ESCALATION - NO DRAFT ***\nStop reason: {pkg['stop_reason']}")
        if isinstance(pkg.get("trigger"), list):
            for t in pkg["trigger"]:
                print(f"  trigger [{t['type']}]: {t['detail']}")
    else:
        pol = p["policy"]
        print(f"\nPolicy: {pol['policy_id']} {pol['topic']} (matched {pol['matched_keywords']}, fallback={pol['fallback_used']})")
        print(f"\nDraft (attempt {len(p['attempts'])}):\n{p['draft']['draft_text']}")
        print(f"Policy cited: {p['draft']['policy_cited']} | remedy: {p['draft'].get('remedy_stated')}")
        if p.get("action_required_before_sending"):
            print(f"ACTION REQUIRED BEFORE SENDING: {p['action_required_before_sending']}")
        print(f"\nVerifier: {p['verifier']['overall_result']}")
        for issue in p["verifier"].get("specific_issues") or []:
            print("  -", issue)
    print(f"\nStatus: {p['status']}  |  LLM calls: {len(p['llm_calls'])}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit("usage: python app/pipeline.py COMPLAINT_ID [--json]")
    try:
        result = run_pipeline(args[0])
    except TypeError as err:
        if "authentication" not in str(err):
            raise
        sys.exit("No Anthropic credentials found. Set ANTHROPIC_API_KEY (then restart this terminal/app "
                 "if you used setx) and run again.")
    if "--json" in sys.argv:
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_packet(result)
