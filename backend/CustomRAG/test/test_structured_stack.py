"""End-to-end tests for the new DB/Chroma/tool-driven retrieval stack."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make the repo importable even when this test module is run directly from the
# moved `backend/CustomRAG/test` location.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.CustomRAG.test.support import StructuredStackFixture


class TestStructuredStack(unittest.TestCase):
    """Exercise the full stack the website query path now depends on."""

    def setUp(self) -> None:
        self.fixture = StructuredStackFixture()
        self.fixture.seed_document()
        self.toolkit = self.fixture.toolkit

    def tearDown(self) -> None:
        self.fixture.cleanup()

    def test_navigation_map_contains_document_and_sections(self) -> None:
        navigation_map = self.toolkit.get_navigation_map()

        self.assertIn("sample_city_code_of_ordinances", navigation_map["documents"])
        document = navigation_map["documents"]["sample_city_code_of_ordinances"]
        self.assertEqual(document["chapter_count"], 2)
        self.assertIn("Sec. 1-2", document["chapters"]["1"]["sections"])

    def test_resolve_document_slug_matches_short_jurisdiction_phrase(self) -> None:
        resolved_slug = self.toolkit.resolve_document_slug("sample city")
        self.assertEqual(resolved_slug, "sample_city_code_of_ordinances")

    def test_summarize_sections_combines_exact_section_bodies(self) -> None:
        summary_payload = self.toolkit.summarize_sections(
            "sample_city_code_of_ordinances",
            ["Sec. 1-2", "Sec. 1-3"],
        )

        self.assertIsNotNone(summary_payload)
        self.assertEqual(summary_payload["section_count"], 2)
        self.assertTrue(summary_payload["summary"])

    def test_run_tool_chain_handles_exact_and_semantic_navigation(self) -> None:
        exact_payload = self.toolkit.run_tool_chain(
            "Summarize Sec. 1-2 and Sec. 1-3",
            jurisdiction="Sample City",
        )
        semantic_payload = self.toolkit.run_tool_chain(
            "Who can enforce the city code?",
            jurisdiction="Sample City",
        )

        self.assertTrue(exact_payload["results"])
        self.assertEqual(exact_payload["navigation"]["matched_sections"], ["Sec. 1-2", "Sec. 1-3"])
        self.assertTrue(exact_payload["summary_preview"])

        self.assertTrue(semantic_payload["results"])
        self.assertEqual(semantic_payload["results"][0]["meta"]["section"], "Sec. 1-2")
        self.assertTrue(semantic_payload["tool_trace"])


if __name__ == "__main__":
    unittest.main()
