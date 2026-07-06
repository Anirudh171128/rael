"""Step 3 — Gemini turns the Brain into a *search plan*: the concrete queries that
would surface likely prospects. Rael never asks the LLM 'give me companies' (it
would hallucinate them); it asks 'what should I search for?' and lets the browser
find the real ones.

Returns a list of {query, source} where source ∈ google | google_news | careers.
Falls back to a template-driven plan when no LLM is configured.
"""
from __future__ import annotations

from ...services.llm import complete, parse_json

_SOURCES = ("google", "google_news", "careers")


async def generate_search_plan(brain: dict, *, max_queries: int = 6) -> list[dict]:
    """Produce up to `max_queries` search instructions from the product Brain."""
    plan = await _llm_plan(brain, max_queries) if _has_llm() else []
    if not plan:
        plan = _template_plan(brain)
    # Normalise + clamp.
    out: list[dict] = []
    seen: set[str] = set()
    for item in plan:
        q = (item.get("query") or "").strip()
        src = item.get("source") if item.get("source") in _SOURCES else "google"
        if not q or q.lower() in seen:
            continue
        seen.add(q.lower())
        out.append({"query": q, "source": src})
        if len(out) >= max_queries:
            break
    return out


def _has_llm() -> bool:
    from ...config import settings

    return settings.llm_provider != "mock"


def _geo_phrase(brain: dict) -> str:
    """The market to scope searches to, from the ICP geography — not hardcoded."""
    geos = [g for g in (brain.get("geographies") or []) if g]
    return geos[0] if geos else ""


async def _llm_plan(brain: dict, max_queries: int) -> list[dict]:
    geo = _geo_phrase(brain)
    scope = f" in {geo}" if geo else ""
    system = (
        "You are a B2B prospecting researcher building a TARGET ACCOUNT LIST. Given a "
        "product 'brain', output web searches that surface REAL OPERATING COMPANIES that "
        "fit the ICP — the actual businesses we could sell to, named directly. "
        "Balance two kinds of query: (1) COMPANY-DISCOVERY searches that enumerate "
        "operating companies in the segment (e.g. 'directory of <segment> companies', "
        "'<segment> companies', 'list of <segment> providers', association / member lists); "
        "(2) SIGNAL searches that surface those same companies while showing a live buying "
        "signal (hiring, funding, expansion, new leadership, going digital). "
        "Do NOT write queries that mainly return news outlets, listicles, blogs, reports, "
        "'top 10' articles or job boards — we want the companies, not media about them. "
        f"{('Scope every query to ' + geo + ' (add the country/region or a major city where it helps). ') if geo else ''}"
        "Return ONLY JSON: "
        '{"searches":[{"query":"...","source":"google|google_news|careers"}]}. '
        f"At most {max_queries} searches. No prose."
    )
    user = (
        f"Industry / segment we sell into: {brain.get('industry', '')}\n"
        f"Market: {geo or 'unspecified'}\n"
        f"Buyers (decision makers): {', '.join(brain.get('buyers', []))}\n"
        f"Pain signals that mean they need us: {', '.join(brain.get('pain_signals', []))}\n"
        f"Negative signals (avoid): {', '.join(brain.get('negative_signals', []))}\n"
        f"Segment themes to enumerate companies from: {', '.join(brain.get('search_themes', []))}"
    )
    try:
        raw = await complete(system, user, max_tokens=1200)
    except Exception:
        return []
    data = parse_json(raw) or {}
    return data.get("searches", []) if isinstance(data, dict) else []


def _template_plan(brain: dict) -> list[dict]:
    """Deterministic plan from the Brain when no LLM is available — still grounded
    in the trained understanding, not random. Company-first: enumerate operating
    companies in the ICP segment, then layer buying-signal queries on top."""
    industry = (brain.get("industry", "") or "B2B").split(",")[0].strip()
    themes = brain.get("search_themes", []) or [f"{industry} companies"]
    geo = _geo_phrase(brain)
    g = f" {geo}" if geo else ""
    # Segment themes are the primary enumeration source (e.g. "travel agencies India").
    plan = [{"query": t if geo and geo.lower() in t.lower() else f"{t}{g}", "source": "google"}
            for t in themes[:4]]
    # A couple of signal-flavoured queries against the same segment.
    plan += [
        {"query": f"{industry} companies{g} hiring", "source": "careers"},
        {"query": f"{industry} companies{g} raise funding OR expansion", "source": "google_news"},
        {"query": f"list of {industry} companies{g}", "source": "google"},
    ]
    return plan
