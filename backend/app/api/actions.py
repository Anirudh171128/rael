"""Write actions that go through the Orchestrator: outcome buttons, draft
approvals, draft edits, reply simulation, on-demand briefs, and mode toggle."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.orchestrator import orchestrator

from ..config import settings
from ..database import get_session
from ..events import log_event
from ..models import Interaction, Lead
from ..schemas import ActionResult, OutcomeIn
from .auth import get_current_user

router = APIRouter(prefix="/api", tags=["actions"], dependencies=[Depends(get_current_user)])


class ModeIn(BaseModel):
    mode: str  # "paused" | "copilot" | "autonomous"


@router.get("/settings/mode")
async def get_mode():
    """Return the current operating mode."""
    if not getattr(settings, "discovery_enabled", True):
        return {"mode": "paused"}
    if getattr(settings, "approval_mode", True):
        return {"mode": "copilot"}
    return {"mode": "autonomous"}


@router.patch("/settings/mode")
async def set_mode(body: ModeIn):
    """Three-state switch: paused → copilot → autonomous.

    - paused: nothing runs (discovery_enabled=false)
    - copilot: scouts/scores/drafts, holds at approval gate (default)
    - autonomous: sends without approval
    """
    if body.mode == "paused":
        settings.discovery_enabled = False
        settings.approval_mode = True
    elif body.mode == "copilot":
        settings.discovery_enabled = True
        settings.approval_mode = True
    elif body.mode == "autonomous":
        settings.discovery_enabled = True
        settings.approval_mode = False
    else:
        return {"ok": False, "detail": f"unknown mode '{body.mode}'"}
    return {"ok": True, "mode": body.mode}


class DraftEdit(BaseModel):
    subject: str | None = None
    content: str | None = None


@router.patch("/interactions/{interaction_id}", response_model=ActionResult)
async def edit_draft(interaction_id: int, body: DraftEdit, session: AsyncSession = Depends(get_session)):
    """Human edits a held draft (subject/body) before approving it."""
    row = (
        await session.execute(select(Interaction).where(Interaction.id == interaction_id))
    ).scalars().first()
    if not row:
        raise HTTPException(404, "interaction not found")
    if row.outcome != "pending_approval":
        raise HTTPException(409, "only drafts awaiting approval can be edited")
    if body.subject is not None:
        row.subject = body.subject.strip()
    if body.content is not None:
        row.content = body.content.strip()
    lead = (await session.execute(select(Lead).where(Lead.id == row.lead_id))).scalars().first()
    await session.commit()
    await log_event(
        "Orchestrator", "draft_edited",
        f"You refined the draft for {lead.company_name if lead else 'a lead'} — I'll send your version.",
        lead_id=row.lead_id, level="info",
    )
    return ActionResult(ok=True, detail="draft updated")


@router.post("/outcomes", response_model=ActionResult)
async def record_outcome(payload: OutcomeIn):
    res = await orchestrator.dispatch("outcome", payload.model_dump())
    return ActionResult(ok=res.get("ok", True), detail=res.get("detail", ""), data=res)


@router.post("/approvals/{lead_id}", response_model=ActionResult)
async def approve(lead_id: int, decision: str = "send"):
    res = await orchestrator.dispatch("approval", {"lead_id": lead_id, "decision": decision})
    return ActionResult(ok=res.get("ok", True), detail=res.get("detail", ""), data=res)


@router.post("/leads/{lead_id}/brief", response_model=ActionResult)
async def brief(lead_id: int):
    res = await orchestrator.dispatch("meeting_scheduled", {"lead_id": lead_id})
    return ActionResult(ok=True, detail="Brief generated", data=res)


@router.post("/leads/{lead_id}/reply", response_model=ActionResult)
async def simulate_reply(lead_id: int, text: str):
    """Simulate an inbound reply (stands in for the SendGrid/LinkedIn webhook)."""
    res = await orchestrator.dispatch("reply_received", {"lead_id": lead_id, "text": text})
    return ActionResult(ok=True, detail="Reply processed", data=res)

