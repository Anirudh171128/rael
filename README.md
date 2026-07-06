# RAEL — Multi-Agent GTM System

Rael is one **orchestrator** routing work to **8 specialized sub-agents**. He watches the
market for buying signals, scores companies against your **Fit Model**, finds the decision
maker, writes a personalized message, handles replies, and escalates warm humans to you.

> Your only job: talk to warm humans and tap one outcome button. Everything else is Rael.

## Repository layout

```
rael/
├── backend/          FastAPI app — DB, REST APIs, WebSocket live feed, webhooks, scheduler
│   └── app/
│       ├── api/          REST + WS routers (leads, onboarding, signals, webhooks, feed)
│       ├── services/     External integrations (LLM, Apollo enrichment, signals, comms)
│       ├── models.py     SQLAlchemy schema (all core tables)
│       ├── database.py   Async engine + session
│       └── main.py       App entrypoint — wires everything together
├── agents/           The brain — orchestrator + 8 sub-agents (imports backend services)
│   ├── orchestrator.py   The execute / hold / escalate decision gate
│   └── *_agent.py        signal, enrichment, qualification, outreach, reply, briefing, memory, reporting
├── frontend/         React + Vite + Tailwind dashboard (live feed, pipeline, avatar)
└── db/init.sql       pgvector extension + schema bootstrap
```

The three layers are deliberately separate folders. `agents/` imports from `backend.app.services`,
and `backend` invokes the orchestrator — so they are wired but never tangled.

## Design decisions (resolved from the blueprint)

| Open question in blueprint | Decision made here | Why |
|---|---|---|
| `text-embedding-3-large` vs `vector(1536)` | Request embeddings at **1536 dims** | Resolves the dimension mismatch |
| LangGraph | Explicit async state machine mirroring LangGraph nodes | Runs without version churn; swap-in ready |
| Celery vs APScheduler | **APScheduler in-process** drives jobs; Celery tasks defined | Runnable with no extra worker |

## Everything runs with ZERO API keys

The LLM + comms providers (Claude, OpenAI, SendGrid, WhatsApp) fall back to a **mock
implementation** when their key is absent, so the discover → verify → qualify → draft →
escalate → log → live-feed loop runs end-to-end offline. **Never fabricated, though:**
*companies* come only from live discovery, *signal feeds* (Crunchbase, NewsAPI,
PeopleDataLabs) return nothing without keys, and *contacts* come **only from Apollo**
(`APOLLO_API_KEY`) — every enrichment is human-approved from the dashboard popup because
credits are precious; without the key (or when Apollo has no verified person) the lead
simply waits as `incomplete`. Rael never invents a contact and never spends credits on
his own.

## Quick start

```bash
# 1. Database (Postgres + pgvector) and Redis
docker compose up -d

# 2. Backend  (from repo root so both `backend` and `agents` import cleanly)
cd backend && pip install -r requirements.txt && cd ..
cp .env.example .env                       # optional — fill in keys to go live
uvicorn backend.app.main:app --reload      # http://localhost:8000  (docs at /docs)

# 3. Frontend
cd frontend && npm install && npm run dev  # http://localhost:5173
```

Finish **Train Rael** (or hit **"Scout now"** in the Scouting view, or `POST /api/discovery/run`)
and watch Rael build its Brain, scout the market, qualify companies, and drive the new leads
through the full pipeline live. There is no mock/demo data — every lead is real discovery output;
third-party signal feeds stay dark until their API keys are set.

## Deploy to Railway (production)

One service runs everything: the `Dockerfile` builds the React frontend and FastAPI
serves it alongside `/api` and `/ws` (same origin — no CORS, no proxy).

1. **Postgres**: add Railway's **pgvector** template (plain Postgres works too —
   vector columns are optional; `CREATE EXTENSION vector` is attempted and skipped
   gracefully, but pgvector is required for the `lead_memory` table).
2. **Service**: "Deploy from GitHub repo" — Railway detects the `Dockerfile`.
3. **Variables** (see `.env.example`):
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}` (asyncpg/sslmode normalization is automatic)
   - `GOOGLE_API_KEY`, `TAVILY_API_KEY` — the Brain + live discovery
   - `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` — login OTPs + outreach email fallback
   - `APOLLO_API_KEY` — contact enrichment (human-approved per company; no mock contacts)
   - `APPROVAL_MODE=true` — keep the human approval gate on in production
Notes:
- Tables are created automatically on first boot; the app seeds a default Fit Model.
- The Docker image ships **without** Playwright browsers — discovery uses Tavily
  (set `TAVILY_API_KEY`); the headless-browser fallback only applies locally.
- Emails: with only SMTP (Gmail app password) outreach sends from that Gmail account.
  For domain-branded sending set `RESEND_API_KEY` or `SENDGRID_API_KEY` — the
  waterfall prefers them automatically.

## Discovery engine — Rael scouts the market on its own

After training, Rael doesn't wait for signals to arrive — it goes looking. The
discovery loop (the `Scouting` view) runs continuously on a scheduler and mirrors
the architecture exactly:

```
Train Rael ─▶ Brain (Gemini distils the Fit Model into {industry, buyers,
                     pain_signals, negative_signals, search_themes})
           ─▶ Search plan (Gemini writes the queries that expose buying intent)
           ─▶ Headless browser (Playwright/Chromium runs Google · News · Careers)
           ─▶ Verify (fetch the company's own site — never trust the SERP)
           ─▶ Qualify against the Fit Model (score BEFORE a lead exists)
           ─▶ Promote → Lead → the normal enrich → re-qualify → outreach pipeline
```

A candidate becomes a **Lead only after it is verified *and* clears qualification**
(`discovery_qualify_threshold`, default 60) — everything below the bar is parked as
a `discovered_companies` row so Rael can show its work and re-evaluate later.

| Piece | File | Live path | Fallback |
|---|---|---|---|
| Brain | `agents/brain_agent.py` | Gemini distillation | template from the Fit Model |
| Plan | `services/discovery/plan.py` | Gemini query writer | grounded templates |
| Execute | `services/discovery/execute.py` | **Tavily search API + Gemini company extraction** → Playwright headless Chromium | deterministic mock stream |
| Verify | `services/discovery/verify.py` | httpx fetch + Gemini extract | heuristic firmographics |
| Qualify / promote | `agents/discovery_agent.py` | Fit-Model scoring | (same — deterministic) |

The continuous cron lives in `scheduler.py` (`discovery_cycle`, every
`DISCOVERY_INTERVAL_HOURS`, default 3h). Finishing **Train Rael** fires an immediate
Brain build + scouting cycle; `POST /api/discovery/run` triggers one on demand, and
`POST /api/discovery/brain/build` re-distils the Brain after a re-train.

```bash
# Preferred live executor — real companies, no scraping. Set the key in .env:
#   TAVILY_API_KEY=tvly-...
# Tavily returns the SERP; Gemini extracts the actual prospect companies named in the
# results (job boards / news sites are filtered out), then each is verified + qualified.

# Fallback executor (used only when TAVILY_API_KEY is absent) — a real browser:
pip install playwright && playwright install chromium
```

> **Executor priority:** `Tavily (real) → headless Chromium → deterministic mock`.
> When `TAVILY_API_KEY` is set there is **no mock fallback** — a query returns real
> companies or nothing, never fabricated names. The headless-browser path remains for
> the no-key case, but scraping Google directly is ToS-gray and brittle (it gets
> blocked), which is why Tavily is preferred.

> **Heads-up (fixed in this build):** `gemini-2.5-flash` is a *thinking* model — it
> spends `max_output_tokens` on internal reasoning, so short completions came back
> empty. `services/llm.py` now sets `ThinkingConfig(thinking_budget=0)` for these
> structured single-turn calls, which is what makes the Gemini Brain/plan/verify
> (and the existing outreach/reply agents) actually produce text.

See `db/init.sql` for the schema and `agents/orchestrator.py` for the decision gate.
