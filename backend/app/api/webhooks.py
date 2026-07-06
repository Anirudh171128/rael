"""Inbound webhooks from external providers. In mock mode you can POST to these
directly to simulate real provider callbacks."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.orchestrator import orchestrator

from ..database import get_session
from ..events import log_event
from ..models import Interaction, Lead

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/reply")
async def inbound_reply(payload: dict):
    """SendGrid/LinkedIn inbound reply → Reply Handler Agent."""
    return await orchestrator.dispatch("reply_received", {"lead_id": payload["lead_id"], "text": payload["text"]})


@router.post("/email-open")
async def email_open(payload: dict, session: AsyncSession = Depends(get_session)):
    """SendGrid open event. Multiple rapid opens = hot buying signal (user story Step 6)."""
    lead_id = payload["lead_id"]
    inter = (
        await session.execute(
            select(Interaction).where(Interaction.lead_id == lead_id, Interaction.direction == "outbound").order_by(desc(Interaction.created_at))
        )
    ).scalars().first()
    if not inter:
        return {"ok": False, "detail": "no outbound message to attribute open to"}
    inter.open_count += 1
    inter.opened_at = datetime.now(timezone.utc)
    opens = inter.open_count
    lead = (await session.execute(select(Lead).where(Lead.id == lead_id))).scalars().first()
    await session.commit()

    if opens >= 5:
        from ..services.comms import WhatsAppTemplates, send_whatsapp

        await send_whatsapp(
            {**WhatsAppTemplates.hot_signal(lead.contact_name or "Contact", lead.company_name, f"opened your email {opens}x in 20 mins"), "lead_id": lead_id}
        )
        await log_event("Reply Handler Agent", "hot_open", f"{lead.company_name}: email opened {opens}x — hot signal sent to you", lead_id=lead_id, level="urgent")
    return {"ok": True, "open_count": opens}


@router.post("/whatsapp")
async def whatsapp_button(request: Request):
    """WhatsApp interactive button callback. Maps Send/Skip taps to approvals."""
    body = await request.json()
    # Meta delivers a nested structure; we accept a simplified shape in mock mode.
    lead_id = body.get("lead_id")
    button = (body.get("button") or "").lower()
    if lead_id is None:
        return {"ok": True, "detail": "ignored (no lead context)"}
    decision = "skip" if "skip" in button or "ignore" in button else "send"
    return await orchestrator.dispatch("approval", {"lead_id": lead_id, "decision": decision})
