from __future__ import annotations

# Standard library imports keep the parser easy to run from both the website
# upload path and the command line.
import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# PyMuPDF gives us fast text and block extraction from ordinance PDFs.
import fitz

# Reuse the normalized relational and vector storage layers built earlier.
try:
    from DB import DatabaseManager
    from chroma import ChromaManager
except ImportError:  # pragma: no cover - fallback for direct script execution
    import sys

    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.append(str(repo_root))

    from backend.CustomRAG.db_scripts.DB import DatabaseManager
    from backend.CustomRAG.db_scripts.chroma import ChromaManager


# ---------------------------------------------------------------------------
# Parser configuration
# ---------------------------------------------------------------------------
# These dataclasses define the filesystem layout and the high-level parsing
# profile of one document. Keeping them explicit makes the pipeline easier to
# debug and easier to reuse from FastAPI.


@dataclass(slots=True)
class ParserPaths:
    # The backend folder, for example `<repo>/backend`.
    backend_root: Path
    # Shared data directory used by the backend.
    data_dir: Path
    # Directory containing uploaded ordinance PDFs.
    pdf_dir: Path
    # Directory where parsed JSON artifacts are written for inspection.
    json_dir: Path
    # Manifest file tracking processed PDFs and summary metadata.
    manifest_path: Path
    # Structured relational database path for the new normalized model.
    db_path: Path
    # Chroma persistence directory for vectorized section/subsection nodes.
    chroma_dir: Path


@dataclass(slots=True)
class DocumentParseProfile:
    # Human-facing title derived from the PDF filename.
    document_title: str
    # Original uploaded filename.
    source_filename: str
    # Either `single_column` or `two_column`.
    layout: str
    # One-based first TOC page, if found.
    toc_start_page: int
    # One-based last TOC page, if found.
    toc_end_page: int
    # One-based page where section parsing begins.
    content_start_page: int


# ---------------------------------------------------------------------------
# Lightweight summary helper
# ---------------------------------------------------------------------------
# The eventual production system may swap this for a model-backed summarizer.
# For now we keep a deterministic extractive implementation so parsing can be
# tested without an LLM call or extra inference cost.


class ExtractiveSummaryBuilder:
    """Create concise summaries from parsed section and subsection text."""

    def summarize(self, text: str, max_words: int = 32) -> str:
        # Normalize whitespace first so our truncation logic is stable.
        normalized = self._normalize_text(text)
        if not normalized:
            return ""

        # Prefer the first sentence when possible because ordinance text often
        # starts with the core rule or prohibition.
        sentence_match = re.split(r"(?<=[.!?;])\s+", normalized, maxsplit=1)
        first_sentence = sentence_match[0].strip()
        if first_sentence and len(first_sentence.split()) <= max_words:
            return first_sentence

        # Fall back to a trimmed leading excerpt when the first sentence is too long.
        words = normalized.split()
        return " ".join(words[:max_words]).strip()

    def _normalize_text(self, text: str) -> str:
        value = re.sub(r"\s+", " ", (text or "").strip())
        return value.strip()


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------
# The parser discovers sections incrementally across pages, so a builder is a
# natural fit. It keeps the mutable parsing state contained in one place and
# emits the nested payload shape expected by `DB.py` and `chroma.py`.


class StructuredDocumentBuilder:
    """Accumulate parsed ordinance structure into the normalized nested payload."""

    def __init__(
        self,
        document_title: str,
        source_filename: str,
        toc_chapters: Iterable[dict],
        summary_builder: ExtractiveSummaryBuilder | None = None,
    ) -> None:
        self.document_title = document_title
        self.source_filename = source_filename
        self.summary_builder = summary_builder or ExtractiveSummaryBuilder()

        # Preseed the chapter map from the table of contents so chapter names and
        # TOC references are preserved even before sections are discovered.
        self.chapters_by_number: dict[str, dict] = {}
        for chapter in toc_chapters:
            self.ensure_chapter(
                chapter_number=chapter["chapter_number"],
                chapter_name=chapter.get("chapter_name", ""),
                toc_page=chapter.get("toc_page"),
                toc_code_page=chapter.get("toc_code_page", ""),
            )

        # Active parsing state for the current section and subsection.
        self.current_chapter_number: str | None = None
        self.current_section: dict | None = None
        self.current_subsection: dict | None = None

    def ensure_chapter(
        self,
        chapter_number: str,
        chapter_name: str = "",
        toc_page: int | None = None,
        toc_code_page: str = "",
    ) -> dict:
        # Normalize the key once so later section parsing can attach to it reliably.
        chapter_key = str(chapter_number).strip()
        chapter = self.chapters_by_number.get(chapter_key)
        if chapter is None:
            chapter = {
                "chapter_number": chapter_key,
                "chapter_name": (chapter_name or f"Chapter {chapter_key}").strip(),
                "toc_page": toc_page,
                "toc_code_page": (toc_code_page or "").strip(),
                "section_count": 0,
                "sections": [],
            }
            self.chapters_by_number[chapter_key] = chapter
        else:
            # Fill in missing metadata if a richer source appears later.
            if chapter_name and not chapter.get("chapter_name"):
                chapter["chapter_name"] = chapter_name.strip()
            if toc_page and not chapter.get("toc_page"):
                chapter["toc_page"] = toc_page
            if toc_code_page and not chapter.get("toc_code_page"):
                chapter["toc_code_page"] = toc_code_page.strip()
        return chapter

    def start_section(self, chapter_number: str, section_number: str, heading_text: str = "") -> None:
        # A new section closes any previous subsection and section state first.
        self._close_subsection()
        self._close_section()

        chapter = self.ensure_chapter(chapter_number=chapter_number)
        self.current_chapter_number = chapter["chapter_number"]
        self.current_section = {
            "section_number": section_number,
            "subsection_count": 0,
            "section_summary": "",
            "section_text": "",
            "subsections": [],
            "_body_lines": [],
        }

        if heading_text:
            self.append_text(heading_text)

    def start_subsection(self, subsection_number: str, heading_text: str = "") -> None:
        # Ignore subsection markers until a parent section exists.
        if self.current_section is None:
            return

        self._close_subsection()
        normalized_subsection_number = subsection_number.strip().lower()
        self.current_subsection = {
            "subsection_number": normalized_subsection_number,
            "subsection_summary": "",
            "subsection_text": "",
            "_body_lines": [],
        }

        if heading_text:
            self.append_text(heading_text)

    def append_text(self, text: str) -> None:
        # Ignore stray text until we have at least entered a section.
        if self.current_section is None:
            return

        cleaned = self._normalize_fragment(text)
        if not cleaned:
            return

        if self.current_subsection is not None:
            self.current_subsection["_body_lines"].append(cleaned)
        else:
            self.current_section["_body_lines"].append(cleaned)

    def build_payload(self) -> list[dict]:
        # Flush any remaining open subsection/section before serializing chapters.
        self._close_subsection()
        self._close_section()

        ordered_chapters = [
            self.chapters_by_number[chapter_number]
            for chapter_number in sorted(self.chapters_by_number, key=self._chapter_sort_key)
        ]

        for chapter in ordered_chapters:
            chapter["section_count"] = len(chapter["sections"])

        return ordered_chapters

    def _close_subsection(self) -> None:
        # Subsection text is finalized only when we see the next subsection or section.
        if self.current_subsection is None or self.current_section is None:
            self.current_subsection = None
            return

        subsection_text = self._merge_lines(self.current_subsection.pop("_body_lines", []))
        self.current_subsection["subsection_text"] = subsection_text
        self.current_subsection["subsection_summary"] = self.summary_builder.summarize(subsection_text)
        existing_subsection = next(
            (
                subsection
                for subsection in self.current_section["subsections"]
                if subsection["subsection_number"] == self.current_subsection["subsection_number"]
            ),
            None,
        )

        if existing_subsection is not None:
            if len(self.current_subsection["subsection_text"]) > len(existing_subsection["subsection_text"]):
                existing_subsection["subsection_text"] = self.current_subsection["subsection_text"]
            if len(self.current_subsection["subsection_summary"]) > len(existing_subsection["subsection_summary"]):
                existing_subsection["subsection_summary"] = self.current_subsection["subsection_summary"]
        else:
            self.current_section["subsections"].append(self.current_subsection)

        self.current_subsection = None

    def _close_section(self) -> None:
        # Finalize the section after all child subsections have been attached.
        if self.current_section is None or self.current_chapter_number is None:
            self.current_section = None
            self.current_chapter_number = None
            return

        section_text = self._merge_lines(self.current_section.pop("_body_lines", []))
        self.current_section["section_text"] = section_text
        self.current_section["subsection_count"] = len(self.current_section["subsections"])

        summary_source = section_text or " ".join(
            (subsection["subsection_text"] or subsection["subsection_summary"]).strip()
            for subsection in self.current_section["subsections"]
            if (subsection["subsection_text"] or subsection["subsection_summary"]).strip()
        )
        self.current_section["section_summary"] = self.summary_builder.summarize(summary_source)

        chapter_sections = self.chapters_by_number[self.current_chapter_number]["sections"]

        # Some ordinance PDFs include a short section listing page immediately
        # before the full section text. When that happens, the same section
        # number appears twice in sequence. We collapse those duplicates here
        # and keep the richer version instead of storing both.
        existing_section = next(
            (
                section
                for section in chapter_sections
                if section["section_number"] == self.current_section["section_number"]
            ),
            None,
        )

        if existing_section is not None:
            if len(self.current_section["section_text"]) > len(existing_section["section_text"]):
                existing_section["section_text"] = self.current_section["section_text"]
            if len(self.current_section["section_summary"]) > len(existing_section["section_summary"]):
                existing_section["section_summary"] = self.current_section["section_summary"]
            if len(self.current_section["subsections"]) > len(existing_section["subsections"]):
                existing_section["subsections"] = self.current_section["subsections"]
                existing_section["subsection_count"] = self.current_section["subsection_count"]
        else:
            chapter_sections.append(self.current_section)

        self.current_section = None
        self.current_chapter_number = None

    def _normalize_fragment(self, text: str) -> str:
        # Normalize one incoming line fragment without destroying punctuation.
        return re.sub(r"\s+", " ", (text or "").strip()).strip()

    def _merge_lines(self, lines: list[str]) -> str:
        # Merge wrapped lines back into one text body while repairing common
        # hyphenation artifacts produced by PDF line breaks.
        if not lines:
            return ""

        merged_parts: list[str] = []
        for line in lines:
            if not merged_parts:
                merged_parts.append(line)
                continue

            # Join broken words like `adminis-` + `tration` back together.
            if merged_parts[-1].endswith("-") and line[:1].islower():
                merged_parts[-1] = merged_parts[-1][:-1] + line
            else:
                merged_parts.append(line)

        return re.sub(r"\s+", " ", " ".join(merged_parts)).strip()

    def _chapter_sort_key(self, chapter_number: str) -> tuple[int, str]:
        # Chapters like `8A` should sort directly after `8`, not alphabetically at the end.
        match = re.match(r"(\d+)([A-Za-z]*)", chapter_number)
        if match:
            return int(match.group(1)), match.group(2) or ""
        return 10_000, chapter_number


# ---------------------------------------------------------------------------
# Factory / builder for parser dependencies
# ---------------------------------------------------------------------------
# This keeps path creation and dependency wiring out of the operational parser.


class ParserComponentFactory:
    """Create the default paths and storage dependencies for the parser."""

    @staticmethod
    def create_default_paths(backend_root: Path | None = None) -> ParserPaths:
        resolved_backend_root = backend_root or Path(__file__).resolve().parents[2]
        data_dir = resolved_backend_root / "Data"
        return ParserPaths(
            backend_root=resolved_backend_root,
            data_dir=data_dir,
            pdf_dir=data_dir / "PDF",
            json_dir=data_dir / "parsed_json",
            manifest_path=data_dir / "processed_files.json",
            db_path=data_dir / "civilai_structured.db",
            chroma_dir=data_dir / "chroma_db",
        )

    @staticmethod
    def create_database_manager(paths: ParserPaths) -> DatabaseManager:
        return DatabaseManager(db_url=f"sqlite:///{paths.db_path.as_posix()}")

    @staticmethod
    def create_chroma_manager(paths: ParserPaths, db_manager: DatabaseManager) -> ChromaManager:
        return ChromaManager(
            persist_directory=paths.chroma_dir,
            db_manager=db_manager,
        )


class ParserPipelineBuilder:
    """Incrementally wire together the parser and its storage dependencies."""

    def __init__(self) -> None:
        self._paths: ParserPaths | None = None
        self._db_manager: DatabaseManager | None = None
        self._chroma_manager: ChromaManager | None = None
        self._summary_builder: ExtractiveSummaryBuilder | None = None

    def with_paths(self, paths: ParserPaths) -> "ParserPipelineBuilder":
        self._paths = paths
        return self

    def with_database_manager(self, db_manager: DatabaseManager) -> "ParserPipelineBuilder":
        self._db_manager = db_manager
        return self

    def with_chroma_manager(self, chroma_manager: ChromaManager) -> "ParserPipelineBuilder":
        self._chroma_manager = chroma_manager
        return self

    def with_summary_builder(self, summary_builder: ExtractiveSummaryBuilder) -> "ParserPipelineBuilder":
        self._summary_builder = summary_builder
        return self

    def build(self) -> "OrdinancePdfParser":
        # Resolve paths first because every other dependency is rooted in them.
        paths = self._paths or ParserComponentFactory.create_default_paths()
        paths.pdf_dir.mkdir(parents=True, exist_ok=True)
        paths.json_dir.mkdir(parents=True, exist_ok=True)
        paths.chroma_dir.mkdir(parents=True, exist_ok=True)

        db_manager = self._db_manager or ParserComponentFactory.create_database_manager(paths)
        chroma_manager = self._chroma_manager or ParserComponentFactory.create_chroma_manager(paths, db_manager)
        summary_builder = self._summary_builder or ExtractiveSummaryBuilder()

        return OrdinancePdfParser(
            paths=paths,
            db_manager=db_manager,
            chroma_manager=chroma_manager,
            summary_builder=summary_builder,
        )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class OrdinancePdfParser:
    """Parse ordinance PDFs into structured SQL rows, JSON artifacts, and Chroma nodes."""

    SECTION_HEADER_PATTERN = re.compile(
        r"^Sec\.\s*([A-Za-z0-9]+(?:[.\-][A-Za-z0-9]+)*)\.?\s*(.*)$",
        re.IGNORECASE,
    )
    SUBSECTION_PATTERN = re.compile(r"^\(([A-Za-z0-9]+)\)\s*(.*)$")
    CHAPTER_TOC_PATTERN = re.compile(r"^(\d+[A-Za-z]?)\.\s+(.+?)(?:\.\s*){3,}$")
    CODE_PAGE_PATTERN = re.compile(r"^(CD\d[0-9A-Za-z:.]*|CHT:[0-9A-Za-z:.]+|SHT:[0-9A-Za-z:.]+)$")

    def __init__(
        self,
        paths: ParserPaths,
        db_manager: DatabaseManager,
        chroma_manager: ChromaManager,
        summary_builder: ExtractiveSummaryBuilder | None = None,
    ) -> None:
        self.paths = paths
        self.db_manager = db_manager
        self.chroma_manager = chroma_manager
        self.summary_builder = summary_builder or ExtractiveSummaryBuilder()

    def parse_all(self, replace_existing: bool = True) -> list[dict]:
        """Parse every PDF currently stored in the backend PDF directory."""

        results: list[dict] = []
        for pdf_path in sorted(self.paths.pdf_dir.glob("*.pdf")):
            results.append(self.parse_pdf(pdf_path, replace_existing=replace_existing))
        return results

    def parse_uploaded_pdf(self, pdf_path: str | Path, replace_existing: bool = True) -> dict:
        """Parse one uploaded PDF immediately after it is saved by the website."""

        return self.parse_pdf(pdf_path, replace_existing=replace_existing)

    def parse_pdf(self, pdf_path: str | Path, replace_existing: bool = True) -> dict:
        """Parse one PDF, persist it to SQL/Chroma, and emit a JSON artifact."""

        resolved_pdf_path = Path(pdf_path)
        if not resolved_pdf_path.is_absolute():
            resolved_pdf_path = self.paths.pdf_dir / resolved_pdf_path
        resolved_pdf_path = resolved_pdf_path.resolve()

        if not resolved_pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {resolved_pdf_path}")

        document_title = resolved_pdf_path.stem.strip()

        with fitz.open(resolved_pdf_path) as document:
            profile = self._build_document_profile(
                document=document,
                document_title=document_title,
                source_filename=resolved_pdf_path.name,
            )
            toc_chapters = self._extract_toc_chapters(document, profile)
            structure_builder = StructuredDocumentBuilder(
                document_title=profile.document_title,
                source_filename=profile.source_filename,
                toc_chapters=toc_chapters,
                summary_builder=self.summary_builder,
            )
            self._parse_document_body(document, profile, structure_builder)

        chapters = structure_builder.build_payload()
        document_slug = DatabaseManager.make_slug(profile.document_title)

        artifact_payload = {
            "document_title": profile.document_title,
            "document_slug": document_slug,
            "source_filename": profile.source_filename,
            "detected_layout": profile.layout,
            "toc_start_page": profile.toc_start_page,
            "toc_end_page": profile.toc_end_page,
            "content_start_page": profile.content_start_page,
            "chapters": chapters,
        }
        self._write_json_artifact(document_slug, artifact_payload)

        storage_result = self.chroma_manager.sync_document(
            document_title=profile.document_title,
            chapters=chapters,
            source_filename=profile.source_filename,
            replace_existing=replace_existing,
            persist_relational=True,
        )

        result = {
            "document_title": profile.document_title,
            "document_slug": document_slug,
            "source_filename": profile.source_filename,
            "detected_layout": profile.layout,
            "toc_start_page": profile.toc_start_page,
            "toc_end_page": profile.toc_end_page,
            "content_start_page": profile.content_start_page,
            "chapter_count": len(chapters),
            "section_count": sum(len(chapter["sections"]) for chapter in chapters),
            "subsection_count": sum(
                len(section["subsections"])
                for chapter in chapters
                for section in chapter["sections"]
            ),
            "json_path": str((self.paths.json_dir / f"{document_slug}.json").resolve()),
            "storage": storage_result,
        }

        self._update_manifest(resolved_pdf_path, result)
        return result

    def _build_document_profile(
        self,
        document: fitz.Document,
        document_title: str,
        source_filename: str,
    ) -> DocumentParseProfile:
        # The TOC pages mark where we can begin trusting the ordinance structure.
        toc_start_page, toc_end_page = self._find_toc_range(document)

        # Find the first page that appears to contain actual section text. This
        # lets the layout detector skip checklist pages and other front matter.
        first_section_candidate = self._find_first_section_candidate_page(
            document=document,
            start_page=max(toc_end_page + 1, 1),
        )

        # The layout heuristic uses real section pages when possible.
        layout = self._detect_document_layout(document, first_section_candidate)

        # Section parsing starts on the first post-TOC page where a real section header appears.
        content_start_page = self._find_first_content_page(document, first_section_candidate, layout)

        return DocumentParseProfile(
            document_title=document_title,
            source_filename=source_filename,
            layout=layout,
            toc_start_page=toc_start_page,
            toc_end_page=toc_end_page,
            content_start_page=content_start_page,
        )

    def _find_first_section_candidate_page(self, document: fitz.Document, start_page: int) -> int:
        # This is a cheap pre-pass that only looks for section headers in the raw
        # page text. It intentionally does not depend on the column heuristic.
        for page_number in range(start_page, len(document) + 1):
            page = document[page_number - 1]
            page_text = page.get_text("text")
            if self._page_should_be_skipped_for_layout(page_text):
                continue

            lines = self._extract_ordered_lines(page, "single_column")
            if self._page_is_section_overview(lines):
                continue

            if any(self.SECTION_HEADER_PATTERN.match(line) for line in lines):
                return page_number
        return max(start_page, 1)

    def _find_toc_range(self, document: fitz.Document) -> tuple[int, int]:
        # Search the first few hundred pages because supplement-heavy ordinance files
        # often bury the TOC well after the cover pages.
        toc_candidates: list[int] = []
        scan_limit = min(len(document), 400)
        for page_index in range(scan_limit):
            page_text = document[page_index].get_text("text")
            if self._page_looks_like_toc(page_text):
                toc_candidates.append(page_index + 1)

        if not toc_candidates:
            # If no TOC is detected, fall back to scanning from page 1.
            return 1, 0

        toc_start_page = toc_candidates[0]
        toc_end_page = toc_start_page
        for page_number in range(toc_start_page + 1, scan_limit + 1):
            page_text = document[page_number - 1].get_text("text")
            if self._page_looks_like_toc(page_text):
                toc_end_page = page_number
            else:
                break

        return toc_start_page, toc_end_page

    def _page_looks_like_toc(self, page_text: str) -> bool:
        normalized = (page_text or "").lower()
        normalized_lines = [
            re.sub(r"\s+", " ", line.strip()).lower()
            for line in (page_text or "").splitlines()
            if line.strip()
        ]

        # Trust an actual TOC heading line, but ignore incidental phrases like
        # "following Table of Contents" that appear on supplement instruction sheets.
        if any(line == "table of contents" for line in normalized_lines[:12]):
            return True

        chapter_entries = len(re.findall(r"(?m)^\s*\d+[A-Za-z]?\.\s+", page_text or ""))
        code_page_refs = len(re.findall(r"\bCD\d[0-9A-Za-z:.]*\b", page_text or ""))
        if chapter_entries >= 1 and code_page_refs >= 1:
            return True

        # Some TOC continuation pages only show the `Chapter / Page` heading and
        # code page labels, so we only trust that pattern when those words appear
        # as the top heading lines, not buried inside supplement instructions.
        top_heading_lines = normalized_lines[:8]
        if "chapter" in top_heading_lines and "page" in top_heading_lines and code_page_refs >= 3:
            return True

        return False

    def _detect_document_layout(self, document: fitz.Document, start_page: int) -> str:
        # Use a small sample of post-TOC pages to determine whether text is laid out
        # in one or two columns. We avoid TOC/checklist pages because they distort the heuristic.
        layout_votes: list[str] = []
        for page_number in range(start_page, min(len(document), start_page + 40) + 1):
            page = document[page_number - 1]
            page_text = page.get_text("text")
            single_column_lines = self._extract_ordered_lines(page, "single_column")
            if self._page_should_be_skipped_for_layout(page_text) or self._page_is_section_overview(single_column_lines):
                continue
            layout_votes.append(self._classify_page_layout(page))
            if len(layout_votes) >= 8:
                break

        if not layout_votes:
            return "single_column"

        two_column_votes = sum(1 for vote in layout_votes if vote == "two_column")
        return "two_column" if two_column_votes >= max(1, len(layout_votes) / 2) else "single_column"

    def _page_should_be_skipped_for_layout(self, page_text: str) -> bool:
        lower = (page_text or "").lower()
        return any(
            phrase in lower
            for phrase in (
                "table of contents",
                "checklist of up-to-date pages",
                "supplement history table",
            )
        )

    def _classify_page_layout(self, page: fitz.Page) -> str:
        # The block-based heuristic is more reliable than raw text width because it
        # reflects the physical layout of the page.
        blocks = [block for block in page.get_text("blocks") if str(block[4]).strip()]
        if len(blocks) < 4:
            return "single_column"

        page_width = page.rect.width
        center = page_width / 2
        left_narrow = 0
        right_narrow = 0
        spanning = 0

        for block in blocks:
            x0, _, x1, _, block_text = block[:5]
            if not str(block_text).strip():
                continue

            block_width = x1 - x0
            if x0 < center - 35 and x1 <= center + 45 and block_width < page_width * 0.62:
                left_narrow += 1
            elif x0 >= center - 45 and x1 > center + 35 and block_width < page_width * 0.62:
                right_narrow += 1
            else:
                spanning += 1

        if left_narrow >= 2 and right_narrow >= 2 and spanning <= max(4, len(blocks) * 0.6):
            return "two_column"
        return "single_column"

    def _find_first_content_page(self, document: fitz.Document, start_page: int, layout: str) -> int:
        # Start parsing from the first page that actually contains a section header.
        for page_number in range(start_page, len(document) + 1):
            lines = self._extract_ordered_lines(document[page_number - 1], layout)
            if self._page_is_section_overview(lines):
                continue
            if any(self.SECTION_HEADER_PATTERN.match(line) for line in lines):
                return page_number
        return max(start_page, 1)

    def _extract_toc_chapters(self, document: fitz.Document, profile: DocumentParseProfile) -> list[dict]:
        # Extract chapters from the TOC so we preserve human chapter names even
        # before we parse any section bodies.
        if profile.toc_end_page < profile.toc_start_page:
            return []

        chapters: list[dict] = []
        seen_numbers: set[str] = set()

        for page_number in range(profile.toc_start_page, profile.toc_end_page + 1):
            lines = [
                re.sub(r"\s+", " ", line.strip())
                for line in document[page_number - 1].get_text("text").splitlines()
                if line.strip()
            ]

            for index, line in enumerate(lines):
                chapter_match = self.CHAPTER_TOC_PATTERN.match(line)
                if not chapter_match:
                    continue

                chapter_number = chapter_match.group(1).strip()
                chapter_name = chapter_match.group(2).strip(" .")
                if chapter_number in seen_numbers:
                    continue

                toc_code_page = self._find_following_code_page(lines, start_index=index + 1)
                chapters.append(
                    {
                        "chapter_number": chapter_number,
                        "chapter_name": chapter_name,
                        "toc_page": page_number,
                        "toc_code_page": toc_code_page,
                        "section_count": 0,
                        "sections": [],
                    }
                )
                seen_numbers.add(chapter_number)

        return chapters

    def _find_following_code_page(self, lines: list[str], start_index: int) -> str:
        # In these ordinance TOCs, the chapter title is usually followed by its code page label.
        for line in lines[start_index : start_index + 6]:
            normalized = re.sub(r"\s+", "", line)
            if self.CODE_PAGE_PATTERN.match(normalized):
                return normalized
            if self.CHAPTER_TOC_PATTERN.match(line):
                break
        return ""

    def _parse_document_body(
        self,
        document: fitz.Document,
        profile: DocumentParseProfile,
        structure_builder: StructuredDocumentBuilder,
    ) -> None:
        # Walk every content page in order and feed section/subsection text into the builder.
        for page_number in range(profile.content_start_page, len(document) + 1):
            page = document[page_number - 1]
            lines = self._extract_ordered_lines(page, profile.layout)
            if self._page_is_section_overview(lines):
                continue

            for line in lines:
                if self._is_noise_line(line):
                    continue

                section_match = self.SECTION_HEADER_PATTERN.match(line)
                if section_match:
                    section_token = section_match.group(1).strip()
                    section_number = f"Sec. {section_token}"
                    chapter_number = self._derive_chapter_number(section_token)
                    structure_builder.start_section(
                        chapter_number=chapter_number,
                        section_number=section_number,
                        heading_text=section_match.group(2).strip(),
                    )
                    continue

                subsection_match = self.SUBSECTION_PATTERN.match(line)
                if subsection_match:
                    structure_builder.start_subsection(
                        subsection_number=f"({subsection_match.group(1)})",
                        heading_text=subsection_match.group(2).strip(),
                    )
                    continue

                structure_builder.append_text(line)

    def _page_is_section_overview(self, lines: list[str]) -> bool:
        # Chapter opening pages often contain nothing but short section listings.
        # We want to skip those so the parser stores the real section body only once.
        if not lines:
            return False

        section_heading_count = sum(1 for line in lines if line.lower().startswith("sec. "))
        long_body_line_count = sum(1 for line in lines if len(line) >= 70)

        return section_heading_count >= 2 and long_body_line_count <= 2

    def _extract_ordered_lines(self, page: fitz.Page, layout: str) -> list[str]:
        # Extract blocks because they preserve visual position. That gives us the
        # control we need to read two-column pages in the correct order.
        raw_blocks = [block for block in page.get_text("blocks") if str(block[4]).strip()]
        page_width = page.rect.width
        center = page_width / 2

        if layout == "two_column":
            top_blocks: list[tuple] = []
            left_blocks: list[tuple] = []
            right_blocks: list[tuple] = []
            trailing_blocks: list[tuple] = []

            for block in raw_blocks:
                x0, y0, x1, _, text = block[:5]
                if not str(text).strip():
                    continue

                block_width = x1 - x0
                if block_width >= page_width * 0.72 and y0 < 120:
                    top_blocks.append(block)
                elif x1 <= center + 45:
                    left_blocks.append(block)
                elif x0 >= center - 45:
                    right_blocks.append(block)
                else:
                    trailing_blocks.append(block)

            ordered_blocks = (
                sorted(top_blocks, key=lambda value: (value[1], value[0]))
                + sorted(left_blocks, key=lambda value: (value[1], value[0]))
                + sorted(right_blocks, key=lambda value: (value[1], value[0]))
                + sorted(trailing_blocks, key=lambda value: (value[1], value[0]))
            )
        else:
            ordered_blocks = sorted(raw_blocks, key=lambda value: (value[1], value[0]))

        ordered_lines: list[str] = []
        for block in ordered_blocks:
            for line in str(block[4]).splitlines():
                normalized = re.sub(r"\s+", " ", line.strip())
                if normalized:
                    ordered_lines.append(normalized)
        return ordered_lines

    def _is_noise_line(self, line: str) -> bool:
        # Strip out page furniture and TOC/checklist leftovers so the section
        # parser only sees ordinance content.
        normalized = re.sub(r"\s+", " ", (line or "").strip())
        lower = normalized.lower()
        if not normalized:
            return True
        if re.fullmatch(r"\[\d+\]", normalized):
            return True
        if re.fullmatch(r"(supp\. no\. \d+|page no\.|page|chapter)", lower):
            return True
        if lower in {
            "table of contents",
            "checklist of up-to-date pages",
            "cooper city code",
            "broward county code",
        }:
            return True
        if self.CODE_PAGE_PATTERN.match(normalized.replace(" ", "")):
            return True
        if re.fullmatch(r"[ivxlcdm]+", lower):
            return True
        return False

    def _derive_chapter_number(self, section_token: str) -> str:
        # Ordinance section numbers usually expose the chapter in the leading token.
        cleaned = section_token.strip().upper()
        if "-" in cleaned:
            return cleaned.split("-", 1)[0]
        if "." in cleaned:
            return cleaned.split(".", 1)[0]

        match = re.match(r"(\d+[A-Z]?)", cleaned)
        if match:
            return match.group(1)
        return cleaned or "UNKNOWN"

    def _write_json_artifact(self, document_slug: str, payload: dict) -> None:
        # The JSON artifact is a debug-friendly cache of what the parser extracted.
        artifact_path = self.paths.json_dir / f"{document_slug}.json"
        artifact_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _update_manifest(self, pdf_path: Path, parse_result: dict) -> None:
        # The manifest makes it cheap for the rest of the app to see which PDFs
        # have already been parsed and what structure was produced.
        if self.paths.manifest_path.exists():
            try:
                manifest = json.loads(self.paths.manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = {}
        else:
            manifest = {}

        manifest[pdf_path.name] = {
            "document_title": parse_result["document_title"],
            "document_slug": parse_result["document_slug"],
            "detected_layout": parse_result["detected_layout"],
            "toc_start_page": parse_result["toc_start_page"],
            "toc_end_page": parse_result["toc_end_page"],
            "content_start_page": parse_result["content_start_page"],
            "chapter_count": parse_result["chapter_count"],
            "section_count": parse_result["section_count"],
            "subsection_count": parse_result["subsection_count"],
            "json_path": parse_result["json_path"],
            "source_path": str(pdf_path.resolve()),
        }

        self.paths.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Command-line entry point
# ---------------------------------------------------------------------------


def main() -> None:
    # Allow the parser to run against either one uploaded file or the whole PDF directory.
    argument_parser = argparse.ArgumentParser(description="Parse ordinance PDFs into SQL, JSON, and Chroma.")
    argument_parser.add_argument(
        "--file",
        dest="file",
        help="Optional PDF filename or path to parse. When omitted, all PDFs are parsed.",
    )
    arguments = argument_parser.parse_args()

    parser = ParserPipelineBuilder().build()
    if arguments.file:
        results = [parser.parse_uploaded_pdf(arguments.file)]
    else:
        results = parser.parse_all()

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
