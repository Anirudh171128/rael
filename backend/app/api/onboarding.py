"""Onboarding — Step 1 of the user story. Seeds the Fit Model (Rael's judgment
brain) from the founder's answers. Also exposes the current Fit Model."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..events import log_event
from ..models import FitModel, User
from ..schemas import FitParam, OnboardingPayload
from ..tenant import current_user_id
from .auth import get_current_user

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"], dependencies=[Depends(get_current_user)])

DEFAULT_WEIGHTS = ["size", "industry", "title", "geography", "trigger"]


async def _seed(session: AsyncSession, p: OnboardingPayload) -> None:
    # Replace prior onboarding-sourced params; keep outcome-tuned weight rows.
    # The tenant hook already scopes this delete; the explicit filter is
    # defense-in-depth — re-onboarding must never wipe another account.
    await session.execute(
        delete(FitModel).where(
            FitModel.updated_from == "onboarding",
            FitModel.user_id == current_user_id.get(),
        )
    )
    rows = {
        "product_description": p.product_description,
        "targets": p.targets,
        "pain_solved": p.pain_solved,
        "icp_company_size_min": str(p.icp_company_size_min),
        "icp_company_size_max": str(p.icp_company_size_max),
        "icp_industries": ", ".join(p.icp_industries),
        "icp_geographies": ", ".join(p.icp_geographies) if p.icp_geographies else "India",
        "icp_funding_stages": ", ".join(p.icp_funding_stages),
        "signals": ", ".join(p.signals),
        "disqualifiers": ", ".join(p.disqualifiers),
        "qualify_threshold": str(p.qualify_threshold),
        "icp_titles": ", ".join(p.icp_titles),
        "past_buyers": ", ".join(p.past_buyers),
        "lost_deals_reasons": ", ".join(p.lost_deals_reasons),
        "exclusions": ", ".join(p.exclusions),
        "competitors": ", ".join(p.competitors),
    }
    for name, value in rows.items():
        session.add(FitModel(parameter_name=name, parameter_value=value, updated_from="onboarding"))
    # Ensure dimension weights exist (don't reset if already tuned by outcomes).
    existing = {
        r.parameter_name for r in (await session.execute(select(FitModel))).scalars().all()
    }
    for dim in DEFAULT_WEIGHTS:
        if f"weight:{dim}" not in existing:
            session.add(FitModel(parameter_name=f"weight:{dim}", parameter_value="1.0", weight=1.0, updated_from="default"))


@router.post("")
async def onboard(
    payload: OnboardingPayload, 
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user)
):
    await _seed(session, payload)
    
    # Mark user as onboarded
    user.onboarding_completed = True
    session.add(user)
    
    await session.commit()
    await log_event("Orchestrator", "onboarding", "Fit Model seeded from onboarding — Rael now knows what a good lead looks like", level="positive")
    # After training, Rael distils its understanding (the Brain) and starts scouting.
    # Fire-and-forget so the founder's "Approve" returns immediately.
    asyncio.create_task(_post_training())
    return {"ok": True, "detail": "Fit Model seeded"}


async def _post_training() -> None:
    """Build the Brain from the fresh Fit Model, then run one scouting cycle."""
    from agents.orchestrator import orchestrator

    try:
        await orchestrator.dispatch("build_brain")
        await orchestrator.dispatch("discovery_cycle")
    except Exception as exc:  # never let a background failure crash silently-unlogged
        await log_event("Brain Agent", "brain_error", f"Post-training discovery failed: {exc}", level="attention")


@router.get("", response_model=list[FitParam])
async def get_fit(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(FitModel).order_by(FitModel.parameter_name))).scalars().all()
    return rows
