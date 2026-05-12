"""Public Parser pipeline entry points."""

from .Tools.parser import (
    ChromaManager,
    DatabaseManager,
    DocumentParseProfile,
    ExtractiveSummaryBuilder,
    OrdinancePdfParser,
    ParserComponentFactory,
    ParserPaths,
    ParserPipelineBuilder,
    StructuredDocumentBuilder,
)


def build_parser_pipeline(paths: ParserPaths | None = None) -> OrdinancePdfParser:
    """Build the parser pipeline through the established builder."""

    builder = ParserPipelineBuilder()
    if paths is not None:
        builder = builder.with_paths(paths)
    return builder.build()


__all__ = [
    "DocumentParseProfile",
    "ChromaManager",
    "DatabaseManager",
    "ExtractiveSummaryBuilder",
    "OrdinancePdfParser",
    "ParserComponentFactory",
    "ParserPaths",
    "ParserPipelineBuilder",
    "StructuredDocumentBuilder",
    "build_parser_pipeline",
]
