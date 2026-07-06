"""Reporting Agent — morning brief + 6 PM end-of-day digest. Aggregates the day's
activity and pushes a WhatsApp summary.

YAML-driven: tools resolved from the engine, messages emitted on bus.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from backend.app.database import SessionLocal
from backend.app.models import Interaction, Lead, Outcome
from backend.app.services.comms import WhatsAppTemplates

from .base import AgentResult
from .graph import engine


def _tools():
    """Resolve tool callables from the YAML registry."""
    return engine.get_agent_tools("reporting_agent")


async def _metrics(window_hours: int) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    async with SessionLocal() as s:
        contacted = (await s.execute(
            select(func.count()).select_from(Interaction).where(
                Interaction.direction == "outbound", Interaction.created_at >= since
            )
        )).scalar() or 0
        replies = (await s.execute(
            select(func.count()).select_from(Interaction).where(
                Interaction.direction == "inbound", Interaction.created_at >= since
            )
        )).scalar() or 0
        warm = (await s.execute(
            select(func.count()).select_from(Lead).where(Lead.status == "warm")
        )).scalar() or 0
        meetings = (await s.execute(
            select(func.count()).select_from(Outcome).where(Outcome.outcome_type == "closed")
        )).scalar() or 0
        pipeline = (await s.execute(
            select(func.coalesce(func.sum(Outcome.closed_value), 0.0))
        )).scalar() or 0.0
    return {"contacted": contacted, "replies": replies, "warm": warm, "meetings": meetings, "pipeline": float(pipeline)}


async def morning() -> AgentResult:
    tools = _tools()
    send_whatsapp_fn = tools["send_whatsapp"]
    log_event = tools["log_event"]

    m = await _metrics(24)
    lines = [
        f"{m['warm']} warm leads need attention",
        f"Rael contacted {m['contacted']} leads in the last 24h",
        f"Pipeline: ${m['pipeline']:,.0f} active",
    ]
    await send_whatsapp_fn(WhatsAppTemplates.morning_brief(lines))
    await log_event("Reporting Agent", "morning_brief", "Morning brief sent", level="info", extra=m)

    # Emit message on the bus per YAML spec.
    engine.emit(
        sender="reporting_agent", recipient="human",
        msg_type="event", payload={"digest_message": lines},
    )

    return AgentResult("Reporting Agent", "Morning brief sent", data=m)


async def end_of_day() -> AgentResult:
    tools = _tools()
    send_whatsapp_fn = tools["send_whatsapp"]
    log_event = tools["log_event"]

    m = await _metrics(24)
    lines = [
        f"{m['contacted']} leads contacted",
        f"{m['replies']} replies ({m['warm']} warm)",
        f"{m['meetings']} meetings booked",
        f"${m['pipeline']:,.0f} pipeline",
    ]
    await send_whatsapp_fn(WhatsAppTemplates.end_of_day(lines))
    await log_event("Reporting Agent", "end_of_day", "End-of-day digest sent", level="info", extra=m)

    # Emit message on the bus per YAML spec.
    engine.emit(
        sender="reporting_agent", recipient="human",
        msg_type="event", payload={"digest_message": lines},
    )

    return AgentResult("Reporting Agent", "EOD digest sent", data=m)
