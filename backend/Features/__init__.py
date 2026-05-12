"""Readable backend feature facades.

Import from this package when you want the high-level backend capabilities
without opening the implementation folders first.
"""

from backend.Features.API.api_run import api_v1_router
from backend.Features.Auth.auth_run import auth_db, auth_router, get_current_user
from backend.Features.Ingestion.ingestion_run import build_ingestion_job_response
from backend.Features.LLM.llm_run import ask_custom_rag, generate_answer, stream_answer
from backend.Features.Parser.parser_run import build_parser_pipeline
from backend.Features.Pipeline.pipeline_run import build_default_pipeline
from backend.Features.RAG.rag_run import build_navigation_toolkit
from backend.Features.Storage.storage_run import get_storage_backend

__all__ = [
    "auth_db",
    "auth_router",
    "api_v1_router",
    "ask_custom_rag",
    "build_default_pipeline",
    "build_ingestion_job_response",
    "build_navigation_toolkit",
    "build_parser_pipeline",
    "generate_answer",
    "get_current_user",
    "get_storage_backend",
    "stream_answer",
]
