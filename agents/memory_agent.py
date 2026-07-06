"""Memory Agent — runs nightly. Builds/updates lead embeddings, tunes Fit Model
weights from outcomes (the feedback loop), and surfaces leads gone silent 90+
days for re-engagement.

YAML-driven: weight_delta, tuned_dimensions, base_weight, weight bounds, and
reengage thresholds all come from rael.yaml → agents.memory_agent.config.

Weight tuning is **idempotent**: each run recomputes every dimension weight from
the base (1.0) plus the sum of all outcome deltas. This means it's safe to apply
on every nightly sweep *and* immediately when the rep taps an outcome button —
neither double-counts.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models import FitModel, Lead, LeadMemory, Outcome

from .base import AgentResult
from .graph import engine


def _cfg(key: str, default=None):
    """Read from rael.yaml → agents.memory_agent.config."""
    return engine.get_agent_config("memory_agent", key, default)


def _tools():
    """Resolve tool callables from the YAML registry."""
    return engine.get_agent_tools("memory_agent")


async def recompute_fit_weights(s) -> int:
    """Idempotently set each tuned dimension weight = base + Σ(outcome deltas)."""
    # All constants from YAML config.
    weight_delta = _cfg("weight_delta", {"closed": 0.15, "great_fit": 0.10, "wrong_fit": -0.12, "follow_up": 0.0})
    tuned_dimensions = _cfg("tuned_dimensions", ["trigger", "industry", "size"])
    base_weight = _cfg("base_weight", 1.0)
    weight_min = _cfg("weight_min", 0.2)
    weight_max = _cfg("weight_max", 3.0)

    outcomes = (await s.execute(select(Outcome))).scalars().all()
    total_delta = sum(weight_delta.get(o.outcome_type or "", 0.0) for o in outcomes)
    new_weight = max(weight_min, min(weight_max, base_weight + total_delta))
    for dim in tuned_dimensions:
        name = f"weight:{dim}"
        row = (await s.execute(select(FitModel).where(FitModel.parameter_name == name))).scalars().first()
        if not row:
            row = FitModel(parameter_name=name, parameter_value=str(new_weight))
            s.add(row)
        row.weight = new_weight
        row.updated_from = f"outcomes:{len(outcomes)}"
        row.updated_at = datetime.now(timezone.utc)
    return len(outcomes)


async def apply_outcomes() -> int:
    """Called right after an outcome is recorded for instant learning."""
    async with SessionLocal() as s:
        n = await recompute_fit_weights(s)
        await s.commit()
    return n


async def run() -> AgentResult:
    tools = _tools()
    embed_fn = tools["embed"]
    log_event = tools["log_event"]

    # Reengage config from YAML.
    reengage_after_days = _cfg("reengage_after_days", 90)
    reengage_exclude = _cfg("reengage_exclude_statuses", ["closed", "unsubscribed"])

    now = datetime.now(timezone.utc)
    embedded = 0
    reengage: list[int] = []

    async with SessionLocal() as s:
        applied = await recompute_fit_weights(s)

        leads = (await s.execute(select(Lead))).scalars().all()
        for lead in leads:
            summary = f"{lead.company_name} {lead.industry or ''} {lead.title or ''} {lead.trigger_event or ''}".strip()
            vec = await embed_fn(summary)
            mem = (await s.execute(select(LeadMemory).where(LeadMemory.lead_id == lead.id))).scalars().first()
            if mem:
                mem.embedding, mem.summary_text, mem.updated_at = vec, summary, now
            else:
                s.add(LeadMemory(lead_id=lead.id, embedding=vec, summary_text=summary))
            embedded += 1

            last = lead.last_touched_at
            if last and last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if last and (now - last) > timedelta(days=reengage_after_days) and lead.status not in reengage_exclude:
                reengage.append(lead.id)
        await s.commit()

    await log_event(
        "Memory Agent", "memory_sweep",
        f"Refreshed {embedded} embeddings, tuned Fit Model from {applied} outcomes, {len(reengage)} silent leads flagged",
        level="positive" if applied else "info", extra={"reengage_lead_ids": reengage, "outcomes_applied": applied},
    )

    # Emit message on the bus per YAML spec.
    engine.emit(
        sender="memory_agent", recipient="qualification_agent",
        msg_type="data_update", payload={"brain_config": {"outcomes_applied": applied}},
    )

    return AgentResult("Memory Agent", f"Nightly sweep: {embedded} embedded, {applied} outcomes applied", data={"reengage": reengage})
