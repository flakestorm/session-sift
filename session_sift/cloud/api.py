from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from session_sift.cloud.models import (
    AuditEventView,
    CloudSavingsReportIn,
    DNASyncRequest,
    DashboardSummary,
    OrganizationCreate,
    ProjectCreate,
    RulesUpsert,
)
from session_sift.cloud.store import CloudStore


def create_cloud_app(db_path: str = ".session-sift/team-cloud.db") -> FastAPI:
    store = CloudStore(db_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await store.initialize()
        yield

    app = FastAPI(
        title="Session Sift Team Cloud API",
        version="0.1.0",
        lifespan=lifespan,
        summary="Team-tier backend for dashboard, shared rules, DNA sync, and audit history.",
    )

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok", "service": "session-sift-team-cloud"}

    @app.get("/api/v1/orgs")
    async def list_orgs() -> dict:
        return {"organizations": await store.list_organizations()}

    @app.post("/api/v1/orgs", status_code=201)
    async def create_org(payload: OrganizationCreate) -> dict:
        return await store.create_organization(payload.name, payload.slug)

    @app.get("/api/v1/orgs/{org_id}/projects")
    async def list_projects(org_id: str) -> dict:
        try:
            return {"projects": await store.list_projects(org_id)}
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/orgs/{org_id}/projects", status_code=201)
    async def create_project(org_id: str, payload: ProjectCreate) -> dict:
        try:
            return await store.create_project(org_id, payload.name, payload.slug)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/orgs/{org_id}/rules")
    async def get_rules(org_id: str) -> dict:
        try:
            rules = await store.get_rules(org_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if rules is None:
            raise HTTPException(status_code=404, detail=f"Rules for organization {org_id} not found")
        return rules

    @app.put("/api/v1/orgs/{org_id}/rules")
    async def upsert_rules(org_id: str, payload: RulesUpsert) -> dict:
        try:
            return await store.upsert_rules(org_id, payload.rules_text, payload.updated_by)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/orgs/{org_id}/dashboard", response_model=DashboardSummary)
    async def org_dashboard(org_id: str, days: int = Query(default=30, ge=1, le=365)):
        try:
            return await store.get_dashboard(org_id, days=days)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/orgs/{org_id}/audit-history", response_model=list[AuditEventView])
    async def org_audit_history(org_id: str, limit: int = Query(default=50, ge=1, le=200)):
        try:
            return await store.list_audit_history(org_id, limit=limit)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/projects/{project_id}/reports", status_code=201)
    async def ingest_report(project_id: str, payload: CloudSavingsReportIn) -> dict:
        try:
            return await store.ingest_report(project_id, payload.model_dump())
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/projects/{project_id}/dashboard", response_model=DashboardSummary)
    async def project_dashboard(project_id: str, days: int = Query(default=30, ge=1, le=365)):
        try:
            latest_dna, _ = await store.get_latest_dna(project_id)
            project = await store._require_project(project_id)
            response = await store.get_dashboard(project["org_id"], project_id=project_id, days=days)
            response["latest_context_summary"] = (latest_dna or {}).get("context_summary", "")
            return response
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/projects/{project_id}/dna/sync", status_code=201)
    async def sync_dna(project_id: str, payload: DNASyncRequest) -> dict:
        try:
            return await store.sync_dna(project_id, payload.base, payload.local, payload.author)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/projects/{project_id}/dna/latest")
    async def latest_dna(project_id: str) -> dict:
        try:
            payload, sha256 = await store.get_latest_dna(project_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if payload is None:
            raise HTTPException(status_code=404, detail=f"No DNA snapshots found for project {project_id}")
        return {"sha256": sha256, "snapshot": payload}

    @app.get("/api/v1/projects/{project_id}/audit-history", response_model=list[AuditEventView])
    async def project_audit_history(project_id: str, limit: int = Query(default=50, ge=1, le=200)):
        try:
            project = await store._require_project(project_id)
            return await store.list_audit_history(project["org_id"], project_id=project_id, limit=limit)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/projects/{project_id}/slack/daily-digest")
    async def slack_daily_digest(project_id: str) -> dict:
        try:
            return await store.build_daily_digest(project_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app