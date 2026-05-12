# CivilAI Feature Folder Map

CivilAI uses feature folders as readable front doors over the working code. Each feature folder follows the same template:

```text
Feature/
  README.md
  feature_run.py or feature_run.ts
  Tools/
    builders_or_adapters
```

The `*_run` file is the public surface. `Tools/` is where builders, adapters, and low-level implementation details are collected. Existing framework-required files, such as Next.js `app/*/page.tsx` routes and FastAPI startup files, stay where the frameworks expect them.

## Top-Level Areas

- `backend/Features`: backend feature facades for API, auth, RAG, LLM/providers, ingestion, storage, and deployment runtime.
- `frontend/Website/civil-ai-web/Features`: frontend feature facades for chat, auth experience, layout, routes, API clients, and assets.
- `backend/agents/Features`: agentic engineering facades for runners, check agents, runtime checks, static checks, reporting, and deploy automation.
- `scripts/Features`: utility script facades for formatting and ordinance downloads.
- `deploy/Features`: deployment config purpose docs and entry points.

## Why This Exists

The implementation can be deep, but the entry point should be obvious. A programmer should be able to open a feature folder, read the README, and call the run file without needing to understand every builder behind it.
