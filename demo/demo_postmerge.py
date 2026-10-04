"""
DEMO BEAT 2 — Post-merge.

"Now a slow query slipped through anyway — PreFlight's Production Watcher
catches the live regression, bisects it, fixes it, and asks a human to
approve before anything is applied."

Run:
    python demo/demo_postmerge.py

Then open the dashboard (streamlit run dashboard/app.py) and click Approve.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.db import drop_index_if_exists
from monitor.prod_watcher import poll_once, simulate_traffic
from monitor.watched_queries import WATCHED_QUERIES
from orchestration.graph import run_pipeline


def main():
    print("=" * 70)
    print("DEMO BEAT 2 — POST-MERGE")
    print("=" * 70)

    # Clean slate so the "before" number is real (no leftover index).
    drop_index_if_exists("idx_orders_customer_email")

    print("\n[1/3] Simulating real production traffic against the "
          "'my orders by email' endpoint...\n")
    simulate_traffic(WATCHED_QUERIES[0], num_calls=25)

    print("\n[2/3] Production Watcher polling pg_stat_statements...\n")
    raised = poll_once()

    if not raised:
        print("No regression detected — is the sandbox already fixed/indexed? "
              "Run sandbox/reset_sandbox.sh to get a clean slate.")
        return

    incident = raised[0]
    print(f"\nIncident raised: {incident['incident_id']}")

    print("\n[3/3] Running incident through the LangGraph pipeline "
          "(Diagnoser -> Fixer -> Reporter)...\n")
    final_incident = run_pipeline(incident)

    print("Diagnosis + fix complete. Status: awaiting_approval.\n")
    print("Open the dashboard now and click Approve to finish the story:")
    print("    streamlit run dashboard/app.py\n")
    print("Postmortem preview:\n")
    print(final_incident["report"]["postmortem_markdown"])


if __name__ == "__main__":
    main()
