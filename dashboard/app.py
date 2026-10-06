"""
PreFlight Dashboard (Streamlit) — futuristic edition.

Reads REAL incidents from seeded_incidents/*.json via common.incident_store.
Approve/Reject call reporter.record_decision(), which writes the decision back
to the incident's JSON file, exactly as before.

New in this version
  * Neon "mission control" theme (Orbitron / Rajdhani / JetBrains Mono)
  * Search, status / source / risk filters and sorting
  * Lifecycle pipeline tracker per incident
  * Before/after benchmark bars
  * Console + Analytics tabs (status, risk, trigger mix, latency gains, timeline)
  * Two-step confirmation on Approve / Reject
  * Prev / Next incident navigation
  * Downloads: incident JSON, fix SQL, postmortem, filtered CSV
  * Raw JSON inspector, session activity log, optional auto-refresh

Run:
    streamlit run dashboard/app.py
"""

import html
import json
import sys
import re
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from common.incident_store import list_incidents
from reporter.reporter import record_decision

st.set_page_config(
    page_title="PreFlight // Incident Console",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------- styling --
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Rajdhani:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

      :root {
        --bg: #04060C;
        --panel: rgba(12, 18, 32, 0.78);
        --panel-solid: #0A101E;
        --line: rgba(80, 140, 190, 0.22);
        --line-strong: rgba(70, 232, 255, 0.45);
        --cyan: #46E8FF;
        --violet: #9B6BFF;
        --magenta: #FF4FD8;
        --ok: #3BF0A2;
        --warn: #FFB547;
        --danger: #FF4D6A;
        --text: #DCE8F5;
        --muted: #7F93AB;
        --display: 'Orbitron', sans-serif;
        --body: 'Rajdhani', sans-serif;
        --mono: 'JetBrains Mono', monospace;
      }

      /* ---- base canvas: deep space + faint grid ---- */
      .stApp {
        background:
          radial-gradient(900px 500px at 8% -5%, rgba(70,232,255,0.10), transparent 60%),
          radial-gradient(800px 520px at 100% 0%, rgba(155,107,255,0.12), transparent 60%),
          linear-gradient(rgba(70,232,255,0.035) 1px, transparent 1px) 0 0 / 48px 48px,
          linear-gradient(90deg, rgba(70,232,255,0.035) 1px, transparent 1px) 0 0 / 48px 48px,
          var(--bg);
        color: var(--text);
        font-family: var(--body);
        font-size: 1.05rem;
      }
      .stApp, .stApp p, .stApp li, .stApp label, .stApp span { font-family: var(--body); }
      header[data-testid="stHeader"] { background: transparent; }
      #MainMenu, footer { visibility: hidden; }

      .block-container {
        padding: 1.4rem 2.2rem 2.5rem 2.2rem !important;
        max-width: 100% !important;
      }
      div[data-testid="stVerticalBlock"] { gap: 0.7rem !important; }

      /* ---- masthead ---- */
      .pf-mast { display:flex; align-items:center; justify-content:space-between; gap:1rem; margin-bottom:0.4rem; }
      .pf-logo {
        font-family: var(--display); font-weight: 900; font-size: 1.7rem; letter-spacing: .06em;
        background: linear-gradient(90deg, var(--cyan), var(--violet) 60%, var(--magenta));
        -webkit-background-clip: text; background-clip: text; color: transparent;
        filter: drop-shadow(0 0 14px rgba(70,232,255,0.35));
      }
      .pf-sub { color: var(--muted); font-family: var(--mono); font-size: .78rem; margin-top: 2px; }
      .pf-live { display:flex; align-items:center; gap:.5rem; font-family: var(--mono); font-size:.78rem; color: var(--ok); }
      .pf-dot { width:9px; height:9px; border-radius:50%; background: var(--ok); box-shadow: 0 0 10px var(--ok); animation: pulse 2s infinite; }
      @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
      @media (prefers-reduced-motion: reduce) { .pf-dot { animation: none; } }

      /* ---- panels ---- */
      div[data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--panel);
        border: 1px solid var(--line) !important;
        border-radius: 4px 18px 4px 18px !important;
        backdrop-filter: blur(6px);
        box-shadow: 0 0 0 1px rgba(0,0,0,.4), 0 10px 40px rgba(0,0,0,.35);
      }
      div[data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="stVerticalBlock"] { padding: .9rem 1.1rem; }
      .pf-h2 { font-family: var(--display); font-size: .95rem; font-weight: 700; letter-spacing: .08em; color: var(--cyan); margin: 0 0 .4rem 0; }
      .pf-title { font-family: var(--display); font-size: 1.35rem; font-weight: 700; color: #fff; line-height: 1.25; }
      .pf-meta { color: var(--muted); font-size: .95rem; margin-top: .35rem; }
      .pf-meta code { color: var(--cyan); background: rgba(70,232,255,.08); border: 1px solid var(--line); }

      /* ---- stat strip ---- */
      .pf-stats { display:grid; grid-template-columns: repeat(5, 1fr); gap: .8rem; margin: .5rem 0 .6rem 0; }
      @media (max-width: 900px) { .pf-stats { grid-template-columns: repeat(2, 1fr); } }
      .pf-stat {
        position: relative; padding: .8rem 1rem; background: var(--panel);
        border: 1px solid var(--line); border-left: 3px solid var(--c, var(--cyan));
        border-radius: 3px 14px 3px 14px;
      }
      .pf-stat-label { font-size: .85rem; color: var(--muted); }
      .pf-stat-value { font-family: var(--display); font-size: 1.9rem; font-weight: 700; color: var(--c, var(--cyan)); text-shadow: 0 0 18px var(--c, var(--cyan)); line-height: 1.1; }
      .pf-stat-note { font-family: var(--mono); font-size: .7rem; color: var(--muted); }

      /* ---- badges ---- */
      .pf-badge { display:inline-block; padding: 2px 11px; border-radius: 999px; font-family: var(--mono); font-size: .72rem; font-weight: 600; border: 1px solid; }
      .pf-badge.new, .pf-badge.diagnosing, .pf-badge.fixing { color: var(--muted); border-color: var(--muted); background: rgba(127,147,171,.08); }
      .pf-badge.diagnosed, .pf-badge.fixed { color: var(--cyan); border-color: var(--cyan); background: rgba(70,232,255,.08); }
      .pf-badge.awaiting_approval { color: var(--warn); border-color: var(--warn); background: rgba(255,181,71,.1); box-shadow: 0 0 12px rgba(255,181,71,.25); }
      .pf-badge.approved, .pf-badge.closed { color: var(--ok); border-color: var(--ok); background: rgba(59,240,162,.08); }
      .pf-badge.rejected { color: var(--danger); border-color: var(--danger); background: rgba(255,77,106,.1); }
      .pf-risk-low { color: var(--ok); } .pf-risk-medium { color: var(--warn); } .pf-risk-high { color: var(--danger); }

      /* ---- pipeline tracker ---- */
      .pf-pipe { display:flex; align-items:center; margin: .3rem 0 .2rem 0; }
      .pf-step { display:flex; flex-direction:column; align-items:center; gap:4px; flex: 0 0 auto; min-width: 84px; }
      .pf-node { width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--line); background: var(--panel-solid); }
      .pf-step.done .pf-node { background: var(--cyan); border-color: var(--cyan); box-shadow: 0 0 12px var(--cyan); }
      .pf-step.active .pf-node { background: var(--bg); border-color: var(--warn); box-shadow: 0 0 14px var(--warn); }
      .pf-step.bad .pf-node { background: var(--danger); border-color: var(--danger); box-shadow: 0 0 14px var(--danger); }
      .pf-step.good .pf-node { background: var(--ok); border-color: var(--ok); box-shadow: 0 0 14px var(--ok); }
      .pf-step-label { font-size: .82rem; color: var(--muted); }
      .pf-step.done .pf-step-label, .pf-step.active .pf-step-label, .pf-step.good .pf-step-label, .pf-step.bad .pf-step-label { color: var(--text); }
      .pf-bar { flex: 1 1 auto; height: 2px; background: var(--line); margin-bottom: 20px; }
      .pf-bar.done { background: linear-gradient(90deg, var(--cyan), var(--violet)); box-shadow: 0 0 8px var(--cyan); }

      /* ---- benchmark bars ---- */
      .pf-bench { display:grid; grid-template-columns: 70px 1fr 90px; gap:.6rem; align-items:center; margin: .35rem 0; font-family: var(--mono); font-size:.82rem; }
      .pf-track { height: 14px; background: rgba(255,255,255,.05); border: 1px solid var(--line); border-radius: 2px 8px 2px 8px; overflow:hidden; }
      .pf-fill { height:100%; }
      .pf-fill.before { background: linear-gradient(90deg, #7a2a3a, var(--danger)); }
      .pf-fill.after { background: linear-gradient(90deg, #14806a, var(--ok)); box-shadow: 0 0 12px var(--ok); }
      .pf-gain { font-family: var(--display); font-size: 2rem; font-weight: 700; color: var(--ok); text-shadow: 0 0 20px var(--ok); }

      /* ---- buttons ---- */
      div.stButton > button, div.stDownloadButton > button {
        width: 100%; white-space: normal !important; text-align: left !important; justify-content: flex-start !important;
        background: rgba(10,16,30,.7) !important; color: var(--text) !important;
        border: 1px solid var(--line) !important; border-radius: 3px 12px 3px 12px !important;
        padding: .55rem .85rem !important; line-height: 1.3rem; font-family: var(--body); font-weight: 600; font-size: .98rem;
        transition: border-color .15s, box-shadow .15s, color .15s;
      }
      div.stButton > button:hover, div.stDownloadButton > button:hover {
        border-color: var(--cyan) !important; color: var(--cyan) !important; box-shadow: 0 0 14px rgba(70,232,255,.25);
      }
      div.stButton > button:focus-visible, div.stDownloadButton > button:focus-visible { outline: 2px solid var(--cyan) !important; outline-offset: 2px; }
      div.stButton > button[kind="primary"] {
        background: linear-gradient(90deg, rgba(70,232,255,.22), rgba(155,107,255,.22)) !important;
        border-color: var(--cyan) !important; color: #fff !important; box-shadow: 0 0 18px rgba(70,232,255,.3), inset 0 0 12px rgba(70,232,255,.12);
      }
      .pf-approve div.stButton > button { border-color: var(--ok) !important; color: var(--ok) !important; text-align:center !important; justify-content:center !important; }
      .pf-approve div.stButton > button:hover { box-shadow: 0 0 18px rgba(59,240,162,.4); }
      .pf-reject div.stButton > button { border-color: var(--danger) !important; color: var(--danger) !important; text-align:center !important; justify-content:center !important; }
      .pf-reject div.stButton > button:hover { box-shadow: 0 0 18px rgba(255,77,106,.4); }

      /* ---- tabs, inputs ---- */
      button[data-baseweb="tab"] { font-family: var(--display) !important; font-size: .78rem !important; letter-spacing: .06em; color: var(--muted) !important; }
      button[data-baseweb="tab"][aria-selected="true"] { color: var(--cyan) !important; }
      div[data-baseweb="tab-highlight"] { background-color: var(--cyan) !important; box-shadow: 0 0 10px var(--cyan); }
      div[data-baseweb="input"], div[data-baseweb="select"] > div { background: rgba(10,16,30,.8) !important; border-color: var(--line) !important; }
      span[data-baseweb="tag"] { background: rgba(70,232,255,.15) !important; color: var(--cyan) !important; }

      /* ---- code, expanders ---- */
      code, pre, div[data-testid="stCode"] * { font-family: var(--mono) !important; font-size: .82rem !important; }
      div[data-testid="stCode"] { border: 1px solid var(--line); border-radius: 3px 12px 3px 12px; }
      div[data-testid="stExpander"] { border: 1px solid var(--line) !important; border-radius: 3px 12px 3px 12px !important; background: rgba(10,16,30,.5); }
      div[data-testid="stExpander"] summary { font-family: var(--display); font-size: .78rem; letter-spacing: .05em; color: var(--cyan); }
      div[data-testid="stExpander"] h1 { font-size: 1.25rem !important; margin: .2rem 0 .6rem 0 !important; }
      div[data-testid="stExpander"] h2 { font-size: 1.05rem !important; margin: .9rem 0 .4rem 0 !important; }
      div[data-testid="stExpander"] h3 { font-size: .95rem !important; margin: .7rem 0 .3rem 0 !important; }
      div[data-testid="stExpander"] p, div[data-testid="stExpander"] li { font-size: .98rem !important; }

      section[data-testid="stSidebar"] { background: #070B15; border-right: 1px solid var(--line); }
      .pf-log { font-family: var(--mono); font-size: .75rem; color: var(--muted); border-left: 2px solid var(--line-strong); padding-left: .6rem; margin: .25rem 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- helpers --

_GREETING_RE = re.compile(r"^\s*hey,?\s*preflight\s*here!?\s*", re.IGNORECASE)
RESOLVED = ("closed", "approved", "rejected")
RISK_RANK = {"high": 3, "medium": 2, "low": 1}
STAGES = ["Detected", "Diagnosed", "Fix proposed", "In review", "Resolved"]


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def clean_text(text: str) -> str:
    """Strip the boilerplate 'Hey, PreFlight here!' greeting at render time."""
    if not text:
        return text
    return _GREETING_RE.sub("", text).strip()


def badge(status: str) -> str:
    return f'<span class="pf-badge {esc(status)}">{esc(status.replace("_", " "))}</span>'


def split_fix_code(sql_or_diff: str):
    """Separate leading `--` comment block (PR notes) from the real statement."""
    lines = sql_or_diff.strip("\n").split("\n")
    comment_lines, code_lines = [], []
    in_leading = True
    for line in lines:
        if in_leading and (line.strip().startswith("--") or line.strip() == ""):
            comment_lines.append(line)
        else:
            in_leading = False
            code_lines.append(line)
    code = "\n".join(code_lines).strip("\n")
    comments = "\n".join(comment_lines).strip("\n")
    return code or sql_or_diff.strip("\n"), (comments if code else "")


def trigger_name(inc: dict) -> str:
    return inc.get("trigger_type", "unknown").replace("_", " ").title()


def fingerprint(inc: dict) -> str:
    return (inc.get("payload") or {}).get("query_fingerprint", "")


def fix_metrics(inc: dict):
    fix = inc.get("fix")
    if not fix:
        return None
    b = fix.get("benchmark") or {}
    return {
        "before": b.get("before_ms"),
        "after": b.get("after_ms"),
        "improvement": b.get("improvement_pct"),
        "risk": fix.get("risk_score"),
    }


STATUS_ICON = {
    "new": "◌", "diagnosing": "◌", "diagnosed": "◍", "fixing": "◍", "fixed": "◍",
    "awaiting_approval": "◈", "approved": "●", "closed": "●", "rejected": "✕",
}


def list_label(inc: dict) -> str:
    ts = inc.get("timestamp", "")[:16].replace("T", " ")
    icon = STATUS_ICON.get(inc.get("status"), "◌")
    return f"{icon}  {trigger_name(inc)}\n{fingerprint(inc)}  ·  {ts}"


def pipeline_html(inc: dict) -> str:
    status = inc.get("status", "new")
    stage = 0
    if inc.get("diagnosis"):
        stage = 1
    if inc.get("fix"):
        stage = 2
    if status == "awaiting_approval":
        stage = 3
    if status in RESOLVED:
        stage = 4

    parts = []
    for i, name in enumerate(STAGES):
        if i < stage:
            cls = "done"
        elif i == stage:
            cls = "active"
            if i == 4:
                cls = "bad" if status == "rejected" else "good"
        else:
            cls = ""
        label = name
        if i == 4 and status in RESOLVED:
            label = status.title()
        parts.append(f'<div class="pf-step {cls}"><div class="pf-node"></div><div class="pf-step-label">{esc(label)}</div></div>')
        if i < len(STAGES) - 1:
            parts.append(f'<div class="pf-bar {"done" if i < stage else ""}"></div>')
    return f'<div class="pf-pipe">{"".join(parts)}</div>'


def benchmark_html(m: dict) -> str:
    before, after = m.get("before"), m.get("after")
    if before is None or after is None or not before:
        return ""
    pct_after = max(2.0, min(100.0, after / before * 100))
    return (
        f'<div class="pf-bench"><span>before</span><div class="pf-track"><div class="pf-fill before" style="width:100%"></div></div><span>{before:.2f} ms</span></div>'
        f'<div class="pf-bench"><span>after</span><div class="pf-track"><div class="pf-fill after" style="width:{pct_after:.1f}%"></div></div><span>{after:.2f} ms</span></div>'
    )


def incidents_to_df(incs) -> pd.DataFrame:
    rows = []
    for i in incs:
        m = fix_metrics(i) or {}
        rows.append({
            "incident_id": i.get("incident_id"),
            "timestamp": i.get("timestamp"),
            "source": i.get("source"),
            "trigger": trigger_name(i),
            "fingerprint": fingerprint(i),
            "status": i.get("status"),
            "risk": m.get("risk"),
            "before_ms": m.get("before"),
            "after_ms": m.get("after"),
            "improvement_pct": m.get("improvement"),
        })
    return pd.DataFrame(rows)


def log_event(msg: str):
    st.session_state.setdefault("activity", []).insert(
        0, f"{datetime.now(timezone.utc).strftime('%H:%M:%S')}Z  {msg}"
    )


def maybe_autorefresh():
    if st.session_state.get("auto_refresh"):
        time.sleep(st.session_state.get("refresh_secs", 10))
        st.rerun()


# ---------------------------------------------------------------- data ----
all_incidents = list_incidents()

# ---------------------------------------------------------------- sidebar --
with st.sidebar:
    st.markdown('<div class="pf-h2">Control panel</div>', unsafe_allow_html=True)
    st.toggle("Auto-refresh", key="auto_refresh", help="Reload incidents on a timer")
    st.slider("Interval (seconds)", 5, 60, 10, key="refresh_secs", disabled=not st.session_state.get("auto_refresh"))
    if st.button("Reload now", use_container_width=True, key="sb_reload"):
        st.rerun()
    st.divider()
    st.markdown('<div class="pf-h2">Session activity</div>', unsafe_allow_html=True)
    events = st.session_state.get("activity", [])
    if events:
        for e in events[:12]:
            st.markdown(f'<div class="pf-log">{esc(e)}</div>', unsafe_allow_html=True)
    else:
        st.caption("No decisions recorded in this session yet.")

# ---------------------------------------------------------------- masthead -
now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
st.markdown(
    f"""
    <div class="pf-mast">
      <div>
        <div class="pf-logo">PREFLIGHT</div>
        <div class="pf-sub">Incident console &nbsp;|&nbsp; {esc(now_utc)}</div>
      </div>
      <div class="pf-live"><span class="pf-dot"></span>Live from seeded_incidents</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if not all_incidents:
    st.info(
        "No incidents yet. Run `python demo/demo_premerge.py` or "
        "`python demo/demo_postmerge.py` to generate one, then reload."
    )
    maybe_autorefresh()
    st.stop()

# ---------------------------------------------------------------- stats ---
open_count = sum(1 for i in all_incidents if i["status"] not in RESOLVED)
awaiting_count = sum(1 for i in all_incidents if i["status"] == "awaiting_approval")
resolved_count = sum(1 for i in all_incidents if i["status"] in RESOLVED)
improvements = [m["improvement"] for m in (fix_metrics(i) for i in all_incidents) if m and m.get("improvement") is not None]
avg_gain = sum(improvements) / len(improvements) if improvements else 0.0

st.markdown(
    f"""
    <div class="pf-stats">
      <div class="pf-stat" style="--c:var(--cyan)"><div class="pf-stat-label">Total incidents</div><div class="pf-stat-value">{len(all_incidents)}</div></div>
      <div class="pf-stat" style="--c:var(--violet)"><div class="pf-stat-label">Open</div><div class="pf-stat-value">{open_count}</div></div>
      <div class="pf-stat" style="--c:var(--warn)"><div class="pf-stat-label">Awaiting approval</div><div class="pf-stat-value">{awaiting_count}</div></div>
      <div class="pf-stat" style="--c:var(--ok)"><div class="pf-stat-label">Resolved</div><div class="pf-stat-value">{resolved_count}</div></div>
      <div class="pf-stat" style="--c:var(--magenta)"><div class="pf-stat-label">Avg latency gain</div><div class="pf-stat-value">{avg_gain:.0f}%</div><div class="pf-stat-note">across {len(improvements)} fixes</div></div>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_console, tab_analytics = st.tabs(["CONSOLE", "ANALYTICS"])

# ================================================================ CONSOLE ==
with tab_console:
    # ---- filters ----
    f1, f2, f3, f4, f5 = st.columns([2.2, 1.6, 1.2, 1.2, 1.4])
    query = f1.text_input("Search", placeholder="id, fingerprint, root cause…", key="q")
    status_opts = sorted({i["status"] for i in all_incidents})
    status_f = f2.multiselect("Status", status_opts, key="f_status")
    source_opts = sorted({i["source"] for i in all_incidents})
    source_f = f3.multiselect("Source", source_opts, key="f_source")
    risk_f = f4.multiselect("Risk", ["low", "medium", "high"], key="f_risk")
    sort_by = f5.selectbox(
        "Sort", ["Newest first", "Oldest first", "Highest risk", "Biggest gain"], key="sort_by"
    )

    def matches(inc: dict) -> bool:
        if status_f and inc["status"] not in status_f:
            return False
        if source_f and inc["source"] not in source_f:
            return False
        if risk_f and ((fix_metrics(inc) or {}).get("risk") not in risk_f):
            return False
        if query:
            hay = " ".join([
                inc.get("incident_id", ""), fingerprint(inc), inc.get("trigger_type", ""),
                (inc.get("diagnosis") or {}).get("root_cause", ""),
            ]).lower()
            if query.lower() not in hay:
                return False
        return True

    incidents = [i for i in all_incidents if matches(i)]
    if sort_by == "Newest first":
        incidents.sort(key=lambda i: i.get("timestamp", ""), reverse=True)
    elif sort_by == "Oldest first":
        incidents.sort(key=lambda i: i.get("timestamp", ""))
    elif sort_by == "Highest risk":
        incidents.sort(key=lambda i: RISK_RANK.get((fix_metrics(i) or {}).get("risk"), 0), reverse=True)
    else:
        incidents.sort(key=lambda i: (fix_metrics(i) or {}).get("improvement") or 0, reverse=True)

    if not incidents:
        st.warning("No incidents match these filters. Clear a filter or the search box to see more.")
    else:
        ids = [i["incident_id"] for i in incidents]
        if st.session_state.get("selected_id") not in ids:
            st.session_state.selected_id = ids[0]
        pos = ids.index(st.session_state.selected_id)

        list_col, detail_col = st.columns([1, 2.3], gap="medium")

        # ---- list ----
        with list_col:
            with st.container(border=True):
                st.markdown(f'<div class="pf-h2">Incidents ({len(incidents)})</div>', unsafe_allow_html=True)
                nav_prev, nav_next = st.columns(2)
                if nav_prev.button("‹ Prev", use_container_width=True, disabled=pos == 0, key="nav_prev"):
                    st.session_state.selected_id = ids[pos - 1]
                    st.rerun()
                if nav_next.button("Next ›", use_container_width=True, disabled=pos >= len(ids) - 1, key="nav_next"):
                    st.session_state.selected_id = ids[pos + 1]
                    st.rerun()
                for inc in incidents:
                    selected = inc["incident_id"] == st.session_state.selected_id
                    if st.button(
                        list_label(inc),
                        key=f"inc_{inc['incident_id']}",
                        use_container_width=True,
                        type="primary" if selected else "secondary",
                    ):
                        st.session_state.selected_id = inc["incident_id"]
                        st.session_state.pop("pending", None)
                        st.rerun()

        incident = next(i for i in incidents if i["incident_id"] == st.session_state.selected_id)
        report = incident.get("report") or {}
        diagnosis = incident.get("diagnosis")
        fix = incident.get("fix")
        metrics = fix_metrics(incident)

        # ---- detail ----
        with detail_col:
            with st.container(border=True):
                st.markdown(f'<div class="pf-title">{esc(trigger_name(incident))}</div>', unsafe_allow_html=True)
                st.markdown(
                    f"<div class='pf-meta'><code>{esc(incident['incident_id'])}</code> &nbsp;·&nbsp; "
                    f"<b>{esc(incident['source'].upper())}</b> &nbsp;·&nbsp; {badge(incident['status'])} &nbsp;·&nbsp; "
                    f"Detected {esc(incident['timestamp'][:19].replace('T', ' '))}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(pipeline_html(incident), unsafe_allow_html=True)

            # ---- decision (always visible, above the tabs) ----
            with st.container(border=True):
                st.markdown('<div class="pf-h2">Decision</div>', unsafe_allow_html=True)
                iid = incident["incident_id"]
                pending = st.session_state.get("pending")
                if incident["source"] == "prod" and incident["status"] == "awaiting_approval":
                    if pending and pending[0] == iid:
                        verb = "approve" if pending[1] == "approved" else "reject"
                        st.warning(f"Confirm: {verb} the proposed fix for `{iid}`? This writes the decision to the incident file.")
                        cc1, cc2 = st.columns(2)
                        cls = "pf-approve" if pending[1] == "approved" else "pf-reject"
                        with cc1:
                            st.markdown(f'<div class="{cls}">', unsafe_allow_html=True)
                            if st.button(f"Yes, {verb}", use_container_width=True, key=f"confirm_{iid}"):
                                record_decision(incident, pending[1])
                                log_event(f"{pending[1].upper()} {iid}")
                                st.session_state.pop("pending", None)
                                st.toast(f"Fix {pending[1]} for {iid}")
                                st.rerun()
                            st.markdown("</div>", unsafe_allow_html=True)
                        with cc2:
                            if st.button("Cancel", use_container_width=True, key=f"cancel_{iid}"):
                                st.session_state.pop("pending", None)
                                st.rerun()
                    else:
                        dc1, dc2 = st.columns(2)
                        with dc1:
                            st.markdown('<div class="pf-approve">', unsafe_allow_html=True)
                            if st.button("Approve fix", use_container_width=True, key=f"approve_{iid}"):
                                st.session_state.pending = (iid, "approved")
                                st.rerun()
                            st.markdown("</div>", unsafe_allow_html=True)
                        with dc2:
                            st.markdown('<div class="pf-reject">', unsafe_allow_html=True)
                            if st.button("Reject", use_container_width=True, key=f"reject_{iid}"):
                                st.session_state.pending = (iid, "rejected")
                                st.rerun()
                            st.markdown("</div>", unsafe_allow_html=True)
                elif report.get("human_decision"):
                    st.markdown(
                        f"**{report['human_decision'].upper()}** by {report.get('decided_by', 'unknown')} "
                        f"at {report.get('decided_at', 'unknown')}"
                    )
                elif incident["source"] == "ci":
                    st.caption("Pre-merge: decided on the PR itself, not here.")
                else:
                    st.caption("Waiting on diagnosis and a proposed fix.")

            # ---- detail tabs ----
            t_over, t_fix, t_report, t_raw = st.tabs(["OVERVIEW", "DIAGNOSIS & FIX", "REPORTS", "RAW"])

            with t_over:
                with st.container(border=True):
                    st.markdown('<div class="pf-h2">Root cause</div>', unsafe_allow_html=True)
                    if diagnosis:
                        st.write(clean_text(diagnosis["root_cause"]))
                    else:
                        st.caption("Diagnosis in progress.")
                if metrics and metrics.get("before"):
                    with st.container(border=True):
                        st.markdown('<div class="pf-h2">Impact</div>', unsafe_allow_html=True)
                        g1, g2 = st.columns([1, 2])
                        imp = metrics.get("improvement") or 0
                        g1.markdown(
                            f"<div class='pf-stat-label'>Latency reduction</div><div class='pf-gain'>-{imp:.1f}%</div>"
                            f"<div class='pf-stat-label'>Risk: <b class='pf-risk-{esc(metrics.get('risk'))}'>{esc((metrics.get('risk') or 'n/a').upper())}</b></div>",
                            unsafe_allow_html=True,
                        )
                        g2.markdown(benchmark_html(metrics), unsafe_allow_html=True)

            with t_fix:
                if diagnosis:
                    with st.container(border=True):
                        st.markdown('<div class="pf-h2">Diagnosis</div>', unsafe_allow_html=True)
                        st.write(clean_text(diagnosis["root_cause"]))
                        with st.expander("Evidence (EXPLAIN ANALYZE / lock timing)"):
                            st.code(diagnosis.get("evidence", ""), language="text")
                if fix:
                    with st.container(border=True):
                        st.markdown('<div class="pf-h2">Proposed fix</div>', unsafe_allow_html=True)
                        code, leading = split_fix_code(fix["sql_or_diff"])
                        st.code(code, language="sql")
                        if leading:
                            with st.expander("Context / PR notes"):
                                st.code(leading, language="text")
                        b1, b2, b3 = st.columns(3)
                        bench = fix.get("benchmark") or {}
                        if bench:
                            b1.metric("Before", f"{bench['before_ms']:.2f} ms")
                            b2.metric("After", f"{bench['after_ms']:.2f} ms", delta=f"-{bench['improvement_pct']:.1f}%")
                        b3.markdown(
                            f"<div class='pf-stat-label'>Risk</div>"
                            f"<span class='pf-risk-{esc(fix.get('risk_score'))}' style='font-family:var(--display);font-size:1.4rem;'>{esc(fix.get('risk_score', '').upper())}</span>",
                            unsafe_allow_html=True,
                        )
                        st.caption(clean_text(fix.get("risk_reasoning", "")))
                        st.download_button(
                            "Download fix (.sql)", data=fix["sql_or_diff"],
                            file_name=f"{incident['incident_id']}_fix.sql", mime="text/plain", key=f"dl_sql_{iid}",
                        )
                elif diagnosis:
                    with st.container(border=True):
                        st.markdown('<div class="pf-h2">Proposed fix</div>', unsafe_allow_html=True)
                        st.caption("No fix proposed yet.")

            with t_report:
                shown = False
                if report.get("postmortem_markdown"):
                    shown = True
                    with st.expander("Postmortem", expanded=False):
                        st.markdown(clean_text(report["postmortem_markdown"]))
                    st.download_button(
                        "Download postmortem (.md)", data=clean_text(report["postmortem_markdown"]),
                        file_name=f"{incident['incident_id']}_postmortem.md", mime="text/markdown", key=f"dl_pm_{iid}",
                    )
                if report.get("pr_comment_markdown"):
                    shown = True
                    with st.expander("PR comment", expanded=False):
                        st.markdown(clean_text(report["pr_comment_markdown"]))
                    st.download_button(
                        "Download PR comment (.md)", data=clean_text(report["pr_comment_markdown"]),
                        file_name=f"{incident['incident_id']}_pr_comment.md", mime="text/markdown", key=f"dl_pr_{iid}",
                    )
                if not shown:
                    st.caption("No reports generated for this incident yet.")

            with t_raw:
                st.json(incident, expanded=False)
                st.download_button(
                    "Download incident (.json)", data=json.dumps(incident, indent=2, default=str),
                    file_name=f"{incident['incident_id']}.json", mime="application/json", key=f"dl_json_{iid}",
                )

        st.download_button(
            "Export filtered list (.csv)", data=incidents_to_df(incidents).to_csv(index=False),
            file_name="preflight_incidents.csv", mime="text/csv", key="dl_csv",
        )

# =============================================================== ANALYTICS ==
with tab_analytics:
    df = incidents_to_df(all_incidents)
    a1, a2 = st.columns(2, gap="medium")
    with a1:
        with st.container(border=True):
            st.markdown('<div class="pf-h2">Status distribution</div>', unsafe_allow_html=True)
            st.bar_chart(df["status"].value_counts(), color="#46E8FF")
    with a2:
        with st.container(border=True):
            st.markdown('<div class="pf-h2">Trigger mix</div>', unsafe_allow_html=True)
            st.bar_chart(df["trigger"].value_counts(), color="#9B6BFF")

    a3, a4 = st.columns(2, gap="medium")
    with a3:
        with st.container(border=True):
            st.markdown('<div class="pf-h2">Risk profile</div>', unsafe_allow_html=True)
            risk_counts = df["risk"].dropna().value_counts().reindex(["low", "medium", "high"]).fillna(0)
            if risk_counts.sum():
                st.bar_chart(risk_counts, color="#FFB547")
            else:
                st.caption("No fixes with a risk score yet.")
    with a4:
        with st.container(border=True):
            st.markdown('<div class="pf-h2">Incidents over time</div>', unsafe_allow_html=True)
            days = pd.to_datetime(df["timestamp"], errors="coerce").dt.date.value_counts().sort_index()
            if len(days):
                st.line_chart(days, color="#FF4FD8")
            else:
                st.caption("No timestamps to plot.")

    with st.container(border=True):
        st.markdown('<div class="pf-h2">Latency before vs after (ms)</div>', unsafe_allow_html=True)
        perf = df.dropna(subset=["before_ms", "after_ms"])
        if len(perf):
            chart_df = perf.set_index("fingerprint")[["before_ms", "after_ms"]]
            st.bar_chart(chart_df, color=["#FF4D6A", "#3BF0A2"])
        else:
            st.caption("No benchmarked fixes yet.")

    with st.container(border=True):
        st.markdown('<div class="pf-h2">All incidents</div>', unsafe_allow_html=True)
        st.dataframe(df, use_container_width=True, hide_index=True)

maybe_autorefresh()