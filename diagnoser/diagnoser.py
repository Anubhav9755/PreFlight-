"""
Diagnoser Agent.

Branches on incident['source']:
  - "ci"   -> diagnose_premerge(): measures real lock-hold time + table size,
              asks Claude to explain the risk in plain English.
  - "prod" -> diagnose_postmerge(): bisects deploy history for the
              responsible commit, runs EXPLAIN ANALYZE on the slow query,
              asks Claude to explain the root cause.

Either way, the result is written into incident["diagnosis"] and the
incident is returned so the next agent (Fixer) can pick it up.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import DEPLOY_HISTORY_FILE
from common.db import execute_ddl, explain_analyze, sandbox_conn
from common.llm import ask_claude

SYSTEM_PROMPT = (
    "You are the Diagnoser Agent inside PreFlight, a database release and "
    "performance doctor. You are given raw evidence (a query plan, a "
    "measured lock duration, or both) about a risky database change. "
    "Write a short, plain-English root-cause explanation (3-5 sentences) "
    "that a developer could read in a PR comment or on a dashboard and "
    "immediately understand — no jargon dump, name the specific risk, and "
    "state its real-world consequence (e.g. blocked writes, slow endpoint)."
)


def _table_row_count(table: str) -> int:
    with sandbox_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT count(*) FROM {table};")
        return cur.fetchone()[0]


def _measure_lock_duration_ms(create_index_sql: str) -> float:
    """Runs the risky CREATE INDEX for real inside a transaction, times it,
    then rolls back so nothing actually changes on the sandbox. This gives
    a genuine measurement of how long the ACCESS EXCLUSIVE lock would be
    held in production — not a guess."""
    import time

    with sandbox_conn(autocommit=False) as conn:
        cur = conn.cursor()
        start = time.perf_counter()
        cur.execute(create_index_sql)
        duration_ms = (time.perf_counter() - start) * 1000
        conn.rollback()  # undo it — this was only a timing probe
    return duration_ms


def diagnose_premerge(incident: dict) -> dict:
    assert incident["source"] == "ci"
    incident["status"] = "diagnosing"

    row_count = _table_row_count("orders")

    # Re-run the exact flagged statement (it's already valid SQL against
    # our schema) as a timing probe, rolled back afterward.
    sql_snippet = incident["payload"]["sql_snippet"]
    probe_sql = sql_snippet.replace("idx_orders_status", "idx_orders_status_PROBE")
    lock_ms = _measure_lock_duration_ms(probe_sql)

    evidence = (
        f"Table `orders` currently has {row_count:,} rows.\n"
        f"Running the proposed migration as written (plain CREATE INDEX, "
        f"no CONCURRENTLY) held an ACCESS EXCLUSIVE-equivalent lock for "
        f"{lock_ms:.1f} ms in the sandbox — on production traffic volumes "
        f"this scales with table size and would block all writes to "
        f"`orders` for the duration of the build.\n"
        f"Migration SQL:\n{sql_snippet}"
    )

    root_cause = ask_claude(
        SYSTEM_PROMPT,
        f"Evidence:\n{evidence}\n\nExplain the root cause and its risk.",
    )

    incident["diagnosis"] = {
        "root_cause": root_cause,
        "evidence": evidence,
        "category": "locking_migration",
    }
    incident["status"] = "diagnosed"
    return incident


def diagnose_postmerge(incident: dict) -> dict:
    assert incident["source"] == "prod"
    incident["status"] = "diagnosing"

    # --- "bisection": match the query fingerprint against deploy history ---
    deploy_history = json.loads(DEPLOY_HISTORY_FILE.read_text())
    fingerprint = incident["payload"]["query_fingerprint"]
    responsible_commit = next(
        (c for c in deploy_history if fingerprint in c.get("affects", [])),
        None,
    )
    if responsible_commit:
        incident["payload"]["commit_sha"] = responsible_commit["commit_sha"]

    # --- real evidence: EXPLAIN ANALYZE on the actual slow query ---
    sql = incident["payload"]["sql_snippet"]
    plan = explain_analyze(sql, {"email": "user1@example.com"})

    evidence = (
        f"pg_stat_statements shows this query now runs at "
        f"{incident['payload']['observed_latency_ms']:.1f}ms mean, vs a "
        f"{incident['payload']['baseline_latency_ms']:.1f}ms baseline "
        f"({incident['payload']['observed_latency_ms'] / incident['payload']['baseline_latency_ms']:.1f}x).\n\n"
        f"Deploy history bisection points to commit "
        f"{responsible_commit['commit_sha'] if responsible_commit else 'unknown'} "
        f"({responsible_commit['message'] if responsible_commit else 'n/a'}).\n\n"
        f"EXPLAIN ANALYZE plan:\n{plan}"
    )

    root_cause = ask_claude(
        SYSTEM_PROMPT,
        f"Evidence:\n{evidence}\n\nExplain the root cause and its risk.",
    )

    incident["diagnosis"] = {
        "root_cause": root_cause,
        "evidence": evidence,
        "category": "missing_index",
    }
    incident["status"] = "diagnosed"
    return incident


def diagnose(incident: dict) -> dict:
    """Entry point — branches on source, exactly like the LangGraph node will."""
    if incident["source"] == "ci":
        return diagnose_premerge(incident)
    elif incident["source"] == "prod":
        return diagnose_postmerge(incident)
    raise ValueError(f"Unknown incident source: {incident['source']}")


if __name__ == "__main__":
    # Quick manual test: `python diagnoser.py <incident_id>`
    from common.incident_store import load_incident, save_incident

    incident_id = sys.argv[1]
    incident = load_incident(incident_id)
    diagnose(incident)
    save_incident(incident)
    print(json.dumps(incident["diagnosis"], indent=2))
