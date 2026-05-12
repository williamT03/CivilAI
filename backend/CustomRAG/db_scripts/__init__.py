"""
Public package exports for the normalized database and Chroma storage layer.

The parser stack depends on PyMuPDF, so parser-specific exports are loaded
optionally. That keeps DB/Chroma consumers working even in lightweight
interpreters where parser-only dependencies are not installed.
"""

from .chroma import (
    ChromaCollectionFactory,
    ChromaDocumentBuilder,
    ChromaDocumentPayload,
    ChromaManager,
    ChromaNode,
    SentenceTransformerEmbeddingProvider,
    create_runtime_chroma_builder,
)
from .DB import (
    ChapterDefinition,
    DatabaseManager,
    DocumentDefinition,
    DocumentSchemaBuilder,
    SectionDefinition,
    SubsectionDefinition,
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
    "SentenceTransformerEmbeddingProvider",
    "DatabaseManager",
    "DocumentDefinition",
    "DocumentSchemaBuilder",
    "SectionDefinition",
    "SubsectionDefinition",
    "create_runtime_chroma_builder",
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
