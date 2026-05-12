"""Public Database Management entry points."""

from .Builders.chroma import (
    ChromaCollectionFactory,
    ChromaDocumentBuilder,
    ChromaManager,
    QdrantStructuredManager,
    create_runtime_vector_manager,
)
from .Builders.DB import DatabaseManager, DocumentSchemaBuilder, RelationalSchemaFactory


def build_database_manager() -> DatabaseManager:
    """Create the default relational database manager."""

    return DatabaseManager()


def build_vector_manager():
    """Create the configured vector manager."""

    return create_runtime_vector_manager()


__all__ = [
    "ChromaCollectionFactory",
    "ChromaDocumentBuilder",
    "ChromaManager",
    "DatabaseManager",
    "DocumentSchemaBuilder",
    "QdrantStructuredManager",
    "RelationalSchemaFactory",
    "build_database_manager",
    "build_vector_manager",
    "create_runtime_vector_manager",
]
