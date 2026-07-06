"""Outreach Agent — pulls qualified leads, writes a personalized message with
the LLM, picks the channel by sequence step, and either sends or holds for
approval depending on APPROVAL_MODE.

YAML-driven: channel sequence, system prompt, tools, and human gate all
come from rael.yaml → agents.outreach_agent.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from backend.app.config import settings
from backend.app.database import SessionLocal
from backend.app.models import Interaction, Lead

from .base import AgentResult, load_fit
from .graph import engine


def _cfg(key: str, default=None):
    """Read from rael.yaml → agents.outreach_agent.config."""
    return engine.get_agent_config("outreach_agent", key, default)


def _subject_for(lead) -> str:
    """A short, trigger-aware subject line. The rep can edit it before sending."""
    t = (lead.trigger_event or "").lower()
    if "fund" in t or "raised" in t or "series" in t:
        return f"Congrats on the raise — quick idea for {lead.company_name}"
    if "hir" in t:
        return f"Saw {lead.company_name} is scaling the team"
    if "leader" in t or "vp" in t or "chief" in t or "head of" in t:
        return f"Quick note for the new chapter at {lead.company_name}"
    if "expan" in t or "launch" in t or "growth" in t:
        return f"Idea for {lead.company_name}'s next phase"
    return f"Quick note for {lead.company_name}"


def _tools():
    """Resolve tool callables from the YAML registry."""
    return engine.get_agent_tools("outreach_agent")


async def run(lead_id: int) -> AgentResult:
    fit = await load_fit()
    tools = _tools()
    complete_fn = tools["llm_complete"]
    send_email_fn = tools["send_email"]
    send_whatsapp_fn = tools["send_whatsapp"]
    log_event = tools["log_event"]

    # Channel cadence from YAML config.
    sequence = _cfg("channel_sequence", ["email", "linkedin", "whatsapp"])

    async with SessionLocal() as s:
        lead = (await s.execute(select(Lead).where(Lead.id == lead_id))).scalars().first()
        if not lead:
            return AgentResult("Outreach Agent", f"Lead {lead_id} not found", level="attention")

        sent_count = (
            await s.execute(
                select(func.count()).select_from(Interaction).where(
                    Interaction.lead_id == lead_id, Interaction.direction == "outbound"
                )
            )
        ).scalar() or 0
        channel = sequence[min(sent_count, len(sequence) - 1)]

        # System prompt from YAML config.
        system_prompt = _cfg("system_prompt", "You are Rael, an SDR writing a first-touch outreach message.")
        system = (
            f"{system_prompt} "
            f"Product: {fit.product or 'a sales enrichment + outreach tool'}. "
            f"Pain you solve: {fit.pain or 'reps waste hours on manual research'}. "
        )
        user = (
            f"company: {lead.company_name}\n"
            f"contact: {lead.contact_name or 'there'}\n"
            f"trigger: {lead.trigger_event or 'recent growth'}\n"
            f"pain: {fit.pain or 'manual research eating the day'}\n"
            f"channel: {channel}"
        )
        message = await complete_fn(system, user)
        subject = _subject_for(lead)
        # LLMs often lead with "Subject: …" — lift it into the subject field
        # so the body reads like the email that will actually go out.
        lines = message.strip().splitlines()
        if lines and lines[0].lower().startswith("subject:"):
            subject = lines[0].split(":", 1)[1].strip() or subject
            message = "\n".join(lines[1:]).strip()

        interaction = Interaction(
            lead_id=lead_id,
            type=channel,
            channel=channel,
            direction="outbound",
            subject=subject if channel == "email" else None,
            content=message,
            agent_name="Outreach Agent",
        )

        contact = lead.contact_name or "the decision maker"
        company = lead.company_name
        email = lead.email

        # Human gate from YAML spec: agents.outreach_agent.human_gate.
        agent_spec = engine.agents.get("outreach_agent")
        human_gate = agent_spec.human_gate if agent_spec else None
        use_approval = settings.approval_mode
        if human_gate and human_gate.get("default_mode") == "full_autonomous":
            use_approval = False

        if use_approval:
            interaction.outcome = "pending_approval"
            lead.status = "pending_approval"
            s.add(interaction)
            await s.commit()
            await send_whatsapp_fn(
                {
                    "kind": "approval",
                    "emoji": "✏️",
                    "title": "DRAFT READY — approve to send",
                    "body": f"To {contact} ({company}) via {channel}:\n\n\"{message}\"",
                    "buttons": ["Send it", "Edit first", "Skip"],
                    "lead_id": lead_id,
                }
            )
            await log_event(
                "Outreach Agent", "draft", f"Draft ready for {contact} ({company}) via {channel} — awaiting approval",
                lead_id=lead_id, level="attention",
            )
            engine.emit(
                sender="outreach_agent", recipient="orchestrator",
                msg_type="event", payload={"outreach": {"channel": channel, "approved": False}},
                correlation_id=str(lead_id),
            )
            return AgentResult("Outreach Agent", "held for approval", next_action="await_approval", data={"lead_id": lead_id}, level="attention")

        # Approval mode off → send directly.
        if channel == "email" and email:
            await send_email_fn(email, subject, message)
        else:
            await send_whatsapp_fn({"kind": "outbound", "emoji": "📤", "title": f"Sent via {channel}", "body": message, "buttons": []})
        interaction.sent_at = datetime.now(timezone.utc)
        interaction.outcome = "sent"
        lead.status = "contacted"
        lead.last_touched_at = datetime.now(timezone.utc)
        s.add(interaction)
        await s.commit()

    await log_event(
        "Outreach Agent", "outreach", f"Sent {channel} to {contact} ({company})",
        lead_id=lead_id, level="info",
    )
    engine.emit(
        sender="outreach_agent", recipient="orchestrator",
        msg_type="event", payload={"outreach": {"channel": channel, "approved": True}},
        correlation_id=str(lead_id),
    )
    return AgentResult("Outreach Agent", f"Sent {channel}", next_action="await_reply", data={"lead_id": lead_id})
