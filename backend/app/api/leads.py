"""Leads — list, create, and the deep-dive (lead + full timeline)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import AgentLog, Interaction, Lead, Signal
from ..schemas import (
    InteractionOut,
    LeadCreate,
    LeadOut,
    LogOut,
    SignalOut,
)
from .auth import get_current_user

router = APIRouter(prefix="/api/leads", tags=["leads"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[LeadOut])
async def list_leads(status: str | None = None, session: AsyncSession = Depends(get_session)):
    q = select(Lead).order_by(Lead.fit_score.desc().nullslast(), Lead.created_at.desc())
    if status:
        q = q.where(Lead.status == status)
    return (await session.execute(q)).scalars().all()


@router.post("", response_model=LeadOut)
async def create_lead(payload: LeadCreate, session: AsyncSession = Depends(get_session)):
    lead = Lead(**payload.model_dump())
    session.add(lead)
    await session.flush()
    await session.refresh(lead)
    return lead


@router.post("/{lead_id}/enrich")
async def enrich_lead(lead_id: int, session: AsyncSession = Depends(get_session)):
    """Human-approved enrichment — the ONLY path that spends Apollo credits.

    Runs lead_pipeline (Apollo contact → re-qualify → draft outreach, which still
    holds at the send-approval gate in co-pilot mode)."""
    from agents.orchestrator import orchestrator

    from ..events import log_event

    lead = (await session.execute(select(Lead).where(Lead.id == lead_id))).scalars().first()
    if not lead:
        raise HTTPException(404, "lead not found")
    await log_event(
        "Orchestrator", "enrich_approved",
        f"You approved spending Apollo credits on {lead.company_name} — finding the decision-maker now.",
        lead_id=lead_id, level="info",
    )
    res = await orchestrator.dispatch("lead_pipeline", {"lead_id": lead_id})
    return {"ok": True, "result": res}


@router.get("/{lead_id}")
async def lead_detail(lead_id: int, session: AsyncSession = Depends(get_session)):
    lead = (await session.execute(select(Lead).where(Lead.id == lead_id))).scalars().first()
    if not lead:
        raise HTTPException(404, "lead not found")
    interactions = (
        await session.execute(select(Interaction).where(Interaction.lead_id == lead_id).order_by(Interaction.created_at))
    ).scalars().all()
    signals = (await session.execute(select(Signal).where(Signal.lead_id == lead_id))).scalars().all()
    logs = (
        await session.execute(select(AgentLog).where(AgentLog.lead_id == lead_id).order_by(AgentLog.created_at))
    ).scalars().all()
    return {
        "lead": LeadOut.model_validate(lead),
        "interactions": [InteractionOut.model_validate(i) for i in interactions],
        "signals": [SignalOut.model_validate(s) for s in signals],
        "logs": [LogOut.model_validate(l) for l in logs],
    }
