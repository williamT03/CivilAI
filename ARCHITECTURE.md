# CivilAI Architecture

CivilAI is organized around a small set of explicit boundaries:

- `backend/`: FastAPI package shell and compatibility entry point.
- `backend/Features/`: backend features split into runnable `*_run.py` entry points and implementation `Tools/` builders.
- `frontend/Website/civil-ai-web/`: Next.js web application.
- `backend/agents/`: agentic engineering harness for security, runtime, deployment, frontend, and policy checks.
- `deploy/`: deployment templates for backend service and nginx.
- `scripts/`: operational and data utility scripts.

## Backend Pattern

The backend uses a feature-builder pattern:

- API contracts live under `backend/Features/API_management`.
- Runtime FastAPI wiring and config live under `backend/Features/Runtime_management`.
- User/auth workflows live under `backend/Features/User_management`.
- Database, Chroma, and migrations live under `backend/Features/Database_management`.
- Parsing, indexing, and ingestion live under `backend/Features/Pipeline_management`.
- RAG, LLM, and storage each own their builders under their matching management domain.

Recommended direction:

- Keep route handlers thin.
- Move long workflows into service classes.
- Keep persistence decisions inside database/store classes.
- Keep tenant ownership checks close to the data access layer.
- Prefer explicit factories/builders for configurable runtime components.

## Agent Harness Pattern

The agent harness uses three patterns:

- **Template Method**: every agent subclasses `BaseAgent` and implements `run()`.
- **Registry**: `backend/agents/Features/Checks_management/Tools/__init__.py` maps stable agent names to classes.
- **Builder**: `AgentRunPlanBuilder` resolves CLI inputs into an immutable `AgentRunPlan`.

This keeps the runner small:

1. Parse CLI arguments.
2. Build a run plan.
3. Execute selected agents.
4. Write reports.

## Frontend Pattern

The frontend follows a route/component/context split:

- `app/context/`: long-lived client state such as auth and theme.
- `app/components/`: reusable interface components.
- `app/lib/`: small framework-neutral helpers.
- `app/<route>/page.tsx`: page-level workflows.

Recommended direction:

- Keep page files focused on orchestration.
- Move repeated fetch logic into typed client helpers.
- Keep local storage/session storage behavior in small library modules.
- Use context only for truly global state.

## Formatting

Python:

```bash
python -m isort backend scripts
python -m black backend scripts
```

Frontend:

```bash
cd frontend/Website/civil-ai-web
npm run format
```

All formatting:

```bash
./scripts/format.sh
```

PowerShell:

```powershell
.\scripts\format.ps1
```

## Testing And Verification

Backend unit-style tests:

```bash
powershell -ExecutionPolicy Bypass -File backend\Features\Quality_management\StructuredStack\run_all_tests.ps1
```

Frontend:

```bash
cd frontend/Website/civil-ai-web
npm run lint
npm run build
```

Agentic server checks:

```bash
./backend/agents/run_agents_server.sh server-safe
./backend/agents/run_agents_server.sh runtime-deep
```

## Refactor Rules

Use a builder when setup has multiple optional parameters and a final immutable product.

Use a factory when choosing between implementations, such as local storage vs S3/R2 or Chroma vs Qdrant.

Use a service class when a workflow has meaningful steps, side effects, or policy decisions.

Avoid adding abstractions around simple one-line operations.
