"""The Orchestrator — Rael's brain (YAML-driven).

Delegates all routing, tool resolution, and pipeline execution to the
GraphEngine which reads ``rael.yaml`` at boot. This module keeps only the
business logic that needs direct DB access (approve, record_outcome) — everything
else is declared in the YAML.

    Event → GraphEngine.dispatch() → pipeline / direct agent call → done
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from backend.app.config import settings
from backend.app.database import SessionLocal
from backend.app.events import log_event
from backend.app.models import Interaction, Lead, Outcome, DiscoveredCompany

from .graph import boot, engine


class Orchestrator:
    """YAML-driven orchestrator. The graph engine handles all routing;
    this class provides the entrypoint and the handful of DB-touching
    actions that live outside the agent modules."""

    def __init__(self):
        # Boot the graph engine (loads rael.yaml, resolves all modules/tools).
        boot()

    # ── Entry point: events come in here ───────────────────────────────
    async def dispatch(self, event_type: str, payload: dict | None = None) -> dict:
        """Route any event through the YAML-defined graph.

        The engine checks pipelines first (discovery_cycle, lead_pipeline, etc.),
        then falls back to direct agent function calls. Only 'approval' and
        'outcome' are handled here because they need inline DB writes.
        """
        payload = payload or {}

        # Special handlers that need direct DB access.
        if event_type == "approval":
            result = await self.approve_outreach(
                payload["lead_id"], payload.get("decision", "send")
            )
            return {"ok": True, "event": event_type, "result": result}

        if event_type == "outcome":
            result = await self.record_outcome(payload)
            return {"ok": True, "event": event_type, "result": result}
            
        if event_type == "manual_import":
            result = await self.manual_import(payload["urls"])
            return {"ok": True, "event": event_type, "result": result}

        # Everything else is routed by the YAML engine.
        return await engine.dispatch(event_type, payload)

    # ── Rep approves (or skips) a held draft ───────────────────────────
    async def approve_outreach(self, lead_id: int, decision: str = "send") -> dict:
        async with SessionLocal() as s:
            lead = (await s.execute(select(Lead).where(Lead.id == lead_id))).scalars().first()
            draft = (
                await s.execute(
                    select(Interaction)
                    .where(Interaction.lead_id == lead_id, Interaction.outcome == "pending_approval")
                    .order_by(Interaction.created_at.desc())
                )
            ).scalars().first()
            if not lead or not draft:
                return {"ok": False, "detail": "no pending draft"}
            if decision == "skip":
                draft.outcome = "skipped"
                lead.status = "qualified"
                await s.commit()
                await log_event("Orchestrator", "approval", f"Rep skipped draft for {lead.company_name}", lead_id=lead_id, level="info")
                return {"ok": True, "detail": "skipped"}
            draft.outcome = "sent"
            draft.sent_at = datetime.now(timezone.utc)
            lead.status = "contacted"
            lead.last_touched_at = datetime.now(timezone.utc)
            company, channel = lead.company_name, draft.channel
            to_email = lead.email
            subject = draft.subject or f"Quick note for {company}"
            body = draft.content or ""
            await s.commit()

        # Actually deliver it. Email goes out through the provider waterfall
        # (Resend → SendGrid → SMTP → mock); other channels mirror to the dashboard.
        delivery = ""
        if channel == "email" and to_email:
            from backend.app.services.comms import send_email

            res = await send_email(to_email, subject, body)
            delivery = f" via {res.get('provider')}" if res.get("sent") else " (delivery failed — logged)"
        await log_event("Orchestrator", "approval", f"Rep approved — sent {channel} to {company}{delivery}", lead_id=lead_id, level="positive")
        return {"ok": True, "detail": "sent"}

    # ── Outcome buttons (Great fit / Wrong fit / Follow up / Closed) ───
    async def record_outcome(self, payload: dict) -> dict:
        lead_id = payload["lead_id"]
        outcome_type = payload["outcome_type"]
        async with SessionLocal() as s:
            lead = (await s.execute(select(Lead).where(Lead.id == lead_id))).scalars().first()
            if not lead:
                return {"ok": False, "detail": "lead not found"}
            s.add(
                Outcome(
                    lead_id=lead_id,
                    outcome_type=outcome_type,
                    notes=payload.get("notes"),
                    closed_value=payload.get("closed_value"),
                )
            )
            lead.status = {"closed": "closed", "wrong_fit": "disqualified"}.get(outcome_type, lead.status)
            company = lead.company_name
            await s.commit()

        # Instant feedback into the Fit Model via the YAML-resolved Memory Agent.
        applied = await engine.invoke_agent_fn("memory_agent", "apply_outcomes")
        follow = {
            "great_fit": "I'll find more leads like this one.",
            "wrong_fit": "I'll avoid companies like this.",
            "follow_up": "I'll handle the follow-up sequence.",
            "closed": "Logged to CRM and added to the winning pattern.",
        }.get(outcome_type, "")
        await log_event(
            "Orchestrator", "outcome",
            f"{company}: marked '{outcome_type}'. {follow} (Fit Model retuned from {applied} outcomes)",
            lead_id=lead_id, level="positive",
        )
        return {"ok": True, "detail": follow, "outcomes_applied": applied}

    # ── Mode B: Target Accounts (Manual Import) ────────────────────────
    async def manual_import(self, urls: list[str]) -> dict:
        async with SessionLocal() as s:
            created = 0
            for url in urls:
                if not url.strip():
                    continue
                domain = url.strip().replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
                existing = (await s.execute(select(DiscoveredCompany).where(DiscoveredCompany.domain == domain))).scalars().first()
                if not existing:
                    dc = DiscoveredCompany(
                        company_name=domain.split(".")[0].title(),
                        domain=domain,
                        discovery_source="manual",
                        status="discovered"
                    )
                    s.add(dc)
                    created += 1
            await s.commit()
            
        if created > 0:
            await log_event("Orchestrator", "manual_import", f"Imported {created} target accounts. Handing off to the verification engine.", level="info")
            # Use the YAML engine to kick the discovery cycle to verify these.
            import asyncio
            asyncio.create_task(engine.dispatch("discovery_cycle", {}))
            
        return {"ok": True, "created": created}


orchestrator = Orchestrator()
