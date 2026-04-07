# Session Sift Cloud Platform Plan

This plan turns the README's OSS-vs-Cloud split into an actual product architecture. The rule is simple: **OSS stays local and inspectable; Cloud is additive team infrastructure on top of the OSS core.**

## Goals

1. Preserve the current OSS product as the local-first engine: CLI, proxy, MCP, SDK, local DNA, deterministic pruning, local semantic fallback.
2. Add Team Cloud services that give teams shared visibility and shared context without breaking local workflows.
3. Build the backend API first, then a focused dashboard frontend that sits on top of those APIs.

## Cloud Scope Derived From README

### OSS (already in repo)

- Pass 1 structural pruning
- Pass 2 temporal pruning with SQLite registry
- Pass 3 semantic compression with BYO API key
- Local MCP server
- Local multi-provider proxy
- Project DNA export/import
- Python SDK
- GitHub Actions savings gate
- Console SavingsReport

### Cloud / Team Tier (to build)

- Team dashboard and aggregate savings trends
- Cloud DNA Sync for shared project context across developers
- Shared organization rules (`.session-sift/rules` semantics managed centrally)
- Centralized audit history
- SavingsReport web dashboard and Slack digest delivery

### Enterprise Follow-ons (not in first backend cut)

- GitHub App onboarding
- SAML SSO
- On-prem deployment
- Compliance export

## Backend Plan

### Phase 1: Team Cloud API foundation

Status: implemented in this change set.

FastAPI service with SQLite persistence for local development and API contract stabilization.

Implemented endpoints:

- `GET /healthz`
- `GET /api/v1/orgs`
- `POST /api/v1/orgs`
- `GET /api/v1/orgs/{org_id}/projects`
- `POST /api/v1/orgs/{org_id}/projects`
- `GET /api/v1/orgs/{org_id}/rules`
- `PUT /api/v1/orgs/{org_id}/rules`
- `GET /api/v1/orgs/{org_id}/dashboard`
- `GET /api/v1/orgs/{org_id}/audit-history`
- `POST /api/v1/projects/{project_id}/reports`
- `GET /api/v1/projects/{project_id}/dashboard`
- `POST /api/v1/projects/{project_id}/dna/sync`
- `GET /api/v1/projects/{project_id}/dna/latest`
- `GET /api/v1/projects/{project_id}/audit-history`
- `GET /api/v1/projects/{project_id}/slack/daily-digest`

Core backend entities:

- `organizations`
- `projects`
- `rule_sets`
- `savings_reports`
- `dna_snapshots`
- `audit_events`

### Phase 2: Production backend hardening

- Replace SQLite dev storage with Postgres for multi-tenant production.
- Add authn/authz: session tokens for local dev, then GitHub OAuth or Clerk/Auth0 for hosted.
- Add RBAC roles: owner, maintainer, viewer.
- Add project membership tables.
- Add webhook delivery for Slack instead of preview-only digest endpoint.
- Add background jobs for daily digest generation and dashboard rollups.
- Add rate limiting and request IDs.

### Phase 3: Enterprise backend

- SAML/OIDC SSO
- audit export endpoints
- on-prem deployment packaging
- tenant isolation and encryption policy controls

## Frontend Plan

### App surfaces

1. Organization dashboard
   Shows total savings, daily trend, top projects, recent audit activity.

2. Project dashboard
   Shows recent sessions, per-pass savings, latest DNA snapshot summary, daily digest preview.

3. Rules manager
   YAML editor for org-wide rules with version history and validation.

4. DNA sync explorer
   Shows latest cloud DNA, diff summary from last sync, recent decisions, active TODOs.

5. Audit history view
   Searchable event stream across reports, rules, DNA syncs, and onboarding changes.

### Frontend stack recommendation

- Next.js App Router for the hosted product shell
- React + TypeScript
- TanStack Query for API state
- Recharts or Visx for savings graphs
- Monaco editor for YAML rules
- shadcn/ui or a similarly restrained component base, then customize branding

### Frontend route map

- `/login`
- `/orgs/:orgSlug`
- `/orgs/:orgSlug/projects/:projectSlug`
- `/orgs/:orgSlug/rules`
- `/orgs/:orgSlug/audit`
- `/orgs/:orgSlug/projects/:projectSlug/dna`

## Integration Plan With OSS Clients

1. Proxy/MCP/SDK continue emitting local `SavingsReport` and local DNA snapshots.
2. OSS clients optionally POST reports to Cloud using the Team API.
3. OSS clients optionally sync DNA by POSTing `{base, local}` and receiving merged cloud DNA.
4. OSS clients optionally fetch org rules and apply them before prune/refine cycles.

## API Contract Priorities

### First production client integrations

1. SavingsReport ingestion from proxy mode
2. DNA sync from CLI / SDK
3. Rules fetch from proxy / MCP startup

### Second-wave integrations

1. Slack webhook delivery
2. GitHub App setup flow
3. Billing and subscription enforcement

## Run The Team Cloud API Locally

```bash
pip install -e .[cloud]
session-sift cloud-api --host 127.0.0.1 --port 9980
```

Local dev database path:

```text
.session-sift/team-cloud.db
```

## Definition Of Done For Backend MVP

- FastAPI service runs locally
- Organizations, projects, and rules are persisted
- Savings reports can be ingested and aggregated into dashboards
- DNA sync performs deterministic 3-way merge
- Audit history records major cloud mutations
- API tests cover the full happy path

## Definition Of Done For Frontend MVP

- Organization dashboard renders live API data
- Project dashboard shows aggregate and recent-session metrics
- Rules page updates org-wide rules
- DNA page shows latest merged snapshot and diff summary
- Audit page shows searchable event history