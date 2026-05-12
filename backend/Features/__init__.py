"""Readable backend feature entry points.

The feature package stays lazy on purpose: importing `backend.Features.*`
should not create database connections, vector-store clients, or FastAPI apps.
Use the named `*_run.py` modules when you want to execute a feature.
"""

__all__ = [
    "api_v1_router",
    "ask_custom_rag",
    "auth_db",
    "auth_router",
    "build_default_pipeline",
    "build_ingestion_job_response",
    "build_navigation_toolkit",
    "build_parser_pipeline",
    "generate_answer",
    "get_current_user",
    "get_storage_backend",
    "stream_answer",
]


def __getattr__(name: str):
    """Resolve public feature helpers lazily to avoid import side effects."""

    if name == "api_v1_router":
        from backend.Features.API_management.api_run import api_v1_router

        return api_v1_router
    if name in {"auth_db", "auth_router", "get_current_user"}:
        from backend.Features.User_management import auth_run

        return getattr(auth_run, name)
    if name == "build_ingestion_job_response":
        from backend.Features.Pipeline_management.Ingestion.ingestion_run import (
            build_ingestion_job_response,
        )

        return build_ingestion_job_response
    if name in {"ask_custom_rag", "generate_answer", "stream_answer"}:
        from backend.Features.LLM_management import llm_run

        return getattr(llm_run, name)
    if name == "build_parser_pipeline":
        from backend.Features.Pipeline_management.Parser.parser_run import build_parser_pipeline

        return build_parser_pipeline
    if name == "build_default_pipeline":
        from backend.Features.Pipeline_management.Pipeline.pipeline_run import (
            build_default_pipeline,
        )

        return build_default_pipeline
    if name == "build_navigation_toolkit":
        from backend.Features.RAG_management.rag_run import build_navigation_toolkit

        return build_navigation_toolkit
    if name == "get_storage_backend":
        from backend.Features.Storage_management.storage_run import get_storage_backend

        return get_storage_backend
    raise AttributeError(f"module 'backend.Features' has no attribute {name!r}")
