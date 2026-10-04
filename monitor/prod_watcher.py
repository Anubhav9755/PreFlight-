"""
Production Watcher (the other half of the Monitor Agent).

Polls the REAL pg_stat_statements view in the sandbox (standing in for
production) and compares each watched query's mean execution time against
its known-healthy baseline. If it's regressed past the threshold, it emits
an incident — same shape as the CI Watcher's output, so the Diagnoser
doesn't need to know which watcher triggered it.

Usage:
    # Generate some real traffic against the slow query, then poll and detect:
    python prod_watcher.py --simulate-traffic 25

    # Just poll without generating traffic (e.g. if traffic already happened):
    python prod_watcher.py
"""

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import REGRESSION_MULTIPLIER
from common.db import sandbox_conn
from common.incident_store import new_incident, save_incident
from monitor.watched_queries import WATCHED_QUERIES


def simulate_traffic(query, num_calls: int) -> None:
    """Runs the watched query for real, with different emails, so
    pg_stat_statements has genuine stats to report. This stands in for
    real users hitting the endpoint."""
    print(f"Simulating {num_calls} real calls to '{query['query_fingerprint']}'...")
    with sandbox_conn() as conn:
        cur = conn.cursor()
        for i in range(num_calls):
            email = f"user{random.randint(1, 5000)}@example.com"
            cur.execute(query["sql_template"], {"email": email})
            cur.fetchall()
        conn.rollback()


def get_current_mean_ms(match_pattern: str) -> float | None:
    """Looks up the REAL mean_exec_time for a query from pg_stat_statements."""
    with sandbox_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT mean_exec_time, calls
            FROM pg_stat_statements
            WHERE query ILIKE %s
            ORDER BY calls DESC
            LIMIT 1;
            """,
            (f"%{match_pattern}%",),
        )
        row = cur.fetchone()
        conn.rollback()
        return row[0] if row else None


def poll_once() -> list[dict]:
    raised = []
    for query in WATCHED_QUERIES:
        observed_ms = get_current_mean_ms(query["match_pattern"])
        if observed_ms is None:
            print(f"  {query['query_fingerprint']}: no stats yet (query hasn't run)")
            continue

        baseline_ms = query["baseline_ms"]
        ratio = observed_ms / baseline_ms
        print(
            f"  {query['query_fingerprint']}: observed={observed_ms:.2f}ms "
            f"baseline={baseline_ms:.2f}ms ({ratio:.1f}x)"
        )

        if ratio >= REGRESSION_MULTIPLIER:
            incident = new_incident(
                source="prod",
                trigger_type="latency_regression",
                payload={
                    "commit_sha": query["introduced_by_commit_sha"],
                    "pr_number": None,
                    "file_path": None,
                    "sql_snippet": query["sql_template"],
                    "query_fingerprint": query["query_fingerprint"],
                    "observed_latency_ms": round(observed_ms, 2),
                    "baseline_latency_ms": baseline_ms,
                },
            )
            save_incident(incident)
            print(
                f"    -> REGRESSION DETECTED ({ratio:.1f}x baseline). "
                f"incident_id: {incident['incident_id']}"
            )
            raised.append(incident)

    return raised


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--simulate-traffic",
        type=int,
        default=0,
        help="Number of real calls to make before polling, to generate genuine stats",
    )
    args = parser.parse_args()

    if args.simulate_traffic:
        simulate_traffic(WATCHED_QUERIES[0], args.simulate_traffic)

    print("Production Watcher: polling pg_stat_statements...")
    poll_once()
