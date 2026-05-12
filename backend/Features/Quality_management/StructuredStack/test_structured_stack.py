"""End-to-end tests for the new DB/Chroma/tool-driven retrieval stack."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make the repo importable even when this test module is run directly from the
# moved `backend/Features/Quality_management/StructuredStack` location.
REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.Features.Quality_management.StructuredStack.support import StructuredStackFixture


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

    def test_zoning_shorthand_prefers_base_district_setbacks_over_wireless(self) -> None:
        self.fixture.cleanup()
        self.fixture = StructuredStackFixture()
        self.fixture.seed_document(
            document_title="Indian River County, FL Code of Ordinances",
            source_filename="Indian River County, FL Code of Ordinances.pdf",
            chapters=[
                {
                    "chapter_number": "911",
                    "chapter_name": "Zoning Districts",
                    "toc_page": 40,
                    "sections": [
                        {
                            "section_number": "Sec. 911.09",
                            "section_summary": "Commercial district development standards.",
                            "section_text": (
                                "Commercial General CG district development standards. "
                                "Minimum yard setbacks for the CG district are front yard 25 feet, "
                                "side yard 10 feet, and rear yard 20 feet."
                            ),
                            "page_number": 118,
                            "subsections": [],
                        }
                    ],
                },
                {
                    "chapter_number": "971",
                    "chapter_name": "Specific Land Uses",
                    "toc_page": 65,
                    "sections": [
                        {
                            "section_number": "Sec. 971.44",
                            "section_summary": "Wireless facility master plan.",
                            "section_text": (
                                "Wireless communication facility standards for CG and other districts. "
                                "Antenna-supporting structures and wireless equipment must meet special "
                                "setbacks from property lines and occupied residences."
                            ),
                            "page_number": 72,
                            "subsections": [],
                        }
                    ],
                },
            ],
        )
        self.toolkit = self.fixture.toolkit

        for query in (
            "What are the setbacks for CG?",
            "What are the setbacks for Commercial General?",
            "CG building setbacks",
            "commercial zone setbacks",
        ):
            with self.subTest(query=query):
                payload = self.toolkit.run_tool_chain(query, jurisdiction="Indian River County")

                self.assertTrue(payload["results"])
                top_result = payload["results"][0]
                self.assertEqual(top_result["meta"]["section"], "Sec. 911.09")
                self.assertEqual(top_result["meta"]["page"], 118)
                self.assertNotIn("Wireless communication facility", top_result["text"])


if __name__ == "__main__":
    unittest.main()
