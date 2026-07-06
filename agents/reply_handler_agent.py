"""Reply Handler Agent — triggered by an inbound reply webhook. Classifies the
reply and routes: warm/unknown escalate to the rep; FAQ answered autonomously;
objection handled from the map; unsubscribe honored.

YAML-driven: classification labels, escalation labels, objection map, and
routing rules all come from rael.yaml → agents.reply_handler_agent.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models import Interaction, Lead
from backend.app.services.comms import WhatsAppTemplates

from .base import AgentResult, load_fit
from .graph import engine


def _cfg(key: str, default=None):
    """Read from rael.yaml → agents.reply_handler_agent.config."""
    return engine.get_agent_config("reply_handler_agent", key, default)


def _tools():
    """Resolve tool callables from the YAML registry."""
    return engine.get_agent_tools("reply_handler_agent")


async def run(lead_id: int, reply_text: str) -> AgentResult:
    fit = await load_fit()
    tools = _tools()
    classify_fn = tools["llm_classify"]
    complete_fn = tools["llm_complete"]
    send_email_fn = tools["send_email"]
    send_whatsapp_fn = tools["send_whatsapp"]
    log_event = tools["log_event"]

    # Labels and routing from YAML config.
    labels = _cfg("classification_labels", ["Warm", "FAQ", "Objection", "Out of office", "Unsubscribe", "Unknown"])
    escalate_labels = _cfg("escalate_labels", ["Warm", "Unknown"])
    objection_map = _cfg("objection_map", {})

    label = await classify_fn(reply_text, labels)

    async with SessionLocal() as s:
        lead = (await s.execute(select(Lead).where(Lead.id == lead_id))).scalars().first()
        if not lead:
            return AgentResult("Reply Handler", f"Lead {lead_id} not found", level="attention")
        s.add(
            Interaction(
                lead_id=lead_id, type="reply", channel="email", direction="inbound",
                content=reply_text, replied_at=datetime.now(timezone.utc),
                outcome=label.lower(), agent_name="Reply Handler Agent",
            )
        )
        contact = lead.contact_name or "Contact"
        company = lead.company_name
        email = lead.email

        if label in escalate_labels:
            lead.status = "warm"
        elif label == "Unsubscribe":
            lead.status = "unsubscribed"
        await s.commit()

    # ── Route using YAML-defined routing rules ──
    if label in escalate_labels:
        await send_whatsapp_fn({**WhatsAppTemplates.warm_reply(contact, company, reply_text[:90]), "lead_id": lead_id})
        await log_event(
            "Reply Handler Agent", "escalate",
            f"{label} reply from {contact} ({company}) — escalated to you. I'm not handling this one.",
            lead_id=lead_id, level="urgent",
        )
        engine.emit(
            sender="reply_handler_agent", recipient="human",
            msg_type="escalation", payload={"lead_id": lead_id, "label": label, "priority": "urgent"},
            correlation_id=str(lead_id),
        )
        return AgentResult("Reply Handler", f"{label} → escalated", next_action="escalate", data={"lead_id": lead_id}, level="urgent")

    if label == "FAQ":
        answer = await complete_fn(
            f"You are Rael. Answer this prospect's question briefly using approved info. Product: {fit.product}.",
            reply_text,
        )
        if email:
            await send_email_fn(email, f"Re: your question, {company}", answer)
        await log_event("Reply Handler Agent", "faq", f"Answered FAQ from {contact} ({company}) autonomously", lead_id=lead_id, level="info")
        return AgentResult("Reply Handler", "FAQ answered", data={"lead_id": lead_id})

    if label == "Objection":
        # Match against YAML-defined objection map.
        key = next((k for k in objection_map if k in reply_text.lower()), None)
        if key:
            if email:
                await send_email_fn(email, f"Re: {company}", objection_map[key])
            await log_event("Reply Handler Agent", "objection", f"Handled objection from {contact} ({company}) via map", lead_id=lead_id, level="info")
            return AgentResult("Reply Handler", "objection handled", data={"lead_id": lead_id})
        await send_whatsapp_fn({**WhatsAppTemplates.warm_reply(contact, company, reply_text[:90]), "lead_id": lead_id})
        await log_event("Reply Handler Agent", "objection_flag", f"Unmapped objection from {contact} ({company}) — flagged to you", lead_id=lead_id, level="attention")
        return AgentResult("Reply Handler", "objection flagged", next_action="escalate", data={"lead_id": lead_id}, level="attention")

    if label == "Out of office":
        await log_event("Reply Handler Agent", "ooo", f"{contact} ({company}) is OOO — I'll retry later", lead_id=lead_id, level="info")
        return AgentResult("Reply Handler", "OOO — retry scheduled", data={"lead_id": lead_id})

    # Unsubscribe
    await log_event("Reply Handler Agent", "unsubscribe", f"{contact} ({company}) unsubscribed — stopping outreach", lead_id=lead_id, level="info")
    return AgentResult("Reply Handler", "unsubscribed", data={"lead_id": lead_id})
