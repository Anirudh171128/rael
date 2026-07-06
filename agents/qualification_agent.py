"""Qualification Agent — runs after enrichment. Scores the lead against the Fit
Model (0-100). Threshold and gates from rael.yaml.

YAML-driven: gates read from YAML spec, tools from the engine, messages via bus.
"""
from __future__ import annotations

from sqlalchemy import desc, select

from backend.app.config import settings
from backend.app.database import SessionLocal
from backend.app.models import Lead, Signal

from .base import AgentResult, load_fit, score_lead
from .graph import engine


def _tools():
    """Resolve tool callables from the YAML registry."""
    return engine.get_agent_tools("qualification_agent")


def _gates():
    """Read gate definitions from rael.yaml → agents.qualification_agent.gates."""
    spec = engine.agents.get("qualification_agent")
    return spec.gates if spec else []


async def run(lead_id: int) -> AgentResult:
    fit = await load_fit()
    tools = _tools()
    log_event = tools["log_event"]

    async with SessionLocal() as s:
        lead = (await s.execute(select(Lead).where(Lead.id == lead_id))).scalars().first()
        if not lead:
            return AgentResult("Qualification Agent", f"Lead {lead_id} not found", level="attention")

        # Trigger strength comes from the signal that surfaced this lead.
        sig = (
            await s.execute(
                select(Signal).where(Signal.lead_id == lead_id).order_by(desc(Signal.detected_at))
            )
        ).scalars().first()
        trigger_strength = sig.score if sig and sig.score else 50

        score, reasoning = score_lead(
            company_size=lead.company_size,
            industry=lead.industry,
            title=lead.title,
            geography=lead.geography,  # HQ country stored at discovery-verify time
            trigger_strength=trigger_strength,
            fit=fit,
        )
        lead.fit_score = score
        lead.reasoning = reasoning
        # Threshold comes from settings (which can be overridden by YAML gates).
        qualified = score >= settings.qualify_threshold
        lead.status = "qualified" if qualified else "watching"
        company = lead.company_name
        await s.commit()

    level = "positive" if qualified else "info"
    await log_event(
        "Qualification Agent", "qualify",
        f"{company} scored {score} — {reasoning}",
        lead_id=lead_id, level=level, extra={"score": score, "qualified": qualified},
    )

    # Emit message on the bus per YAML spec.
    engine.emit(
        sender="qualification_agent",
        recipient="orchestrator",
        msg_type="event",
        payload={"score": score, "stage": lead.status if qualified else "watching"},
        correlation_id=str(lead_id),
    )

    return AgentResult(
        "Qualification Agent",
        f"{company} scored {score}",
        next_action="outreach" if qualified else "hold",
        data={"lead_id": lead_id, "score": score},
        level=level,
    )
