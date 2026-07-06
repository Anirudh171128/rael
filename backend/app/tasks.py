"""Celery task definitions for a scaled deployment (Celery + Redis from the
blueprint). In local/pilot mode APScheduler runs these cadences in-process, so a
Celery worker is optional. Each task simply forwards to the Orchestrator.

Run a worker (optional):  celery -A backend.app.tasks worker --beat
"""
from __future__ import annotations

import asyncio

try:
    from celery import Celery
except ImportError:  # Celery is optional for local runs
    Celery = None

from .config import settings

if Celery:
    celery_app = Celery("rael", broker=settings.redis_url, backend=settings.redis_url)

    def _run(coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @celery_app.task
    def signal_cycle():
        from agents.orchestrator import orchestrator
        return _run(orchestrator.dispatch("signal_cycle"))

    @celery_app.task
    def discovery_cycle():
        from agents.orchestrator import orchestrator
        return _run(orchestrator.dispatch("discovery_cycle"))

    @celery_app.task
    def memory_sweep():
        from agents.orchestrator import orchestrator
        return _run(orchestrator.dispatch("memory_sweep"))

    @celery_app.task
    def daily_report(kind: str = "end_of_day"):
        from agents.orchestrator import orchestrator
        return _run(orchestrator.dispatch(kind))
