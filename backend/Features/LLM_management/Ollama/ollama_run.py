"""Public Ollama subfeature entry points."""

from .Tools.ollama import OllamaProvider


def build_ollama_provider() -> OllamaProvider:
    """Build an Ollama provider adapter using configured settings."""

    return OllamaProvider()


__all__ = ["OllamaProvider", "build_ollama_provider"]
