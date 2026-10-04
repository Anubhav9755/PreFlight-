"""
DEMO BEAT 1 — Pre-merge.

"A developer opens a PR that adds an index on orders.status — looks fine,
but it's missing CONCURRENTLY."

Run:
    python demo/demo_premerge.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.db import drop_index_if_exists
from monitor.ci_watcher import watch_file
from orchestration.graph import run_pipeline

WEAKNESS_FILE = str(
    Path(__file__).resolve().parent.parent / "sandbox" / "weaknesses" / "001_add_status_index.sql"
)


def main():
    print("=" * 70)
    print("DEMO BEAT 1 — PRE-MERGE")
    print("=" * 70)

    # Clean slate so the benchmark numbers are honest on re-runs.
    drop_index_if_exists("idx_orders_status")

    print("\n[1/3] CI Watcher: scanning PR #142...\n")
    incident = watch_file(WEAKNESS_FILE, pr_number=142, commit_sha="a1b2c3d")
    if incident is None:
        print("Nothing flagged — did the sandbox get reset with a fixed migration file?")
        return

    print("\n[2/3] Running incident through the LangGraph pipeline "
          "(Diagnoser -> Fixer -> Reporter)...\n")
    final_incident = run_pipeline(incident)

    print("\n[3/3] Rendered PR comment:\n")
    print(final_incident["report"]["pr_comment_markdown"])
    print("=" * 70)
    print(f"Incident saved as: {final_incident['incident_id']}")
    print("(Open the dashboard to see it alongside the post-merge incident.)")


if __name__ == "__main__":
    main()
