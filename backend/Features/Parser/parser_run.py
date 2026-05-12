"""Public Parser feature entry points."""

from backend.CustomRAG.db_scripts import ParserPaths

from .Tools.parser import ParserPipelineBuilder


def build_parser_pipeline(paths: ParserPaths | None = None):
    """Build the parser pipeline through the established builder."""

    builder = ParserPipelineBuilder()
    if paths is not None:
        builder = builder.with_paths(paths)
    return builder.build()


__all__ = ["build_parser_pipeline"]
