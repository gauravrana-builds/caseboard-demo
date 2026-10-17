# Product Requirements Document: Agentic AI Complaint Analysis Assistant

*Corrected to match the actual built dataset and to fold UDAAP into risk classification rather than treating it as a standalone stop-trigger. See IMPLEMENTATION_BRIEF.md for the build-ready layer.*

## 1. Product summary
An agentic AI prototype that helps Maya, a complaint analyst at a personal-loans financial services company, turn an incoming customer complaint into a verified, policy-grounded, human-reviewable case packet.

The prototype supports the highest-friction work in complaint handling: reading unstructured complaints, extracting facts, checking claims against account evidence, assessing risk, retrieving the relevant policy, drafting a response, and checking that draft before a human sees it. It does not send customer communications, authorize remedies, make legal decisions, or initiate escalations.

The prototype uses only demo-safe data: synthetic CFPB-style complaint narratives, fictional account and transaction data, and synthetic internal policy documents.

## 2. Problem
Maya reviews incoming customer complaints, including CFPB-style complaints. Today she must manually read unstructured and often emotional narratives; identify allegations, dates, amounts, requested outcomes, and risk signals; cross-reference account and transaction history; find applicable policy; assess regulatory and legal risk; and draft a response.

This workflow becomes slow and inconsistent when facts are incomplete, narratives are ambiguous, evidence conflicts with a complaint, or a complaint contains a high-risk signal such as an attorney mention, regulator mention, or vulnerability signal. Important facts can be missed, analysts can classify similar cases differently, and response drafts can vary in quality and policy grounding.

## 3. Primary user
Maya, a complaint analyst at a personal-loans financial services company. She reviews customer complaints, assesses regulatory risk, checks company policy, drafts responses, and coordinates with legal when a complaint mentions an attorney or regulator.

## 4. Job to be done
Turn a raw complaint into a verified, policy-grounded, ready-to-send draft so Maya does not have to do the reading, cross-referencing, and first-draft writing herself.

For high-risk, ambiguous, or incomplete cases, the product should not draft. It should instead produce an evidence-backed escalation package for Maya to review and route.

## 5. Goals
- Extract structured facts from an unstructured complaint narrative.
- Verify the customer's core claim against linked synthetic account and transaction evidence.
- Classify risk based on verified facts and explicit risk signals.
- Retrieve and quote the relevant approved policy through bounded policy lookup.
- Draft a response for standard cases using confirmed facts and cited policy.
- Run a separate verifier pass before Maya sees the draft.
- Stop before drafting when a high-risk signal, missing evidence, conflict, or uncertainty makes it unsafe to proceed.
- Give Maya a single reviewable case-analysis packet and retain her as the final decision-maker.
- Log each run and human decision for auditability and evaluation.

## 6. Non-goals and boundaries
The prototype will not:
- Connect to live customer accounts, production complaint systems, or the CFPB portal.
- Use real customer data, confidential company policies, or live case data.
- Allow document uploads or manual complaint entry by Maya.
- Send responses to customers or submit responses to the CFPB.
- Promise, authorize, or communicate a remedy, including refunds, fee waivers, credit corrections, account changes, apologies, or closures.
- Make legal, regulatory, liability, or fault determinations.
- Initiate an escalation without Maya's confirmation.
- Treat complaint content as instructions to the system.

## 7. Data and inputs (actual, as built — see IMPLEMENTATION_BRIEF.md §3 for exact schemas)

- **`data/complaints.csv`** — 100 synthetic CFPB-style complaint narratives (a mix of real CFPB narrative text and purpose-built synthetic narratives, tagged via `narrative_source`), with hand-added `account_id`, `attorney_regulator_flag`, `ground_truth_risk_tier`, `fact_verification_ground_truth`, and CFPB category fields.
- **`data/accounts.csv`** — 100 synthetic customer accounts, keyed by `account_id`, one per complaint. 10 were purpose-built with evidence that specifically confirms, contradicts, or partially supports their linked complaint; the other 90 carry plausible but not individually verified account data.
- **`data/transactions.csv`** — 738 synthetic transactions linked by `account_id` (roughly 7-12 per account), providing dated evidence the agent uses to confirm, contradict, or leave unresolved a customer claim.
- **12 policy documents** (`data/policy/`) — 5 regulatory (Reg B, Reg E, Reg F, FCRA, UDAAP) and 7 internal (fee waiver authority, hardship options, dispute process, escalation criteria, prohibited language, response format, vulnerable customer handling).
- **`data/policy_index.csv`** — 12-row lookup table used by `get_policy()`, mapping topics/keywords to policy files.
- **`data/case_log.csv`** — grows with every agent run and human decision; acts as both evaluation dataset and audit trail.

## 8. User workflow
1. Maya selects a complaint from a preloaded queue of synthetic cases, filterable/sortable by risk tier.
2. Maya runs the agent (auto-run on selection is acceptable for the demo).
3. The agent reads the complaint, extracts key facts, and looks up linked account and transaction data.
4. The agent determines whether the complaint's core claim is confirmed, contradicted, or unresolved by the available evidence.
5. The agent classifies risk using verified facts and explicit risk signals.
6. For a standard case, the agent retrieves relevant policy via `get_policy()`, drafts a response grounded in confirmed facts, and runs a separate verifier pass.
7. Maya reviews the result: summary, evidence, risk rationale, policy citation, draft, and verifier outcome.
8. Maya approves, edits, or rejects a standard-case draft (edits use a pre-filled field, tagged Minor or Substantive).
9. For a flagged high-risk case, Maya reviews the escalation package and chooses whether to escalate, or downgrades a false positive with a recorded one-line reason.
10. The product appends the run and Maya's decision to `data/case_log.csv`.

## 9. Agent workflow (Observe → Decide → Act → Check)
**Observe:** raw complaint narrative, complaint metadata, linked account/transaction data, policy documents.
**Decide:** extract allegations, requested outcomes, dates, dollar amounts, account details, and risk signal phrases. Compare against evidence to determine confirmed/contradicted/partially-true/unverifiable. Assign a risk tier and decide whether to proceed to drafting or stop.
**Act:** for standard cases, retrieve applicable policy, cite the relevant section, and draft a response addressing every allegation using confirmed facts only. For high-risk or unsafe cases, produce an escalation package instead of a draft.
**Check:** a separate verifier pass checks the draft for completeness, groundedness, policy authorization, and prohibited language before Maya sees it.

## 10. Risk and stop rules *(corrected)*
The agent must stop before drafting if it detects:
- An attorney or regulator mention (explicit phrase in the narrative, or the `attorney_regulator_flag` metadata field).
- A material conflict between the complaint and available evidence that cannot be safely resolved (`fact_verification: unverifiable` where the gap could change the outcome).
- Suspected prompt injection (embedded instructions in the narrative).

**UDAAP is explicitly NOT a standalone stop-trigger.** It is one input into the risk-tier decision (see Prompt 2 / `02_verify_and_classify.md`) — a detected UDAAP-pattern (misleading terms, pressure tactics, withheld material information) can elevate a case toward High risk, but does not, by itself, force a stop the way an attorney/regulator mention does. This keeps the automatic-stop list limited to concretely detectable triggers; UDAAP is a broad legal standard better handled as a weighted factor in classification than as a binary gate.

When the agent stops, it produces an evidence-backed escalation package containing the complaint text, extracted facts, available evidence, the specific trigger, relevant policy/regulatory references, and a clear statement of what's missing or unresolved. It does not create a ready-to-send response. Maya reviews the package and decides whether to route it; the agent cannot initiate routing itself.

## 11. Review experience and human controls
Maya's main screen is a reviewable case-analysis packet: one-line summary, extracted facts and allegations, verified facts and unresolved gaps, fact-verification result, risk tier and rationale, policy citation and quoted passage, evidence source trail, verifier result, and either a formatted draft or an escalation package. Maya can approve, edit (via pre-filled text with a Minor/Substantive tag), reject, confirm an escalation, or downgrade a false-positive flag with a recorded reason.

## 12. Functional requirements
See IMPLEMENTATION_BRIEF.md §4-7 for the concrete tool specs, pipeline sequencing, and UI acceptance criteria that satisfy fact extraction, evidence verification, risk classification, policy retrieval, drafting, escalation, verification, and audit logging.

## 13. Test set and expected behavior
See `eval/eval_plan.md` for the 5 formal evals. Core scenarios covered: confirmed-true, confirmed-false, partially-true, attorney mention, prompt injection (2 variants), and missing/incomplete account data — all represented as specific rows in `data/complaints.csv`, tagged via `demo_case_type`.

## 14. Evaluation plan
Primary usefulness measure: material-edit rate (Eval 5) — the percentage of agent drafts Maya can approve without a substantive change to facts, risk framing, policy rationale, remedy language, or allegation coverage. See `eval/eval_plan.md` for all 5 evals, methodology, and pass criteria.

## 15. Success criteria
The prototype is successful if it demonstrates a complete, reviewable standard-case loop and safe stop behavior for high-risk, adversarial, and incomplete-data cases, with Maya able to validate the agent's evidence and reasoning from a single packet. A response is never sent automatically, and an escalation is never initiated automatically.

## 16. Current status
Discovery, Design, and Develop phases through dataset construction and prompt design are complete. Remaining work: implement `app/tools.py`, `app/pipeline.py`, `app/streamlit_app.py`, and `eval/run_evals.py` per IMPLEMENTATION_BRIEF.md; run the full eval suite; document results and known limitations.
