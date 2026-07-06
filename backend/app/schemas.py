"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─── Onboarding / Fit Model ─────────────────────────────────────────────
class OnboardingPayload(BaseModel):
    product_description: str
    targets: str = ""               # free-text: the companies / kinds of companies to go after
    icp_company_size_min: int = 1
    icp_company_size_max: int = 10000
    icp_industries: list[str] = []
    icp_geographies: list[str] = ["India"]
    icp_funding_stages: list[str] = []
    signals: list[str] = []
    disqualifiers: list[str] = []
    qualify_threshold: int = 65
    
    icp_titles: list[str] = []
    pain_solved: str = ""
    past_buyers: list[str] = []
    lost_deals_reasons: list[str] = []
    exclusions: list[str] = []      # segments Rael should NOT target
    competitors: list[str] = []     # who Rael positions against


class FitParam(ORM):
    id: int
    parameter_name: str
    parameter_value: str | None
    weight: float
    updated_from: str | None


# ─── Leads ──────────────────────────────────────────────────────────────
class LeadCreate(BaseModel):
    company_name: str
    contact_name: str | None = None
    industry: str | None = None
    company_size: int | None = None
    trigger_event: str | None = None
    trigger_source: str | None = None


class LeadOut(ORM):
    id: int
    company_name: str
    contact_name: str | None
    email: str | None
    phone: str | None
    linkedin_url: str | None
    title: str | None
    company_size: int | None
    industry: str | None
    fit_score: int | None
    status: str
    trigger_event: str | None
    trigger_source: str | None
    enrichment_cost: float
    reasoning: str | None
    created_at: datetime
    last_touched_at: datetime


class InteractionOut(ORM):
    id: int
    lead_id: int | None
    type: str | None
    channel: str | None
    direction: str | None
    subject: str | None
    content: str | None
    open_count: int
    outcome: str | None
    agent_name: str | None
    created_at: datetime


class SignalOut(ORM):
    id: int
    company_name: str
    signal_type: str | None
    signal_data: dict | None
    source: str | None
    score: int | None
    acted_on: bool
    lead_id: int | None
    detected_at: datetime


class LogOut(ORM):
    id: int
    agent_name: str | None
    action_type: str | None
    description: str | None
    lead_id: int | None
    level: str
    extra: dict | None
    created_at: datetime


# ─── Discovery / Brain ──────────────────────────────────────────────────
class BrainOut(ORM):
    id: int
    summary: str | None
    understanding: dict | None
    built_from: str
    created_at: datetime


class DiscoveredCompanyOut(ORM):
    id: int
    company_name: str
    domain: str | None
    discovery_query: str | None
    discovery_source: str | None
    evidence: list | None
    verified: bool
    industry: str | None
    employee_count: int | None
    funding: str | None
    signals: list | None
    verification_notes: str | None
    fit_score: int | None
    reasoning: str | None
    status: str
    lead_id: int | None
    created_at: datetime
    updated_at: datetime


class OutcomeIn(BaseModel):
    lead_id: int
    outcome_type: str  # great_fit | wrong_fit | follow_up | closed
    notes: str | None = None
    closed_value: float | None = None


class DemoRequest(BaseModel):
    company_name: str | None = None


class ActionResult(BaseModel):
    ok: bool
    detail: str
    data: Any | None = None
