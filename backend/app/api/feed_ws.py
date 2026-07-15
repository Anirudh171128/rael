"""WebSocket endpoint for the live activity feed + WhatsApp mirror. The frontend
opens one socket; every agent action and notification streams through here.

The client authenticates with its session token as a query param — the browser
WebSocket API can't set an Authorization header."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from ..database import SessionLocal
from ..models import Session as UserSession
from ..websocket import manager

router = APIRouter()


async def _user_for_token(token: str | None) -> int | None:
    """Resolve the session token to its owning user id (None = invalid/expired)."""
    if not token:
        return None
    async with SessionLocal() as s:
        row = (await s.execute(select(UserSession).where(UserSession.token == token))).scalar()
    if not row:
        return None
    if row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return None
    return row.user_id


@router.websocket("/ws/feed")
async def feed(ws: WebSocket):
    user_id = await _user_for_token(ws.query_params.get("token"))
    if user_id is None:
        await ws.close(code=4401)
        return
    await manager.connect(ws, user_id)
    try:
        await ws.send_json({"channel": "system", "description": "connected to Rael's live feed"})
        while True:
            # We don't expect client→server messages, but keep the socket alive
            # and drain anything sent (e.g. ping/pong) so it doesn't error.
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception:
        await manager.disconnect(ws)
