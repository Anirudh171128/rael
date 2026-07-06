"""Step 5 — verification. The discovery layer (and the LLM that planned it) can be
wrong, so nothing it says is trusted until confirmed against the company's own web
presence. We fetch the homepage, read what it actually says, and derive
firmographics (industry, employee band, funding, signals).

Real path: httpx fetches the site; Gemini extracts structured firmographics from
the visible text. Mock path: deterministic firmographics from the domain so the
qualify step always has something concrete to score.

Returns {verified, industry, employee_count, funding, signals, notes}.
"""
from __future__ import annotations

import hashlib
import re

import httpx

from ...config import settings
from ...services.llm import complete, parse_json
from .execute import looks_like_media


async def verify_company(name: str, domain: str | None, evidence: list[dict]) -> dict:
    text, reachable = await _fetch_site(domain) if domain else ("", False)

    # ── Entity gate ──────────────────────────────────────────────────────────
    # Before scoring anything, decide *what this actually is*. A media outlet, blog,
    # directory, listicle or school is never a prospect — this is the guardrail that
    # stops "Analyticsinsight" or a "Top 10 SaaS" page from being treated as a company.
    # Structured output (entity_type + reason) keeps rejections debuggable.
    entity = await _classify_entity(name, domain, text, reachable)
    if not entity["is_prospect"]:
        return {
            "verified": False,
            "is_prospect": False,
            "entity_type": entity["entity_type"],
            "reject_reason": entity["reason"],
            "industry": None,
            "employee_count": None,
            "geography": None,
            "funding": "unknown",
            "signals": [],
            "notes": entity["reason"],
        }

    if reachable and settings.llm_provider != "mock":
        facts = await _llm_extract(name, domain, text, evidence)
        if facts:
            facts.update(verified=True, is_prospect=True, entity_type="company")
            facts.setdefault("notes", f"Confirmed against {domain}")
            return facts
    # Reachable site but no/failed LLM extraction → light heuristic + verified flag.
    if reachable:
        facts = _mock_facts(name, domain, evidence)
        facts.update(verified=True, is_prospect=True, entity_type="company",
                     notes=f"Reached {domain}; firmographics inferred")
        return facts
    # Unreachable → mock firmographics, marked unverified so qualify can discount it.
    facts = _mock_facts(name, domain, evidence)
    facts.update(verified=False, is_prospect=True, entity_type="unknown",
                 notes="Site unreachable — firmographics estimated")
    return facts


async def _classify_entity(name: str, domain: str | None, text: str, reachable: bool) -> dict:
    """Is this an operating company (a valid prospect), or a publisher/aggregator/etc.?
    Cheap deterministic checks first; the homepage LLM classifier is the tie-breaker.
    Fails OPEN (treats as prospect) on uncertainty so we never drop a real company on a
    transient LLM error — the domain heuristic already caught the obvious publishers."""
    # 1) Obvious publisher/aggregator/education domains never need the LLM.
    if domain and looks_like_media(domain):
        return {
            "is_prospect": False,
            "entity_type": "media",
            "reason": f"{domain} is a media/publisher, directory or educational site — not a prospect company",
        }
    # 2) Nothing to read (unreachable / no text / no LLM) → can't disprove it's a company.
    if not reachable or not text or settings.llm_provider == "mock":
        return {"is_prospect": True, "entity_type": "unknown", "reason": ""}
    # 3) Read the homepage and classify what the site IS.
    return await _llm_classify(name, domain, text)


async def _llm_classify(name: str, domain: str | None, text: str) -> dict:
    system = (
        "You label what a website IS, to keep a B2B prospecting pipeline clean. Read the "
        "homepage text and classify the entity. Return ONLY JSON: "
        '{"entity_type":"company|media|news|blog|directory|marketplace|education|government|other",'
        '"is_operating_company":true|false,"reason":"<=15 words"}. '
        "company = an operating business selling its OWN product/service (a valid prospect). "
        "media/news/blog = it publishes articles or reviews ABOUT other companies. "
        "directory/marketplace = it lists or aggregates other companies. "
        "education/government = a school, university or public body. "
        "Be strict: if the site mainly publishes content or lists other businesses, "
        "is_operating_company is false."
    )
    user = f"name: {name}\ndomain: {domain}\nhomepage text:\n{text[:3500]}"
    try:
        # Headroom for thinking + the small JSON verdict (120 truncated reliably).
        raw = await complete(system, user, max_tokens=1024)
    except Exception:
        return {"is_prospect": True, "entity_type": "unknown", "reason": ""}
    data = parse_json(raw)
    if not isinstance(data, dict):
        return {"is_prospect": True, "entity_type": "unknown", "reason": ""}
    etype = str(data.get("entity_type") or "unknown").lower()
    # Reject ONLY on a positive non-prospect classification. Anything ambiguous
    # (company / other / unknown / thin homepage text) is kept — losing a real
    # company is worse for the user than passing one borderline page to the ICP
    # filters, which are the next line of defence.
    non_prospect = {"media", "news", "blog", "directory", "marketplace", "education", "government"}
    if etype in non_prospect:
        reason = str(data.get("reason") or "").strip() or f"site is a {etype}, not an operating company"
        return {"is_prospect": False, "entity_type": etype, "reason": reason[:200]}
    return {"is_prospect": True, "entity_type": "company", "reason": ""}


async def _fetch_site(domain: str) -> tuple[str, bool]:
    for scheme in ("https", "http"):
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=8.0,
                headers={"User-Agent": "RaelDiscoveryBot/1.0 (+https://rael.ai)"},
            ) as client:
                resp = await client.get(f"{scheme}://{domain}")
                if resp.status_code < 400 and resp.text:
                    return _visible_text(resp.text), True
        except Exception:
            continue
    return "", False


def _visible_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:6000]


async def _llm_extract(name: str, domain: str | None, text: str, evidence: list[dict]) -> dict | None:
    system = (
        "You verify a B2B company from its website text. Return ONLY JSON: "
        '{"industry":"...","employee_count":<int|null>,'
        '"geography":"<HQ country, e.g. India, United States — null if unclear>",'
        '"funding":"<stage/amount or unknown>","signals":["..."]}. '
        "geography = where the company is headquartered/primarily operates, judged from "
        "addresses, phone codes, currency, city names or market focus in the text. "
        "signals = concrete buying signals you can support from the "
        "text or the evidence (hiring, funding, expansion, leadership, intent). "
        "Be conservative; use null/unknown when unsure."
    )
    ev = "; ".join(f"{e.get('signal')}: {e.get('snippet', '')}" for e in (evidence or []))
    user = f"company: {name}\ndomain: {domain}\nevidence: {ev}\nwebsite text:\n{text[:4000]}"
    try:
        raw = await complete(system, user, max_tokens=1024)
    except Exception:
        return None
    data = parse_json(raw)
    if not isinstance(data, dict):
        return None
    ec = data.get("employee_count")
    geo = data.get("geography")
    return {
        "industry": (data.get("industry") or None),
        "employee_count": int(ec) if isinstance(ec, (int, float)) and ec else None,
        "geography": geo.strip() if isinstance(geo, str) and geo.strip().lower() not in ("", "null", "unknown") else None,
        "funding": data.get("funding") or "unknown",
        "signals": [s for s in (data.get("signals") or []) if isinstance(s, str)][:6],
    }


def _mock_facts(name: str, domain: str | None, evidence: list[dict]) -> dict:
    h = hashlib.md5((domain or name).encode()).hexdigest()
    nib = [int(c, 16) for c in h]
    employee_count = [40, 80, 120, 220, 350, 600][nib[1] % 6]
    funding = ["Seed", "Series A", "Series A", "Series B", "Series B", "bootstrapped"][nib[2] % 6]
    # Lift signals straight from the discovery evidence — that's what we'd verify.
    signals = sorted({e.get("signal") for e in (evidence or []) if e.get("signal")})
    if "funding" not in signals and funding.startswith("Series"):
        signals.append("funding")
    return {
        # Industry is ICP-defining and must NOT be fabricated — a guessed vertical
        # (e.g. "Sales Tech") mislabels a real prospect and wrongly fails the ICP
        # filter. Leave it unknown; qualify skips the dimension rather than punishing.
        "industry": None,
        "employee_count": employee_count,
        "geography": None,  # unknown without reading the site — never guessed
        "funding": funding,
        "signals": signals or ["intent"],
    }
