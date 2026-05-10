"""Focused tests for the normalized relational storage layer."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make the repo importable even when this test module is run directly from the
# moved `backend/CustomRAG/test` location.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.CustomRAG.db_scripts import DatabaseManager
from backend.CustomRAG.test.support import StructuredStackFixture


class TestDatabaseManager(unittest.TestCase):
    """Exercise the exact SQL helpers that the new tool layer depends on."""

    def setUp(self) -> None:
        self.fixture = StructuredStackFixture()
        self.fixture.seed_document()
        self.db_manager = self.fixture.db_manager

    def tearDown(self) -> None:
        self.fixture.cleanup()

    def test_fetch_document_hierarchy_returns_nested_sections(self) -> None:
        hierarchy = self.db_manager.fetch_document_hierarchy("Sample City Code of Ordinances")

        self.assertIsNotNone(hierarchy)
        self.assertEqual(hierarchy["document_slug"], "sample_city_code_of_ordinances")
        self.assertEqual(len(hierarchy["chapters"]), 2)
        self.assertEqual(hierarchy["chapters"][0]["sections"][0]["section_number"], "Sec. 1-2")
        self.assertEqual(
            hierarchy["chapters"][0]["sections"][0]["subsections"][1]["subsection_number"],
            "(b)",
        )

    def test_find_sections_returns_joined_section_context(self) -> None:
        sections = self.db_manager.find_sections(
            document_title_or_slug="sample_city_code_of_ordinances",
            section_numbers=["Sec. 1-2"],
        )

        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["chapter_number"], "1")
        self.assertEqual(sections[0]["chapter_name"], "General Provisions")
        self.assertEqual(len(sections[0]["subsections"]), 2)

    def test_find_subsections_returns_exact_subsection_rows(self) -> None:
        subsections = self.db_manager.find_subsections(
            document_title_or_slug="Sample City Code of Ordinances",
            section_number="Sec. 1-2",
            subsection_numbers=["(b)"],
        )

        self.assertEqual(len(subsections), 1)
        self.assertEqual(subsections[0]["subsection_number"], "(b)")
        self.assertIn("designate code compliance officers", subsections[0]["subsection_text"].lower())

    def test_drop_document_schema_removes_document(self) -> None:
        self.db_manager.drop_document_schema("sample_city_code_of_ordinances")

        self.assertEqual(self.db_manager.list_documents(), [])
        self.assertIsNone(self.db_manager.fetch_document_hierarchy("sample_city_code_of_ordinances"))


if __name__ == "__main__":
    unittest.main()
