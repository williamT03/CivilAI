"""Public RAG database subfeature entry points."""

from .Tools.database import DatabaseManager, DocumentSchemaBuilder, RelationalSchemaFactory


def build_database_manager() -> DatabaseManager:
    """Create the default structured database manager."""

    return DatabaseManager()


__all__ = [
    "DatabaseManager",
    "DocumentSchemaBuilder",
    "RelationalSchemaFactory",
    "build_database_manager",
]
