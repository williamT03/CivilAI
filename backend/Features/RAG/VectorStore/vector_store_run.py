"""Public RAG vector-store subfeature entry points."""

from .Tools.vector_store import ChromaManager, create_runtime_vector_manager


def build_vector_manager():
    """Build the configured vector manager for runtime retrieval."""

    return create_runtime_vector_manager()


__all__ = ["ChromaManager", "build_vector_manager", "create_runtime_vector_manager"]
