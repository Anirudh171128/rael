-- RAEL schema bootstrap. Runs automatically on first `docker compose up`.
-- SQLAlchemy also creates these tables on startup; this file documents the
-- canonical schema and enables pgvector.

CREATE EXTENSION IF NOT EXISTS vector;

-- Auth: passwordless users (OTP) and their sessions.
CREATE TABLE IF NOT EXISTS users (
  id                   SERIAL PRIMARY KEY,
  email                TEXT NOT NULL UNIQUE,
  otp                  TEXT,
  otp_expires_at       TIMESTAMPTZ,
  is_verified          BOOLEAN NOT NULL DEFAULT false,
  onboarding_completed BOOLEAN NOT NULL DEFAULT false,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
  token       TEXT PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at  TIMESTAMPTZ NOT NULL
);

-- The Fit Model is seeded from onboarding and mutated by outcomes.
CREATE TABLE IF NOT EXISTS fit_model (
  id              SERIAL PRIMARY KEY,
  parameter_name  TEXT NOT NULL,
  parameter_value TEXT,
  weight          REAL NOT NULL DEFAULT 1.0,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_from    TEXT                         -- 'onboarding' | 'outcome:<lead_id>'
);

CREATE TABLE IF NOT EXISTS leads (
  id              SERIAL PRIMARY KEY,
  company_name    TEXT NOT NULL,
  contact_name    TEXT,
  email           TEXT,
  phone           TEXT,
  linkedin_url    TEXT,
  title           TEXT,
  company_size    INTEGER,
  industry        TEXT,
  geography       TEXT,
  fit_score       INTEGER,
  status          TEXT NOT NULL DEFAULT 'identified',
  -- Lifecycle tracking: a lead persists across cycles; we age, re-verify and suppress it.
  lifecycle_status     TEXT NOT NULL DEFAULT 'active',       -- active | dormant | suppressed
  lifecycle_source     TEXT NOT NULL DEFAULT 'discovered',   -- how the lead entered the system
  first_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_enriched_at     TIMESTAMPTZ,
  touch_count          INTEGER NOT NULL DEFAULT 0,
  re_verify_after_days INTEGER NOT NULL DEFAULT 90,
  suppressed_reason    TEXT,
  technographics       JSONB,
  signals_present      JSONB,
  trigger_event   TEXT,
  trigger_source  TEXT,
  enrichment_cost REAL DEFAULT 0,
  reasoning       TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_touched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  assigned_to     TEXT
);

CREATE TABLE IF NOT EXISTS interactions (
  id          SERIAL PRIMARY KEY,
  lead_id     INTEGER REFERENCES leads(id) ON DELETE CASCADE,
  type        TEXT,          -- email | linkedin | whatsapp | call | note
  channel     TEXT,
  direction   TEXT,          -- outbound | inbound
  subject     TEXT,          -- email subject (editable by the rep before send)
  content     TEXT,
  sent_at     TIMESTAMPTZ,
  opened_at   TIMESTAMPTZ,
  open_count  INTEGER DEFAULT 0,
  replied_at  TIMESTAMPTZ,
  outcome     TEXT,
  agent_name  TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS signals (
  id           SERIAL PRIMARY KEY,
  company_name TEXT NOT NULL,
  signal_type  TEXT,         -- funding | hiring | leadership | intent | news | growth
  signal_data  JSONB,
  source       TEXT,
  score        INTEGER,
  detected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  acted_on     BOOLEAN DEFAULT false,
  lead_id      INTEGER REFERENCES leads(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS lead_memory (
  id           SERIAL PRIMARY KEY,
  lead_id      INTEGER REFERENCES leads(id) ON DELETE CASCADE,
  embedding    vector(1536),
  summary_text TEXT,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS outcomes (
  id           SERIAL PRIMARY KEY,
  lead_id      INTEGER REFERENCES leads(id) ON DELETE CASCADE,
  meeting_id   TEXT,
  outcome_type TEXT,          -- great_fit | wrong_fit | follow_up | closed
  notes        TEXT,
  closed_value REAL,
  attributed_signals JSONB,   -- which signals the Memory Agent credits for this outcome
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Global suppression list: domains/emails we must never discover or contact
-- (bad fit, unsubscribed, bounced).
CREATE TABLE IF NOT EXISTS suppression_list (
  id              SERIAL PRIMARY KEY,
  domain_or_email TEXT NOT NULL UNIQUE,
  reason          TEXT,
  suppressed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_logs (
  id          SERIAL PRIMARY KEY,
  agent_name  TEXT,
  action_type TEXT,
  description TEXT,
  lead_id     INTEGER REFERENCES leads(id) ON DELETE SET NULL,
  level       TEXT DEFAULT 'info',  -- info | positive | attention | urgent
  metadata    JSONB,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Rael's distilled understanding of who we sell to (Gemini turns the Fit Model
-- answers into this structured "brain"). Latest row wins; history is kept.
CREATE TABLE IF NOT EXISTS product_brain (
  id               SERIAL PRIMARY KEY,
  summary          TEXT,
  understanding    JSONB,      -- {industry, buyers[], pain_signals[], negative_signals[], competitive_signals[], search_themes[]}
  built_from       TEXT NOT NULL DEFAULT 'gemini',  -- gemini | anthropic | mock
  fit_fingerprint  TEXT,       -- detects a stale brain after re-training
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Companies the discovery engine surfaced + verified, BEFORE a lead exists. A row
-- is promoted to a lead only once it clears qualification (status='promoted').
CREATE TABLE IF NOT EXISTS discovered_companies (
  id                 SERIAL PRIMARY KEY,
  company_name       TEXT NOT NULL,
  domain             TEXT,
  discovery_query    TEXT,
  discovery_source   TEXT,     -- google | google_news | careers
  evidence           JSONB,    -- [{signal, source, url, snippet}]
  verified           BOOLEAN DEFAULT false,
  industry           TEXT,
  employee_count     INTEGER,
  geography          TEXT,
  funding            TEXT,
  signals            JSONB,
  verification_notes TEXT,
  fit_score          INTEGER,
  reasoning          TEXT,
  status             TEXT NOT NULL DEFAULT 'discovered', -- discovered|verified|qualified|rejected|promoted
  lead_id            INTEGER REFERENCES leads(id) ON DELETE SET NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_leads_status   ON leads(status);
CREATE INDEX IF NOT EXISTS idx_disc_status     ON discovered_companies(status);
CREATE INDEX IF NOT EXISTS idx_signals_acted  ON signals(acted_on);
CREATE INDEX IF NOT EXISTS idx_logs_created    ON agent_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inter_lead      ON interactions(lead_id);
