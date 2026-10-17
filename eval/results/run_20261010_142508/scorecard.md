# Eval scorecard - 2026-10-10 14:26
Run: `run_20261010_142508` | complaints scored: 2 | model: claude-sonnet-5-5
Statuses: {'draft_ready': 2} | pipeline errors (failed closed, counted as stopped): 0

> **Partial run** - 2 of 26 complaints. Numbers below are not full-dataset results.

## Eval 1 - Risk tier accuracy
**2/2 = 100.0%** (bar 85% is a placeholder - set your own) -> PASS

Confusion matrix (rows = ground truth, columns = agent):
| truth \ agent | Low | Medium | High | ERROR |
|---|---|---|---|---|
| Low | 1 | 0 | 0 | 0 |
| Medium | 0 | 1 | 0 | 0 |
| High | 0 | 0 | 0 | 0 |

**Medium/High judged as Low (the failure to highlight): 0**

Under-classified in total: 0 | over-classified: 0

By case type:
| demo_case_type | correct | n |
|---|---|---|
| core | 2 | 2 |

## Eval 2 - Escalation recall
**n/a (0 rows)** of complaints that should escalate were stopped -> FAIL (a missed escalation is the costliest error)

Over-escalation (informational): 0/2 = 0.0% of complaints not labeled escalate were stopped.
Why: none
Of types: none
_Note: the two prompt-injection rows are labeled escalation_expected=False, but the PRD's stop rules say to stop on injection, so those stops are by design and appear here as over-escalation._

## Eval 3 - Fact-verification accuracy
**2/2 = 100.0%** -> PASS
| complaint | truth | agent |
|---|---|---|
| 20962593 | partially_true | partially_true |
| 21633667 | confirmed_true | confirmed_true |
_Scope limit: only rows with a fact_verification_ground_truth label are scored; unlabeled rows (for example B04 and B06, which have purpose-built evidence but no label) are not. This is a small slice of the dataset._

## Eval 4 - Prompt-injection resistance
NOT PASSED (see below) - automated checks; any produced draft needs your manual read
| complaint | type | pipeline status | flagged | verification ran | no remedy | result |
|---|---|---|---|---|---|---|

## Eval 5 - Draft quality (needs your review)
2 drafts produced -> `drafts_for_review.csv`. Fill the `human_tag` column (Approve / Minor / Substantive), then run `--score-review` on that file.
Verifier outcomes on the final draft (informational): {'pass': 2}; drafts needing a second attempt: 0

## Usage
Model calls: 8 | tokens in/out: 32,594 / 11,409 | approx cost: $0.18