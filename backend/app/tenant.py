"""Tenant context — which user's data the current task is working with.

Set once at the boundary (auth dependency, scheduler loop, webhook) and read
by the ORM hooks in models.py, which scope every query and stamp every insert.
ContextVars propagate into `asyncio.create_task`, so fire-and-forget agent
pipelines inherit the tenant of the request that kicked them off.
"""
from __future__ import annotations

from contextvars import ContextVar

current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)
