"""Discovery Agent — the scouting loop (architecture steps 3-7).

    Brain → search plan → headless browser → verify → qualify → (promote to Lead)

YAML-driven: all tools resolved from the engine, all constants from
rael.yaml → agents.discovery_agent.config.
"""
from __future__ import annotations

from sqlalchemy import select

from backend.app.config import settings
from backend.app.database import SessionLocal
from backend.app.models import DiscoveredCompany, Lead, Signal

from . import brain_agent
from .base import AgentResult, Fit, load_fit, score_lead
from .graph import engine


def _cfg(key: str, default=None):
    """Read from rael.yaml → agents.discovery_agent.config."""
    return engine.get_agent_config("discovery_agent", key, default)


def _tools():
    """Resolve tool callables from the YAML registry."""
    return engine.get_agent_tools("discovery_agent")


async def run() -> AgentResult:
    fit = await load_fit()
    brain = await brain_agent.ensure_brain()

    # Tools resolved from YAML, not hardcoded imports.
    tools = _tools()
    generate_search_plan = tools["generate_search_plan"]
    execute_search_plan = tools["web_search"]
    verify_company = tools["verify_company"]
    log_event = tools["log_event"]

    plan = await generate_search_plan(brain, max_queries=settings.discovery_max_queries)
    await log_event(
        "Discovery Agent", "search_plan",
        f"Drew up {len(plan)} searches: " + " · ".join(p["query"] for p in plan[:5]),
        level="info", extra={"plan": plan},
    )

    # Hand the prospect profile to extraction so it pulls companies relevant to what
    # we sell, not any company a page happens to name.
    product_context = brain.get("industry", "") or ", ".join(brain.get("buyers", [])[:3])
    raw = await execute_search_plan(
        plan,
        per_query=settings.discovery_results_per_query,
        context=product_context,
    )

    fresh = await _filter_new(raw, brain)
    max_candidates = _cfg("max_candidates", 24)
    fresh = fresh[:max_candidates]
    await log_event(
        "Discovery Agent", "discovered",
        f"Browser surfaced {len(raw)} companies — {len(fresh)} are new to evaluate",
        level="info",
    )

    promoted: list[int] = []
    qualified_ct = 0

    rejected_ct = 0

    for cand in fresh:
        facts = await verify_company(cand["company_name"], cand.get("domain"), cand["evidence"])

        # Entity gate: media/publisher/aggregator/education sites are rejected upstream
        # of scoring — they were never a company, so the ICP filters never apply. Record
        # the rejection (status + reason) so it's diagnosable, then move on.
        if facts.get("is_prospect") is False:
            reason = facts.get("reject_reason") or "not an operating company"
            async with SessionLocal() as s:
                dc = DiscoveredCompany(
                    company_name=cand["company_name"],
                    domain=cand.get("domain"),
                    discovery_query=cand.get("query"),
                    discovery_source=cand.get("source"),
                    evidence=cand["evidence"],
                    verified=False,
                    verification_notes=reason,
                    fit_score=0,
                    reasoning=reason,
                    status="rejected",
                )
                s.add(dc)
                await s.flush()
                dc_id = dc.id
                await s.commit()
            rejected_ct += 1
            await log_event(
                "Discovery Agent", "rejected",
                f"Rejected {cand['company_name']} — {reason}",
                level="info",
                extra={"discovered_id": dc_id, "entity_type": facts.get("entity_type")},
            )
            continue

        score, reasoning, trigger = _qualify(cand, facts, fit)
        qualified = score >= settings.discovery_qualify_threshold and facts.get("verified", False)

        async with SessionLocal() as s:
            dc = DiscoveredCompany(
                company_name=cand["company_name"],
                domain=cand.get("domain"),
                discovery_query=cand.get("query"),
                discovery_source=cand.get("source"),
                evidence=cand["evidence"],
                verified=facts.get("verified", False),
                industry=facts.get("industry"),
                employee_count=facts.get("employee_count"),
                geography=facts.get("geography"),
                funding=facts.get("funding"),
                signals=facts.get("signals"),
                verification_notes=facts.get("notes"),
                fit_score=score,
                reasoning=reasoning,
                status="qualified" if qualified else ("verified" if facts.get("verified") else "rejected"),
            )
            s.add(dc)
            await s.flush()
            dc_id = dc.id

            if qualified:
                qualified_ct += 1
                lead_id = await _promote(s, cand, facts, score, reasoning, trigger)
                dc.status = "promoted"
                dc.lead_id = lead_id
                promoted.append(lead_id)
            await s.commit()

        if qualified:
            await log_event(
                "Discovery Agent", "qualified",
                f"{cand['company_name']} scored {score} — {reasoning} → new lead",
                lead_id=promoted[-1], level="positive",
                extra={"discovered_id": dc_id, "score": score},
            )
        else:
            await log_event(
                "Discovery Agent", "parked",
                f"{cand['company_name']} scored {score} — {reasoning}. Parked, watching.",
                level="info", extra={"discovered_id": dc_id, "score": score},
            )

    # Emit message through the engine bus.
    if promoted:
        engine.emit(
            sender="discovery_agent",
            recipient=engine.agents["discovery_agent"].emits_message.get("recipient", "qualification_agent"),
            msg_type="event",
            payload={"created_lead_ids": promoted},
        )

    return AgentResult(
        "Discovery Agent",
        f"Scouted {len(raw)} companies, rejected {rejected_ct} non-companies, "
        f"qualified {qualified_ct}, promoted {len(promoted)} leads",
        next_action="pipeline_new_leads",
        data={"created_lead_ids": promoted},
        level="positive" if promoted else "info",
    )


async def _filter_new(raw: list[dict], brain: dict) -> list[dict]:
    """Drop companies we already know (as a lead or prior discovery) and anything
    that trips a negative signal from the Brain."""
    negatives = [n.lower() for n in brain.get("negative_signals", [])]
    async with SessionLocal() as s:
        known_leads = {
            n.lower() for n in (await s.execute(select(Lead.company_name))).scalars().all()
        }
        known_disc = {
            n.lower() for n in (await s.execute(select(DiscoveredCompany.company_name))).scalars().all()
        }
    known = known_leads | known_disc
    out: list[dict] = []
    for c in raw:
        name = c["company_name"]
        if name.lower() in known:
            continue
        blob = (name + " " + " ".join(e.get("snippet", "") for e in c["evidence"])).lower()
        if any(neg and neg in blob for neg in negatives):
            continue
        out.append(c)
    return out


def _qualify(cand: dict, facts: dict, fit: Fit) -> tuple[int, str, int]:
    """Score a verified company against the Fit Model BEFORE any lead exists."""
    # Trigger strength map from YAML config.
    trigger_strength_map = _cfg("trigger_strength", {})
    default_trigger = _cfg("default_trigger", 50)
    unverified_penalty = _cfg("unverified_penalty", 15)

    sig_types = set(facts.get("signals") or []) | {e.get("signal") for e in cand["evidence"]}
    trigger = max((trigger_strength_map.get(t, default_trigger) for t in sig_types if t), default=default_trigger)
    score, reasoning = score_lead(
        company_size=facts.get("employee_count"),
        industry=facts.get("industry"),
        title=None,            # no contact at discovery time
        geography=facts.get("geography"),  # HQ country from verify — None if unreadable
        trigger_strength=trigger,
        fit=fit,
    )
    if not facts.get("verified", False):
        score = max(0, score - unverified_penalty)
        reasoning += " (unverified — site unreachable)"
    return score, reasoning, trigger


async def _promote(s, cand: dict, facts: dict, score: int, reasoning: str, trigger: int) -> int:
    """Create the Lead + the Signal that justifies it. The Lead enters the normal
    pipeline (enrich → re-qualify with a contact → outreach) from here."""
    ev = cand["evidence"][0] if cand["evidence"] else {}
    summary = ev.get("snippet") or f"{ev.get('signal', 'signal')} via {cand.get('source')}"
    lead = Lead(
        company_name=cand["company_name"],
        industry=facts.get("industry"),
        company_size=facts.get("employee_count"),
        geography=facts.get("geography"),
        fit_score=score,
        reasoning=reasoning,
        status="identified",
        trigger_event=f"{ev.get('signal', 'discovery')}: {summary}"[:280],
        trigger_source=f"discovery:{cand.get('source')}",
    )
    s.add(lead)
    await s.flush()
    s.add(
        Signal(
            company_name=cand["company_name"],
            signal_type=ev.get("signal", "intent"),
            signal_data={
                "query": cand.get("query"),
                "domain": cand.get("domain"),
                "funding": facts.get("funding"),
                "signals": facts.get("signals"),
                "evidence": cand["evidence"],
            },
            source=f"discovery:{cand.get('source')}",
            score=trigger,
            acted_on=True,
            lead_id=lead.id,
        )
    )
    return lead.id
