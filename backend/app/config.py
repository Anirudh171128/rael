"""Central settings. Every external provider key is optional — absence flips
that provider into mock mode so the whole system runs offline."""
from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Railway's UI keeps surrounding quotes and trailing newlines literally,
    # which silently corrupts pasted API keys (SendGrid then 401s).
    @field_validator("*", mode="before")
    @classmethod
    def _strip_env_noise(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().strip("'\"").strip()
        return v

    # Core
    database_url: str = "postgresql+asyncpg://rael:rael@localhost:5432/rael"
    redis_url: str = "redis://localhost:6379/0"
    app_env: str = "development"
    cors_origins: str = "http://localhost:5173"

    # LLM / embeddings
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"
    openai_api_key: str = ""
    google_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    embedding_model: str = "text-embedding-3-large"
    embedding_dims: int = 1536

    # Contact enrichment — Apollo is the ONLY source (no mock contacts).
    # Enrichment runs only after the rep approves it (credits are precious).
    apollo_api_key: str = ""

    # Signals
    crunchbase_api_key: str = ""
    newsapi_key: str = ""
    peopledatalabs_api_key: str = ""

    # Discovery search — Tavily is the preferred live executor (real SERP results,
    # robust). When set it takes priority over the headless browser; absent, discovery
    # falls back to the browser, then to a deterministic mock.
    tavily_api_key: str = ""

    # Comms
    sendgrid_api_key: str = ""
    resend_api_key: str = ""
    whatsapp_token: str = ""
    whatsapp_phone_id: str = ""
    whatsapp_rep_number: str = ""

    # Decision gate
    approval_mode: bool = True
    qualify_threshold: int = 65

    # SMTP for Auth
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "alerts@rael.com"

    # Discovery engine (headless-browser scouting). Runs on a continuous cron;
    # absent browser binaries / no network → graceful mock so the loop still runs.
    discovery_enabled: bool = True
    discovery_interval_hours: float = 3.0   # how often Rael scouts the market
    discovery_max_queries: int = 6          # search plans executed per cycle
    discovery_results_per_query: int = 6    # SERP results parsed per query
    discovery_qualify_threshold: int = 60   # pre-lead bar a company must clear
    discovery_headless: bool = True         # run Chromium headless (False to watch it)

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_provider(self) -> str:
        """Gemini if configured (the chosen default), else Claude, else mock."""
        if self.google_api_key:
            return "gemini"
        if self.anthropic_api_key:
            return "anthropic"
        return "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
