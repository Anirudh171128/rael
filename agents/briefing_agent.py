"""Briefing Agent — fires 30 min before a meeting. Pulls full lead context and
generates a spoken + visual brief, then pings the rep on WhatsApp.

YAML-driven: system prompt, max_tokens from rael.yaml config.
Tools resolved from the engine.
"""
from __future__ import annotations

from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models import Interaction, Lead, Signal
from backend.app.services.comms import WhatsAppTemplates

from .base import AgentResult, load_fit
from .graph import engine


def _cfg(key: str, default=None):
    """Read from rael.yaml → agents.briefing_agent.config."""
    return engine.get_agent_config("briefing_agent", key, default)


def _tools():
    """Resolve tool callables from the YAML registry."""
    return engine.get_agent_tools("briefing_agent")


async def run(lead_id: int) -> AgentResult:
    fit = await load_fit()
    tools = _tools()
    complete_fn = tools["llm_complete"]
    send_whatsapp_fn = tools["send_whatsapp"]
    log_event = tools["log_event"]

    async with SessionLocal() as s:
        lead = (await s.execute(select(Lead).where(Lead.id == lead_id))).scalars().first()
        if not lead:
            return AgentResult("Briefing Agent", f"Lead {lead_id} not found", level="attention")
        interactions = (
            await s.execute(select(Interaction).where(Interaction.lead_id == lead_id).order_by(Interaction.created_at))
        ).scalars().all()
        signals = (await s.execute(select(Signal).where(Signal.lead_id == lead_id))).scalars().all()

        contact = lead.contact_name or "Contact"
        company = lead.company_name
        context = (
            f"Lead: {contact}, {lead.title or 'unknown title'} at {company} "
            f"({lead.company_size or '?'} employees, {lead.industry or 'unknown industry'}). "
            f"Fit score {lead.fit_score}. Trigger: {lead.trigger_event}. "
            f"{len(interactions)} interactions, {len(signals)} signals. "
            f"Pain we solve: {fit.pain}."
        )

    # System prompt and max_tokens from YAML config.
    system_prompt = _cfg("system_prompt", "You are Rael preparing a sales rep for a call.")
    max_tokens = _cfg("max_tokens", 400)

    brief_text = await complete_fn(
        system_prompt,
        context,
        max_tokens=max_tokens,
    )

    card = {
        "contact": contact,
        "company": company,
        "company_size": lead.company_size,
        "industry": lead.industry,
        "fit_score": lead.fit_score,
        "trigger": lead.trigger_event,
        "brief": brief_text,
    }
    await send_whatsapp_fn(WhatsAppTemplates.pre_call_brief(contact, company))
    await log_event(
        "Briefing Agent", "brief", f"Pre-call brief ready for {contact} ({company})",
        lead_id=lead_id, level="attention", extra={"card": card},
    )

    # Emit message on the bus per YAML spec.
    engine.emit(
        sender="briefing_agent", recipient="human",
        msg_type="data_update", payload={"brief_document": card},
        correlation_id=str(lead_id),
    )

    return AgentResult("Briefing Agent", f"Brief ready for {contact}", data={"lead_id": lead_id, "card": card}, level="attention")
