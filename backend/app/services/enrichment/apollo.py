"""Apollo.io — the ONLY contact source. No waterfall, no mock, no fabricated
contacts: if Apollo doesn't return a verified person, the lead simply waits.

Credits are treated as precious:
- `enrich()` is only ever called from the human-approved path
  (POST /api/leads/{id}/enrich) — nothing in the autonomous loop calls it.
- One enrichment = one people-search + one email reveal (`people/match`),
  i.e. ~1 export credit per company.
"""
from __future__ import annotations

import httpx

from ...config import settings

_BASE = "https://api.apollo.io/api/v1"

# Used only when the Brain has no buyer titles yet.
_DEFAULT_TITLES = ["Founder", "CEO", "Co-Founder", "COO", "VP Sales", "Head of Sales", "Head of Growth"]
_SENIORITIES = ["owner", "founder", "c_suite", "vp", "head", "director"]


def _headers() -> dict:
    return {
        "X-Api-Key": settings.apollo_api_key,
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
    }


async def _post(client: httpx.AsyncClient, path: str, body: dict) -> tuple[dict | None, str]:
    """POST to Apollo; returns (json, error). Error strings are short and loggable."""
    try:
        r = await client.post(f"{_BASE}{path}", json=body, headers=_headers())
    except Exception as exc:
        return None, f"apollo unreachable: {exc}"
    if r.status_code == 401 or r.status_code == 403:
        return None, "apollo key rejected (401/403)"
    if r.status_code == 422:
        return None, f"apollo rejected the query: {r.text[:160]}"
    if r.status_code >= 400:
        return None, f"apollo error {r.status_code}: {r.text[:160]}"
    try:
        return r.json(), ""
    except Exception:
        return None, "apollo returned non-JSON"


async def _find_domain(client: httpx.AsyncClient, company: str) -> str | None:
    """Resolve a company name to its primary domain via Apollo org search."""
    data, err = await _post(client, "/mixed_companies/search", {
        "q_organization_name": company,
        "page": 1,
        "per_page": 1,
    })
    if err or not data:
        return None
    orgs = (data.get("organizations") or []) + (data.get("accounts") or [])
    return orgs[0].get("primary_domain") if orgs else None


async def enrich(company: str, domain: str | None = None, titles: list[str] | None = None) -> dict:
    """Find the decision-maker at `company` and reveal their work email.

    Returns:
        {found: bool, contact: {name, first_name, last_name, title, email,
         linkedin_url, phone}, credits_used: int, error: str}
    """
    if not settings.apollo_api_key:
        return {"found": False, "contact": {}, "credits_used": 0,
                "error": "apollo_not_configured"}

    wanted_titles = [t for t in (titles or []) if t] or _DEFAULT_TITLES

    async with httpx.AsyncClient(timeout=30) as client:
        if not domain:
            domain = await _find_domain(client, company)
        if not domain:
            return {"found": False, "contact": {}, "credits_used": 0,
                    "error": "couldn't resolve the company's domain on Apollo"}

        # 1) People search (api_search — no credits). Results are masked:
        #    we get the person id, first name, title, and has_email flags.
        data, err = await _post(client, "/mixed_people/api_search", {
            "q_organization_domains_list": [domain],
            "person_titles": wanted_titles,
            "person_seniorities": _SENIORITIES,
            "page": 1,
            "per_page": 5,
        })
        if err:
            return {"found": False, "contact": {}, "credits_used": 0, "error": err}

        people = (data.get("people") or []) + (data.get("contacts") or [])
        if not people:
            return {"found": False, "contact": {}, "credits_used": 0,
                    "error": "no matching decision-maker on Apollo"}
        # Prefer someone whose email Apollo actually holds — that's what we pay for.
        person = next((p for p in people if p.get("has_email")), people[0])

        # 2) Reveal by person id — THE credit spend. Never reveal personal emails.
        matched, m_err = await _post(client, "/people/match", {
            "id": person.get("id"),
            "reveal_personal_emails": False,
        })
        revealed = (matched or {}).get("person") or {}
        email = revealed.get("email")
        if email and "email_not_unlocked" in email:
            email = None

        contact = {
            "name": revealed.get("name")
                or f"{person.get('first_name', '')} {revealed.get('last_name', '')}".strip()
                or person.get("first_name"),
            "first_name": revealed.get("first_name") or person.get("first_name"),
            "last_name": revealed.get("last_name"),
            "title": revealed.get("title") or person.get("title"),
            "email": email,
            "linkedin_url": revealed.get("linkedin_url"),
            "phone": ((revealed.get("phone_numbers") or [{}])[0] or {}).get("sanitized_number"),
        }
        return {
            "found": bool(contact["name"] and (email or contact["linkedin_url"])),
            "contact": contact,
            "credits_used": 1 if email else 0,
            "error": m_err or ("" if email else "Apollo matched the person but returned no email"),
        }
