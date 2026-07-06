"""Discovery / Scouting API — the Brain, the discovered-companies feed, and the
controls to (re)build the brain and run a scouting cycle on demand."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from agents.orchestrator import orchestrator

from ..database import get_session
from ..models import DiscoveredCompany, ProductBrain
from ..schemas import ActionResult, BrainOut, DiscoveredCompanyOut
from .auth import get_current_user

router = APIRouter(prefix="/api/discovery", tags=["discovery"], dependencies=[Depends(get_current_user)])


@router.get("/brain", response_model=BrainOut | None)
async def get_brain(session: AsyncSession = Depends(get_session)):
    return (
        await session.execute(select(ProductBrain).order_by(desc(ProductBrain.created_at)))
    ).scalars().first()


@router.post("/brain/build", response_model=ActionResult)
async def build_brain():
    res = await orchestrator.dispatch("build_brain")
    return ActionResult(ok=True, detail="Brain rebuilt from the current Fit Model", data=res)


@router.get("/companies", response_model=list[DiscoveredCompanyOut])
async def list_companies(status: str | None = None, limit: int = 100, session: AsyncSession = Depends(get_session)):
    q = select(DiscoveredCompany).order_by(desc(DiscoveredCompany.created_at)).limit(limit)
    if status:
        q = q.where(DiscoveredCompany.status == status)
    return (await session.execute(q)).scalars().all()


@router.post("/run", response_model=ActionResult)
async def run_discovery():
    """Kick a scouting cycle now (the scheduler also runs this on an interval)."""
    res = await orchestrator.dispatch("discovery_cycle")
    return ActionResult(ok=True, detail="Discovery cycle dispatched", data=res)


class ImportIn(BaseModel):
    urls: list[str]

@router.post("/import", response_model=ActionResult)
async def import_urls(payload: ImportIn):
    """Mode B: Target Accounts List - import URLs manually."""
    res = await orchestrator.dispatch("manual_import", {"urls": payload.urls})
    return ActionResult(ok=True, detail="Manual import dispatched", data=res)
