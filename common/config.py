"""
Single source of truth for shared settings. Import from here — don't
re-hardcode the DSN or paths in your own agent's file.
"""

import os
from pathlib import Path

# Sandbox Postgres connection (matches sandbox/docker-compose.yml)
SANDBOX_DSN = os.environ.get(
    "PREFLIGHT_SANDBOX_DSN",
    "host=localhost port=5433 dbname=preflight_sandbox user=preflight password=preflight",
)

# Where incident JSON files live. Every agent reads/writes here.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INCIDENTS_DIR = PROJECT_ROOT / "seeded_incidents"
INCIDENTS_DIR.mkdir(exist_ok=True)

# Claude model used for the reasoning steps (Diagnoser + Fixer explanations)
LLM_MODEL = os.environ.get("PREFLIGHT_LLM_MODEL", "gemini-2.5-flash")

# Fake deploy history used to simulate git-bisection for the post-merge path
# tonight, instead of real `git log` integration. The Diagnoser matches an
# incident's query_fingerprint against each commit's "affects" list to find
# the responsible commit — swap-in-able for real `git log` bisection later.
DEPLOY_HISTORY_FILE = PROJECT_ROOT / "diagnoser" / "deploy_history.json"

# Regression threshold: how many times slower than baseline counts as
# a regression worth raising an incident for.
REGRESSION_MULTIPLIER = 2.0
