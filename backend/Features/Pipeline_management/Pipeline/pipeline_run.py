"""Public indexing pipeline entry points."""

from .Tools.pipeline import ParserPaths, ParserPipelineBuilder


def build_default_pipeline():
    """Build the default parsing/indexing pipeline."""

    return ParserPipelineBuilder().build()


def build_pipeline_with_paths(paths: ParserPaths):
    """Build the parsing/indexing pipeline with explicit storage paths."""

    return ParserPipelineBuilder().with_paths(paths).build()


__all__ = [
    "ParserPaths",
    "ParserPipelineBuilder",
    "build_default_pipeline",
    "build_pipeline_with_paths",
]
