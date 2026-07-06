"""Discovery engine — Rael's scouting layer.

The pipeline mirrors the architecture doc:

    Brain ──▶ plan (Gemini writes searches)
          ──▶ execute (headless browser runs them)
          ──▶ verify (don't trust the SERP — fetch + confirm)

Every layer degrades to a deterministic mock when its capability is absent
(no Gemini key, no Chromium, no network) so the full loop runs offline.
"""
from .plan import generate_search_plan  # noqa: F401
from .execute import execute_search_plan  # noqa: F401
from .verify import verify_company  # noqa: F401
