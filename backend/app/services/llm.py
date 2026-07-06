"""LLM wrapper. Prefers Gemini (the chosen default), falls back to Claude, then to
a deterministic mock when no key is set — so message generation / reply
classification run offline."""
from __future__ import annotations

import json
import re

from ..config import settings

_PROVIDER = settings.llm_provider  # "gemini" | "anthropic" | "mock"
_LIVE = _PROVIDER != "mock"


async def complete(system: str, user: str, *, max_tokens: int = 700) -> str:
    """Single-turn completion. Returns plain text."""
    if _PROVIDER == "mock":
        return _mock_complete(system, user)
    if _PROVIDER == "gemini":
        return await _gemini_complete(system, user, max_tokens)
    return await _anthropic_complete(system, user, max_tokens)


async def _gemini_complete(system: str, user: str, max_tokens: int) -> str:
    # Lazy import so google-genai isn't required unless Gemini is the provider.
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.google_api_key)
    # Gemini 2.5 models *think* before answering and spend output tokens doing it —
    # left on, a small max_output_tokens budget is consumed entirely by reasoning and
    # the visible answer comes back empty (finish_reason=MAX_TOKENS). These are short
    # structured completions, so disable thinking to keep the whole budget for output.
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
    )
    try:
        cfg.thinking_config = types.ThinkingConfig(thinking_budget=0)
    except Exception:
        pass  # older google-genai / non-2.5 model — no thinking knob, ignore
    resp = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=user,
        config=cfg,
    )
    return (resp.text or "").strip()


async def _anthropic_complete(system: str, user: str, max_tokens: int) -> str:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model=settings.claude_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in resp.content if block.type == "text").strip()


async def classify(text: str, labels: list[str]) -> str:
    """Return exactly one label from `labels` for the given text."""
    system = (
        "You classify an inbound sales reply into exactly one category. "
        f"Respond with ONLY one of: {', '.join(labels)}."
    )
    if not _LIVE:
        return _mock_classify(text, labels)
    out = await complete(system, text, max_tokens=12)
    for label in labels:
        if label.lower() in out.lower():
            return label
    return labels[-1]


# ─── Mock implementations ───────────────────────────────────────────────
def _mock_complete(system: str, user: str) -> str:
    """Heuristic stand-in for Claude — produces a plausible personalized message."""
    company = _extract(user, "company") or "your company"
    name = _extract(user, "contact") or "there"
    trigger = _extract(user, "trigger") or "your recent growth"
    pain = _extract(user, "pain") or "manual research eating your team's day"
    return (
        f"Hi {name.split()[0] if name != 'there' else 'there'} — saw {trigger}, congrats. "
        f"Teams at {company}'s stage often tell us {pain}. "
        "We cut that to under 20 minutes. Worth a quick look?"
    )


def _mock_classify(text: str, labels: list[str]) -> str:
    t = text.lower()
    rules = {
        "unsubscribe": ["unsubscribe", "remove me", "stop emailing"],
        "out of office": ["out of office", "ooo", "on leave", "vacation"],
        "objection": ["already use", "too expensive", "not interested", "no budget"],
        "faq": ["how much", "pricing", "cost", "what does", "how does"],
        "warm": ["interested", "let's talk", "send me", "book", "demo", "call"],
    }
    for label in labels:
        for kw in rules.get(label.lower(), []):
            if kw in t:
                return label
    return next((l for l in labels if l.lower() == "unknown"), labels[-1])


def _extract(blob: str, key: str) -> str | None:
    # Pull "key: value" lines out of the structured user prompt agents build.
    m = re.search(rf"{key}\s*[:=]\s*(.+)", blob, re.IGNORECASE)
    return m.group(1).strip() if m else None


def parse_json(text: str) -> dict | None:
    """Best-effort JSON extraction from an LLM response. Handles ```json code fences
    (Gemini wraps JSON in them) and prose around the object."""
    if not text:
        return None
    s = text.strip()
    # Strip a leading/trailing markdown code fence if present.
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None
