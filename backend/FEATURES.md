# Backend Feature Map

The backend is organized around feature folders. Each feature exposes a small `*_run.py` file for the readable entry point while heavier builders and implementation details live behind `Tools/` or `Builders/`.

## Current Management Domains

- `Features/API_management/api_run.py`: versioned platform API router and schemas.
- `Features/User_management/auth_run.py`: authentication, account data, saved chat ownership, uploads, subscriptions, and API keys.
- `Features/Runtime_management/backend_run.py`: FastAPI app entry point, middleware, security boundary, metrics, and health checks.
- `Features/Runtime_management/Config/config_run.py`: runtime settings and environment configuration.
- `Features/Database_management/Database_run.py`: SQLite, Alembic migrations, Chroma, and database builders.
- `Features/Pipeline_management/Parser/parser_run.py`: parser pipeline and document-structure builders.
- `Features/Pipeline_management/Pipeline/pipeline_run.py`: end-to-end PDF parsing/indexing pipeline entry points.
- `Features/Pipeline_management/Ingestion/ingestion_run.py`: ingestion job models and queue-facing helpers.
- `Features/LLM_management/llm_run.py`: answer generation, streaming, provider routing, usage tracking, and Ollama helpers.
- `Features/RAG_management/rag_run.py`: navigation, retrieval, grounding, and custom RAG API wiring.
- `Features/Storage_management/storage_run.py`: local/cloud file storage and vector-store helpers.
- `Features/Quality_management/test_run.py`: backend test command references.
- `Features/__init__.py`: lazy feature facade for importing common backend capabilities without startup side effects.

## Compatibility

External servers should prefer `backend.Features.Runtime_management.backend_run:app`. `backend.main:app` remains only as a small compatibility shim.
