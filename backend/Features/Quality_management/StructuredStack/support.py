"""Shared test helpers for the structured Civil AI backend stack."""

from __future__ import annotations

import gc
import shutil
import sys
import tempfile
from pathlib import Path

# Add the repo and backend roots to the import path so the tests can be run
# after being moved under `backend/Features/Quality_management/StructuredStack`.
#
# support.py
# └── StructuredStack
#     └── Tests
#         └── Features
#             └── backend
#                 └── <repo root>
REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"

for path in (REPO_ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from backend.Features.Pipeline_management.Parser.parser_run import ChromaManager, DatabaseManager
from backend.Features.RAG_management.Navigation.Tools.navigation import (
    StructuredRetrievalToolkit,
    StructuredToolPaths,
)


def build_sample_chapters() -> list[dict]:
    """Return one deterministic ordinance hierarchy used across the tests."""

    return [
        {
            "chapter_number": "1",
            "chapter_name": "General Provisions",
            "toc_page": 12,
            "sections": [
                {
                    "section_number": "Sec. 1-2",
                    "section_summary": "Describes enforcement authority.",
                    "section_text": "The city manager may enforce this code and may designate code officers.",
                    "subsections": [
                        {
                            "subsection_number": "(a)",
                            "subsection_summary": "Primary enforcement authority.",
                            "subsection_text": "The city manager is the primary enforcement official.",
                        },
                        {
                            "subsection_number": "(b)",
                            "subsection_summary": "Delegation authority.",
                            "subsection_text": "The city manager may designate code compliance officers.",
                        },
                    ],
                },
                {
                    "section_number": "Sec. 1-3",
                    "section_summary": "Explains administrative remedies.",
                    "section_text": "Administrative remedies include notice, hearing, and corrective orders.",
                    "subsections": [],
                },
            ],
        },
        {
            "chapter_number": "2",
            "chapter_name": "Noise Control",
            "toc_page": 24,
            "sections": [
                {
                    "section_number": "Sec. 2-10",
                    "section_summary": "Limits loud construction activity at night.",
                    "section_text": (
                        "Construction noise is prohibited after 9 p.m. and before 7 a.m. "
                        "in residential areas."
                    ),
                    "subsections": [
                        {
                            "subsection_number": "(a)",
                            "subsection_summary": "Nighttime construction limit.",
                            "subsection_text": (
                                "No person may operate construction equipment after 9 p.m. "
                                "in a residential area."
                            ),
                        }
                    ],
                }
            ],
        },
    ]


class StructuredStackFixture:
    """Create an isolated structured DB + Chroma stack for tests."""

    def __init__(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="civilai_structured_test_"))
        self.backend_root = self.temp_dir / "backend"
        self.data_dir = self.backend_root / "Data"
        self.chroma_dir = self.data_dir / "chroma_db"
        self.json_dir = self.data_dir / "parsed_json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.json_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.data_dir / "civilai_structured.db"
        self.db_manager = DatabaseManager(db_url=f"sqlite:///{self.db_path.as_posix()}")
        self.chroma_manager = ChromaManager(
            persist_directory=self.chroma_dir,
            db_manager=self.db_manager,
        )
        self.toolkit = StructuredRetrievalToolkit(
            paths=StructuredToolPaths(
                backend_root=self.backend_root,
                data_dir=self.data_dir,
                db_path=self.db_path,
                chroma_dir=self.chroma_dir,
                json_dir=self.json_dir,
                manifest_path=self.data_dir / "processed_files.json",
            ),
            db_manager=self.db_manager,
            chroma_manager=self.chroma_manager,
        )

    def seed_document(
        self,
        document_title: str = "Sample City Code of Ordinances",
        source_filename: str = "Sample City Code of Ordinances.pdf",
        chapters: list[dict] | None = None,
    ) -> dict:
        """Populate the temporary SQL and Chroma stores with one sample document."""

        sample_chapters = chapters or build_sample_chapters()
        return self.chroma_manager.sync_document(
            document_title=document_title,
            chapters=sample_chapters,
            source_filename=source_filename,
            replace_existing=True,
            persist_relational=True,
        )

    def cleanup(self) -> None:
        """Best-effort cleanup for SQLite and Chroma temp files on Windows."""

        try:
            self.db_manager.close()
        finally:
            # Chroma can keep file handles open briefly on Windows, so we force a
            # collection cycle and ignore cleanup errors if the lock lingers.
            gc.collect()
            shutil.rmtree(self.temp_dir, ignore_errors=True)
