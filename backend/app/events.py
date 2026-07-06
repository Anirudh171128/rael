"""The single chokepoint every agent uses to record an action.

`log_event` does two things at once, which is the whole point of the live feed:
  1. persists an `agent_logs` row (the audit trail)
  2. broadcasts the same event over the WebSocket (the dashboard sees it instantly)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .database import SessionLocal
from .models import AgentLog
from .websocket import manager


async def log_event(
    agent_name: str,
    action_type: str,
    description: str,
    *,
    lead_id: int | None = None,
    level: str = "info",  # info | positive | attention | urgent
    extra: dict[str, Any] | None = None,
) -> None:
    async with SessionLocal() as session:
        row = AgentLog(
            agent_name=agent_name,
            action_type=action_type,
            description=description,
            lead_id=lead_id,
            level=level,
            extra=extra,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        created_at = row.created_at or datetime.now(timezone.utc)

    await manager.broadcast(
        {
            "channel": "feed",
            "id": row.id,
            "agent_name": agent_name,
            "action_type": action_type,
            "description": description,
            "lead_id": lead_id,
            "level": level,
            "metadata": extra,
            "created_at": created_at.isoformat(),
        }
    )
