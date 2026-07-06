"""Brain Agent — Step 2 of the architecture.

After training, Rael doesn't store raw answers and call it understanding. This
agent asks the LLM one question: *given what we sell and who's bought, what does
a prospect look like and what signals betray them?* The result is a structured
Brain — industry, buyers, pain_signals, negative_signals, search_themes — that
the discovery engine reasons over. Persisted to `product_brain`; rebuilt when
the Fit Model changes.

YAML-driven: system prompt, max_tokens, and all fallback values come from
rael.yaml → agents.brain_agent.config.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import desc, select

from backend.app.database import SessionLocal
from backend.app.models import FitModel, ProductBrain

from .base import AgentResult
from .graph import engine


def _cfg(key: str, default=None):
    """Read from rael.yaml → agents.brain_agent.config."""
    return engine.get_agent_config("brain_agent", key, default)


def _tools():
    """Resolve tool callables from the YAML registry."""
    return engine.get_agent_tools("brain_agent")


async def _fit_dict() -> dict[str, str]:
    async with SessionLocal() as s:
        rows = (await s.execute(select(FitModel))).scalars().all()
    return {r.parameter_name: (r.parameter_value or "") for r in rows if not r.parameter_name.startswith("weight:")}


def _fingerprint(fit: dict) -> str:
    blob = json.dumps(fit, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


async def latest_brain() -> ProductBrain | None:
    async with SessionLocal() as s:
        return (
            await s.execute(select(ProductBrain).order_by(desc(ProductBrain.created_at)))
        ).scalars().first()


async def ensure_brain() -> dict:
    """Return the current understanding, building (or rebuilding) it if the Fit
    Model has changed since the last brain was distilled."""
    fit = await _fit_dict()
    fp = _fingerprint(fit)
    existing = await latest_brain()
    if existing and existing.fit_fingerprint == fp and existing.understanding:
        return existing.understanding
    res = await run()
    return res.data.get("understanding", {})


async def run() -> AgentResult:
    """Distil the Fit Model into a Brain and persist it."""
    tools = _tools()
    log_event = tools["log_event"]

    fit = await _fit_dict()
    fp = _fingerprint(fit)

    understanding, built_from = await _build(fit)
    summary = _summary(understanding)

    async with SessionLocal() as s:
        s.add(
            ProductBrain(
                summary=summary,
                understanding=understanding,
                built_from=built_from,
                fit_fingerprint=fp,
            )
        )
        await s.commit()

    await log_event(
        "Brain Agent", "brain_built",
        f"Built my understanding of who we sell to — {summary}",
        level="positive",
        extra={"built_from": built_from, "understanding": understanding},
    )

    # Emit message on the bus per YAML spec.
    engine.emit(
        sender="brain_agent", recipient="discovery_agent",
        msg_type="data_update",
        payload={"brain_config": understanding},
    )

    return AgentResult(
        "Brain Agent",
        f"Understanding built ({built_from})",
        next_action="discover",
        data={"understanding": understanding},
        level="positive",
    )


async def _build(fit: dict) -> tuple[dict, str]:
    from backend.app.config import settings

    if settings.llm_provider != "mock":
        u = await _llm_build(fit)
        if u:
            return u, settings.llm_provider
    return _template_build(fit), "mock"


async def _llm_build(fit: dict) -> dict | None:
    tools = _tools()
    complete_fn = tools["llm_complete"]
    parse_json_fn = tools["llm_parse_json"]

    # System prompt and max_tokens from YAML config.
    system = _cfg("system_prompt", "")
    max_tokens = _cfg("max_tokens", 600)

    user = (
        f"Product: {fit.get('product_description', '')}\n"
        f"Target companies we want to reach (in India): {fit.get('targets', '')}\n"
        f"Market: India only"
    )
    try:
        raw = await complete_fn(system, user, max_tokens=max_tokens)
    except Exception:
        return None
    data = parse_json_fn(raw)
    if not isinstance(data, dict) or not data.get("buyers"):
        return None

    def _l(k):
        v = data.get(k)
        return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []

    # Fallbacks from YAML config.
    fallback_buyers = _cfg("fallback_buyers", ["Founder", "VP Sales"])

    return {
        "industry": data.get("industry") or fit.get("targets", "") or fit.get("icp_industries", ""),
        "geographies": _clean_geos(fit.get("icp_geographies", "")),
        "buyers": _l("buyers") or _split(fit.get("icp_titles", "")) or fallback_buyers,
        "pain_signals": _l("pain_signals"),
        "negative_signals": _l("negative_signals") or _split(fit.get("exclusions", "")),
        "competitive_signals": _l("competitive_signals") or _split(fit.get("competitors", "")),
        "search_themes": _l("search_themes"),
    }


def _split(v: str) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def _clean_geos(v: str) -> list[str]:
    """ICP geographies from onboarding ('India (All)', 'Tier 1 Cities') → clean market
    names the search planner can scope queries to, dropping parenthetical scope hints."""
    out: list[str] = []
    for g in _split(v):
        base = g.split("(")[0].strip()
        if "tier" in base.lower() and "cities" in base.lower():
            base = "India"  # onboarding's tier-city entries are Indian metros
        if base and base.lower() not in (x.lower() for x in out):
            out.append(base)
    return out


def _template_build(fit: dict) -> dict:
    """Mock / fallback brain using YAML-defined defaults."""
    return {
        "industry": fit.get("targets", "") or fit.get("icp_industries", "") or "B2B SaaS",
        "geographies": _clean_geos(fit.get("icp_geographies", "")),
        "buyers": _split(fit.get("icp_titles", "")) or _cfg("fallback_buyers", ["Founder", "VP Sales", "CRO"]),
        "pain_signals": _cfg("fallback_pain_signals", [
            "hiring SDRs or AEs",
            "recently funded",
            "new sales leader joined",
            "expanding outbound",
            "scaling go-to-market",
        ]),
        "negative_signals": (
            _split(fit.get("exclusions", ""))
            + _split(fit.get("lost_deals_reasons", ""))
        ) or _cfg("fallback_negative_signals", ["under 20 employees", "no sales team"]),
        "competitive_signals": _split(fit.get("competitors", "")) or _cfg("fallback_competitive_signals", []),
        "search_themes": _cfg("fallback_search_themes", ["scaling sales in India", "outbound efficiency", "recently funded India"]),
    }


def _summary(u: dict) -> str:
    buyers = ", ".join(u.get("buyers", [])[:3]) or "buyers"
    industry = u.get("industry", "") or "the market"
    return f"sell into {industry}, reach {buyers}, hunt for {len(u.get('pain_signals', []))} pain signals"
