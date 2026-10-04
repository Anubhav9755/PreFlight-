"""
Shared Postgres helpers against the sandbox. Diagnoser and Fixer both need
"run this and tell me how long it took" / "run EXPLAIN ANALYZE and give me
the plan" — that logic lives here once instead of being copy-pasted twice.
"""

import time
from contextlib import contextmanager

import psycopg2

from common.config import SANDBOX_DSN


@contextmanager
def sandbox_conn(autocommit: bool = False):
    conn = psycopg2.connect(SANDBOX_DSN)
    conn.autocommit = autocommit
    try:
        yield conn
    finally:
        conn.close()


def explain_analyze(sql: str, params: dict | None = None) -> str:
    """Runs EXPLAIN (ANALYZE, BUFFERS) and returns the plan as plain text.
    Used by the Diagnoser to get real evidence, not a guess."""
    with sandbox_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {sql}", params)
        rows = cur.fetchall()
        conn.rollback()  # never let an EXPLAIN'd write actually commit
        return "\n".join(row[0] for row in rows)


def timed_run(sql: str, params: dict | None = None, repeats: int = 5) -> float:
    """Runs a query `repeats` times against the sandbox and returns the
    median wall-clock latency in milliseconds. Used for real before/after
    benchmark numbers in the Fixer's output."""
    durations_ms = []
    with sandbox_conn() as conn:
        cur = conn.cursor()
        for _ in range(repeats):
            start = time.perf_counter()
            cur.execute(sql, params)
            cur.fetchall()
            durations_ms.append((time.perf_counter() - start) * 1000)
        conn.rollback()
    durations_ms.sort()
    return durations_ms[len(durations_ms) // 2]  # median, less noisy than mean


def execute_ddl(sql: str) -> None:
    """Runs a DDL statement (CREATE INDEX, ALTER TABLE, etc.) for real
    against the sandbox. Autocommits since DDL like CREATE INDEX CONCURRENTLY
    cannot run inside a transaction block."""
    with sandbox_conn(autocommit=True) as conn:
        cur = conn.cursor()
        cur.execute(sql)


def drop_index_if_exists(index_name: str) -> None:
    """Used by demo scripts to reset a single index between rehearsals
    without wiping the whole sandbox."""
    execute_ddl(f"DROP INDEX IF EXISTS {index_name};")
