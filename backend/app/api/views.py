"""Read-only dashboard views: signals, logs feed, metrics (Rael's Desk), and the
Hot Now bar."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import AgentLog, Interaction, Lead, Outcome, Signal
from ..schemas import LogOut, SignalOut
from .auth import get_current_user

router = APIRouter(prefix="/api", tags=["views"], dependencies=[Depends(get_current_user)])


@router.get("/signals", response_model=list[SignalOut])
async def list_signals(session: AsyncSession = Depends(get_session)):
    return (await session.execute(select(Signal).order_by(desc(Signal.detected_at)).limit(100))).scalars().all()


@router.get("/logs", response_model=list[LogOut])
async def list_logs(limit: int = 100, session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(AgentLog).order_by(desc(AgentLog.created_at)).limit(limit))).scalars().all()
    return rows


@router.get("/metrics")
async def metrics(session: AsyncSession = Depends(get_session)):
    async def count(q):
        return (await session.execute(q)).scalar() or 0

    contacted = await count(select(func.count()).select_from(Interaction).where(Interaction.direction == "outbound"))
    replies = await count(select(func.count()).select_from(Interaction).where(Interaction.direction == "inbound"))
    working = await count(select(func.count()).select_from(Lead).where(Lead.status.in_(["identified", "enriched", "qualified", "contacted"])))
    waiting = await count(select(func.count()).select_from(Lead).where(Lead.status.in_(["pending_approval", "warm"])))
    in_pipeline = await count(select(func.count()).select_from(Lead))
    meetings = await count(select(func.count()).select_from(Outcome).where(Outcome.outcome_type == "closed"))
    pipeline_value = float(await count(select(func.coalesce(func.sum(Outcome.closed_value), 0.0))))
    return {
        "working_on": working,
        "waiting_on_you": waiting,
        "in_pipeline": in_pipeline,
        "contacted": contacted,
        "replies": replies,
        "meetings": meetings,
        "pipeline_value": pipeline_value,
    }


@router.get("/hot")
async def hot_now(session: AsyncSession = Depends(get_session)):
    """Highest-intent leads right now: warm replies + pending approvals, then top scores."""
    leads = (
        await session.execute(
            select(Lead)
            .where(Lead.status.in_(["warm", "pending_approval", "qualified", "contacted"]))
            .order_by(Lead.fit_score.desc().nullslast())
            .limit(6)
        )
    ).scalars().all()
    out = []
    for lead in leads:
        last = (
            await session.execute(
                select(Interaction).where(Interaction.lead_id == lead.id).order_by(desc(Interaction.created_at))
            )
        ).scalars().first()
        out.append(
            {
                "lead_id": lead.id,
                "contact_name": lead.contact_name,
                "company_name": lead.company_name,
                "status": lead.status,
                "fit_score": lead.fit_score,
                "why": lead.trigger_event,
                "last_action": (last.type if last else None),
                "needs_you": lead.status in ("warm", "pending_approval"),
            }
        )
    # Surface the ones needing the rep first.
    out.sort(key=lambda x: (not x["needs_you"], -(x["fit_score"] or 0)))
    return out


@router.get("/outreach")
async def outreach_inbox(session: AsyncSession = Depends(get_session)):
    """Return interactions for the Outreach tab: drafts, sent, and inbox."""
    rows = (
        await session.execute(
            select(Interaction)
            .order_by(desc(Interaction.created_at))
            .limit(200)
        )
    ).scalars().all()

    # Attach lead info.
    lead_ids = {r.lead_id for r in rows if r.lead_id}
    leads_map = {}
    if lead_ids:
        leads_rows = (await session.execute(select(Lead).where(Lead.id.in_(lead_ids)))).scalars().all()
        leads_map = {l.id: l for l in leads_rows}

    def _serialize(i):
        lead = leads_map.get(i.lead_id)
        # Legacy drafts embedded "Subject: …" as the first content line — lift it.
        subject, content = i.subject, i.content
        if not subject and content and content.lstrip().lower().startswith("subject:"):
            first, _, rest = content.lstrip().partition("\n")
            subject = first.split(":", 1)[1].strip()
            content = rest.strip()
        return {
            "id": i.id,
            "lead_id": i.lead_id,
            "type": i.type,
            "channel": i.channel,
            "direction": i.direction,
            "subject": subject,
            "content": content,
            "outcome": i.outcome,
            "agent_name": i.agent_name,
            "sent_at": i.sent_at.isoformat() if i.sent_at else None,
            "replied_at": i.replied_at.isoformat() if i.replied_at else None,
            "created_at": i.created_at.isoformat() if i.created_at else None,
            "contact_name": lead.contact_name if lead else None,
            "company_name": lead.company_name if lead else None,
            "status": lead.status if lead else None,
        }

    drafts = [_serialize(r) for r in rows if r.outcome == "pending_approval"]
    sent = [_serialize(r) for r in rows if r.direction == "outbound" and r.outcome != "pending_approval"]
    inbox = [_serialize(r) for r in rows if r.direction == "inbound"]

    return {"drafts": drafts, "sent": sent, "inbox": inbox}

