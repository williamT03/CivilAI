# CivilAI Agentic Test Harness

This folder contains focused engineering agents for validating CivilAI.

## Agents

- `security`: static and runtime security checks for env hygiene, auth behavior, headers, and dependency audit support.
- `api-contract`: backend API contract smoke tests for health, auth, validation, and protected routes.
- `feature-flow`: frontend/backend feature checks for build health, route presence, API configuration, and user-facing pages.
- `frontend-features`: deeper static checks for auth, chat, account, subscription, upload, guest, and saved-thread features.
- `server-connections`: runtime checks for backend API wiring, CORS, custom RAG endpoints, metrics, auth, and frontend reachability.
- `server-runtime`: server deployment checks for systemd, Docker Compose, data directories, and deploy artifacts.

## Design

The harness follows a small template-method pattern:

1. Each agent extends `BaseAgent`.
2. Each agent returns a list of `CheckResult` objects.
3. `runner.py` handles selection, execution, console output, and JSON reports.

This keeps new agents easy to add without changing the runner.

## Usage

Run all first-wave agents:

```powershell
.\agents\run_agents.ps1
```

Run one agent:

```powershell
.\agents\run_agents.ps1 -Agent security
.\agents\run_agents.ps1 -Agent api-contract
.\agents\run_agents.ps1 -Agent feature-flow
.\agents\run_agents.ps1 -Agent frontend-features
.\agents\run_agents.ps1 -Agent server-connections
.\agents\run_agents.ps1 -Agent server-runtime
```

Point runtime checks at a different backend:

```powershell
.\agents\run_agents.ps1 -BackendUrl http://127.0.0.1:8000
```

Write reports somewhere else:

```powershell
.\agents\run_agents.ps1 -ReportDir .\agents\reports\local-run
```

## Runtime Expectations

Some checks are static and always run. Runtime checks need the app running:

```powershell
.\run-local.ps1
```

Default URLs:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://localhost:3000`

Reports are written to `agents/reports/` and ignored by git.

## Running On The Server

Copy or pull this repo on the Linux server, then run:

```bash
chmod +x ./agents/run_agents_server.sh
./agents/run_agents_server.sh
```

Run a single server-focused agent:

```bash
./agents/run_agents_server.sh server-connections
./agents/run_agents_server.sh server-runtime
```

Override deployed URLs:

```bash
export CIVILAI_BACKEND_URL="https://api.yourdomain.com"
export CIVILAI_FRONTEND_URL="https://your-frontend.pages.dev"
./agents/run_agents_server.sh all
```

Server reports are written to `agents/reports/server/` by default.
