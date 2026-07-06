"""Step 4 — execute the search plan and extract candidate companies.

Three executors, in priority order — all return the SAME shape:

    {company_name, domain, query, source, evidence:[{signal, source, url, snippet}]}

1. **Tavily** (preferred, live): a search API built for agents — real SERP results,
   no captchas. Used whenever `TAVILY_API_KEY` is set. When Tavily is active there is
   NO mock fallback: a query returns real companies or nothing, never fabricated names.
2. **Headless browser** (Playwright/Chromium): scrapes Google / News / careers directly.
   Brittle — Google blocks bots — so per-query failures fall back to the mock.
3. **Mock** (offline): a deterministic generator keyed off each query, so the
   discover → verify → qualify loop still runs with no key and no network.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import quote_plus, urlparse

from ...config import settings
from ...services.llm import complete, parse_json

_SERP = {
    "google": "https://www.google.com/search?q={q}&num=10",
    "google_news": "https://www.google.com/search?q={q}&tbm=nws&num=10",
    "careers": "https://www.google.com/search?q={q}+careers+jobs&num=10",
}
# Aggregator / noise domains that are never the prospect itself.
_NOISE = {
    "google.com", "youtube.com", "linkedin.com", "facebook.com", "twitter.com",
    "x.com", "wikipedia.org", "crunchbase.com", "glassdoor.com", "indeed.com",
    "bloomberg.com", "techcrunch.com", "forbes.com", "reddit.com", "medium.com",
    "yahoo.com", "ycombinator.com", "g2.com", "capterra.com",
    # job boards / listing + news aggregators — they appear as the SERP domain, but
    # the real prospect company is named *inside* the page (LLM extraction handles it).
    "ziprecruiter.com", "builtin.com", "builtinsf.com", "builtinnyc.com", "lever.co",
    "greenhouse.io", "remoterocketship.com", "remotequota.com", "wellfound.com",
    "angel.co", "monster.com", "dice.com", "simplyhired.com", "trendhunter.com",
    "arstechnica.com", "fintechfutures.com", "thefintechtimes.com", "mobihealthnews.com",
    "businesswire.com", "prnewswire.com", "globenewswire.com", "venturebeat.com",
    "theverge.com", "cnbc.com", "reuters.com", "sifted.eu", "eu-startups.com",
    "investopedia.com", "analyticsinsight.net", "yourstory.com", "inc42.com",
    "entrepreneur.com", "businessinsider.com", "gartner.com", "statista.com",
    # travel & tech trade press that surfaces on these queries
    "skift.com", "phocuswire.com", "infoq.com", "consultancy.eu", "consultancy.uk",
    "futurumgroup.com", "instagram.com", "macaubusiness.com",
}

# Category-based publisher/aggregator detection — catches the long tail of media,
# news, blog, wiki, listicle and educational domains a static blocklist misses
# (investopedia.com, analyticsinsight.net, "top-10-saas" roundups, …). These are the
# sites that get mislabelled as "companies" when extraction trusts the page's own
# domain instead of the company named *inside* the article.
_MEDIA_DOMAIN_TOKENS = (
    "news", "times", "magazine", "journal", "insight", "insights", "herald",
    "tribune", "gazette", "wire", "digest", "bulletin", "chronicle", "wiki",
    "pedia", "blog", "coverage", "gazette",
)
_LISTICLE_RE = re.compile(
    r"(top[-_ ]?\d+|best[-_ ]|list[-_ ]of|what[-_ ]is|how[-_ ]to|ultimate[-_ ]guide"
    r"|[-_ ]vs[-_ ]|roundup|companies[-_ ]to[-_ ]watch|unicorn[-_ ]tracker|leaderboard)",
    re.I,
)

# An extracted "company name" that is really an article headline, report title,
# listicle, job posting or news item — never an operating company. This is the
# deterministic backstop for when the LLM extractor returns the *thing the page is*
# instead of the company it's ABOUT (e.g. "India SaaS Report 2021", "Indara appoints
# its first CTO", "238 SaaS SDR jobs in India", "What Is Series Funding").
_HEADLINE_NAME_RE = re.compile(
    r"(?i)(\bnews\b|\bjobs?\b|\bhiring\b|\bvacanc|\breport\b|\blandscape\b|\btracker\b"
    r"|\broundup\b|\bguide\b|\bwhat\s+is\b|\bhow\s+to\b|\btop\s*\d+|\bbest\b|\blist\s+of\b"
    r"|\bappoints?\b|\bnamed?\b|\bunveils?\b|\blaunches\b|\braises?\b|\bfunding\b"
    r"|\bseries\s+[a-e]\b|\b20\d{2}\b|\bwebinar\b|\bpodcast\b|\bepisode\b|\breview\b)"
)


def looks_like_headline_name(name: str) -> bool:
    """True when an extracted 'company' name reads like an article/report/job/news
    title rather than an operating company. Deliberately high-precision so we don't
    drop real companies — the LLM extractor is the first line, this is the backstop."""
    n = (name or "").strip()
    if not n:
        return True
    if _LISTICLE_RE.search(n) or _HEADLINE_NAME_RE.search(n):
        return True
    # Headlines are sentences; company names are short. 6+ words is almost always a title.
    if len(n.split()) >= 6:
        return True
    return False


def looks_like_media(domain: str = "", url: str = "", title: str = "") -> bool:
    """True when a domain/url/title is a media publisher, blog, wiki, directory,
    listicle or educational resource — i.e. it *writes about* companies, it isn't one.
    A category heuristic, deliberately high-precision; the homepage LLM classifier in
    verify.py is the authoritative second gate."""
    d = (domain or "").lower().removeprefix("www.")
    if d:
        parts = d.split(".")
        # Registrable domain, so subdomains (en.wikipedia.org) collapse to wikipedia.org.
        if len(parts) >= 3 and parts[-2] in {"co", "com", "ac", "org", "gov", "net"}:
            registrable = ".".join(parts[-3:])
        elif len(parts) >= 2:
            registrable = ".".join(parts[-2:])
        else:
            registrable = d
        if registrable in _NOISE or d in _NOISE:
            return True
        if registrable.endswith((".edu", ".gov")) or ".edu." in d or ".gov." in d or ".ac." in d:
            return True
        head = registrable.split(".")[0]
        if any(tok in head for tok in _MEDIA_DOMAIN_TOKENS):
            return True
    if url and _LISTICLE_RE.search(url):
        return True
    if title and _LISTICLE_RE.search(title):
        return True
    return False


async def execute_search_plan(plan: list[dict], *, per_query: int = 6, context: str = "") -> list[dict]:
    """Run every search in the plan; return a flat, de-duplicated candidate list.

    `context` is a short description of the prospect profile we sell into (from the
    Brain). It's handed to the extraction LLM so it pulls companies *relevant to the
    product* out of each page, rather than any company that happens to be mentioned."""
    candidates: list[dict] = []
    tavily = _try_tavily()
    browser = None if tavily is not None else await _try_browser()
    try:
        for item in plan:
            q, src = item["query"], item.get("source", "google")
            if tavily is not None:
                # Live, real results only — no mock fallback when Tavily is active.
                found = await _tavily_search(tavily, q, src, per_query, context)
            elif browser is not None:
                found = await _scrape(browser, q, src, per_query)
            else:
                found = _mock_results(q, src, per_query)
            candidates.extend(found)
    finally:
        if browser is not None:
            await _close(browser)

    # De-dup by domain (fall back to name) — keep the first/strongest evidence.
    out: dict[str, dict] = {}
    for c in candidates:
        key = (c.get("domain") or c["company_name"]).lower()
        if key in out:
            out[key]["evidence"].extend(c["evidence"])
        else:
            out[key] = c
    return list(out.values())


# ─── Tavily search-API path (preferred) ─────────────────────────────────
def _try_tavily():
    """Return an AsyncTavilyClient when configured + importable, else None."""
    if not settings.tavily_api_key:
        return None
    try:
        from tavily import AsyncTavilyClient
    except Exception:
        return None
    try:
        return AsyncTavilyClient(api_key=settings.tavily_api_key)
    except Exception:
        return None


async def _tavily_search(client, query: str, source: str, limit: int, context: str = "") -> list[dict]:
    """One Tavily query → candidate companies. Returns [] on error or no results —
    never mock data, so a configured key means real-or-nothing."""
    topic = "news" if source == "google_news" else "general"
    try:
        resp = await client.search(
            query=query,
            max_results=max(limit + 4, 8),  # over-fetch; we filter aggregators out
            topic=topic,
            search_depth="basic",
        )
    except Exception:
        return []

    raw = resp.get("results") or []
    if not raw:
        return []
    # SERP results are usually articles / job boards / news pages; the real prospect
    # company is named *inside* them, not in the page's own domain. When an LLM is
    # configured it extracts the actual companies from the CONTENT — and we return
    # exactly what it finds, EVEN IF EMPTY. We must NOT fall back to the result domain
    # here: that fallback is what mislabels publishers (Skift, InfoQ, Investopedia) as
    # companies. Real-or-nothing. The domain fallback exists only for the no-LLM case.
    if settings.llm_provider != "mock":
        return await _extract_companies(query, source, raw, limit, context)
    return _from_domains(query, source, raw, limit)


async def _extract_companies(query: str, source: str, raw: list[dict], limit: int, context: str = "") -> list[dict]:
    """Gemini reads the search results and returns the real prospect companies named
    in the CONTENT (not the aggregator/publisher hosting the page)."""
    signal = _signal_for(source)
    blocks = "\n".join(
        f"- title: {r.get('title', '')}\n  url: {r.get('url', '')}\n  text: {(r.get('content') or '')[:320]}"
        for r in raw[:8]
    )
    relevance = (
        f"We sell to this kind of prospect: {context}. Only return companies that plausibly "
        "fit that profile — a buyer of our product, not a random company mentioned in passing. "
        if context else ""
    )
    system = (
        "You extract real PROSPECT COMPANIES named in the CONTENT of B2B sales search "
        "results. The prospect is the operating company the article/post is ABOUT — never "
        "the site that published it. NEVER return a media outlet, news site, blog, wiki, "
        "directory, listicle, job board or aggregator (investopedia, analyticsinsight, "
        "yourstory, inc42, ziprecruiter, builtin, crunchbase, techcrunch, gartner, etc.), "
        "and never a listicle title like 'Top 10 SaaS Companies' or 'SaaS Unicorn Tracker'. "
        f"{relevance}"
        'Return ONLY JSON: {"companies":[{"name":"<operating company name>",'
        '"domain":"<its own homepage domain or null>","evidence":"short quote from the content"}]}. '
        f"At most {limit}. If the results are only articles that name no real prospect company, "
        "return an empty list."
    )
    user = f"signal: {signal}\nquery: {query}\n\nresults:\n{blocks}"
    try:
        # Generous budget: gemini-2.5-flash may 'think' before answering (the installed
        # google-genai can't disable it), and a tight budget gets truncated mid-JSON.
        text = await complete(system, user, max_tokens=1500)
    except Exception:
        return []
    data = parse_json(text)
    comps = data.get("companies") if isinstance(data, dict) else None
    if not comps:
        return []

    src_url = raw[0].get("url")
    out: list[dict] = []
    seen: set[str] = set()
    for c in comps:
        if not isinstance(c, dict):
            continue
        name = (c.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        # Drop anything that reads like an article/report/job/news title rather than a
        # company ("Top 10 …", "… Tracker", "SaaS Report 2021", "Indara appoints its CTO").
        if looks_like_headline_name(name):
            continue
        seen.add(name.lower())
        domain = (c.get("domain") or "").strip().lower().removeprefix("www.")
        # If the LLM handed back a publisher/aggregator domain, don't trust it as the
        # company's site; derive one from the name instead. If even that reads as media,
        # skip the candidate entirely — it's the page, not a prospect.
        if looks_like_media(domain):
            domain = ""
        derived = domain or _derive_domain(name)
        if looks_like_media(derived or ""):
            continue
        out.append(
            {
                "company_name": name,
                "domain": derived,
                "query": query,
                "source": source,
                "evidence": [
                    {
                        "signal": signal,
                        "source": source,
                        "url": src_url,
                        "snippet": (c.get("evidence") or "").strip()[:300],
                    }
                ],
            }
        )
        if len(out) >= limit:
            break
    return out


def _from_domains(query: str, source: str, raw: list[dict], limit: int) -> list[dict]:
    """No-LLM fallback: treat each non-aggregator result domain as the company."""
    results: list[dict] = []
    seen: set[str] = set()
    for r in raw:
        domain = _domain(r.get("url", ""))
        if not domain or domain in seen:
            continue
        # Never turn a media/publisher/listicle page into a "company" — this is the
        # exact leak that mislabelled Investopedia/Analyticsinsight as prospects.
        if looks_like_media(domain, r.get("url", ""), r.get("title", "")):
            continue
        name = _name_from(r.get("title", ""), domain)
        if not name or looks_like_headline_name(name):
            continue
        seen.add(domain)
        results.append(
            {
                "company_name": name,
                "domain": domain,
                "query": query,
                "source": source,
                "evidence": [
                    {
                        "signal": _signal_for(source),
                        "source": source,
                        "url": r.get("url"),
                        "snippet": (r.get("content") or "").strip()[:300],
                    }
                ],
            }
        )
        if len(results) >= limit:
            break
    return results


def _derive_domain(name: str) -> str | None:
    slug = "".join(ch for ch in name.lower() if ch.isalnum())
    return f"{slug}.com" if slug else None


# ─── Real headless-browser path ─────────────────────────────────────────
async def _try_browser():
    """Launch headless Chromium, or return None so the caller uses the mock."""
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return None
    try:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=settings.discovery_headless)
        return {"pw": pw, "browser": browser}
    except Exception:
        return None


async def _close(handle) -> None:
    try:
        await handle["browser"].close()
        await handle["pw"].stop()
    except Exception:
        pass


async def _scrape(handle, query: str, source: str, limit: int) -> list[dict]:
    url = _SERP.get(source, _SERP["google"]).format(q=quote_plus(query))
    ctx = None
    try:
        ctx = await handle["browser"].new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        )
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        # Each organic result is an <a> wrapping an <h3>; grab href + title + snippet.
        rows = await page.evaluate(
            """() => {
                const out = [];
                document.querySelectorAll('a:has(h3)').forEach(a => {
                    const h3 = a.querySelector('h3');
                    if (!h3) return;
                    const block = a.closest('div');
                    out.push({
                        href: a.href,
                        title: h3.innerText,
                        snippet: block ? block.innerText.slice(0, 300) : ''
                    });
                });
                return out.slice(0, 20);
            }"""
        )
    except Exception:
        # Captcha, timeout, blocked — fall back to the mock for this query.
        return _mock_results(query, source, limit)
    finally:
        if ctx is not None:
            try:
                await ctx.close()
            except Exception:
                pass

    results: list[dict] = []
    for r in rows:
        domain = _domain(r.get("href", ""))
        if not domain or looks_like_media(domain, r.get("href", ""), r.get("title", "")):
            continue
        name = _name_from(r.get("title", ""), domain)
        if not name or looks_like_headline_name(name):
            continue
        results.append(
            {
                "company_name": name,
                "domain": domain,
                "query": query,
                "source": source,
                "evidence": [
                    {
                        "signal": _signal_for(source),
                        "source": source,
                        "url": r.get("href"),
                        "snippet": (r.get("snippet") or "").strip(),
                    }
                ],
            }
        )
        if len(results) >= limit:
            break
    return results or _mock_results(query, source, limit)


def _domain(href: str) -> str:
    try:
        host = urlparse(href).netloc.lower()
    except Exception:
        return ""
    host = host.removeprefix("www.")
    # collapse co.uk-style two-part TLDs to the registrable domain heuristically
    parts = host.split(".")
    return host if len(parts) <= 2 else ".".join(parts[-2:]) if parts[-2] not in {"co", "com"} else ".".join(parts[-3:])


def _name_from(title: str, domain: str) -> str:
    # Prefer the brand from the domain; title often has "… | Careers" noise.
    base = domain.split(".")[0]
    head = re.split(r"[|\-–—:]", title)[0].strip()
    if 2 <= len(head) <= 40 and not head.lower().startswith(("http", "www")):
        return head
    return base.capitalize()


def _signal_for(source: str) -> str:
    return {
        "careers": "hiring",
        "google_news": "news",
        "google": "intent",
    }.get(source, "intent")


# ─── Deterministic mock path ────────────────────────────────────────────
_PREFIX = ["Fin", "Growth", "Cloud", "Scale", "Data", "Nexa", "Bright", "Hyper",
           "Velo", "North", "Bold", "Prime", "Lumen", "Apex", "Quanta"]
_SUFFIX = ["stack", "base", "flow", "labs", "works", "hq", "wave", "core",
           "spark", "grid", "loop", "forge", "pulse", "io"]


def _mock_results(query: str, source: str, limit: int) -> list[dict]:
    """Synthesise companies deterministically from the query so the offline loop
    has a realistic, repeatable stream to discover."""
    h = hashlib.md5(f"{query}|{source}".encode()).hexdigest()
    nibbles = [int(c, 16) for c in h]
    n = 2 + (nibbles[0] % min(limit, 4))  # 2..limit candidates
    snippet_for = {
        "careers": "is hiring {k} Sales Development Representatives to scale outbound.",
        "google_news": "raised a fresh round to accelerate go-to-market expansion.",
        "google": "team posted about spending too long on manual prospecting.",
    }
    out: list[dict] = []
    for i in range(n):
        a = _PREFIX[nibbles[(i + 1) % len(nibbles)] % len(_PREFIX)]
        b = _SUFFIX[nibbles[(i + 3) % len(nibbles)] % len(_SUFFIX)]
        name = f"{a}{b}"
        domain = f"{name.lower()}.com"
        k = 2 + (nibbles[(i + 5) % len(nibbles)] % 6)
        snippet = snippet_for.get(source, snippet_for["google"]).format(k=k)
        out.append(
            {
                "company_name": name,
                "domain": domain,
                "query": query,
                "source": source,
                "evidence": [
                    {
                        "signal": _signal_for(source),
                        "source": source,
                        "url": f"https://{domain}",
                        "snippet": f"{name} {snippet}",
                    }
                ],
            }
        )
    return out
