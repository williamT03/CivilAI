# CivilAI Agentic Test Harness

This folder contains focused engineering agents for validating CivilAI.

## Agents

- `security`: static and runtime security checks for env hygiene, auth behavior, headers, and dependency audit support.
- `api-contract`: backend API contract smoke tests for health, auth, validation, and protected routes.
- `feature-flow`: frontend/backend feature checks for build health, route presence, API configuration, and user-facing pages.

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
