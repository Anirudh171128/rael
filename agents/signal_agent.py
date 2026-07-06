"""Signal Agent — runs every 6h. Scans sources, scores each signal for ICP
relevance, and creates/updates a lead when the signal is strong enough.

YAML-driven: signal_threshold, boost_types, boost_amount from rael.yaml config.
Tools resolved from the engine.
"""
from __future__ import annotations

from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models import Lead, Signal

from .base import AgentResult, load_fit
from .graph import engine


def _cfg(key: str, default=None):
    """Read from rael.yaml → agents.signal_agent.config."""
    return engine.get_agent_config("signal_agent", key, default)


def _tools():
    """Resolve tool callables from the YAML registry."""
    return engine.get_agent_tools("signal_agent")


def _summarize(sig: dict) -> str:
    d = sig.get("signal_data", {})
    t = sig["signal_type"]
    if t == "funding":
        return f"raised {d.get('round', 'a round')} (${d.get('amount_usd', 0):,})"
    if t == "hiring":
        return f"hiring {len(d.get('roles', []))} sales roles"
    if t == "intent":
        return f'posted: "{d.get("quote", "")}"'
    if t == "leadership":
        return d.get("change", "leadership change")
    if t == "growth":
        return f"+{d.get('linkedin_follower_delta_30d', 0)} LinkedIn followers in 30d"
    return t


async def run() -> AgentResult:
    fit = await load_fit()
    tools = _tools()
    scan_signals_fn = tools["scan_signals"]
    log_event = tools["log_event"]

    # Config from YAML.
    signal_threshold = _cfg("signal_threshold", 50)
    boost_types = _cfg("boost_types", ["intent", "funding"])
    boost_amount = _cfg("boost_amount", 10)

    raw = await scan_signals_fn()
    created: list[int] = []
    logs: list[tuple] = []  # (desc, lead_id, level)

    async with SessionLocal() as s:
        for sig in raw:
            company = sig["company_name"]
            # ICP relevance: source confidence, boosted for the strongest signal types.
            score = min(100, sig["raw_strength"] + (boost_amount if sig["signal_type"] in boost_types else 0))
            summary = _summarize(sig)

            row = Signal(
                company_name=company,
                signal_type=sig["signal_type"],
                signal_data=sig.get("signal_data"),
                source=sig.get("source"),
                score=score,
            )
            s.add(row)

            if score < signal_threshold:
                logs.append((f"{company}: {sig['signal_type']} signal below threshold ({score}) — watching", None, "info"))
                continue

            existing = (await s.execute(select(Lead).where(Lead.company_name == company))).scalars().first()
            if existing:
                row.acted_on = True
                row.lead_id = existing.id
                logs.append((f"New {sig['signal_type']} signal for {company} — refreshed existing lead", existing.id, "info"))
                continue

            lead = Lead(
                company_name=company,
                status="identified",
                trigger_event=f"{sig['signal_type']}: {summary}",
                trigger_source=sig.get("source"),
            )
            s.add(lead)
            await s.flush()  # assign lead.id
            row.acted_on = True
            row.lead_id = lead.id
            created.append(lead.id)
            logs.append(
                (f"Detected {sig['signal_type']} signal for {company} — new lead created, score {score}", lead.id, "positive")
            )
        await s.commit()

    for desc, lead_id, level in logs:
        await log_event("Signal Agent", "signal_scan", desc, lead_id=lead_id, level=level)

    # Emit message on the bus per YAML spec.
    if created:
        engine.emit(
            sender="signal_agent", recipient="discovery_agent",
            msg_type="event", payload={"created_lead_ids": created},
        )

    return AgentResult(
        agent="Signal Agent",
        summary=f"Scanned {len(raw)} signals, created {len(created)} leads",
        next_action="enrich_new_leads",
        data={"created_lead_ids": created},
        level="positive" if created else "info",
    )
