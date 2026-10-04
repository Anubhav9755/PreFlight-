"""
PreFlight Dashboard (Streamlit).

Reads REAL incidents from seeded_incidents/*.json via common.incident_store
— nothing here is hardcoded or mocked. Approve/Reject buttons call
reporter.record_decision(), which writes the decision back to the incident's
JSON file for real, exactly like a human reviewer's call in production would.

Run:
    streamlit run dashboard/app.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from common.incident_store import list_incidents
from reporter.reporter import record_decision

st.set_page_config(
    page_title="PreFlight — Incident Console",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------- styling --
st.markdown(
    """
    <style>
      :root {
        --accent: #2F6F5E;
        --danger: #B23B3B;
        --warning: #B8843A;
        --border: #2A2C31;
        --surface: #16171B;
        --muted: #8A8D93;
      }

      /* remove streamlit's own top toolbar so nothing can overlap the title,
         and reclaim full width / height */
      header[data-testid="stHeader"] { display: none; }
      #MainMenu { visibility: hidden; }
      footer { visibility: hidden; }

      .block-container {
        padding-top: 1.6rem !important;
        padding-bottom: 2rem !important;
        padding-left: 2.5rem !important;
        padding-right: 2.5rem !important;
        max-width: 100% !important;
      }
      div[data-testid="stVerticalBlock"] { gap: 0.6rem !important; }

      /* title bar */
      .pf-title {
        font-size: 1.8rem;
        font-weight: 800;
        margin: 0 0 1rem 0;
      }

      /* generic bordered card wrapper (st.container(border=True)) */
      div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px !important;
        border-color: var(--border) !important;
      }
      div[data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="stVerticalBlock"] {
        padding: 1rem 1.1rem;
      }

      /* stat strip */
      .pf-stats {
        display: flex;
        border: 1px solid var(--border);
        border-radius: 12px;
        overflow: hidden;
        margin-bottom: 1rem;
      }
      .pf-stat {
        flex: 1;
        padding: 0.75rem 1.2rem;
        border-right: 1px solid var(--border);
      }
      .pf-stat:last-child { border-right: none; }
      .pf-stat-label {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: .04em;
        color: var(--muted);
        margin-bottom: 3px;
      }
      .pf-stat-value { font-size: 1.8rem; font-weight: 800; line-height: 1; }

      /* badges */
      .pf-badge {
        display: inline-block; padding: 3px 11px; border-radius: 999px;
        font-size: 12px; font-weight: 700; letter-spacing: .01em;
      }
      .pf-badge.new, .pf-badge.diagnosing, .pf-badge.fixing { background: #ECEBE5; color: #6B6D72; }
      .pf-badge.awaiting_approval { background: #F4E7D2; color: var(--warning); }
      .pf-badge.diagnosed, .pf-badge.fixed { background: #DDEAE6; color: var(--accent); }
      .pf-badge.approved, .pf-badge.closed { background: #DDEAE6; color: var(--accent); }
      .pf-badge.rejected { background: #F3DEDE; color: var(--danger); }
      .pf-risk-low { color: var(--accent); font-weight: 700; }
      .pf-risk-medium { color: var(--warning); font-weight: 700; }
      .pf-risk-high { color: var(--danger); font-weight: 700; }

      /* incident list — plain full-width boxes, no radio bullets */
      div.stButton { margin-bottom: 0.5rem; }
      div.stButton > button {
        width: 100%;
        white-space: normal !important;
        text-align: left !important;
        justify-content: flex-start !important;
        padding: 0.65rem 0.9rem !important;
        border-radius: 10px !important;
        line-height: 1.35rem;
        font-size: 0.92rem;
      }
      /* selected incident (primary button) — use the accent teal instead of
         streamlit's default red, and keep unselected ones subtle */
      div.stButton > button[kind="primary"] {
        background-color: var(--accent) !important;
        border-color: var(--accent) !important;
        color: #fff !important;
      }
      div.stButton > button[kind="primary"]:hover {
        background-color: #275E50 !important;
        border-color: #275E50 !important;
        color: #fff !important;
      }
      div.stButton > button[kind="secondary"] {
        background-color: transparent !important;
        border-color: var(--border) !important;
      }
      div.stButton > button[kind="secondary"]:hover {
        border-color: var(--accent) !important;
        color: var(--accent) !important;
      }

      /* section headers */
      .pf-h2 { font-size: 1.2rem; font-weight: 800; margin: 0 0 0.5rem 0; }
      .pf-meta { color: var(--muted); font-size: 0.88rem; }

      /* code / metrics tightened */
      div[data-testid="stMetric"] { padding: 0; }
      div[data-testid="stMetricValue"] { font-size: 1.6rem; }
      code, pre { font-size: 0.86rem !important; }

      /* shrink oversized markdown headings rendered inside expanders
         (postmortem / PR comment bodies) so they don't blow up the box */
      div[data-testid="stExpander"] h1 { font-size: 1.3rem !important; margin: 0.2rem 0 0.6rem 0 !important; }
      div[data-testid="stExpander"] h2 { font-size: 1.05rem !important; margin: 0.9rem 0 0.4rem 0 !important; }
      div[data-testid="stExpander"] h3 { font-size: 0.95rem !important; margin: 0.7rem 0 0.3rem 0 !important; }
      div[data-testid="stExpander"] p, div[data-testid="stExpander"] li { font-size: 0.88rem !important; }
      div[data-testid="stExpander"] table { font-size: 0.85rem !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- helpers --

_GREETING_RE = re.compile(r"^\s*hey,?\s*preflight\s*here!?\s*", re.IGNORECASE)


def clean_text(text: str) -> str:
    """Strip the boilerplate 'Hey, PreFlight here!' greeting from any
    generated copy — applied everywhere this text can appear, for every
    incident, past or future, since it's stripped at render time rather
    than baked into stored data."""
    if not text:
        return text
    return _GREETING_RE.sub("", text).strip()


def badge(status: str) -> str:
    return f'<span class="pf-badge {status}">{status.replace("_", " ")}</span>'


def risk_class(score: str) -> str:
    return f"pf-risk-{score}"


def split_fix_code(sql_or_diff: str):
    """Some fixes ship with a long block of leading `--` comments (PR
    metadata, rationale, etc.) before the actual statement. Splitting them
    keeps the card compact: the real fix is always front and center, the
    commentary is tucked behind an expander."""
    lines = sql_or_diff.strip("\n").split("\n")
    comment_lines, code_lines = [], []
    in_leading_comments = True
    for line in lines:
        if in_leading_comments and (line.strip().startswith("--") or line.strip() == ""):
            comment_lines.append(line)
        else:
            in_leading_comments = False
            code_lines.append(line)
    code = "\n".join(code_lines).strip("\n")
    comments = "\n".join(comment_lines).strip("\n")
    return code or sql_or_diff.strip("\n"), (comments if code else "")


def format_incident_label(inc: dict) -> str:
    trigger = inc["trigger_type"].replace("_", " ").title()
    fingerprint = inc["payload"].get("query_fingerprint", "")
    ts = inc["timestamp"][:16].replace("T", " ")
    return f"{trigger} · {fingerprint} · {ts}"


# ---------------------------------------------------------------- data ----
incidents = list_incidents()

title_col, refresh_col = st.columns([8, 1])
with title_col:
    st.markdown('<div class="pf-title">PreFlight — Incident Console</div>', unsafe_allow_html=True)
with refresh_col:
    if st.button("Refresh", use_container_width=True):
        st.rerun()

if not incidents:
    st.info(
        "No incidents yet. Run `python demo/demo_premerge.py` or "
        "`python demo/demo_postmerge.py` to generate one, then refresh."
    )
    st.stop()

# ---------------------------------------------------------------- stats ---
open_count = sum(1 for i in incidents if i["status"] not in ("closed", "approved", "rejected"))
awaiting_count = sum(1 for i in incidents if i["status"] == "awaiting_approval")
resolved_count = sum(1 for i in incidents if i["status"] in ("closed", "approved", "rejected"))

st.markdown(
    f"""
    <div class="pf-stats">
      <div class="pf-stat"><div class="pf-stat-label">Total incidents</div><div class="pf-stat-value">{len(incidents)}</div></div>
      <div class="pf-stat"><div class="pf-stat-label">Open</div><div class="pf-stat-value">{open_count}</div></div>
      <div class="pf-stat"><div class="pf-stat-label">Awaiting approval</div><div class="pf-stat-value">{awaiting_count}</div></div>
      <div class="pf-stat"><div class="pf-stat-label">Resolved</div><div class="pf-stat-value">{resolved_count}</div></div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- layout --
if "selected_idx" not in st.session_state:
    st.session_state.selected_idx = 0
if st.session_state.selected_idx >= len(incidents):
    st.session_state.selected_idx = 0

list_col, detail_col = st.columns([1, 2.3], gap="medium")

with list_col:
    with st.container(border=True):
        st.markdown('<div class="pf-h2">Incidents</div>', unsafe_allow_html=True)
        for i, inc in enumerate(incidents):
            selected = i == st.session_state.selected_idx
            if st.button(
                format_incident_label(inc),
                key=f"inc_{inc['incident_id']}",
                use_container_width=True,
                type="primary" if selected else "secondary",
            ):
                st.session_state.selected_idx = i
                st.rerun()

incident = incidents[st.session_state.selected_idx]

with detail_col:
    with st.container(border=True):
        st.markdown(
            f'<div class="pf-h2" style="font-size:1.4rem;">{incident["trigger_type"].replace("_", " ").title()}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='pf-meta'>"
            f"<code>{incident['incident_id']}</code> &nbsp;·&nbsp; "
            f"<b>{incident['source'].upper()}</b> &nbsp;·&nbsp; "
            f"{badge(incident['status'])} &nbsp;·&nbsp; "
            f"Detected {incident['timestamp'][:19].replace('T', ' ')}"
            f"</div>",
            unsafe_allow_html=True,
        )

    diagnosis = incident.get("diagnosis")
    if diagnosis:
        with st.container(border=True):
            st.markdown('<div class="pf-h2">Diagnosis</div>', unsafe_allow_html=True)
            st.write(clean_text(diagnosis["root_cause"]))
            with st.expander("Evidence (EXPLAIN ANALYZE / lock timing)"):
                st.code(diagnosis["evidence"], language="text")

    fix = incident.get("fix")
    if fix:
        with st.container(border=True):
            st.markdown('<div class="pf-h2">Proposed fix</div>', unsafe_allow_html=True)
            code, leading_comments = split_fix_code(fix["sql_or_diff"])
            st.code(code, language="sql")
            if leading_comments:
                with st.expander("Context / PR notes"):
                    st.code(leading_comments, language="text")

            bench = fix["benchmark"]
            b1, b2, b3 = st.columns(3)
            b1.metric("Before", f"{bench['before_ms']:.2f} ms")
            b2.metric("After", f"{bench['after_ms']:.2f} ms", delta=f"-{bench['improvement_pct']:.1f}%")
            b3.markdown(
                f"<div class='pf-stat-label'>Risk</div>"
                f"<span class='{risk_class(fix['risk_score'])}' style='font-size:1.5rem;'>{fix['risk_score'].upper()}</span>",
                unsafe_allow_html=True,
            )
            st.caption(clean_text(fix["risk_reasoning"]))
    elif diagnosis:
        with st.container(border=True):
            st.markdown('<div class="pf-h2">Proposed fix</div>', unsafe_allow_html=True)
            st.caption("No fix proposed yet.")

    report = incident.get("report") or {}
    with st.container(border=True):
        st.markdown('<div class="pf-h2">Decision</div>', unsafe_allow_html=True)
        if incident["source"] == "prod" and incident["status"] == "awaiting_approval":
            dc1, dc2 = st.columns(2)
            if dc1.button("Approve fix", use_container_width=True, key=f"approve_{incident['incident_id']}"):
                record_decision(incident, "approved")
                st.rerun()
            if dc2.button("Reject", use_container_width=True, key=f"reject_{incident['incident_id']}"):
                record_decision(incident, "rejected")
                st.rerun()
        elif report.get("human_decision"):
            st.markdown(
                f"**{report['human_decision'].upper()}** by {report.get('decided_by', 'unknown')} "
                f"at {report.get('decided_at', 'unknown')}"
            )
        elif incident["source"] == "ci":
            st.caption("Pre-merge — decided on the PR itself, not here.")
        else:
            st.caption("Waiting on diagnosis and a proposed fix.")

# ------------------------------------------------- postmortem / PR comment --
# Rendered full width, below the incident list + detail columns entirely,
# rather than squeezed into the right-hand column.
report = incident.get("report") or {}
if report.get("postmortem_markdown"):
    with st.container(border=True):
        with st.expander("Postmortem", expanded=False):
            st.markdown(clean_text(report["postmortem_markdown"]))

if report.get("pr_comment_markdown"):
    with st.container(border=True):
        with st.expander("PR comment", expanded=False):
            st.markdown(clean_text(report["pr_comment_markdown"]))