"""Public RAG navigation subfeature entry points."""

from .Tools.navigation import StructuredToolFactory


def build_navigation_toolkit():
    """Build the default structured retrieval toolkit."""

    return StructuredToolFactory().build()


__all__ = ["build_navigation_toolkit"]
