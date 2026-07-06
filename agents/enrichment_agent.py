"""Enrichment Agent — Apollo-only, human-approved.

GUARDRAIL: this agent never runs on its own. Discovery promoting a lead does
NOT trigger it — the dashboard asks the rep first ("spend Apollo credits?"),
and only POST /api/leads/{id}/enrich dispatches the pipeline that lands here.

No mock contacts: if Apollo doesn't return a verified person, the lead is
marked `incomplete` and simply waits. Nothing is fabricated.
"""
from __future__ import annotations

from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models import DiscoveredCompany, Lead

from . import brain_agent
from .base import AgentResult
from .graph import engine


def _tools():
    """Resolve tool callables from the YAML registry."""
    return engine.get_agent_tools("enrichment_agent")


async def run(lead_id: int) -> AgentResult:
    tools = _tools()
    enrich_fn = tools["enrich"]
    log_event = tools["log_event"]

    async with SessionLocal() as s:
        lead = (await s.execute(select(Lead).where(Lead.id == lead_id))).scalars().first()
        if not lead:
            return AgentResult("Enrichment Agent", f"Lead {lead_id} not found", level="attention")
        company = lead.company_name
        # The domain lives on the discovery record the lead was promoted from.
        dc = (
            await s.execute(
                select(DiscoveredCompany).where(DiscoveredCompany.lead_id == lead_id)
            )
        ).scalars().first()
        domain = dc.domain if dc else None

    # Buyer titles from the Brain steer Apollo at the right decision-maker.
    brain = await brain_agent.ensure_brain()
    titles = brain.get("buyers") or []

    result = await enrich_fn(company, domain, titles)

    if result.get("error") == "apollo_not_configured":
        await log_event(
            "Enrichment Agent", "enrich_blocked",
            f"Can't enrich {company} — Apollo isn't configured. Add APOLLO_API_KEY; "
            "I never invent contacts.",
            lead_id=lead_id, level="attention",
        )
        return AgentResult("Enrichment Agent", "Apollo not configured", next_action="needs_review",
                           data={"lead_id": lead_id}, level="attention")

    contact = result.get("contact") or {}
    found = result.get("found") and (contact.get("email") or contact.get("linkedin_url"))

    async with SessionLocal() as s:
        lead = (await s.execute(select(Lead).where(Lead.id == lead_id))).scalars().first()
        if found:
            lead.contact_name = contact.get("name") or lead.contact_name
            lead.title = contact.get("title") or lead.title
            lead.email = contact.get("email") or lead.email
            lead.phone = contact.get("phone") or lead.phone
            lead.linkedin_url = contact.get("linkedin_url") or lead.linkedin_url
            lead.status = "enriched"
        else:
            lead.status = "incomplete"
        lead.enrichment_cost = round((lead.enrichment_cost or 0) + result.get("credits_used", 0), 2)
        await s.commit()

    if found:
        who = f"{contact.get('name')} ({contact.get('title') or 'decision maker'})"
        credits = result.get("credits_used", 1)
        await log_event(
            "Enrichment Agent", "enrich",
            f"Apollo found {who} at {company}"
            + (f" · {contact.get('email')}" if contact.get("email") else " · email locked, have LinkedIn")
            + f" — {credits} credit{'s' if credits != 1 else ''} used",
            lead_id=lead_id, level="positive",
            extra={"credits_used": credits, "provider": "apollo"},
        )
        engine.emit(
            sender="enrichment_agent", recipient="qualification_agent",
            msg_type="data_update",
            payload={"lead_id": lead_id, "company": company},
            correlation_id=str(lead_id),
        )
        return AgentResult("Enrichment Agent", f"Enriched {company} via Apollo",
                           next_action="qualify", data={"lead_id": lead_id})

    reason = result.get("error") or "no verified contact returned"
    await log_event(
        "Enrichment Agent", "enrich_incomplete",
        f"{company}: Apollo had no verified decision-maker ({reason}). "
        "No contact invented — the lead waits.",
        lead_id=lead_id, level="attention",
        extra={"credits_used": result.get("credits_used", 0), "provider": "apollo"},
    )
    return AgentResult("Enrichment Agent", f"{company} — no contact found",
                       next_action="needs_review", data={"lead_id": lead_id}, level="attention")
