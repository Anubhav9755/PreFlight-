"""
Every agent reads and writes incidents through THIS module — never open
seeded_incidents/*.json directly with your own json.load/dump. That's how
we guarantee everyone stays on the same schema shape.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from common.config import INCIDENTS_DIR


def new_incident_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"inc_{stamp}_{short}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_incident(
    source: str,
    trigger_type: str,
    payload: dict,
    incident_id: Optional[str] = None,
) -> dict:
    """Build a fresh incident dict in the agreed shape. Called by the Monitor
    agent (ci_watcher.py / prod_watcher.py) only — downstream agents should
    load and extend an existing incident, not create new ones."""
    assert source in ("ci", "prod"), "source must be 'ci' or 'prod'"
    return {
        "incident_id": incident_id or new_incident_id(),
        "source": source,
        "trigger_type": trigger_type,
        "timestamp": now_iso(),
        "payload": payload,
        "status": "new",
    }


def save_incident(incident: dict) -> str:
    path = INCIDENTS_DIR / f"{incident['incident_id']}.json"
    with open(path, "w") as f:
        json.dump(incident, f, indent=2)
    return str(path)


def load_incident(incident_id: str) -> dict:
    path = INCIDENTS_DIR / f"{incident_id}.json"
    with open(path) as f:
        return json.load(f)


def list_incidents() -> list[dict]:
    """Returns all incidents, newest first. Used by the dashboard."""
    incidents = []
    for path in INCIDENTS_DIR.glob("*.json"):
        with open(path) as f:
            incidents.append(json.load(f))
    incidents.sort(key=lambda i: i["timestamp"], reverse=True)
    return incidents
