"""WebSocket connection manager — streams the live activity feed to connected
dashboards. Connections are keyed by user so one account's events are never
pushed to another account's socket. Agents call `broadcast()` the moment
something happens."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[WebSocket, int | None] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, user_id: int | None = None) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[ws] = user_id

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.pop(ws, None)

    async def broadcast(self, message: dict[str, Any], user_id: int | None = None) -> None:
        """Send a JSON message to the given user's sockets (all sockets when
        user_id is None — system-level events); drop dead sockets."""
        dead: list[WebSocket] = []
        for ws, owner in list(self._connections.items()):
            if user_id is not None and owner != user_id:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.pop(ws, None)


manager = ConnectionManager()
