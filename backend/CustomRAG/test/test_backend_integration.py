"""Backend-only integration tests for the mounted FastAPI + structured stack."""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Make the repo importable even when this test module is run directly from the
# moved `backend/CustomRAG/test` location.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from backend import main as backend_main
from backend.app import app_custom
from backend.CustomRAG.test.support import StructuredStackFixture

# The FastAPI app imports `CustomRAG.LLM.rag` at runtime, so this integration
# test patches that exact module namespace instead of the parallel
# `backend.CustomRAG...` package copy.
runtime_rag = importlib.import_module("CustomRAG.LLM.rag")


class TestBackendIntegration(unittest.TestCase):
    """Verify the backend routes work together on the new DB/Chroma stack."""

    def setUp(self) -> None:
        self.fixture = StructuredStackFixture()
        self.fixture.seed_document()

        # Swap the live toolkit globals onto the temporary stack so the API
        # routes operate entirely on the test database and Chroma store.
        self.original_app_toolkit = app_custom.TOOLKIT
        self.original_rag_toolkit = runtime_rag.TOOLKIT
        app_custom.TOOLKIT = self.fixture.toolkit
        runtime_rag.TOOLKIT = self.fixture.toolkit

        # Stub the final answer generation so this stays backend-only and does
        # not depend on Ollama being available during test runs.
        self.answer_patch = patch(
            "CustomRAG.LLM.rag.generate_answer",
            side_effect=self._fake_generate_answer,
        )
        self.answer_patch.start()

        self.client = TestClient(backend_main.app)

    def tearDown(self) -> None:
        self.answer_patch.stop()
        app_custom.TOOLKIT = self.original_app_toolkit
        runtime_rag.TOOLKIT = self.original_rag_toolkit
        self.fixture.cleanup()

    def test_health_and_navigation_endpoints_work_on_structured_stack(self) -> None:
        health_response = self.client.get("/health")
        jurisdictions_response = self.client.get("/api/custom/jurisdictions")
        navigation_response = self.client.get("/api/custom/navigation-map")
        structure_response = self.client.get(
            "/api/custom/structure",
            params={"jurisdiction": "Sample City"},
        )

        self.assertEqual(health_response.status_code, 200)
        self.assertTrue(health_response.json()["custom_api"])

        self.assertEqual(jurisdictions_response.status_code, 200)
        jurisdictions = jurisdictions_response.json()["jurisdictions"]
        self.assertEqual(jurisdictions[0]["name"], "Sample City Code of Ordinances")

        self.assertEqual(navigation_response.status_code, 200)
        navigation_documents = navigation_response.json()["documents"]
        self.assertIn("sample_city_code_of_ordinances", navigation_documents)

        self.assertEqual(structure_response.status_code, 200)
        self.assertEqual(
            structure_response.json()["document_slug"],
            "sample_city_code_of_ordinances",
        )

    def test_query_endpoint_returns_structured_answer_sources_and_accuracy(self) -> None:
        response = self.client.get(
            "/api/custom/query",
            params={
                "q": "Who can enforce the city code?",
                "jurisdiction": "Sample City",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertIn("Sec. 1-2", payload["answer"])
        self.assertEqual(payload["system"], "custom")
        self.assertEqual(payload["jurisdiction"], "Sample City Code of Ordinances")
        self.assertTrue(payload["sources"])
        self.assertEqual(payload["sources"][0]["section"], "Sec. 1-2")
        self.assertIn(payload["accuracy"]["label"], {"High", "Medium", "Low"})
        self.assertTrue(payload["navigation"]["tool_trace"])

    def _fake_generate_answer(self, query: str, search_payload: dict | list[dict]) -> str:
        """Return a deterministic answer from the top retrieved source."""

        if isinstance(search_payload, dict):
            results = search_payload.get("results", [])
        else:
            results = search_payload

        if not results:
            return "No relevant sections retrieved from the municipal code."

        top_meta = results[0]["meta"]
        section = top_meta.get("section", "Unknown section")
        subsection = top_meta.get("subsection")
        jurisdiction = top_meta.get("jurisdiction", "Unknown jurisdiction")
        citation = f"{section} {subsection}".strip() if subsection else section
        return f"Backend integration answer for {jurisdiction} using {citation}."


if __name__ == "__main__":
    unittest.main()
