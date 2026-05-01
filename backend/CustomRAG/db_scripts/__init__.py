"""
Public package exports for the normalized database and Chroma storage layer.

The parser stack depends on PyMuPDF, so parser-specific exports are loaded
optionally. That keeps DB/Chroma consumers working even in lightweight
interpreters where parser-only dependencies are not installed.
"""

from .DB import (
    ChapterDefinition,
    DatabaseManager,
    DocumentDefinition,
    DocumentSchemaBuilder,
    SectionDefinition,
    SubsectionDefinition,
)
from .chroma import (
    ChromaCollectionFactory,
    ChromaDocumentBuilder,
    ChromaDocumentPayload,
    ChromaManager,
    ChromaNode,
)

try:
    from .parse import (
        DocumentParseProfile,
        ExtractiveSummaryBuilder,
        OrdinancePdfParser,
        ParserComponentFactory,
        ParserPaths,
        ParserPipelineBuilder,
        StructuredDocumentBuilder,
    )
    PARSER_IMPORT_ERROR = None
except Exception as error:  # pragma: no cover - parser deps can be optional in some runtimes
    DocumentParseProfile = None
    ExtractiveSummaryBuilder = None
    OrdinancePdfParser = None
    ParserComponentFactory = None
    ParserPaths = None
    ParserPipelineBuilder = None
    StructuredDocumentBuilder = None
    PARSER_IMPORT_ERROR = error

__all__ = [
    "ChapterDefinition",
    "ChromaCollectionFactory",
    "ChromaDocumentBuilder",
    "ChromaDocumentPayload",
    "ChromaManager",
    "ChromaNode",
    "DatabaseManager",
    "DocumentDefinition",
    "DocumentSchemaBuilder",
    "SectionDefinition",
    "SubsectionDefinition",
]

if PARSER_IMPORT_ERROR is None:
    __all__.extend(
        [
            "DocumentParseProfile",
            "ExtractiveSummaryBuilder",
            "OrdinancePdfParser",
            "ParserComponentFactory",
            "ParserPaths",
            "ParserPipelineBuilder",
            "StructuredDocumentBuilder",
        ]
    )
