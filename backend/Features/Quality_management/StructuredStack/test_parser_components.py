"""Focused tests for parser-side helpers that do not require a real PDF file."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make the repo importable even when this test module is run directly from the
# moved `backend/Features/Quality_management/StructuredStack` location.
REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
try:
    from backend.Features.Pipeline_management.Parser.Tools.parser import (
        ExtractiveSummaryBuilder,
        ParserComponentFactory,
        StructuredDocumentBuilder,
    )

    PARSER_IMPORT_ERROR = None
except Exception as error:  # pragma: no cover - depends on local parser runtime
    ExtractiveSummaryBuilder = None
    ParserComponentFactory = None
    StructuredDocumentBuilder = None
    PARSER_IMPORT_ERROR = error


@unittest.skipIf(
    PARSER_IMPORT_ERROR is not None, f"Parser dependencies unavailable: {PARSER_IMPORT_ERROR}"
)
class TestParserComponents(unittest.TestCase):
    """Exercise the builder and summary logic that shapes parser output."""

    def test_summary_builder_prefers_first_sentence_when_short(self) -> None:
        summary_builder = ExtractiveSummaryBuilder()
        summary = summary_builder.summarize(
            "This section governs enforcement authority. It also describes delegation."
        )

        self.assertEqual(summary, "This section governs enforcement authority.")

    def test_structured_document_builder_merges_duplicate_sections(self) -> None:
        builder = StructuredDocumentBuilder(
            document_title="Sample City Code of Ordinances",
            source_filename="sample.pdf",
            toc_chapters=[
                {
                    "chapter_number": "1",
                    "chapter_name": "General Provisions",
                    "toc_page": 10,
                }
            ],
        )

        # Seed a short duplicate preview section first.
        builder.start_section("1", "Sec. 1-2", "Enforcement authority.")
        builder.append_text("The city manager may enforce.")

        # Then start the same section again with the richer body and subsection.
        builder.start_section("1", "Sec. 1-2", "Enforcement authority.")
        builder.append_text("The city manager may adminis-")
        builder.append_text("tration remedies and enforce the code.")
        builder.start_subsection("(a)", "Primary officer.")
        builder.append_text("The city manager is the primary enforcement official.")

        payload = builder.build_payload()
        section = payload[0]["sections"][0]

        self.assertEqual(len(payload[0]["sections"]), 1)
        self.assertIn("administration remedies", section["section_text"].lower())
        self.assertEqual(section["subsection_count"], 1)
        self.assertEqual(section["subsections"][0]["subsection_number"], "(a)")

    def test_parser_component_factory_uses_structured_database_path(self) -> None:
        paths = ParserComponentFactory.create_default_paths()

        self.assertEqual(paths.db_path.name, "civilai_structured.db")
        self.assertEqual(paths.chroma_dir.name, "chroma_db")


if __name__ == "__main__":
    unittest.main()
