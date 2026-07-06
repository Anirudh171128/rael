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


async def _valid_token(token: str | None) -> bool:
    if not token:
        return False
    async with SessionLocal() as s:
        row = (await s.execute(select(UserSession).where(UserSession.token == token))).scalar()
    if not row:
        return False
    return row.expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)


@router.websocket("/ws/feed")
async def feed(ws: WebSocket):
    if not await _valid_token(ws.query_params.get("token")):
        await ws.close(code=4401)
        return
    await manager.connect(ws)
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
