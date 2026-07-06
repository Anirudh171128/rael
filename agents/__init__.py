"""Rael's brain: YAML-driven multi-agent orchestration.

The orchestrator reads ``rael.yaml`` at boot, resolves every agent module and
tool, wires the graph edges, and dispatches events through named pipelines.
No agent calls another agent directly — all communication flows through the
shared state and the in-process message bus.

Usage:
    from agents.orchestrator import orchestrator
    await orchestrator.dispatch("discovery_cycle")
"""
