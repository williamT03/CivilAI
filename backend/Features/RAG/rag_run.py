"""Public RAG feature entry points."""

from .Tools.rag import StructuredToolFactory, ask, retrieve, stream_ask


def build_navigation_toolkit():
    """Build the default structured retrieval/navigation toolkit."""

    return StructuredToolFactory().build()


def answer_question(question: str, *, jurisdiction: str | None = None):
    """Ask CivilAI's custom RAG stack for a grounded answer."""

    return ask(question, jurisdiction=jurisdiction)


__all__ = [
    "answer_question",
    "ask",
    "build_navigation_toolkit",
    "retrieve",
    "stream_ask",
]
