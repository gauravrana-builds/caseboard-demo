# Caseboard (Complaint Agent) — Capstone Build

## Read these in order
1. `PRD.md`                   — product requirements (Discovery/Design/Develop context)
2. `IMPLEMENTATION_BRIEF.md`  — the build-ready spec and current status: schemas, tools, pipeline, UI, build order, eval results
3. `prompts/`                 — the 4 actual system prompts the pipeline calls, in sequence
4. `eval/eval_plan.md`        — 5 evals, methodology and pass criteria

## Folder structure
- data/               — complaints (26), accounts (26), transactions (138), 12 policy docs, policy_index, case_log (empty)
  - data/proposed/    — staging for the batch-1 evidence drafts and review doc (already merged into the CSVs)
  - data/backup_before_batch1_*/ — the original 100-complaint data (complaints, accounts, transactions)
- prompts/            — 4 system prompts: extraction, verify+classify, drafting, verifier
- app/                — tools.py, pipeline.py, streamlit_app.py (the review UI) and ui_theme.py (its look and feel), plus test_tools.py, test_log_case.py and test_pipeline_offline.py
- eval/               — eval_plan.md, run_evals.py (built), test_run_evals_offline.py, results/ (one folder per run)
- capstone_dataset.xlsx — human labeling workspace; not read by the app and still shows the original 100 complaints (data/*.csv are the flat exports the app reads)

## Quick start (run from this folder)
Needs Python 3.11+, `pip install pandas anthropic`, and `ANTHROPIC_API_KEY` set in your environment.

```
python app/test_tools.py              # tools against the real CSVs (no API cost)
python app/test_pipeline_offline.py   # pipeline logic with a stubbed model (no API cost)
python eval/test_run_evals_offline.py # eval harness with a stubbed model (no API cost)

python app/pipeline.py SYN-F01        # one complaint through the real pipeline (about $0.05)
python eval/run_evals.py              # score all complaints (about $1.40; asks before spending)

python -m streamlit run app/streamlit_app.py   # the review UI (saved results are instant; live mode costs about $0.05 a complaint)
python app/pregenerate_downgrade_drafts.py     # prepare the replies shown when a stopped case is downgraded (about $0.60; already done)
```

The default model is `claude-sonnet-5-5`; set `COMPLAINT_AGENT_MODEL` to use another.

## Status
Built: tools (including log_case), pipeline, eval harness, and the Streamlit review UI.
Latest full eval run: `eval/results/run_20261008_130001/` (Evals 1, 2 and 4 pass; Eval 3 misses one case; Eval 5 needs the reviewer's tags). Results and open decisions are in IMPLEMENTATION_BRIEF.md section 10.

## For Claude Code
Read IMPLEMENTATION_BRIEF.md in full first. Follow the build order in its Section 8: everything in the build order is now built; the open work is
evaluation follow-ups. Do not edit data/*.csv or the eval labels without the user's approval; back up
the files first and close them in Excel before writing (Excel locks the CSVs).
