"""Signal sources. Live integrations require API keys (Crunchbase, NewsAPI,
PeopleDataLabs, LinkedIn). With no keys configured this returns nothing — there is
no mock/canned stream — so the app never shows fabricated companies. Rael's live
lead source is the discovery engine (see `agents/discovery_agent.py`).

Each signal: {company_name, signal_type, signal_data, source, raw_strength}.
`raw_strength` is the source's own 0-100 confidence; the Signal Agent re-scores
it against the Fit Model.
"""
from __future__ import annotations

from ...config import settings


async def scan_signals() -> list[dict]:
    """Return newly detected signals from the configured providers. No keys → no
    signals (never mock data)."""
    if settings.crunchbase_api_key or settings.newsapi_key or settings.peopledatalabs_api_key:
        # Live integration point — query each configured source here.
        ...
    return []
