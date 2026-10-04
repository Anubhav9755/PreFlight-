"""
CI Watcher (half of the Monitor Agent).

In the real system this is triggered by a GitHub Actions webhook on every
PR. Tonight, we simulate the webhook by pointing this script at a migration
file directly — same input shape (a SQL diff + PR metadata), same output
(a unified incident). Swapping in a real webhook later only changes how
this script gets invoked, not what it does.

Usage:
    python ci_watcher.py --file ../sandbox/weaknesses/001_add_status_index.sql \
                          --pr 142 --commit a1b2c3d
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.incident_store import new_incident, save_incident

# Simple rule-based detectors. Each one looks at the raw SQL text and
# decides whether it's the kind of change PreFlight cares about, and what
# to call it. This is intentionally rule-based, not an LLM call — cheap,
# fast, deterministic, and it's the Diagnoser's job (not Monitor's) to
# actually reason about severity.
DETECTORS = [
    (
        "migration_missing_concurrently",
        re.compile(r"\bCREATE\s+INDEX\b(?!\s+CONCURRENTLY)", re.IGNORECASE),
        "CREATE INDEX without CONCURRENTLY on what may be a large table",
    ),
    (
        "unsafe_alter_table",
        re.compile(r"\bALTER\s+TABLE\b.*\bNOT\s+NULL\b", re.IGNORECASE),
        "ALTER TABLE adding a NOT NULL constraint can lock/rewrite the table",
    ),
]


def detect(sql_text: str):
    for trigger_type, pattern, description in DETECTORS:
        if pattern.search(sql_text):
            return trigger_type, description
    return None, None


def watch_file(file_path: str, pr_number: int, commit_sha: str) -> dict | None:
    path = Path(file_path)
    sql_text = path.read_text()

    trigger_type, description = detect(sql_text)
    if trigger_type is None:
        print(f"No risky pattern detected in {file_path} — nothing to flag.")
        return None

    incident = new_incident(
        source="ci",
        trigger_type=trigger_type,
        payload={
            "commit_sha": commit_sha,
            "pr_number": pr_number,
            "file_path": str(path),
            "sql_snippet": sql_text.strip(),
            "query_fingerprint": f"qf_{path.stem}",
            "observed_latency_ms": None,
            "baseline_latency_ms": None,
        },
    )
    incident["status"] = "new"
    save_incident(incident)

    print(f"CI Watcher: flagged PR #{pr_number} ({file_path})")
    print(f"  trigger_type: {trigger_type}  —  {description}")
    print(f"  incident_id : {incident['incident_id']}")
    return incident


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Path to the migration/query file to scan")
    parser.add_argument("--pr", type=int, required=True, help="PR number (simulated)")
    parser.add_argument("--commit", required=True, help="Commit SHA (simulated)")
    args = parser.parse_args()

    watch_file(args.file, args.pr, args.commit)
