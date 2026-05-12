# Backend Feature Map

The backend is organized around feature facades. Each facade gives programmers a small public file to call while the heavier builders and implementation details stay behind `Tools/`.

## Current Facades

- `Features/Auth/auth_run.py`: authentication router, current-user dependency, token helpers, and auth database.
- `Features/API/api_run.py`: versioned platform API router and schemas.
- `Features/Config/config_run.py`: runtime settings and environment configuration.
- `Features/Ingestion/ingestion_run.py`: ingestion job models and queue-facing helpers.
- `Features/LLM/llm_run.py`: custom RAG answering, generation, streaming, and provider routing.
- `Features/Parser/parser_run.py`: parser pipeline and document-structure builders.
- `Features/Pipeline/pipeline_run.py`: end-to-end PDF parsing/indexing pipeline entry points.
- `Features/RAG/rag_run.py`: navigation, retrieval, database, and vector-store builders.
- `Features/Runtime/runtime_run.py`: FastAPI app entry points and runtime service modules.
- `Features/Storage/storage_run.py`: local/cloud storage and vector-store helpers.
- `Features/Tests/test_run.py`: backend test command references.
- `Features/__init__.py`: the final feature facade for importing common backend capabilities.

## Compatibility

Existing imports such as `backend.app.auth` and `backend.CustomRAG.db_scripts` still work. The feature facade is for readability and future code, not a breaking migration.
