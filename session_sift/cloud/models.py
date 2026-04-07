from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, max_length=120)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, max_length=120)


class RulesUpsert(BaseModel):
    rules_text: str = Field(min_length=1)
    updated_by: str = Field(default="system", min_length=1, max_length=120)


class CloudSavingsReportIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=120)
    user_id: str | None = Field(default=None, max_length=120)
    original_tokens: int = Field(ge=0)
    refined_tokens: int = Field(ge=0)
    pass1_savings: int = Field(ge=0)
    pass2_savings: int = Field(ge=0)
    pass3_savings: int = Field(ge=0)
    elapsed_ms: float = Field(ge=0.0)
    turn: int = Field(ge=0)
    provider: str | None = Field(default=None, max_length=80)
    client_name: str | None = Field(default=None, max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DNASyncRequest(BaseModel):
    base: dict[str, Any] = Field(default_factory=dict)
    local: dict[str, Any] = Field(default_factory=dict)
    author: str = Field(default="system", min_length=1, max_length=120)


class AuditEventView(BaseModel):
    id: int
    org_id: str
    project_id: str | None = None
    event_type: str
    actor: str | None = None
    created_at: float
    details: dict[str, Any]


class DailySavingsPoint(BaseModel):
    day: str
    sessions: int
    tokens_saved: int
    estimated_cost_saved_usd: float


class DashboardSummary(BaseModel):
    scope: str
    org_id: str
    project_id: str | None = None
    latest_context_summary: str | None = None
    total_sessions: int
    total_original_tokens: int
    total_refined_tokens: int
    total_tokens_saved: int
    avg_savings_pct: float
    avg_latency_ms: float
    pass_totals: dict[str, int]
    daily_savings: list[DailySavingsPoint]
    recent_reports: list[dict[str, Any]]