"""YAML-driven scheduler — reads scheduled_jobs from rael.yaml and wires them
into APScheduler. No hardcoded job definitions: add/remove a job in the YAML,
restart, and the scheduler rebuilds.

Cadences are defined in rael.yaml § scheduled_jobs.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from agents.graph import boot, engine
from agents.orchestrator import orchestrator

from .config import settings
from .database import SessionLocal
from .models import User
from .tenant import current_user_id

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    """Read scheduled_jobs from rael.yaml and register each with APScheduler."""
    # Ensure the graph engine is loaded so we have the YAML spec.
    boot()

    for job in engine.scheduled_jobs:
        job_id = job["id"]

        # enabled_if (e.g. "settings.discovery_enabled") is evaluated at FIRE time,
        # not just at boot — so flipping the mode switch to Paused actually pauses
        # the cycle, and unpausing resumes it without a restart.
        enabled_if = job.get("enabled_if", "")

        # Build the dispatch coroutine.
        event_name = job.get("event") or job.get("pipeline", job_id)

        def _make_dispatch(ev: str, cond: str):
            async def _run():
                if cond:
                    try:
                        if not eval(cond, {"settings": settings}):  # noqa: S307
                            logger.info("Skipping scheduled '%s' — %s is false", ev, cond)
                            return
                    except Exception as e:
                        logger.warning("Could not evaluate enabled_if '%s': %s", cond, e)
                # Scheduled cycles run once per onboarded account, each inside
                # that account's tenant context so agents only ever see (and
                # write) that tenant's Fit Model, Brain, and leads.
                async with SessionLocal() as s:
                    user_ids = (
                        await s.execute(
                            select(User.id).where(User.onboarding_completed == True)  # noqa: E712
                        )
                    ).scalars().all()
                for uid in user_ids:
                    token = current_user_id.set(uid)
                    try:
                        await orchestrator.dispatch(ev)
                    except Exception:
                        logger.exception("Scheduled '%s' failed for user %s", ev, uid)
                    finally:
                        current_user_id.reset(token)

            return _run

        trigger_type = job.get("trigger", "interval")
        if trigger_type == "interval":
            hours = job.get("hours", 3)
            scheduler.add_job(
                _make_dispatch(event_name, enabled_if),
                "interval", hours=hours,
                id=job_id, replace_existing=True,
            )
            logger.info("Scheduled job '%s': every %sh → dispatch('%s')", job_id, hours, event_name)
        elif trigger_type == "cron":
            kwargs = {k: v for k, v in job.items()
                      if k in ("year", "month", "day", "week", "day_of_week",
                               "hour", "minute", "second")}
            scheduler.add_job(
                _make_dispatch(event_name, enabled_if),
                "cron", **kwargs,
                id=job_id, replace_existing=True,
            )
            logger.info("Scheduled job '%s': cron %s → dispatch('%s')", job_id, kwargs, event_name)
        else:
            logger.warning("Unknown trigger type '%s' for job '%s'", trigger_type, job_id)

    scheduler.start()
    logger.info("Scheduler started with %d jobs from rael.yaml", len(scheduler.get_jobs()))


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
