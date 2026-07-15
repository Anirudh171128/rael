"""SQLAlchemy ORM models — one class per core table in the blueprint."""
from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import event
from sqlalchemy.orm import Mapped, Session as OrmSession, mapped_column, with_loader_criteria

from .config import settings
from .database import Base
from .tenant import current_user_id


class TenantMixin:
    """Every table that belongs to one account carries the owning user.

    The ORM hooks at the bottom of this module do the rest: every SELECT /
    UPDATE / DELETE against a TenantMixin table is filtered to the current
    tenant, and every INSERT is stamped with it — no per-query .where() needed.
    """

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    otp: Mapped[str | None] = mapped_column(String, nullable=True)
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"
    token: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FitModel(TenantMixin, Base):
    __tablename__ = "fit_model"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parameter_name: Mapped[str] = mapped_column(String)
    parameter_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_from: Mapped[str | None] = mapped_column(String, nullable=True)


class Lead(TenantMixin, Base):
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_name: Mapped[str] = mapped_column(String)
    contact_name: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    company_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    geography: Mapped[str | None] = mapped_column(String, nullable=True)  # HQ country/region from verify
    fit_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, default="identified")
    # Lifecycle Tracking
    lifecycle_status: Mapped[str] = mapped_column(String, default="active")
    lifecycle_source: Mapped[str] = mapped_column(String, default="discovered")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    touch_count: Mapped[int] = mapped_column(Integer, default=0)
    re_verify_after_days: Mapped[int] = mapped_column(Integer, default=90)
    suppressed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    technographics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    signals_present: Mapped[list | None] = mapped_column(JSON, nullable=True)
    trigger_event: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_source: Mapped[str | None] = mapped_column(String, nullable=True)
    enrichment_cost: Mapped[float] = mapped_column(Float, default=0.0)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_touched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    assigned_to: Mapped[str | None] = mapped_column(String, nullable=True)


class Interaction(TenantMixin, Base):
    __tablename__ = "interactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=True)
    type: Mapped[str | None] = mapped_column(String, nullable=True)
    channel: Mapped[str | None] = mapped_column(String, nullable=True)
    direction: Mapped[str | None] = mapped_column(String, nullable=True)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Signal(TenantMixin, Base):
    __tablename__ = "signals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_name: Mapped[str] = mapped_column(String)
    signal_type: Mapped[str | None] = mapped_column(String, nullable=True)
    signal_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acted_on: Mapped[bool] = mapped_column(Boolean, default=False)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)


class LeadMemory(TenantMixin, Base):
    __tablename__ = "lead_memory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embedding_dims), nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Outcome(TenantMixin, Base):
    __tablename__ = "outcomes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=True)
    meeting_id: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome_type: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    attributed_signals: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentLog(TenantMixin, Base):
    __tablename__ = "agent_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_name: Mapped[str | None] = mapped_column(String, nullable=True)
    action_type: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    level: Mapped[str] = mapped_column(String, default="info")
    extra: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SuppressionList(Base):
    """Global suppression list to prevent discovering or contacting bad fit or unsubscribed domains/emails."""
    __tablename__ = "suppression_list"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain_or_email: Mapped[str] = mapped_column(String, unique=True, index=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    suppressed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ProductBrain(TenantMixin, Base):
    """Rael's distilled understanding of what we sell and who buys it — Gemini
    turns the raw Fit Model answers into a structured brain the discovery engine
    reasons over (buyers, pain signals, negative signals, search themes). Latest
    row wins; we keep history so a re-train can be diffed."""

    __tablename__ = "product_brain"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    understanding: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # {industry, buyers[], pain_signals[], negative_signals[], competitive_signals[], search_themes[]}
    built_from: Mapped[str] = mapped_column(String, default="gemini")  # gemini | mock
    fit_fingerprint: Mapped[str | None] = mapped_column(String, nullable=True)  # detects stale brain
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DiscoveredCompany(TenantMixin, Base):
    """A company the discovery engine surfaced, with the evidence that surfaced it
    and the verification we did before trusting it. This is the holding pen BEFORE
    a Lead exists — a row is promoted to a Lead only once it clears qualification,
    per the architecture ('Lead Created — Not before')."""

    __tablename__ = "discovered_companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_name: Mapped[str] = mapped_column(String)
    domain: Mapped[str | None] = mapped_column(String, nullable=True)
    # discovery provenance
    discovery_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovery_source: Mapped[str | None] = mapped_column(String, nullable=True)  # google | google_news | careers
    evidence: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{signal, source, url, snippet}]
    # verification (filled by the verify layer — never trust discovery alone)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    geography: Mapped[str | None] = mapped_column(String, nullable=True)  # HQ country/region from verify
    funding: Mapped[str | None] = mapped_column(String, nullable=True)
    signals: Mapped[list | None] = mapped_column(JSON, nullable=True)
    verification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # qualification (scored against the Brain before any lead is created)
    fit_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="discovered")
    # discovered | verifying | verified | qualified | rejected | promoted
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ── Tenant isolation hooks ──────────────────────────────────────────────
# Registered on the sync Session class, so they fire for every AsyncSession
# too. When no tenant is set (startup, provider webhooks before the lead is
# resolved) queries run unfiltered — every user-facing path sets the tenant.


@event.listens_for(OrmSession, "do_orm_execute")
def _scope_to_tenant(execute_state) -> None:
    if execute_state.is_column_load or execute_state.is_relationship_load:
        return
    if not (execute_state.is_select or execute_state.is_update or execute_state.is_delete):
        return
    uid = current_user_id.get()
    if uid is None:
        return
    # uid must be a closure variable, not a call inside the lambda — the lambda
    # SQL system extracts it as a bound parameter on every execution.
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            TenantMixin,
            lambda cls: cls.user_id == uid,
            include_aliases=True,
        )
    )


@event.listens_for(OrmSession, "before_flush")
def _stamp_tenant(session, flush_context, instances) -> None:
    uid = current_user_id.get()
    if uid is None:
        return
    for obj in session.new:
        if isinstance(obj, TenantMixin) and obj.user_id is None:
            obj.user_id = uid
