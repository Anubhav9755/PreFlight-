"""
The actual LangGraph pipeline. Monitor Agent runs *before* this graph (it's
triggered by a webhook/poll, not by graph state) and hands off an incident
dict. From there, this graph branches on `incident["source"]` right away,
runs source-specific Diagnoser + Fixer logic, and rejoins at the Reporter
node — exactly the shape described in the architecture doc.

Usage:
    from orchestration.graph import run_pipeline
    final_incident = run_pipeline(incident)
"""

import sys
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.graph import END, StateGraph

from diagnoser.diagnoser import diagnose_postmerge, diagnose_premerge
from fixer.fixer import fix_locking_migration, fix_missing_index
from reporter.reporter import report_postmerge, report_premerge


class PipelineState(TypedDict):
    incident: dict


# --- nodes ---

def diagnoser_premerge_node(state: PipelineState) -> PipelineState:
    return {"incident": diagnose_premerge(state["incident"])}


def diagnoser_postmerge_node(state: PipelineState) -> PipelineState:
    return {"incident": diagnose_postmerge(state["incident"])}


def fixer_premerge_node(state: PipelineState) -> PipelineState:
    return {"incident": fix_locking_migration(state["incident"])}


def fixer_postmerge_node(state: PipelineState) -> PipelineState:
    return {"incident": fix_missing_index(state["incident"])}


def reporter_premerge_node(state: PipelineState) -> PipelineState:
    return {"incident": report_premerge(state["incident"])}


def reporter_postmerge_node(state: PipelineState) -> PipelineState:
    return {"incident": report_postmerge(state["incident"])}


# --- routing ---

def route_by_source(state: PipelineState) -> str:
    return state["incident"]["source"]  # "ci" or "prod"


def build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("diagnose_ci", diagnoser_premerge_node)
    graph.add_node("diagnose_prod", diagnoser_postmerge_node)
    graph.add_node("fix_ci", fixer_premerge_node)
    graph.add_node("fix_prod", fixer_postmerge_node)
    graph.add_node("report_ci", reporter_premerge_node)
    graph.add_node("report_prod", reporter_postmerge_node)

    # Branch immediately on source (Monitor already ran before this graph).
    graph.set_conditional_entry_point(
        route_by_source,
        {"ci": "diagnose_ci", "prod": "diagnose_prod"},
    )

    graph.add_edge("diagnose_ci", "fix_ci")
    graph.add_edge("diagnose_prod", "fix_prod")

    graph.add_edge("fix_ci", "report_ci")
    graph.add_edge("fix_prod", "report_prod")

    # Rejoin at the end — both paths terminate here.
    graph.add_edge("report_ci", END)
    graph.add_edge("report_prod", END)

    return graph.compile()


_compiled_graph = None


def run_pipeline(incident: dict) -> dict:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    result = _compiled_graph.invoke({"incident": incident})
    return result["incident"]
