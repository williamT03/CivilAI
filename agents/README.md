# CivilAI Agentic Test Harness

This folder contains focused engineering agents for validating CivilAI.

## Agents

- `security`: static and runtime security checks for env hygiene, auth behavior, headers, and dependency audit support.
- `api-contract`: backend API contract smoke tests for health, auth, validation, and protected routes.
- `feature-flow`: frontend/backend feature checks for build health, route presence, API configuration, and user-facing pages.
- `frontend-features`: deeper static checks for auth, chat, account, subscription, upload, guest, and saved-thread features.
- `server-connections`: runtime checks for backend API wiring, CORS, custom RAG endpoints, metrics, auth, and frontend reachability.
- `server-runtime`: server deployment checks for systemd, Docker Compose, data directories, and deploy artifacts.
- `risk-register`: writes a living risk register mapped to agent coverage.
- `policy-gate`: static release gate for critical security controls.
- `threat-model`: STRIDE checks for auth, uploads, RAG, API, and deployment boundaries.
- `data-leak`: scans source/runtime responses for secrets, paths, tokens, and frontend env leaks.
- `tenant-isolation`: runtime cross-user isolation checks for chats, API keys, uploads, and jobs.
- `llm-safety`: LLM/RAG safety checks, with model-calling probes opt-in via `CIVILAI_RUN_LLM_SAFETY=true`.
- `audit-log`: verifies security audit events are wired.
- `deployment-gate`: server release gate for secrets, service health, CORS, headers, and deploy config.

## Design

The harness follows a small template-method pattern:

1. Each agent extends `BaseAgent`.
2. Each agent returns a list of `CheckResult` objects.
3. `runner.py` handles selection, execution, console output, and JSON reports.
4. `AgentRunPlanBuilder` resolves CLI inputs into a concrete run plan.

This keeps new agents easy to add without changing the runner.

## Usage

Run all first-wave agents:

```powershell
.\agents\run_agents.ps1
```

Run a group:

```powershell
.\agents\run_agents.ps1 -Agent server-safe
.\agents\run_agents.ps1 -Agent runtime-deep
.\agents\run_agents.ps1 -Agent frontend
```

Run one agent:

```powershell
.\agents\run_agents.ps1 -Agent security
.\agents\run_agents.ps1 -Agent api-contract
.\agents\run_agents.ps1 -Agent feature-flow
.\agents\run_agents.ps1 -Agent frontend-features
.\agents\run_agents.ps1 -Agent server-connections
.\agents\run_agents.ps1 -Agent server-runtime
.\agents\run_agents.ps1 -Agent tenant-isolation
.\agents\run_agents.ps1 -Agent data-leak
.\agents\run_agents.ps1 -Agent deployment-gate
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

Copy or pull this repo on the Linux server, then run manually:

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
./agents/run_agents_server.sh server-safe
```

Server reports are written to `agents/reports/server/` by default.

## Automatic Server Runs

Install the systemd service and timer:

```bash
cd ~/CivilAI
chmod +x ./agents/install_server_timer.sh ./agents/uninstall_server_timer.sh
sudo ./agents/install_server_timer.sh
```

Run once immediately:

```bash
sudo systemctl start civilai-agents.service
```

Check timer status:

```bash
systemctl status civilai-agents.timer
systemctl list-timers civilai-agents.timer
```

View the last run:

```bash
journalctl -u civilai-agents.service -n 100 --no-pager
```

Configure automatic runs:

```bash
sudo nano /etc/civilai/agents.env
```

Important settings:

- `CIVILAI_AGENT_SET=server-safe`
- `CIVILAI_BACKEND_URL=http://127.0.0.1:8000`
- `CIVILAI_FRONTEND_URL=https://civilai.willcloudlab.com`
- `CIVILAI_AGENT_REPORT_DIR=/home/YOUR_LINUX_USER/CivilAI/agents/reports/server`
- `CIVILAI_RUN_LLM_SAFETY=false`

The default timer runs 5 minutes after boot and then every hour. It uses `server-safe`, which avoids routine DB-mutating disposable user checks. Run `runtime-deep` manually when you want tenant/API mutation coverage:

```bash
./agents/run_agents_server.sh runtime-deep
```

Runtime LLM probes stay off unless `CIVILAI_RUN_LLM_SAFETY=true`.

Uninstall the timer:

```bash
sudo ./agents/uninstall_server_timer.sh
```
