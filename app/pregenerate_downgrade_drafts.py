"""Pre-generate the draft the agent writes when an analyst downgrades a stopped complaint.

Why: a downgrade makes the agent draft a reply (about 20-40 seconds and about $0.04). Generating those drafts ahead of
time makes the demo instant. The drafts are saved in eval/results/overrides/<complaint_id>.json, a folder the queue and
the packet views never read until an analyst actually downgrades that complaint, so nothing about a draft is visible
beforehand. When the analyst downgrades, the UI loads the saved draft and shows the analyst's own reason on it.

Usage (from the project folder; needs ANTHROPIC_API_KEY):
  python app/pregenerate_downgrade_drafts.py            # asks before spending
  python app/pregenerate_downgrade_drafts.py --yes      # no prompt
  python app/pregenerate_downgrade_drafts.py --force    # regenerate drafts that already exist
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipeline  # noqa: E402
from tools import DATA_DIR  # noqa: E402

RESULTS = DATA_DIR.parent / "eval" / "results"
OUT = RESULTS / "overrides"
PLACEHOLDER = "(replaced by the analyst's own reason when the case is downgraded)"
EST_COST_EACH = 0.04


def stopped_packets() -> dict:
    """Newest saved result for each current complaint that the agent stopped."""
    current = set(pd.read_csv(DATA_DIR / "complaints.csv", dtype=str, keep_default_na=False).complaint_id)
    latest = {}
    for run in sorted(RESULTS.glob("run_*")):
        for f in (run / "packets").glob("*.json"):
            try:
                p = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if f.stem in current and p.get("verification") and p.get("status") in ("draft_ready", "escalated", "draft_failed_verification"):
                latest[f.stem] = p
    return {cid: p for cid, p in latest.items() if p["status"] == "escalated"}


def generate(cid: str, packet: dict, client) -> tuple[str, str]:
    try:
        out = pipeline.draft_after_override(packet, PLACEHOLDER, client=client)
    except Exception as err:  # keep going; report at the end
        return cid, f"FAILED: {err}"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{cid}.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return cid, out["status"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    ap.add_argument("--force", action="store_true", help="regenerate drafts that already exist")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    stopped = stopped_packets()
    todo = {c: p for c, p in stopped.items() if args.force or not (OUT / f"{c}.json").exists()}
    print(f"{len(stopped)} stopped complaints; {len(stopped) - len(todo)} already have a saved downgrade draft; {len(todo)} to generate.")
    if not todo:
        return 0
    print(f"Estimated cost: about ${len(todo) * EST_COST_EACH:.2f} (model {pipeline.MODEL}).")
    if not args.yes and input("Proceed? [y/N] ").strip().lower() != "y":
        print("Cancelled.")
        return 1

    import anthropic
    client = anthropic.Anthropic()
    results = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(generate, c, p, client) for c, p in todo.items()]
        for i, fut in enumerate(as_completed(futures), 1):
            cid, status = fut.result()
            results[cid] = status
            print(f"[{i}/{len(todo)}] {cid:10} {status}")
    failed = {c: s for c, s in results.items() if s.startswith("FAILED")}
    print(f"\nDone. {len(results) - len(failed)} saved, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
