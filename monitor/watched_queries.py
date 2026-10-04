"""
Registry of production queries the Production Watcher polls
pg_stat_statements for. In a real deployment this would grow automatically
as new query fingerprints show up; tonight it's a short hand-maintained
list covering the one seeded demo weakness.

`baseline_ms` is the latency PreFlight expects once the right index exists —
i.e. what "healthy" looks like. That's the number regressions get compared
against.
"""

WATCHED_QUERIES = [
    {
        "query_fingerprint": "qf_orders_by_customer_email",
        # substring used to find this query's rows in pg_stat_statements
        "match_pattern": "FROM orders WHERE customer_email",
        "sql_template": (
            "SELECT id, status, total_cents, created_at "
            "FROM orders WHERE customer_email = %(email)s "
            "ORDER BY created_at DESC"
        ),
        "baseline_ms": 2.0,
        "introduced_by_commit_sha": "e4f5a6b",
    }
]
