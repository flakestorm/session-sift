from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from session_sift.cloud.api import create_cloud_app


def test_cloud_api_org_project_rules_dashboard_and_dna(tmp_path: Path) -> None:
    app = create_cloud_app(db_path=str(tmp_path / "team-cloud.db"))

    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        org_response = client.post("/api/v1/orgs", json={"name": "FlakeStorm"})
        assert org_response.status_code == 201
        org = org_response.json()

        project_response = client.post(
            f"/api/v1/orgs/{org['id']}/projects",
            json={"name": "Session Sift Cloud"},
        )
        assert project_response.status_code == 201
        project = project_response.json()

        rules_response = client.put(
            f"/api/v1/orgs/{org['id']}/rules",
            json={
                "rules_text": "version: 1\nprotected:\n  - STRICT\n  - TODO\n",
                "updated_by": "fhumarang",
            },
        )
        assert rules_response.status_code == 200
        assert rules_response.json()["version"] == 1

        report_response = client.post(
            f"/api/v1/projects/{project['id']}/reports",
            json={
                "session_id": "sess-001",
                "user_id": "fhumarang",
                "original_tokens": 12000,
                "refined_tokens": 7200,
                "pass1_savings": 800,
                "pass2_savings": 600,
                "pass3_savings": 400,
                "elapsed_ms": 14.8,
                "turn": 18,
                "provider": "openai",
                "client_name": "cursor",
                "metadata": {"branch": "main"},
            },
        )
        assert report_response.status_code == 201
        report = report_response.json()
        assert report["total_savings"] == 4800

        dna_response = client.post(
            f"/api/v1/projects/{project['id']}/dna/sync",
            json={
                "author": "fhumarang",
                "base": {},
                "local": {
                    "$schema": "https://session-sift.dev/dna/v2.json",
                    "version": 2,
                    "files_modified": [
                        {
                            "path": "session_sift/cloud/api.py",
                            "last_write_turn": 18,
                            "sha256": "abc123",
                            "summary": "Added FastAPI team cloud endpoints",
                        }
                    ],
                    "resolved_errors": [
                        {
                            "error_type": "ImportError",
                            "file_path": "session_sift/cloud/api.py",
                            "resolved_at_turn": 18,
                        }
                    ],
                    "active_todos": [{"file_path": "frontend/dashboard.tsx", "line": 1, "text": "Build team dashboard"}],
                    "key_decisions": [{"turn": 18, "summary": "FastAPI chosen for Team Cloud API"}],
                    "context_summary": "Team cloud API bootstrapped",
                    "total_turns": 18,
                    "total_tokens_saved": 4800,
                },
            },
        )
        assert dna_response.status_code == 201
        dna_payload = dna_response.json()
        assert dna_payload["merged"]["context_summary"] == "Team cloud API bootstrapped"
        assert dna_payload["diff"]["added_files"][0]["path"] == "session_sift/cloud/api.py"

        latest_dna = client.get(f"/api/v1/projects/{project['id']}/dna/latest")
        assert latest_dna.status_code == 200
        assert latest_dna.json()["snapshot"]["total_tokens_saved"] == 4800

        project_dashboard = client.get(f"/api/v1/projects/{project['id']}/dashboard")
        assert project_dashboard.status_code == 200
        assert project_dashboard.json()["total_tokens_saved"] == 4800
        assert project_dashboard.json()["latest_context_summary"] == "Team cloud API bootstrapped"

        org_dashboard = client.get(f"/api/v1/orgs/{org['id']}/dashboard")
        assert org_dashboard.status_code == 200
        assert org_dashboard.json()["total_sessions"] == 1

        org_audit = client.get(f"/api/v1/orgs/{org['id']}/audit-history")
        assert org_audit.status_code == 200
        event_types = {entry["event_type"] for entry in org_audit.json()}
        assert {"org.created", "project.created", "rules.updated", "report.ingested", "dna.synced"}.issubset(event_types)

        digest = client.get(f"/api/v1/projects/{project['id']}/slack/daily-digest")
        assert digest.status_code == 200
        assert "tokens saved" in digest.json()["message"]


def test_cloud_api_returns_404_for_unknown_project(tmp_path: Path) -> None:
    app = create_cloud_app(db_path=str(tmp_path / "team-cloud.db"))

    with TestClient(app) as client:
        response = client.get("/api/v1/projects/missing/dashboard")
        assert response.status_code == 404