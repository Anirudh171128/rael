"""Shared agent machinery: the result envelope, Fit Model loading, and the
scoring function every qualification decision runs through."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models import FitModel


@dataclass
class AgentResult:
    agent: str
    summary: str
    next_action: str | None = None          # hint the orchestrator may act on
    data: dict = field(default_factory=dict)
    level: str = "info"                      # info | positive | attention | urgent


# ─── Fit Model ──────────────────────────────────────────────────────────
@dataclass
class Fit:
    size_min: int = 50
    size_max: int = 500
    industries: list[str] = field(default_factory=list)
    geographies: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    pain: str = ""
    product: str = ""
    weights: dict[str, float] = field(default_factory=dict)

    def w(self, key: str) -> float:
        return self.weights.get(key, 1.0)


async def load_fit() -> Fit:
    """Hydrate the Fit Model from its rows. Dimension weights live as
    `weight:<dimension>` rows so the Memory Agent can tune them from outcomes."""
    async with SessionLocal() as s:
        rows = (await s.execute(select(FitModel))).scalars().all()
    params = {r.parameter_name: r.parameter_value for r in rows}
    weights = {
        r.parameter_name.split(":", 1)[1]: r.weight
        for r in rows
        if r.parameter_name.startswith("weight:")
    }

    def _list(key: str) -> list[str]:
        v = params.get(key)
        return [x.strip().lower() for x in v.split(",")] if v else []

    return Fit(
        size_min=int(params.get("icp_company_size_min", 50) or 50),
        size_max=int(params.get("icp_company_size_max", 500) or 500),
        industries=_list("icp_industries"),
        geographies=_list("icp_geographies"),
        titles=_list("icp_titles"),
        pain=params.get("pain_solved", "") or "",
        product=params.get("product_description", "") or "",
        weights=weights,
    )


_INDIA_METROS = (
    "mumbai", "delhi", "new delhi", "bengaluru", "bangalore", "hyderabad", "chennai",
    "kolkata", "pune", "ahmedabad", "gurgaon", "gurugram", "noida", "jaipur", "kochi",
    "chandigarh", "surat", "indore", "nagpur", "coimbatore",
)
_REGION_MEMBERS = {
    "north america": ("united states", "usa", "u.s.", "america", "canada", "mexico"),
    "europe": ("united kingdom", "uk", "britain", "england", "germany", "france",
               "spain", "italy", "netherlands", "ireland", "sweden", "poland", "portugal"),
}


def _geo_match(geography: str, fit_geos: list[str]) -> bool:
    """Match a verified HQ geography ('United Kingdom', 'India', 'Mumbai') against the
    Fit Model's geography entries, which use the onboarding form's vocabulary
    ('india (all)', 'tier 1 cities', 'north america'). Parentheticals are scope
    qualifiers; tier-city entries mean Indian cities."""
    g = geography.lower().strip()
    for f in fit_geos:
        base = f.split("(")[0].strip()  # "india (all)" → "india"
        if not base:
            continue
        if "tier" in base and "cities" in base:  # tier-1/2 cities ⇒ India
            base = "india"
        if base in g or g in base:
            return True
        # A verified Indian city satisfies an India-scoped ICP even without "India".
        if base == "india" and any(city in g for city in _INDIA_METROS):
            return True
        # Country-in-region: "north america" covers US/Canada; "europe" covers UK/DE/…
        if any(m in g for m in _REGION_MEMBERS.get(base, ())):
            return True
    return False


def geo_mismatch(geography: str | None, fit_geos: list[str]) -> bool:
    """True only when geography is KNOWN and clearly outside the ICP. Unknown
    geography (None) is never a mismatch — we don't punish an unreadable site."""
    if not geography or not fit_geos:
        return False
    return not _geo_match(geography, fit_geos)


def score_lead(
    *,
    company_size: int | None,
    industry: str | None,
    title: str | None,
    geography: str | None,
    trigger_strength: int,
    fit: Fit,
) -> tuple[int, str]:
    """Weighted 0-100 fit score + 2-3 sentence reasoning. This is Rael's judgment."""
    parts: list[tuple[str, float, float, str]] = []  # (dim, got, max, note)

    # Company size within ICP band.
    w = fit.w("size")
    if company_size and fit.size_min <= company_size <= fit.size_max:
        parts.append(("size", w, w, f"company size {company_size} fits ICP"))
    elif company_size:
        parts.append(("size", 0.0, w, f"company size {company_size} outside ICP"))

    # Industry match (substring either direction). A KNOWN off-ICP industry scores 0;
    # an UNKNOWN industry (site unreadable) skips the dimension — same rule as geography,
    # so we never reject a real prospect just because we couldn't read its vertical.
    w = fit.w("industry")
    if industry and any(i in industry.lower() or industry.lower() in i for i in fit.industries):
        parts.append(("industry", w, w, f"industry '{industry}' matches"))
    elif industry and fit.industries:
        parts.append(("industry", 0.0, w, f"industry '{industry}' off-ICP"))

    # Title = decision maker.
    w = fit.w("title")
    if title and any(t in title.lower() for t in fit.titles):
        parts.append(("title", w, w, f"reached a decision maker ({title})"))
    elif fit.titles:
        parts.append(("title", 0.4 * w, w, "contact is not the primary decision maker"))

    # Geography. A KNOWN mismatch scores 0 (a UK company under an India-only ICP must
    # lose points, not skip the dimension); unknown geography stays out of the
    # denominator so we never punish a company for an unreadable site.
    w = fit.w("geography")
    if geography and fit.geographies:
        if _geo_match(geography, fit.geographies):
            parts.append(("geo", w, w, f"{geography} in target geography"))
        else:
            parts.append(("geo", 0.0, w, f"{geography} outside target geography"))

    # Trigger strength dominates — a fresh buying signal is the whole point.
    w = fit.w("trigger") * 1.5
    parts.append(("trigger", (trigger_strength / 100) * w, w, "active buying signal present"))

    got = sum(p[1] for p in parts)
    mx = sum(p[2] for p in parts) or 1.0
    score = max(0, min(100, round((got / mx) * 100)))

    positives = [p[3] for p in parts if p[1] >= 0.6 * p[2]]
    reasoning = ". ".join(positives[:3]) or "weak overall fit"
    return score, reasoning[0].upper() + reasoning[1:] + "."
