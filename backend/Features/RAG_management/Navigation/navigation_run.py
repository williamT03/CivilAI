"""Public RAG navigation subfeature entry points."""

from .Tools.navigation import StructuredRetrievalToolkit, StructuredToolFactory, StructuredToolPaths


def build_navigation_toolkit():
    """Build the default structured retrieval toolkit."""

    return StructuredToolFactory.create_toolkit()


__all__ = [
    "StructuredRetrievalToolkit",
    "StructuredToolFactory",
    "StructuredToolPaths",
    "build_navigation_toolkit",
]
