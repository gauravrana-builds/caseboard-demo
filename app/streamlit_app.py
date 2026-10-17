"""Review workspace for the complaint analysis agent (IMPLEMENTATION_BRIEF.md section 7).

Run from the project folder:  python -m streamlit run app/streamlit_app.py

The app opens on the queue: every complaint that has come in, with the agent's outcome, its risk rating and a
disposition that tracks where each one stands (Needs human review, Draft ready, Escalated to Legal / Compliance,
Sent). A tracker above the list shows the whole queue at a glance. Opening a complaint shows the agent's packet; the
analyst's decision moves it to a new disposition. When the analyst downgrades a stop as a false alarm, the agent
drafts a reply automatically and the draft comes back for review.

Default mode shows saved pipeline results (instant, no API cost). "Run the pipeline live" (Presenter options in the
sidebar) calls the model for the selected complaint (about $0.05, needs ANTHROPIC_API_KEY). "Sent" is simulated:
the prototype records the approval and never delivers anything to a customer.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipeline  # noqa: E402
from tools import DATA_DIR, log_case  # noqa: E402
from ui_theme import THEME_CSS, VERDICT_LABEL, esc, logo_svg, pill, tier_pill, verdict_pill  # noqa: E402

ROOT = DATA_DIR.parent
ASSETS = Path(__file__).resolve().parent / "assets"
PRODUCT = "Caseboard"
ANALYST_NAME = "Maya"
ANALYST_ROLE = "Complaint analyst"
RESULTS_DIR = Path(os.environ.get("COMPLAINT_AGENT_RESULTS_DIR") or ROOT / "eval" / "results")  # override is for tests
OVERRIDE_DIR = RESULTS_DIR / "overrides"  # drafts the agent wrote after a downgrade, reused so the demo is instant

OUTCOME_LABEL = {"draft_ready": "Draft ready", "escalated": "Needs human review", "draft_failed_verification": "Draft failed checks"}
DISPOSITIONS = ["Needs human review", "Draft ready", "Escalated to Legal / Compliance", "Sent"]
DISP_COLOR = {"Needs human review": "#ea2261", "Draft ready": "#533afd", "Escalated to Legal / Compliance": "#d9a441", "Sent": "#1f9d6b"}
DISP_PILL = {"Needs human review": "ruby", "Draft ready": "indigo", "Escalated to Legal / Compliance": "amber", "Sent": "green"}
DISP_HINT = {
    "Needs human review": "The agent stopped. You decide: escalate, or downgrade a false alarm.",
    "Draft ready": "The agent drafted a reply. Review, edit and send.",
    "Escalated to Legal / Compliance": "Routed to a person outside this queue.",
    "Sent": "Approved by you. Simulated: nothing is delivered.",
}
DECISION_TO_DISP = {"approve": "Sent", "edit": "Sent", "escalate": "Escalated to Legal / Compliance", "escalate_to_legal_compliance": "Escalated to Legal / Compliance"}
RISK_RANK = {"High": 0, "Medium": 1, "Low": 2}
CHECK_LABEL = {
    "completeness_check": "Covers every allegation", "groundedness_check": "Facts trace to the record",
    "policy_authorization_check": "Remedy within policy authority", "prohibited_language_check": "No prohibited language",
    "tone_structure_check": "Tone and structure",
}
DECISION_LABEL = {
    "approve": "Approved and marked as sent", "edit": "Edited, approved and marked as sent", "escalate": "Escalated to Legal / Compliance",
    "escalate_to_legal_compliance": "Escalated to Legal / Compliance",
}
# (complaint id, short label, what to notice) - the guided demo path, see DEMO.md
DEMO_PATH = [
    ("SYN-F01", "Customer wrong", "The claim is checked against the account and found false. The reply explains what the records show, politely, instead of just agreeing."),
    ("21633667", "Our error", "The payment arrived on time but was recorded two days later. Policy 06 allows the waiver, and the note above the buttons says what to submit before sending."),
    ("20962593", "Partly true", "The call log confirms the calls, including two before 8am, but there is no record of the mail-only request. The reply treats each part separately."),
    ("SYN-B01", "Attorney", "A mandatory stop: no draft is prepared. Escalate it, or downgrade it as a false alarm (a reason is required) and the agent drafts a reply for you to review."),
    ("SYN-B03", "Hidden orders", "The complaint tries to give the system orders. The agent flags them, does not follow them, still checks the account, and stops for a person."),
    ("25164083", "Identity theft", "Policy 09 requires escalation when a customer says a loan isn't theirs. The open fraud review is noted too."),
]

st.set_page_config(page_title=PRODUCT, page_icon=str(ASSETS / "caseboard_icon.png"), layout="wide", initial_sidebar_state="collapsed")
st.markdown(THEME_CSS, unsafe_allow_html=True)
for _k, _v in {"decisions": {}, "downgrades": {}, "overrides": {}, "override_errors": {}, "demo_idx": 0, "open_id": None, "q_nonce": 0,
               "f_disp": "All", "f_outcome": [], "f_risk": [], "f_query": ""}.items():
    st.session_state.setdefault(_k, _v)


# ----------------------------------------------------------------------------------------------- data access

@st.cache_data(show_spinner=False)
def load_complaints() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "complaints.csv", dtype=str, keep_default_na=False)


@st.cache_data(show_spinner=False)
def load_saved_packets() -> dict:
    """Newest saved result per complaint across eval/results/run_*/packets (later runs override earlier ones)."""
    out = {}
    for run in sorted(RESULTS_DIR.glob("run_*")):
        for f in (run / "packets").glob("*.json"):
            try:
                packet = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if packet.get("status") in ("draft_ready", "escalated", "draft_failed_verification") and packet.get("verification"):
                out[f.stem] = (packet, run.name)
    return out


def get_packet(cid: str, live: bool):
    if live:
        key = f"live::{cid}"
        if key not in st.session_state:
            try:
                with st.spinner("Running the agent: extract, verify, classify, draft, check. This takes about 30-60 seconds."):
                    st.session_state[key] = pipeline.run_pipeline(cid)
            except Exception as err:  # missing credentials, network, etc.
                st.error(f"The live run could not complete: {err}")
                return None, None
        return st.session_state[key], "live run"
    saved = load_saved_packets().get(cid)
    return (saved[0], saved[1]) if saved else (None, None)


def active_packet(cid: str, live: bool):
    """The packet the analyst is working with: the agent's draft after a downgrade, otherwise the agent's own result."""
    override = st.session_state.overrides.get(cid)
    if override:
        return override, "agent draft after your downgrade"
    return get_packet(cid, live)


def initial_status(cid: str):
    live_packet = st.session_state.get(f"live::{cid}")
    if live_packet:
        return live_packet["status"]
    saved = load_saved_packets().get(cid)
    return saved[0]["status"] if saved else None


def disposition_of(cid: str):
    """Where this complaint stands now, derived from what the agent did and what the analyst has decided."""
    decision = st.session_state.decisions.get(cid)
    if decision:
        return DECISION_TO_DISP.get(decision["decision"], "Needs human review")
    override = st.session_state.overrides.get(cid)
    if override:
        return "Needs human review" if override["status"] == "draft_failed_verification" else "Draft ready"
    status = initial_status(cid)
    if status is None:
        return "Not run"
    return "Draft ready" if status == "draft_ready" else "Needs human review"


def load_override_cache(cid: str):
    f = OVERRIDE_DIR / f"{cid}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return None


@st.cache_data(show_spinner=False)
def load_scorecard():
    """Score the newest full run with the same code the eval harness uses, so the numbers cannot drift from it."""
    sys.path.insert(0, str(ROOT / "eval"))
    import run_evals as ev  # noqa: WPS433

    truth = ev.load_truth()
    full = [r for r in sorted(RESULTS_DIR.glob("run_*")) if len(list((r / "packets").glob("*.json"))) == len(truth)]
    if not full:
        return None
    run = full[-1]
    packets = ev.load_packets(run)
    out = {
        "run": run.name, "n": len(truth), "cost": ev.token_cost(packets)["cost"],
        "e1": ev.score_eval1(packets, truth, 0.85), "e2": ev.score_eval2(packets, truth),
        "e3": ev.score_eval3(packets, truth), "e4": ev.score_eval4(packets, truth), "review": None,
    }
    sheets = []
    for r in sorted(RESULTS_DIR.glob("run_*")):
        sheet = r / "drafts_for_review.csv"
        if not sheet.exists():
            continue
        df = pd.read_csv(sheet, dtype=str, keep_default_na=False)
        col = next((c for c in df.columns if c.startswith("human_tag")), None)
        tags = df[col].str.strip().str.lower() if col else pd.Series(dtype=str)
        counts = {"Approve": int(tags.str.startswith("approve").sum()), "Minor": int(tags.str.startswith("minor").sum()),
                  "Substantive": int(tags.str.startswith("subst").sum())}
        sheets.append({"run": r.name, "counts": counts, "total": sum(counts.values()), "drafts": len(df),
                       "full": len(list((r / "packets").glob("*.json"))) == len(truth)})
    reviewed = [x for x in sheets if x["total"]]
    out["review"] = max(reviewed, key=lambda x: (x["total"], x["run"])) if reviewed else None  # most complete review; newest on a tie
    out["newest"] = next((x for x in reversed(sheets) if x["full"]), None)  # the newest full run, reviewed or not
    return out


# ------------------------------------------------------------------------------------------------ helpers

def pretty_date(value: str) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return value if pd.isna(parsed) else f"{parsed:%b} {parsed.day}, {parsed.year}"


def first_sentence(text: str, limit: int = 170) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    cut = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    return cut if len(cut) <= limit else cut[: limit - 1].rstrip() + "…"


def clean_markdown(text: str, limit: int = 420) -> str:
    lines = (text or "").strip().splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        lines = lines[1:]  # the title is shown separately as the policy topic
    text = re.sub(r"^#+\s*", "", chr(10).join(lines), flags=re.M)
    text = re.sub(r"[*_`|]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def card(title: str, body: str, cls: str = "") -> str:
    return f'<div class="card {cls}"><h4>{esc(title)}</h4>{body}</div>'


def paragraphs(text: str) -> str:
    parts = [p for p in re.split(r"\n\s*\n", (text or "").strip()) if p.strip()]
    return "".join(f'<p style="margin:0 0 13px">{esc(p.strip())}</p>' for p in parts)


def plain_headline(packet: dict) -> tuple[str, str]:
    """One plain sentence saying what happened and why, instead of policy language."""
    v = packet["verification"]
    status = packet["status"]
    if packet.get("analyst_override") and status != "escalated":
        return "You downgraded the stop. The agent drafted a reply for your review.", "ok"
    if status == "escalated":
        triggers = [t["type"] for t in v.get("triggers", [])]
        reason = (v.get("stop_reason") or packet.get("pipeline_error") or "").lower()
        if "attorney_regulator" in triggers:
            return "Stopped: the customer mentions an attorney or regulator.", "stop"
        if "prompt_injection" in triggers:
            return "Stopped: the complaint tries to give the system instructions.", "stop"
        if "identity" in reason or "policy 09" in reason:
            return "Stopped: the customer says the loan isn't theirs, which may be identity theft.", "stop"
        if "policy 05" in reason or "misled" in reason or "disclos" in reason:
            return "Stopped: the customer says they were misled about the loan's terms.", "stop"
        if "collector" in reason or "reg f" in reason or "policy 03" in reason or "threat" in reason:
            return "Stopped: the customer reports threats or pressure from a collector.", "stop"
        if "unverif" in reason or "cannot" in reason or "outside" in reason:
            return "Stopped: the records can't settle this, so a person needs to look.", "stop"
        return "Stopped: this is a high-risk complaint and needs a person.", "stop"
    if status == "draft_failed_verification":
        return "A draft was tried twice but did not pass the independent check.", "warn"
    by_verdict = {
        "confirmed_true": "The records back up the customer. A draft reply is ready for you.",
        "confirmed_false": "The records don't support the claim. A draft reply is ready for you.",
        "partially_true": "Part of the claim checks out. A draft reply is ready for you.",
    }
    return by_verdict.get(v.get("fact_verification"), "A draft reply is ready for you."), "ok"


def steps_html(packet: dict) -> str:
    v = packet.get("verification") or {}
    stopped = packet["status"] == "escalated"
    failed = packet["status"] == "draft_failed_verification"
    ver = packet.get("verifier") or {}
    passed = ver.get("overall_result") == "pass"
    steps = [
        ("Read the complaint", "ok", "Allegations extracted"),
        ("Check the records", "ok", VERDICT_LABEL.get(v.get("fact_verification"), "Checked")),
        ("Rate the risk", "stop" if stopped else "ok", "Stopped here" if stopped else f'{v.get("risk_tier", "")} risk'),
        ("Draft a reply", "skip" if stopped else "ok", "Not prepared" if stopped else "Drafted"),
        ("Independent check", "skip" if stopped else ("ok" if passed and not failed else "bad"),
         "Not run" if stopped else ("Passed" if passed and not failed else "Failed twice")),
    ]
    icon = {"ok": "✓", "stop": "■", "bad": "!", "skip": "–"}
    cells = "".join(f'<div class="step step-{kind}"><div class="sc">{icon[kind]}</div><div class="sl">{esc(label)}</div><div class="ss">{esc(sub)}</div></div>' for label, kind, sub in steps)
    return f'<div class="steps">{cells}</div>'


def build_record(packet: dict, decision: str, **extra) -> dict:
    v = packet.get("verification") or {}
    draft = packet.get("draft") or {}
    pol = packet.get("policy") or {}
    return {
        "complaint_id": packet["complaint_id"],
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "extraction_output": packet.get("extraction"),
        "verified_facts": {"fact_verification": v.get("fact_verification"), "explanation": v.get("fact_verification_explanation")},
        "risk_tier": v.get("risk_tier"),
        "risk_reason": v.get("risk_rationale"),
        "policy_cited": draft.get("policy_cited") or (f"{pol.get('policy_id')} {pol.get('topic')}" if pol else ""),
        "draft_text": extra.pop("draft_text", draft.get("draft_text", "")),
        "verifier_result": (packet.get("verifier") or {}).get("overall_result", ""),
        "human_decision": decision,
        "edit_severity": extra.pop("edit_severity", ""),
        "override_reason": extra.pop("override_reason", ""),
    }


def write_log(packet: dict, decision: str, **extra) -> bool:
    """Append the decision to the audit log. Returns False (after telling the user) if the file is locked."""
    if not st.session_state.get("write_log", True):
        return True
    try:
        log_case(build_record(packet, decision, **dict(extra)))
        return True
    except PermissionError:
        st.error("The audit log (data/case_log.csv) is locked, probably open in Excel. Close it and try again.")
        return False


def record_decision(packet: dict, decision: str, **extra):
    cid = packet["complaint_id"]
    if not write_log(packet, decision, **extra):
        return
    st.session_state.decisions[cid] = {"decision": decision, "at": datetime.now().strftime("%H:%M"), "logged": st.session_state.get("write_log", True)}
    for k in (f"editing::{cid}", f"downgrading::{cid}"):
        st.session_state.pop(k, None)
    st.rerun()


def draft_after_downgrade(packet: dict, reason: str, live: bool) -> None:
    """The analyst called the stop a false alarm: the agent drafts a reply and the draft returns for review."""
    cid = packet["complaint_id"]
    st.session_state.override_errors.pop(cid, None)
    cached = None if live else load_override_cache(cid)
    if cached and cached.get("analyst_override"):
        cached["analyst_override"] = {**cached["analyst_override"], "reason": reason}  # keep the cached draft, show this analyst's reason
        st.session_state.overrides[cid] = cached
        return
    try:
        with st.spinner("Downgraded. The agent is drafting a reply now: policy lookup, draft, independent check. About 20-40 seconds."):
            new = pipeline.draft_after_override(packet, reason)
    except Exception as err:  # missing credentials, network, refusal, etc.
        st.session_state.override_errors[cid] = str(err)
        return
    st.session_state.overrides[cid] = new
    try:
        OVERRIDE_DIR.mkdir(parents=True, exist_ok=True)
        (OVERRIDE_DIR / f"{cid}.json").write_text(json.dumps(new, indent=2, default=str), encoding="utf-8")
    except OSError:
        pass  # the cache is a convenience only


def handle_downgrade(packet: dict, reason: str, live: bool):
    cid = packet["complaint_id"]
    if not write_log(packet, "downgrade", override_reason=reason):
        return
    st.session_state.downgrades[cid] = {"reason": reason, "at": datetime.now().strftime("%H:%M")}
    st.session_state.pop(f"downgrading::{cid}", None)
    draft_after_downgrade(packet, reason, live)
    st.rerun()


def reset_demo():
    for k in list(st.session_state.keys()):
        if k.startswith(("editing::", "downgrading::", "text::", "sev::", "reason::", "live::")):
            del st.session_state[k]
    st.session_state.update({"decisions": {}, "downgrades": {}, "overrides": {}, "override_errors": {}, "demo_idx": 0, "open_id": None,
                             "f_disp": "All", "f_outcome": [], "f_risk": [], "f_query": ""})
    st.session_state.q_nonce += 1


def clear_filters():
    st.session_state.update({"f_disp": "All", "f_outcome": [], "f_risk": [], "f_query": ""})


# --------------------------------------------------------------------------------------------------- queue

def queue_frame(complaints: pd.DataFrame, saved: dict) -> pd.DataFrame:
    rows = []
    for i, r in complaints.iterrows():
        cid = r.complaint_id
        packet = (st.session_state.get(f"live::{cid}") or (saved[cid][0] if cid in saved else None))
        outcome = OUTCOME_LABEL.get(packet["status"], "") if packet else "Not run"
        risk = packet["verification"]["risk_tier"] if packet else ""
        rows.append({"complaint_id": cid, "Issue": r.issue, "State": r.state, "Agent outcome": outcome, "Agent risk": risk,
                     "Disposition": disposition_of(cid), "Ground-truth tier": r.ground_truth_risk_tier, "_i": i,
                     "_text": f"{cid} {r.issue} {r.sub_issue} {r.state} {r.narrative}".lower()})
    df = pd.DataFrame(rows)
    df["_d"] = df.Disposition.map({d: n for n, d in enumerate(DISPOSITIONS)}).fillna(9)
    df["_r"] = df["Agent risk"].map(RISK_RANK).fillna(3)
    return df.sort_values(["_d", "_r", "_i"]).reset_index(drop=True)  # what needs the analyst first, riskiest first


def tracker_html(counts: dict, total: int) -> str:
    done = counts["Sent"] + counts["Escalated to Legal / Compliance"]
    open_n = counts["Needs human review"] + counts["Draft ready"]
    seg = "".join(f'<span style="width:{counts[d] / total * 100:.2f}%;background:{DISP_COLOR[d]}"></span>' for d in DISPOSITIONS if counts[d])
    tiles = "".join(
        f'<div class="tile" style="border-top-color:{DISP_COLOR[d]}"><div class="tn">{counts[d]}</div><div class="tl">{esc(d)}</div><div class="th">{esc(DISP_HINT[d])}</div></div>'
        for d in DISPOSITIONS)
    return (f'<div class="tracker"><div class="tracker-top"><div class="tracker-title">Disposition tracker</div>'
            f'<div class="tracker-sub">{done} of {total} dispositioned · {open_n} still in the queue</div></div>'
            f'<div class="seg">{seg}</div><div class="tiles">{tiles}</div></div>')


def next_in_queue(frame: pd.DataFrame, exclude: str | None = None):
    todo = frame[frame.Disposition.isin(["Needs human review", "Draft ready"]) & (frame.complaint_id != exclude)]
    return todo.iloc[0] if len(todo) else None


def queue_view(complaints: pd.DataFrame, saved: dict):
    frame = queue_frame(complaints, saved)
    counts = {d: int((frame.Disposition == d).sum()) for d in DISPOSITIONS}
    total = len(frame)
    st.markdown(tracker_html(counts, total), unsafe_allow_html=True)

    nxt = next_in_queue(frame)
    review_rows = frame[frame.Disposition == "Needs human review"]
    if nxt is None:
        st.markdown('<div class="focus"><b>The queue is clear.</b> Every complaint has been dispositioned.</div>', unsafe_allow_html=True)
    else:
        high = int((review_rows["Agent risk"] == "High").sum())
        st.markdown(
            f'<div class="focus"><b>Agent focus.</b> {counts["Needs human review"]} need your review ({high} high risk) and {counts["Draft ready"]} have a draft waiting. '
            f'Next up: <b>{esc(nxt.complaint_id)}</b> · {esc(nxt.Issue)} · {esc(nxt["Agent risk"])} risk · {esc(nxt.Disposition)}.</div>', unsafe_allow_html=True)
        if st.button("Open next in queue →", type="primary", key="open_next"):
            st.session_state.open_id = nxt.complaint_id
            st.rerun()

    st.markdown('<div class="filters-label">Filter the queue</div>', unsafe_allow_html=True)
    disp = st.segmented_control("Disposition", ["All"] + DISPOSITIONS, key="f_disp", label_visibility="collapsed",
                                format_func=lambda k: f"All ({total})" if k == "All" else f"{k} ({counts[k]})") or "All"
    c1, c2, c3, c4 = st.columns([1.3, 1.1, 2.2, 0.9])
    outcomes = c1.multiselect("Agent outcome", [o for o in ["Draft ready", "Needs human review", "Draft failed checks"] if o in set(frame["Agent outcome"])],
                              key="f_outcome", placeholder="Agent outcome", label_visibility="collapsed")
    risks = c2.multiselect("Agent risk", ["High", "Medium", "Low"], key="f_risk", placeholder="Agent risk", label_visibility="collapsed")
    query = c3.text_input("Search", key="f_query", placeholder="Search by ID, issue or complaint text", label_visibility="collapsed")
    # Streamlit applies a text box only on Enter or blur. This small script applies it as you type or clear it, so the list always matches the box.
    st.iframe("""<script>
    const doc = window.parent.document;
    function attach() {
      const el = doc.querySelector('input[placeholder^="Search by ID"]');
      if (!el || el.dataset.liveSearch) return;
      el.dataset.liveSearch = "1";
      let timer;
      el.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(() => el.dispatchEvent(new KeyboardEvent("keydown", {key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true})), 450);
      });
    }
    attach();
    new MutationObserver(attach).observe(doc.body, {childList: true, subtree: true});
    </script>""", height=1)  # trusted, static script of our own; st.iframe replaces the deprecated components.html
    c4.button("Clear filters", on_click=clear_filters, width="stretch")

    view = frame
    if disp != "All":
        view = view[view.Disposition == disp]
    if outcomes:
        view = view[view["Agent outcome"].isin(outcomes)]
    if risks:
        view = view[view["Agent risk"].isin(risks)]
    if (query or "").strip():
        q = query.strip().lower()
        view = view[view["_text"].str.contains(q, regex=False)]
    view = view.reset_index(drop=True)

    st.markdown(f'<div class="tracker-sub" style="margin:8px 0 6px">Showing {len(view)} of {total} complaints. Click the checkbox at the left of a row to open it.</div>', unsafe_allow_html=True)
    if view.empty:
        st.markdown('<div class="empty"><div class="t">No complaints match these filters</div><div class="muted">Use Clear filters to see the full queue again.</div></div>', unsafe_allow_html=True)
        return
    cols = ["complaint_id", "Issue", "State", "Agent outcome", "Agent risk", "Disposition"]
    if st.session_state.get("show_truth"):
        cols.append("Ground-truth tier")
    table = view[cols].rename(columns={"complaint_id": "Complaint"})
    tint = {"Needs human review": "background-color:#fde6ee;color:#a3123f", "Draft ready": "background-color:#e9e7ff;color:#4434d4",
            "Escalated to Legal / Compliance": "background-color:#fbf0dc;color:#9b6829", "Sent": "background-color:#dff5ea;color:#13694a"}
    risk_tint = {"High": "color:#a3123f;font-weight:600", "Medium": "color:#9b6829", "Low": "color:#273951"}
    styled = table.style.map(lambda v: tint.get(v, ""), subset=["Disposition"]).map(lambda v: risk_tint.get(v, ""), subset=["Agent risk"])
    sig = abs(hash((disp, tuple(outcomes), tuple(risks), (query or "").strip().lower())))  # a new key resets any stale row selection
    event = st.dataframe(styled, hide_index=True, width="stretch", height=min(560, 38 + 35 * len(table)), on_select="rerun",
                         selection_mode="single-row", key=f"queue::{st.session_state.q_nonce}::{sig}")
    if event.selection.rows:
        st.session_state.open_id = view.complaint_id[event.selection.rows[0]]
        st.rerun()


# --------------------------------------------------------------------------------------------------- panels

def decision_panel(packet: dict, stopped: bool, live: bool):
    cid = packet["complaint_id"]
    done = st.session_state.decisions.get(cid)
    with st.container(key="decision"):
        if done:
            where = "Saved to the audit log." if done["logged"] else "Not written to the audit log (logging is off)."
            sim = " Simulated: nothing was delivered." if done["decision"] in ("approve", "edit") else ""
            st.markdown(
                '<div class="dk">Decision recorded</div>'
                f'<div class="recorded"><b>{esc(DECISION_LABEL.get(done["decision"], done["decision"]))}</b> at {esc(done["at"])}. {where}{sim}</div>',
                unsafe_allow_html=True)
            if st.button("Record a different decision", key=f"redo::{cid}"):
                st.session_state.decisions.pop(cid, None)
                st.rerun()
            return
        if stopped:
            down = st.session_state.downgrades.get(cid)
            if down:  # downgraded, but the agent could not produce the draft yet
                st.markdown('<div class="dk">Downgraded</div><div class="dt">The draft is not ready</div>'
                            f'<div class="ds">The agent could not draft a reply: {esc(st.session_state.override_errors.get(cid, "unknown problem"))}</div>', unsafe_allow_html=True)
                if st.button("Try drafting again", type="primary", key=f"retry::{cid}", width="stretch"):
                    draft_after_downgrade(packet, down["reason"], live)
                    st.rerun()
            else:
                st.markdown('<div class="dk">Your decision</div><div class="dt">Escalate it, or clear a false alarm</div>'
                            '<div class="ds">The agent does not escalate on its own. If you downgrade it, the agent drafts a reply for you to review.</div>', unsafe_allow_html=True)
                if st.button("Escalate to Legal / Compliance", type="primary", key=f"legal::{cid}", width="stretch"):
                    record_decision(packet, "escalate_to_legal_compliance")
                if st.button("Downgrade (false alarm)", key=f"down::{cid}", width="stretch"):
                    st.session_state[f"downgrading::{cid}"] = True
                if st.session_state.get(f"downgrading::{cid}"):
                    reason = st.text_input("One-line reason for downgrading (required)", key=f"reason::{cid}")
                    if st.button("Downgrade and draft a reply", type="primary", key=f"submitdown::{cid}", disabled=not reason.strip()):
                        handle_downgrade(packet, reason.strip(), live)
            return
        st.markdown('<div class="dk">Your decision</div><div class="dt">Review before anything is sent</div>'
                    '<div class="ds">Approve sends the reply (simulated in this prototype). Edit changes it first. Escalate routes it to Legal / Compliance.</div>', unsafe_allow_html=True)
        if st.button("Approve and send", type="primary", key=f"approve::{cid}", width="stretch"):
            record_decision(packet, "approve")
        b, c = st.columns(2)
        if b.button("Edit", key=f"edit::{cid}", width="stretch"):
            st.session_state[f"editing::{cid}"] = True
        if c.button("Escalate", key=f"esc::{cid}", width="stretch"):
            record_decision(packet, "escalate")
        if st.session_state.get(f"editing::{cid}"):
            text = st.text_area("Edit the draft", value=(packet.get("draft") or {}).get("draft_text", ""), height=320, key=f"text::{cid}")
            severity = st.radio("How substantial is the edit? (required)", ["Minor", "Substantive"], index=None, horizontal=True, key=f"sev::{cid}")
            if st.button("Save edit and send", type="primary", key=f"save::{cid}", disabled=severity is None):
                record_decision(packet, "edit", edit_severity=severity, draft_text=text)


def verifier_card(packet: dict) -> str:
    ver = packet.get("verifier") or {}
    if not ver:
        return ""
    rows = ""
    for key, label in CHECK_LABEL.items():
        if key in ver:
            ok = str(ver[key]).strip().lower().startswith("pass")
            rows += f'<div class="check"><div class="dot {"dot-ok" if ok else "dot-bad"}">{"✓" if ok else "!"}</div><div>{esc(label)}</div></div>'
    issues = "".join(f"<li>{esc(i)}</li>" for i in (ver.get("specific_issues") or []))
    extra = f'<div class="small" style="margin-top:10px"><b>Verifier notes</b><ul>{issues}</ul></div>' if issues else ""
    badge = pill("Passed", "ok") if ver.get("overall_result") == "pass" else pill("Failed", "ruby")
    return card("Independent check", f'<div style="margin-bottom:8px">{badge}</div>{rows}{extra}')


def render_packet(packet: dict, source: str, live: bool):
    cid = packet["complaint_id"]
    complaint = packet["complaint"]
    v = packet["verification"]
    status = packet["status"]
    stopped = status == "escalated"
    failed = status == "draft_failed_verification"
    ex = packet.get("extraction") or {}
    pkg = packet.get("escalation_package") or {}
    override = packet.get("analyst_override")
    headline, kind = plain_headline(packet)
    date = pretty_date((complaint.get("date_received") or "")[:10])
    disp = disposition_of(cid)

    flags = [f"“{p}”" for p in (ex.get("risk_signal_phrases") or [])] + [f"Embedded instruction: “{p}”" for p in (ex.get("suspicious_embedded_instructions") or [])]
    flag_html = "".join(f'<span style="margin-right:6px">{pill(f, "ruby")}</span>' for f in flags)
    # always open at the top of the page, not wherever the queue was scrolled to (the cid in the script makes it run once per case)
    st.iframe(f"""<script>/* {esc(cid)} */
    const d = window.parent.document;
    const go = () => {{ d.querySelectorAll('[data-testid="stMain"], [data-testid="stAppViewContainer"], section.main').forEach(e => e.scrollTo(0, 0)); window.parent.scrollTo(0, 0); }};
    go(); setTimeout(go, 150); setTimeout(go, 500);
    </script>""", height=1)  # trusted, static script of our own
    # 1. which case, and what the agent found: the headline, the status pills and the five-step check
    st.markdown(
        f'<div class="packet-id">{esc(cid)} &nbsp;·&nbsp; {esc(complaint.get("issue"))} &nbsp;·&nbsp; {esc(date)} &nbsp;·&nbsp; {esc(complaint.get("state"))}</div>'
        '<div class="section-label">What the agent found</div>'
        f'<div class="headline {kind if kind != "ok" else ""}">{esc(headline)}</div>'
        f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px">{pill(disp, DISP_PILL.get(disp, "calm"))}{tier_pill(v.get("risk_tier", ""))}{verdict_pill(v.get("fact_verification", ""))}</div>',
        unsafe_allow_html=True)
    st.markdown(steps_html(packet), unsafe_allow_html=True)
    # 2. then what the customer said, in their own words
    st.markdown(
        f'<div class="said"><div class="sl2">What the customer said</div><p class="q">{esc(complaint.get("narrative"))}</p>'
        + (f'<div class="meta2">{flag_html}</div>' if flag_html else "") + '</div>',
        unsafe_allow_html=True)
    # 3. then where it stopped and why, or the draft, beside the decision

    left, right = st.columns([1.5, 1], gap="large")
    with left:
        if override:
            st.markdown(card("The agent stopped this complaint, and you downgraded it",
                             f'<p style="margin:0 0 6px"><b>Original stop:</b> {esc(first_sentence(override.get("original_stop_reason") or "", 260))}</p>'
                             f'<p style="margin:0"><b>Your reason:</b> {esc(override.get("reason"))}</p>', "soft"), unsafe_allow_html=True)
        if stopped:
            trig = pkg.get("trigger")
            trig_html = "".join(f"<div>{esc(t.get('detail'))}</div>" for t in trig) if isinstance(trig, list) else ""
            st.markdown(f'<div class="banner"><div class="k">Stopped before drafting</div><div class="t">{esc(v.get("stop_reason") or packet.get("pipeline_error"))}</div>'
                        f'<div class="why">{trig_html}</div></div>', unsafe_allow_html=True)
            if pkg.get("unresolved"):
                st.markdown(card("What is missing or unresolved", f'<p style="margin:0">{esc(first_sentence(pkg["unresolved"], 420))}</p>', "ruby"), unsafe_allow_html=True)
            st.markdown(card("No draft was prepared", f'<p class="muted" style="margin:0">{esc(pkg.get("agent_actions_taken", "Analysis only. Nothing was drafted, sent, or escalated."))}</p>', "soft"), unsafe_allow_html=True)
        else:
            attempts = packet.get("attempts") or []
            if failed and len(attempts) > 1:
                st.markdown(card("Needs your attention", '<p style="margin:0">The agent could not produce a draft that passed the independent check in two tries. Both attempts and the checker\'s objections are shown; edit, or escalate.</p>', "cream"), unsafe_allow_html=True)
                tabs = st.tabs([f"Attempt {a['attempt']}" for a in attempts])
                for tab, a in zip(tabs, attempts):
                    with tab:
                        st.markdown(f'<div class="paper"><div class="paper-head"><div class="meta">Draft reply · not sent</div></div><div class="paper-body">{paragraphs(a["draft"]["draft_text"])}</div></div>', unsafe_allow_html=True)
            else:
                draft = packet.get("draft") or {}
                sent = disp == "Sent"
                st.markdown(
                    f'<div class="paper"><div class="paper-head"><div class="meta">Draft reply · <b>{"sent (simulated)" if sent else "not sent"}</b> · {esc(draft.get("policy_cited", ""))}</div>{pill("Sent" if sent else "Proposal", "green" if sent else "indigo")}</div>'
                    f'<div class="paper-body">{paragraphs(draft.get("draft_text", ""))}</div></div>', unsafe_allow_html=True)
            action = packet.get("action_required_before_sending")
            if action:
                st.markdown(card("Before you send this", f'<p style="margin:0">{esc(action)}</p>', "cream"), unsafe_allow_html=True)
    with right:
        decision_panel(packet, stopped, live)
        if not stopped:
            st.markdown(verifier_card(packet), unsafe_allow_html=True)

    t_customer, t_records, t_policy, t_run = st.tabs(["Allegations", "What the records show", "Policy", "Run details"])
    with t_customer:
        allegations = "".join(f"<li>{esc(a)}</li>" for a in ex.get("allegations", []))
        outcome = ex.get("requested_outcome")
        st.markdown(card("Allegations the agent extracted", f"<ul>{allegations}</ul>" + (f'<p class="muted small" style="margin:10px 0 0">Customer wants: {esc(outcome)}</p>' if outcome else "")), unsafe_allow_html=True)
    with t_records:
        c1, c2 = st.columns(2, gap="large")
        c1.markdown(card("What the records show", f'<p style="margin:0 0 12px">{esc(v.get("fact_verification_explanation"))}</p>{verdict_pill(v.get("fact_verification", ""))}'), unsafe_allow_html=True)
        c2.markdown(card("Why this risk tier", f'<p style="margin:0 0 12px">{esc(v.get("risk_rationale"))}</p>{tier_pill(v.get("risk_tier", ""))}'), unsafe_allow_html=True)
        ev = packet.get("evidence") or {}
        acct = ev.get("account") or {}
        if acct.get("found"):
            st.markdown(f'**Account** {esc(acct.get("account_id"))} · {esc(acct.get("product_type"))} · status {esc(acct.get("payment_status"))} · balance ${acct.get("loan_balance"):,.2f} · opened {esc(acct.get("origination_date") or "n/a")}', unsafe_allow_html=True)
        txns = ev.get("transactions") or []
        if txns:
            df = pd.DataFrame(txns)[["date", "type", "amount", "note"]]
            st.dataframe(df, hide_index=True, width="stretch", column_config={"amount": st.column_config.NumberColumn("amount", format="$%.2f")})
        else:
            st.caption("No transactions on file.")
    with t_policy:
        policy = packet.get("policy") or pkg.get("policy_reference") or {}
        if policy:
            tag = pill(f'Policy {policy.get("policy_id")}', "navy")
            fallback = ' <span class="muted small">(general fallback: no more specific policy matched)</span>' if policy.get("fallback_used") else ""
            st.markdown(card("Policy applied", f'<p style="margin:0 0 8px"><b>{esc(policy.get("topic"))}</b> {tag}{fallback}</p><p class="muted" style="margin:0">{esc(clean_markdown(policy.get("text", ""), 700))}</p>'), unsafe_allow_html=True)
            with st.expander("Read the full policy"):
                st.text(policy.get("text", ""))
        else:
            st.caption("No policy was applied.")
    with t_run:
        calls = packet.get("llm_calls") or []
        guards = (v.get("code_overrides") or [])
        st.markdown(
            card("How this packet was produced",
                 f'<p style="margin:0 0 6px">Source: {esc(source)} · model {esc(packet.get("model"))}</p>'
                 f'<p style="margin:0 0 6px">{len(calls)} model calls · {sum(c.get("input_tokens") or 0 for c in calls):,} tokens in · {sum(c.get("output_tokens") or 0 for c in calls):,} tokens out</p>'
                 + (f'<p class="muted small" style="margin:0">Safety guards that changed the model\'s answer: {esc("; ".join(guards))}</p>' if guards else
                    '<p class="muted small" style="margin:0">No safety guard needed to change the model\'s answer.</p>')),
            unsafe_allow_html=True)


# -------------------------------------------------------------------------------------------- scorecard tab

def bar_html(frac: float, line: float | None = None) -> str:
    marker = f'<div class="line" style="left:{line * 100:.0f}%"></div>' if line is not None else ""
    return f'<div class="bar"><i style="width:{max(0, min(1, frac)) * 100:.1f}%"></i>{marker}</div>'


def render_scorecard():
    sc = load_scorecard()
    st.markdown('<div class="section-title">How well does it work?</div>', unsafe_allow_html=True)
    if not sc:
        st.info("No full evaluation run has been saved yet. Run python eval/run_evals.py to create one.")
        return
    e1, e2, e3, e4, rv = sc["e1"], sc["e2"], sc["e3"], sc["e4"], sc["review"]
    st.markdown(f'<div class="section-sub">Scored against {sc["n"]} hand-labeled complaints. Latest full run: {esc(sc["run"])}.</div>', unsafe_allow_html=True)

    def status(ok: bool) -> str:
        return pill("Passes", "ok") if ok else pill("Short of the bar", "amber")

    missed3 = [c for c, t, g in e3["results"] if t != g]
    missed3_txt = "; ".join(f"{c}: labeled {VERDICT_LABEL.get(t, t).lower()}, the agent said {VERDICT_LABEL.get(g, g).lower()}" for c, t, g in e3["results"] if t != g)
    cards = [
        ("Risk rating", f'{e1["correct"]}<small>of {e1["n"]} right</small>', bar_html(e1["accuracy"], e1["bar"]),
         f'The agent rated Low, Medium or High the same as the labeled answer. Pass line: {e1["bar"]:.0%} (marked). Medium or High cases rated Low: {len(e1["to_low"])}.', status(e1["pass"])),
        ("Stops when it should", f'{e2["caught"]}<small>of {e2["n_should"]} stopped</small>', bar_html(e2["caught"] / e2["n_should"] if e2["n_should"] else 0, 1.0),
         f'Complaints that must go to a person (attorney, regulator, identity theft, and others) were all stopped. It also stopped {len(e2["false_stops"])} that were not labeled to escalate, mostly by design (hidden instructions, missing evidence).', status(e2["pass"])),
        ("Reads the records correctly", f'{e3["correct"]}<small>of {e3["n"]} right</small>', bar_html(e3["correct"] / e3["n"] if e3["n"] else 0, 1.0),
         "Whether the claim is confirmed true, false, partly true, or can't be verified, compared with the labeled answer. The bar is every case." + (f" Missed: {missed3_txt}." if missed3 else ""), status(e3["pass"])),
        ("Resists hidden instructions", f'{sum(c["result"] == "pass" for c in e4["cases"])}<small>of {len(e4["cases"])} resisted</small>', bar_html(sum(c["result"] == "pass" for c in e4["cases"]) / max(1, len(e4["cases"])), 1.0),
         "Complaints that try to tell the system what to do: the agent flagged the instruction, did not follow it, and still checked the account.", status(e4["pass"])),
    ]
    html_cards = "".join(f'<div class="score"><div class="st">{esc(t)}</div><div class="big">{big}</div>{bar}<div class="what">{esc(what)}</div>{badge}</div>' for t, big, bar, what, badge in cards)
    st.markdown(f'<div class="score-grid">{html_cards}</div>', unsafe_allow_html=True)

    newest = sc.get("newest")
    if rv:
        c = rv["counts"]
        tot = rv["total"]
        seg = (f'<div class="mini-seg"><span style="width:{c["Approve"] / tot * 100:.1f}%;background:#533afd"></span>'
               f'<span style="width:{c["Minor"] / tot * 100:.1f}%;background:#b9b9f9"></span>'
               f'<span style="width:{c["Substantive"] / tot * 100:.1f}%;background:#ea2261"></span></div>')
        newest_note = ""
        if newest and newest["run"] != rv["run"]:
            newest_note = (f' The newest full run ({esc(newest["run"])}) has {newest["drafts"]} drafts, {newest["total"]} reviewed so far. '
                           f'Tag them in eval/results/{esc(newest["run"])}/drafts_for_review.csv to update this card.')
        body = (f'<p style="margin:0 0 6px">A person reviewed {tot} of the {rv["drafts"]} drafts from {esc(rv["run"])}: <b>{c["Approve"]}</b> approved as written, <b>{c["Minor"]}</b> needed minor edits, <b>{c["Substantive"]}</b> needed substantive edits.</p>{seg}'
                f'<p class="muted small" style="margin:0">This is the most complete review so far.{newest_note}</p>')
    else:
        body = '<p style="margin:0">Draft quality is judged by a person: tag each draft Approve, Minor or Substantive in the review sheet. Not reviewed yet.</p>'
    st.markdown(card("Draft quality (judged by a person)", body), unsafe_allow_html=True)

    cost = f"about ${sc['cost']:.2f}" if sc.get("cost") is not None else "a few dollars"
    st.markdown(card("Read this honestly",
                     '<ul><li>The prompts and labels were adjusted over several runs against these same complaints, so these results show the design fits this set, not that it generalizes. Fresh held-out cases are the next step.</li>'
                     '<li>Each score is from a single run, and the agent has changed its answer on the same complaint between runs.</li>'
                     '<li>The data is synthetic, and nothing is connected to a real account or sent to a customer.</li>'
                     f'<li>A full run over these complaints costs {cost}.</li></ul>', "cream"), unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------------ sidebar

complaints = load_complaints()
saved = load_saved_packets()
with st.sidebar:
    st.markdown(f'<div class="brand">{logo_svg(30)}<div class="brand-name">{PRODUCT}</div></div>'
                f'<div class="side-note">Signed in as <b>{ANALYST_NAME}</b>, {ANALYST_ROLE.lower()}. The agent prepares; you decide.</div>', unsafe_allow_html=True)
    if os.environ.get("ANTHROPIC_API_KEY"):
        st.markdown('<div class="side-label">Presenter options</div>', unsafe_allow_html=True)
        live = st.toggle("Run the pipeline live", value=False, help="Calls the model for the selected complaint (and for a downgrade's draft): about $0.05 and 30-60 seconds. Off shows saved results instantly.")
        st.session_state["write_log"] = st.toggle("Write decisions to the audit log", value=True, help="Appends a row to data/case_log.csv for every decision. Turn off for rehearsals.")
        st.session_state["show_truth"] = st.toggle("Show ground-truth tier in the queue (testing)", value=False)
    else:
        # A shared, hosted copy has no API key: it only replays saved results, so nobody can run up a bill, and visitors' decisions are not written to a shared log.
        live = False
        st.session_state["write_log"] = False
        st.session_state["show_truth"] = False
        st.markdown('<div class="side-note">Shared demo: it replays saved results. Your decisions last for this session only.</div>', unsafe_allow_html=True)
    if st.button("Reset demo", width="stretch", help="Returns every complaint to its starting disposition and clears this session's decisions."):
        reset_demo()
        st.rerun()
    st.markdown(f'<div class="side-note" style="margin-top:18px">Model: {esc(pipeline.MODEL)}<br>Demo-safe synthetic data. "Sent" is simulated: nothing is ever delivered.</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------------------------ main

st.markdown(
    f'<div class="hero slim"><div class="topbar"><div class="tb-brand">{logo_svg(34)}<span class="tb-name">{PRODUCT}</span><span class="tb-tag">Complaint review workspace</span></div>'
    f'<div class="tb-user"><div class="tb-who"><div class="tb-n">{ANALYST_NAME}</div><div class="tb-r">{ANALYST_ROLE}</div></div><div class="avatar">{ANALYST_NAME[:1]}</div></div></div>'
    '<h1>Complaint queue</h1>'
    '<p class="lead">Everything that has come in and needs a disposition. The agent has already read, checked and drafted; you decide.</p></div>', unsafe_allow_html=True)

tab_review, tab_score = st.tabs(["Queue", "How well does it work?"])

with tab_review:
    open_id = st.session_state.open_id
    if open_id:
        frame = queue_frame(complaints, saved)
        total = len(frame)
        pos = int(frame.index[frame.complaint_id == open_id][0]) + 1 if (frame.complaint_id == open_id).any() else 0
        nxt = next_in_queue(frame, exclude=open_id)

        def case_nav(where: str):
            """The two navigation buttons; shown above the case and again below it, so nobody has to scroll back up."""
            with st.container(horizontal=True, gap="small"):  # a wrapping row: at narrow widths the second button drops below instead of overlapping the first
                if st.button("← Back to queue", key=f"back_queue_{where}"):
                    st.session_state.open_id = None
                    st.session_state.q_nonce += 1  # a fresh table, so the row you opened is not still selected
                    st.rerun()
                if st.button("Next needing attention →", key=f"next_attention_{where}", disabled=nxt is None):
                    st.session_state.open_id = nxt.complaint_id
                    st.rerun()

        case_nav("top")
        packet, source = active_packet(open_id, live)
        if packet is None:
            st.info("There is no saved result for this complaint yet. Turn on “Run the pipeline live” in the sidebar to generate one.")
        else:
            render_packet(packet, source, live)
            st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)
            case_nav("bottom")
    else:
        mode = st.segmented_control("View", ["Queue", "Guided demo"], default="Queue", key="mode", label_visibility="collapsed") or "Queue"
        if mode == "Queue":
            queue_view(complaints, saved)
        else:
            path = [d for d in DEMO_PATH if d[0] in set(complaints.complaint_id)]
            idx = min(st.session_state.demo_idx, len(path) - 1)
            st.markdown('<div class="demo-label">Demo path: six cases, in order</div>', unsafe_allow_html=True)
            chips = st.columns(len(path))
            for i, (_, label, _) in enumerate(path):
                if chips[i].button(f"{i + 1} · {label}", key=f"chip{i}", type="primary" if i == idx else "secondary", width="stretch"):
                    st.session_state.demo_idx = i
                    st.rerun()
            cid, label, why = path[idx]
            st.markdown(f'<div class="notice"><b>What to notice.</b> {esc(why)}</div>', unsafe_allow_html=True)
            back, nxt_btn, _ = st.columns([1, 1.3, 6])
            if back.button("← Back", key="back", disabled=idx == 0):
                st.session_state.demo_idx = idx - 1
                st.rerun()
            if nxt_btn.button("Next case →", key="next", type="primary", disabled=idx == len(path) - 1):
                st.session_state.demo_idx = idx + 1
                st.rerun()
            packet, source = active_packet(cid, live)
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            if packet is None:
                st.info("There is no saved result for this complaint yet. Turn on “Run the pipeline live” in the sidebar to generate one.")
            else:
                render_packet(packet, source, live)

with tab_score:
    render_scorecard()

st.markdown('<div class="footer">Prototype built on synthetic, demo-safe data. The agent proposes; a person reviews every draft and every escalation.</div>', unsafe_allow_html=True)
