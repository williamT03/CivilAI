"""Focused tests for the structured Chroma vector storage layer."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make the repo importable even when this test module is run directly from the
# moved `backend/Features/Quality_management/StructuredStack` location.
REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.Features.Database_management.Builders.chroma import ChromaCollectionFactory
from backend.Features.Quality_management.StructuredStack.support import StructuredStackFixture


class TestChromaManager(unittest.TestCase):
    """Verify vector collections, batching, and semantic lookup behavior."""

    def setUp(self) -> None:
        self.fixture = StructuredStackFixture()
        self.fixture.seed_document()
        self.chroma_manager = self.fixture.chroma_manager

    def tearDown(self) -> None:
        self.fixture.cleanup()

    def test_collection_counts_match_expected_node_totals(self) -> None:
        counts = self.chroma_manager.collection_counts()

        self.assertEqual(counts[ChromaCollectionFactory.DOCUMENT_COLLECTION], 1)
        self.assertEqual(counts[ChromaCollectionFactory.CHAPTER_COLLECTION], 2)
        self.assertEqual(counts[ChromaCollectionFactory.SECTION_COLLECTION], 3)
        self.assertEqual(counts[ChromaCollectionFactory.SUBSECTION_COLLECTION], 3)

    def test_section_query_returns_relevant_section_metadata(self) -> None:
        results = self.chroma_manager.query_collection(
            collection_name=ChromaCollectionFactory.SECTION_COLLECTION,
            query_text="night construction noise after 9 p.m.",
            n_results=3,
        )

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["metadata"]["section_number"], "Sec. 2-10")

    def test_subsection_query_returns_relevant_subsection_metadata(self) -> None:
        results = self.chroma_manager.query_collection(
            collection_name=ChromaCollectionFactory.SUBSECTION_COLLECTION,
            query_text="designate code compliance officers",
            n_results=3,
        )

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["metadata"]["subsection_number"], "(b)")


if __name__ == "__main__":
    unittest.main()
