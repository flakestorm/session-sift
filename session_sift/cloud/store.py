from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from time import time
from uuid import uuid4

import aiosqlite

from session_sift.cloud.sync import compute_diff, merge_dna
from session_sift.models import SavingsReport
from session_sift.utils import ensure_parent_dir


CLOUD_SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    tier TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(org_id, slug)
);

CREATE TABLE IF NOT EXISTS rule_sets (
    org_id TEXT PRIMARY KEY,
    rules_text TEXT NOT NULL,
    version INTEGER NOT NULL,
    updated_by TEXT,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS savings_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    user_id TEXT,
    provider TEXT,
    client_name TEXT,
    original_tokens INTEGER NOT NULL,
    refined_tokens INTEGER NOT NULL,
    pass1_savings INTEGER NOT NULL,
    pass2_savings INTEGER NOT NULL,
    pass3_savings INTEGER NOT NULL,
    elapsed_ms REAL NOT NULL,
    turn INTEGER NOT NULL,
    created_at REAL NOT NULL,
    metadata TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dna_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    base_sha256 TEXT,
    author TEXT,
    created_at REAL NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id TEXT NOT NULL,
    project_id TEXT,
    event_type TEXT NOT NULL,
    actor TEXT,
    created_at REAL NOT NULL,
    details TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_org ON projects(org_id);
CREATE INDEX IF NOT EXISTS idx_reports_project_created ON savings_reports(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_reports_org_created ON savings_reports(org_id, created_at);
CREATE INDEX IF NOT EXISTS idx_dna_project_created ON dna_snapshots(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_org_created ON audit_events(org_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_project_created ON audit_events(project_id, created_at);
"""


class CloudStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            ensure_parent_dir(self.path)
            async with aiosqlite.connect(self.path) as db:
                await db.executescript(CLOUD_SCHEMA)
                await db.execute("PRAGMA journal_mode=WAL;")
                await db.commit()
            self._initialized = True

    async def create_organization(self, name: str, slug: str | None = None) -> dict:
        await self.initialize()
        now = time()
        payload = {
            "id": uuid4().hex,
            "name": name,
            "slug": _slugify(slug or name),
            "tier": "team",
            "created_at": now,
        }
        async with self._write_lock:
            async with aiosqlite.connect(self.path) as db:
                await db.execute(
                    "INSERT INTO organizations(id, name, slug, tier, created_at) VALUES(?, ?, ?, ?, ?)",
                    (payload["id"], payload["name"], payload["slug"], payload["tier"], payload["created_at"]),
                )
                await self._insert_audit_event(db, payload["id"], None, "org.created", "system", {"name": name, "slug": payload["slug"]})
                await db.commit()
        return payload

    async def list_organizations(self) -> list[dict]:
        await self.initialize()
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT id, name, slug, tier, created_at FROM organizations ORDER BY created_at ASC"
            )
            rows = await cursor.fetchall()
        return [
            {"id": row[0], "name": row[1], "slug": row[2], "tier": row[3], "created_at": row[4]}
            for row in rows
        ]

    async def create_project(self, org_id: str, name: str, slug: str | None = None) -> dict:
        await self._require_org(org_id)
        now = time()
        payload = {
            "id": uuid4().hex,
            "org_id": org_id,
            "name": name,
            "slug": _slugify(slug or name),
            "created_at": now,
        }
        async with self._write_lock:
            async with aiosqlite.connect(self.path) as db:
                await db.execute(
                    "INSERT INTO projects(id, org_id, name, slug, created_at) VALUES(?, ?, ?, ?, ?)",
                    (payload["id"], payload["org_id"], payload["name"], payload["slug"], payload["created_at"]),
                )
                await self._insert_audit_event(db, org_id, payload["id"], "project.created", "system", {"name": name, "slug": payload["slug"]})
                await db.commit()
        return payload

    async def list_projects(self, org_id: str) -> list[dict]:
        await self._require_org(org_id)
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT id, org_id, name, slug, created_at FROM projects WHERE org_id = ? ORDER BY created_at ASC",
                (org_id,),
            )
            rows = await cursor.fetchall()
        return [
            {"id": row[0], "org_id": row[1], "name": row[2], "slug": row[3], "created_at": row[4]}
            for row in rows
        ]

    async def upsert_rules(self, org_id: str, rules_text: str, updated_by: str) -> dict:
        await self._require_org(org_id)
        now = time()
        async with self._write_lock:
            async with aiosqlite.connect(self.path) as db:
                cursor = await db.execute("SELECT version FROM rule_sets WHERE org_id = ?", (org_id,))
                row = await cursor.fetchone()
                version = (row[0] + 1) if row else 1
                await db.execute(
                    """
                    INSERT INTO rule_sets(org_id, rules_text, version, updated_by, updated_at)
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(org_id) DO UPDATE SET
                        rules_text = excluded.rules_text,
                        version = excluded.version,
                        updated_by = excluded.updated_by,
                        updated_at = excluded.updated_at
                    """,
                    (org_id, rules_text, version, updated_by, now),
                )
                await self._insert_audit_event(db, org_id, None, "rules.updated", updated_by, {"version": version})
                await db.commit()
        return {
            "org_id": org_id,
            "rules_text": rules_text,
            "version": version,
            "updated_by": updated_by,
            "updated_at": now,
        }

    async def get_rules(self, org_id: str) -> dict | None:
        await self._require_org(org_id)
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT org_id, rules_text, version, updated_by, updated_at FROM rule_sets WHERE org_id = ?",
                (org_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "org_id": row[0],
            "rules_text": row[1],
            "version": row[2],
            "updated_by": row[3],
            "updated_at": row[4],
        }

    async def ingest_report(self, project_id: str, payload: dict) -> dict:
        project = await self._require_project(project_id)
        now = time()
        report = SavingsReport(
            original_tokens=payload["original_tokens"],
            refined_tokens=payload["refined_tokens"],
            pass1_savings=payload["pass1_savings"],
            pass2_savings=payload["pass2_savings"],
            pass3_savings=payload["pass3_savings"],
            elapsed_ms=payload["elapsed_ms"],
            turn=payload["turn"],
            session_id=payload["session_id"],
        )
        stored = report.to_dict()
        stored.update(
            {
                "user_id": payload.get("user_id"),
                "provider": payload.get("provider"),
                "client_name": payload.get("client_name"),
                "metadata": payload.get("metadata", {}),
                "created_at": now,
                "project_id": project_id,
                "org_id": project["org_id"],
            }
        )
        async with self._write_lock:
            async with aiosqlite.connect(self.path) as db:
                await db.execute(
                    """
                    INSERT INTO savings_reports(
                        org_id, project_id, session_id, user_id, provider, client_name,
                        original_tokens, refined_tokens, pass1_savings, pass2_savings, pass3_savings,
                        elapsed_ms, turn, created_at, metadata, payload
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stored["org_id"],
                        stored["project_id"],
                        stored["session_id"],
                        stored["user_id"],
                        stored["provider"],
                        stored["client_name"],
                        stored["original_tokens"],
                        stored["refined_tokens"],
                        stored["pass1_savings"],
                        stored["pass2_savings"],
                        stored["pass3_savings"],
                        stored["elapsed_ms"],
                        stored["turn"],
                        stored["created_at"],
                        json.dumps(stored["metadata"], sort_keys=True),
                        json.dumps(stored, sort_keys=True),
                    ),
                )
                await self._insert_audit_event(
                    db,
                    project["org_id"],
                    project_id,
                    "report.ingested",
                    stored.get("user_id") or "system",
                    {"session_id": stored["session_id"], "total_savings": stored["total_savings"]},
                )
                await db.commit()
        return stored

    async def get_dashboard(self, org_id: str, project_id: str | None = None, days: int = 30) -> dict:
        await self._require_org(org_id)
        if project_id is not None:
            project = await self._require_project(project_id)
            if project["org_id"] != org_id:
                raise LookupError(f"Project {project_id} does not belong to org {org_id}")

        where = ["org_id = ?"]
        params: list[object] = [org_id]
        if project_id is not None:
            where.append("project_id = ?")
            params.append(project_id)

        where_sql = " AND ".join(where)
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                f"""
                SELECT COUNT(*), COALESCE(SUM(original_tokens), 0), COALESCE(SUM(refined_tokens), 0),
                       COALESCE(SUM(pass1_savings), 0), COALESCE(SUM(pass2_savings), 0), COALESCE(SUM(pass3_savings), 0),
                       COALESCE(AVG(elapsed_ms), 0)
                FROM savings_reports
                WHERE {where_sql}
                """,
                params,
            )
            summary_row = await cursor.fetchone()

            trend_cursor = await db.execute(
                f"""
                SELECT date(created_at, 'unixepoch') AS day,
                       COUNT(*) AS sessions,
                       COALESCE(SUM(original_tokens - refined_tokens), 0) AS tokens_saved
                FROM savings_reports
                WHERE {where_sql} AND created_at >= ?
                GROUP BY day
                ORDER BY day ASC
                """,
                [*params, time() - (days * 86400)],
            )
            trend_rows = await trend_cursor.fetchall()

            recent_cursor = await db.execute(
                f"""
                SELECT payload FROM savings_reports
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT 10
                """,
                params,
            )
            recent_rows = await recent_cursor.fetchall()

        total_sessions, original_tokens, refined_tokens, pass1_total, pass2_total, pass3_total, avg_latency_ms = summary_row
        total_tokens_saved = max(0, original_tokens - refined_tokens)
        avg_savings_pct = ((total_tokens_saved / original_tokens) * 100) if original_tokens else 0.0
        return {
            "scope": "project" if project_id else "organization",
            "org_id": org_id,
            "project_id": project_id,
            "total_sessions": total_sessions,
            "total_original_tokens": original_tokens,
            "total_refined_tokens": refined_tokens,
            "total_tokens_saved": total_tokens_saved,
            "avg_savings_pct": round(avg_savings_pct, 3),
            "avg_latency_ms": round(float(avg_latency_ms or 0.0), 3),
            "pass_totals": {
                "pass1": int(pass1_total or 0),
                "pass2": int(pass2_total or 0),
                "pass3": int(pass3_total or 0),
            },
            "daily_savings": [
                {
                    "day": row[0],
                    "sessions": row[1],
                    "tokens_saved": row[2],
                    "estimated_cost_saved_usd": round((row[2] / 1_000_000) * 3.0, 6),
                }
                for row in trend_rows
            ],
            "recent_reports": [json.loads(row[0]) for row in recent_rows],
        }

    async def sync_dna(self, project_id: str, base: dict, local: dict, author: str) -> dict:
        project = await self._require_project(project_id)
        remote_payload, remote_sha = await self.get_latest_dna(project_id)
        remote = remote_payload or {}
        diff = compute_diff(base, local, remote)
        merged, merged_sha = merge_dna(base, local, remote)
        now = time()
        async with self._write_lock:
            async with aiosqlite.connect(self.path) as db:
                await db.execute(
                    """
                    INSERT INTO dna_snapshots(org_id, project_id, sha256, base_sha256, author, created_at, payload)
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project["org_id"],
                        project_id,
                        merged_sha,
                        remote_sha,
                        author,
                        now,
                        json.dumps(merged, sort_keys=True),
                    ),
                )
                await self._insert_audit_event(
                    db,
                    project["org_id"],
                    project_id,
                    "dna.synced",
                    author,
                    {"sha256": merged_sha, "base_sha256": remote_sha, "added_files": len(diff.added_files), "modified_files": len(diff.modified_files)},
                )
                await db.commit()
        return {
            "project_id": project_id,
            "org_id": project["org_id"],
            "sha256": merged_sha,
            "base_sha256": remote_sha,
            "merged": merged,
            "diff": diff.to_dict(),
            "created_at": now,
        }

    async def get_latest_dna(self, project_id: str) -> tuple[dict | None, str | None]:
        await self._require_project(project_id)
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT payload, sha256 FROM dna_snapshots WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None, None
        return json.loads(row[0]), row[1]

    async def list_audit_history(
        self,
        org_id: str,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        await self._require_org(org_id)
        if project_id is not None:
            await self._require_project(project_id)
        where = ["org_id = ?"]
        params: list[object] = [org_id]
        if project_id is not None:
            where.append("project_id = ?")
            params.append(project_id)
        params.append(limit)
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                f"""
                SELECT id, org_id, project_id, event_type, actor, created_at, details
                FROM audit_events
                WHERE {' AND '.join(where)}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params,
            )
            rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "org_id": row[1],
                "project_id": row[2],
                "event_type": row[3],
                "actor": row[4],
                "created_at": row[5],
                "details": json.loads(row[6]),
            }
            for row in rows
        ]

    async def build_daily_digest(self, project_id: str) -> dict:
        project = await self._require_project(project_id)
        dashboard = await self.get_dashboard(project["org_id"], project_id=project_id, days=1)
        latest_dna, dna_sha = await self.get_latest_dna(project_id)
        message = (
            f"Session Sift daily digest for {project['name']}: "
            f"{dashboard['total_sessions']} sessions, {dashboard['total_tokens_saved']:,} tokens saved "
            f"({dashboard['avg_savings_pct']:.1f}% avg). "
            f"Latest DNA snapshot: {dna_sha or 'none'}."
        )
        return {
            "project_id": project_id,
            "org_id": project["org_id"],
            "message": message,
            "dashboard": dashboard,
            "latest_dna_sha256": dna_sha,
            "latest_context_summary": (latest_dna or {}).get("context_summary", ""),
        }

    async def _require_org(self, org_id: str) -> None:
        await self.initialize()
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT 1 FROM organizations WHERE id = ?", (org_id,))
            row = await cursor.fetchone()
        if row is None:
            raise LookupError(f"Organization {org_id} not found")

    async def _require_project(self, project_id: str) -> dict:
        await self.initialize()
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT id, org_id, name, slug, created_at FROM projects WHERE id = ?",
                (project_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            raise LookupError(f"Project {project_id} not found")
        return {"id": row[0], "org_id": row[1], "name": row[2], "slug": row[3], "created_at": row[4]}

    async def _insert_audit_event(
        self,
        db: aiosqlite.Connection,
        org_id: str,
        project_id: str | None,
        event_type: str,
        actor: str | None,
        details: dict,
    ) -> None:
        await db.execute(
            "INSERT INTO audit_events(org_id, project_id, event_type, actor, created_at, details) VALUES(?, ?, ?, ?, ?, ?)",
            (org_id, project_id, event_type, actor, time(), json.dumps(details, sort_keys=True)),
        )


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or Path(value).stem.lower() or uuid4().hex[:12]