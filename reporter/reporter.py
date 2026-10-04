"""
Reporter Agent.

Pre-merge -> renders a PR comment (markdown). Tonight we print/display it
instead of posting to a real GitHub PR (see roadmap "stretch goal").
Post-merge -> renders a postmortem and puts the incident into
"awaiting_approval" so the dashboard can show Approve/Reject. Once a human
decides, `record_decision()` finalizes the report and the postmortem.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.incident_store import save_incident


def generate_pr_comment(incident: dict) -> str:
    diag = incident["diagnosis"]
    fix = incident["fix"]
    bench = fix["benchmark"]

    comment = f"""## 🛫 PreFlight caught a risky database change

**Risk:** `{fix['risk_score'].upper()}`  |  **Category:** `{diag['category']}`

### What's wrong
{diag['root_cause']}

### Suggested fix
```sql
{fix['sql_or_diff']}
```

### Benchmarked impact (measured on sandbox replica)
| | Before | After |
|---|---|---|
| Write-blocking time | {bench['before_ms']:.1f} ms | {bench['after_ms']:.1f} ms |

**Why this fix:** {fix['risk_reasoning']}

---
*PreFlight tested this fix against a sandboxed replica before suggesting it. Nothing was applied to production. Accept the suggested diff to apply it, or dismiss this comment if you disagree.*
"""
    return comment


def generate_postmortem(incident: dict) -> str:
    diag = incident["diagnosis"]
    fix = incident["fix"]
    bench = fix["benchmark"]
    report = incident.get("report", {})

    decision_line = "**Pending human review.**"
    if report.get("human_decision"):
        decision_line = (
            f"**Decision:** {report['human_decision'].upper()} "
            f"by {report.get('decided_by', 'unknown')} at {report.get('decided_at', 'unknown')}"
        )

    postmortem = f"""# Postmortem — {incident['incident_id']}

**Detected:** {incident['timestamp']}
**Trigger:** {incident['trigger_type']}
**Responsible commit:** `{incident['payload'].get('commit_sha', 'unknown')}`

## Timeline
1. Production Watcher detected `{incident['payload']['query_fingerprint']}` running at
   {incident['payload']['observed_latency_ms']:.1f}ms, {incident['payload']['observed_latency_ms'] / incident['payload']['baseline_latency_ms']:.1f}x
   its {incident['payload']['baseline_latency_ms']:.1f}ms baseline.
2. Diagnoser bisected the regression to commit `{incident['payload'].get('commit_sha', 'unknown')}` and
   confirmed the cause via EXPLAIN ANALYZE.
3. Fixer proposed and benchmarked a fix against the sandbox replica.
4. {decision_line}

## Root cause
{diag['root_cause']}

## Fix applied
```sql
{fix['sql_or_diff']}
```

## Benchmark (sandbox replica)
| | Before | After | Improvement |
|---|---|---|---|
| Query latency | {bench['before_ms']:.1f} ms | {bench['after_ms']:.1f} ms | {bench['improvement_pct']:.1f}% |

**Risk score:** {fix['risk_score'].upper()} — {fix['risk_reasoning']}
"""
    return postmortem


def report_premerge(incident: dict) -> dict:
    comment = generate_pr_comment(incident)
    incident["report"] = {
        "pr_comment_markdown": comment,
        "postmortem_markdown": None,
        "human_decision": None,
        "decided_by": None,
        "decided_at": None,
    }
    incident["status"] = "closed"  # decision happens on GitHub itself, outside PreFlight
    save_incident(incident)
    return incident


def report_postmerge(incident: dict) -> dict:
    postmortem = generate_postmortem(incident)
    incident["report"] = {
        "pr_comment_markdown": None,
        "postmortem_markdown": postmortem,
        "human_decision": None,
        "decided_by": None,
        "decided_at": None,
    }
    incident["status"] = "awaiting_approval"
    save_incident(incident)
    return incident


def record_decision(incident: dict, decision: str, decided_by: str = "demo-reviewer") -> dict:
    """Called by the dashboard when someone clicks Approve/Reject."""
    assert decision in ("approved", "rejected")
    incident["report"]["human_decision"] = decision
    incident["report"]["decided_by"] = decided_by
    incident["report"]["decided_at"] = datetime.now(timezone.utc).isoformat()
    incident["status"] = "approved" if decision == "approved" else "rejected"
    # Regenerate the postmortem so it now includes the decision line.
    incident["report"]["postmortem_markdown"] = generate_postmortem(incident)
    save_incident(incident)
    return incident


def report(incident: dict) -> dict:
    """Entry point — branches on source, same pattern as Diagnoser/Fixer."""
    if incident["source"] == "ci":
        return report_premerge(incident)
    elif incident["source"] == "prod":
        return report_postmerge(incident)
    raise ValueError(f"Unknown incident source: {incident['source']}")
