"""Graph introspection API — lets the dashboard (and devs) inspect the live
YAML-driven agent graph at runtime.

    GET  /api/graph           → full graph summary
    GET  /api/graph/agents    → all agents with roles, tools, status
    GET  /api/graph/agent/{n} → single agent detail (raw YAML spec + resolved tools)
    GET  /api/graph/pipelines → all pipeline definitions
    GET  /api/graph/edges     → static + conditional edges
    GET  /api/graph/bus       → current message bus depth
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from agents.graph import engine

from .auth import get_current_user

router = APIRouter(prefix="/api/graph", tags=["graph"], dependencies=[Depends(get_current_user)])


@router.get("")
async def graph_summary():
    """Full graph summary: agents, tools, pipelines, edges, bus depth."""
    return engine.describe()


@router.get("/agents")
async def list_agents():
    """All agents with their role, tools, and status."""
    return {
        name: {
            "role": a.role,
            "tools": a.tools,
            "reads": a.reads,
            "writes": a.writes,
            "status": a.status,
            "triggers": a.triggers,
            "gates": a.gates,
            "human_gate": a.human_gate,
        }
        for name, a in engine.agents.items()
    }


@router.get("/agent/{name}")
async def get_agent(name: str):
    """Detailed spec for a single agent (raw YAML + resolved tools)."""
    spec = engine.get_agent_spec(name)
    if not spec:
        return {"error": f"agent '{name}' not found"}
    return {
        "yaml_spec": spec,
        "resolved_tools": engine.list_agent_tools(name),
        "module_resolved": engine.agents[name]._run_fn is not None if name in engine.agents else False,
    }


@router.get("/pipelines")
async def list_pipelines():
    """All pipeline definitions from rael.yaml."""
    return {
        name: {
            "description": p.description,
            "entry_event": p.entry_event,
            "requires": p.requires,
            "steps": [
                {
                    "node": s.node,
                    "type": s.type,
                    "next_on": s.next_on,
                    "post_action": s.post_action or None,
                }
                for s in p.steps
            ],
        }
        for name, p in engine.pipelines.items()
    }


@router.get("/edges")
async def list_edges():
    """Static + conditional edges."""
    return {
        "static": [{"from": s, "to": d} for s, d in engine.static_edges],
        "conditional": engine.conditional_edges,
    }


@router.get("/bus")
async def bus_status():
    """Current message bus depth and recent messages."""
    return {
        "depth": len(engine.message_bus),
        "recent": [
            {
                "id": m.message_id[:8],
                "sender": m.sender,
                "recipient": m.recipient,
                "type": m.type,
                "timestamp": m.timestamp,
            }
            for m in engine.message_bus[-10:]
        ],
    }
