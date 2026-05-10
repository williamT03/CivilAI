from __future__ import annotations

# Standard library imports are enough for path resolution, lightweight matching,
# and small in-memory hashmaps.
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

# Reuse the normalized SQL and Chroma layers that were built for the new stack.
try:
    from ..db_scripts.DB import DatabaseManager
    from ..db_scripts.chroma import (
        ChromaCollectionFactory,
        ChromaManager,
        create_runtime_vector_manager,
    )
except ImportError:
    from CustomRAG.db_scripts.DB import DatabaseManager
    from CustomRAG.db_scripts.chroma import (
        ChromaCollectionFactory,
        ChromaManager,
        create_runtime_vector_manager,
    )


# ---------------------------------------------------------------------------
# Runtime paths
# ---------------------------------------------------------------------------
# The tool layer needs to know where the structured SQLite database, Chroma
# store, and parsed JSON artifacts live. Keeping those paths in one dataclass
# makes the rest of the code easier to test and easier to reason about.


@dataclass(slots=True)
class StructuredToolPaths:
    # The `<repo>/backend` directory.
    backend_root: Path
    # Shared data directory used by the backend.
    data_dir: Path
    # The structured relational database path for the new normalized model.
    db_path: Path
    # Chroma persistence directory containing vectorized nodes.
    chroma_dir: Path
    # JSON artifact directory emitted by the parser.
    json_dir: Path
    # Parser manifest file tracking processed PDFs.
    manifest_path: Path


# ---------------------------------------------------------------------------
# Summary helper
# ---------------------------------------------------------------------------
# This helper is intentionally lightweight. It gives the tool layer a cheap way
# to summarize one or more exact sections before sending the final answer prompt
# to the LLM. A model-backed summarizer can be swapped in later without changing
# the retrieval flow.


class StructuredSummaryBuilder:
    """Build concise summaries from one or more ordinance text blocks."""

    def summarize(self, text: str, max_words: int = 48) -> str:
        # Normalize whitespace so the word limit behaves consistently.
        normalized = self._normalize_text(text)
        if not normalized:
            return ""

        # Prefer the first sentence when it already fits inside the budget.
        first_sentence = re.split(r"(?<=[.!?;])\s+", normalized, maxsplit=1)[0].strip()
        if first_sentence and len(first_sentence.split()) <= max_words:
            return first_sentence

        # Fall back to a leading excerpt when the sentence runs too long.
        return " ".join(normalized.split()[:max_words]).strip()

    def summarize_many(self, text_blocks: Sequence[str], max_words: int = 72) -> str:
        # Join multiple exact section bodies into one summary scope.
        combined = " ".join(self._normalize_text(text) for text in text_blocks if self._normalize_text(text))
        return self.summarize(combined, max_words=max_words)

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip()).strip()


# ---------------------------------------------------------------------------
# Navigation hashmap builder
# ---------------------------------------------------------------------------
# The LLM should not need access to every stored row at once. Instead, we build
# a compact hashmap that says which documents exist, which chapters live under
# them, and which sections/subsections can be navigated to from there.


class NavigationMapBuilder:
    """Build the in-memory navigation hashmap used by the tool-driven RAG stack."""

    def build(self, hierarchies: Sequence[dict]) -> dict:
        navigation_map = {
            "documents": {},
            "alias_map": {},
        }

        for hierarchy in hierarchies:
            document_slug = hierarchy["document_slug"]
            document_title = hierarchy["document_title"]
            chapter_payloads: dict[str, dict] = {}
            section_total = 0
            subsection_total = 0

            # Each chapter becomes a stable hashmap key that can later be used
            # for exact chapter/section navigation.
            for chapter in hierarchy.get("chapters", []):
                sections_payload: dict[str, dict] = {}
                for section in chapter.get("sections", []):
                    section_total += 1
                    subsection_total += len(section.get("subsections", []))
                    sections_payload[section["section_number"]] = {
                        "section_number": section["section_number"],
                        "section_summary": section.get("section_summary", ""),
                        "subsection_count": section.get("subsection_count", 0),
                        "subsections": [
                            {
                                "subsection_number": subsection["subsection_number"],
                                "subsection_summary": subsection.get("subsection_summary", ""),
                            }
                            for subsection in section.get("subsections", [])
                        ],
                    }

                chapter_payloads[chapter["chapter_number"]] = {
                    "chapter_number": chapter["chapter_number"],
                    "chapter_name": chapter.get("chapter_name", ""),
                    "toc_page": chapter.get("toc_page"),
                    "section_count": chapter.get("section_count", len(sections_payload)),
                    "sections": sections_payload,
                }

            aliases = sorted(self._build_aliases(document_title=document_title, document_slug=document_slug))
            navigation_map["documents"][document_slug] = {
                "document_title": document_title,
                "document_slug": document_slug,
                "source_filename": hierarchy.get("source_filename"),
                "owner_user_id": hierarchy.get("owner_user_id"),
                "visibility": hierarchy.get("visibility", "public"),
                "aliases": aliases,
                "chapter_count": len(chapter_payloads),
                "section_count": section_total,
                "subsection_count": subsection_total,
                "chapters": chapter_payloads,
            }

            # One alias can map to more than one document, so we keep a list.
            for alias in aliases:
                navigation_map["alias_map"].setdefault(alias, []).append(document_slug)

        return navigation_map

    def _build_aliases(self, document_title: str, document_slug: str) -> set[str]:
        aliases: set[str] = set()

        # Preserve the two most important lookup representations first.
        aliases.add(self._normalize_lookup_value(document_title))
        aliases.add(self._normalize_lookup_value(document_slug.replace("_", " ")))

        # Strip common ordinance suffixes so the user can just say "Broward County".
        trimmed_title = re.sub(
            r"\bcode of ordinances?\b",
            "",
            document_title,
            flags=re.IGNORECASE,
        )
        trimmed_title = re.sub(r"\bmunicipal code\b", "", trimmed_title, flags=re.IGNORECASE)
        trimmed_title = trimmed_title.replace(",", " ")
        aliases.add(self._normalize_lookup_value(trimmed_title))

        # Keep "city" and "county" phrasing because users commonly refer to a
        # jurisdiction in that shorter form rather than the full PDF title.
        location_match = re.search(
            r"([A-Za-z][A-Za-z .'-]+?\b(?:city|county))",
            document_title,
            flags=re.IGNORECASE,
        )
        if location_match:
            aliases.add(self._normalize_lookup_value(location_match.group(1)))

        # Add a no-state version such as "Cooper City" from "Cooper City FL".
        no_state = re.sub(r"\bfl\b", "", trimmed_title, flags=re.IGNORECASE)
        aliases.add(self._normalize_lookup_value(no_state))

        # Single-word aliases are only useful when the name is unique, but they
        # are still stored here because the resolver applies scoring afterward.
        words = [word for word in re.findall(r"[A-Za-z0-9]+", trimmed_title.lower()) if len(word) > 2]
        if words:
            aliases.add(self._normalize_lookup_value(words[0]))

        return {alias for alias in aliases if alias}

    def _normalize_lookup_value(self, raw_value: str) -> str:
        value = re.sub(r"[^a-z0-9]+", " ", (raw_value or "").lower()).strip()
        return re.sub(r"\s+", " ", value)


# ---------------------------------------------------------------------------
# Tool factory
# ---------------------------------------------------------------------------
# The factory owns path resolution and dependency wiring so the API and RAG code
# can ask for one ready-to-use toolkit instance instead of rebuilding the pieces
# manually each time.


class StructuredToolFactory:
    """Create the DB/Chroma-backed tool layer for the structured Civil AI stack."""

    @staticmethod
    def create_default_paths(backend_root: Path | None = None) -> StructuredToolPaths:
        resolved_backend_root = backend_root or Path(__file__).resolve().parents[2]
        data_dir = resolved_backend_root / "Data"
        return StructuredToolPaths(
            backend_root=resolved_backend_root,
            data_dir=data_dir,
            db_path=StructuredToolFactory._resolve_database_path(data_dir),
            chroma_dir=data_dir / "chroma_db",
            json_dir=data_dir / "parsed_json",
            manifest_path=data_dir / "processed_files.json",
        )

    @staticmethod
    def create_database_manager(paths: StructuredToolPaths) -> DatabaseManager:
        return DatabaseManager(db_url=f"sqlite:///{paths.db_path.as_posix()}")

    @staticmethod
    def create_chroma_manager(paths: StructuredToolPaths, db_manager: DatabaseManager) -> ChromaManager:
        return create_runtime_vector_manager(
            persist_directory=paths.chroma_dir,
            db_manager=db_manager,
        )

    @staticmethod
    def create_toolkit(paths: StructuredToolPaths | None = None) -> "StructuredRetrievalToolkit":
        resolved_paths = paths or StructuredToolFactory.create_default_paths()
        db_manager = StructuredToolFactory.create_database_manager(resolved_paths)
        chroma_manager = StructuredToolFactory.create_chroma_manager(resolved_paths, db_manager)
        return StructuredRetrievalToolkit(
            paths=resolved_paths,
            db_manager=db_manager,
            chroma_manager=chroma_manager,
        )

    @staticmethod
    def _resolve_database_path(data_dir: Path) -> Path:
        # Prefer the new structured database name. If it does not exist yet, we
        # only fall back to `civilai.db` when that file already contains the new
        # normalized schema tables.
        structured_path = data_dir / "civilai_structured.db"
        if structured_path.exists():
            return structured_path

        legacy_path = data_dir / "civilai.db"
        if legacy_path.exists() and StructuredToolFactory._database_looks_structured(legacy_path):
            return legacy_path

        return structured_path

    @staticmethod
    def _database_looks_structured(db_path: Path) -> bool:
        # Inspect the SQLite schema before reusing an existing file so we do not
        # accidentally point the new retrieval layer at the old legacy schema.
        try:
            with sqlite3.connect(str(db_path)) as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                table_names = {row[0] for row in cursor.fetchall()}
        except sqlite3.Error:
            return False

        return {"documents", "chapters", "sections", "subsections"}.issubset(table_names)


# ---------------------------------------------------------------------------
# Structured retrieval toolkit
# ---------------------------------------------------------------------------
# This class is the actual tool surface the LLM-facing RAG layer will use. The
# LLM does not receive the whole database. Instead, this toolkit:
# 1. resolves the target ordinance through a hashmap,
# 2. checks for exact section/subsection references,
# 3. queries Chroma for semantic matches,
# 4. returns only the small evidence set needed for the final prompt.


class StructuredRetrievalToolkit:
    """Tool-driven navigation and retrieval over the normalized DB/Chroma stack."""

    SECTION_REFERENCE_PATTERN = re.compile(r"\b\d+[A-Za-z]?(?:[.-]\d+[A-Za-z0-9]*)+\b")
    SUBSECTION_REFERENCE_PATTERN = re.compile(
        r"(?:sec(?:tion)?\.?\s*)?([A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)+)\s*\(([A-Za-z0-9]+)\)",
        flags=re.IGNORECASE,
    )

    def __init__(
        self,
        paths: StructuredToolPaths,
        db_manager: DatabaseManager,
        chroma_manager: ChromaManager,
        summary_builder: StructuredSummaryBuilder | None = None,
        navigation_builder: NavigationMapBuilder | None = None,
    ) -> None:
        self.paths = paths
        self.db_manager = db_manager
        self.chroma_manager = chroma_manager
        self.summary_builder = summary_builder or StructuredSummaryBuilder()
        self.navigation_builder = navigation_builder or NavigationMapBuilder()
        self._navigation_cache: dict | None = None
        self._navigation_cache_by_user: dict[str, dict] = {}

    def refresh_navigation_cache(self) -> dict:
        """Rebuild the navigation hashmap after new PDFs are parsed and stored."""

        self._navigation_cache = None
        self._navigation_cache_by_user = {}
        return self.get_navigation_map(refresh=True)

    def get_navigation_map(self, refresh: bool = False, user_id: str | None = None) -> dict:
        """Return the current navigation hashmap built from the structured database."""

        if user_id:
            cache_key = str(user_id)
            if cache_key in self._navigation_cache_by_user and not refresh:
                return self._navigation_cache_by_user[cache_key]
        elif self._navigation_cache is not None and not refresh:
            return self._navigation_cache

        hierarchies: list[dict] = []
        for document in self.db_manager.list_documents(user_id=user_id):
            hierarchy = self.db_manager.fetch_document_hierarchy(document["document_slug"], user_id=user_id)
            if hierarchy is not None:
                hierarchies.append(hierarchy)

        navigation_map = self.navigation_builder.build(hierarchies)
        if user_id:
            self._navigation_cache_by_user[str(user_id)] = navigation_map
        else:
            self._navigation_cache = navigation_map
        return navigation_map

    def list_jurisdictions(self, user_id: str | None = None) -> list[dict]:
        """Return the code-focus options that should appear in the website filter."""

        navigation_map = self.get_navigation_map(user_id=user_id)
        jurisdictions = []
        for document in navigation_map.get("documents", {}).values():
            # `chunks` stays as the legacy field name expected by the frontend,
            # but now it reflects the number of queryable section/subsection
            # units rather than the old FAISS chunk count.
            jurisdictions.append(
                {
                    "name": document["document_title"],
                    "chunks": document["section_count"] + document["subsection_count"],
                }
            )
        return sorted(jurisdictions, key=lambda item: item["name"].lower())

    def resolve_document_slug(self, user_text: str | None, user_id: str | None = None) -> str | None:
        """Resolve a user-provided jurisdiction string or query text to one document slug."""

        navigation_map = self.get_navigation_map(user_id=user_id)
        documents = navigation_map.get("documents", {})
        if not documents:
            return None

        if not user_text:
            return next(iter(documents)) if len(documents) == 1 else None

        normalized_input = self._normalize_lookup_value(user_text)
        alias_hits = navigation_map.get("alias_map", {}).get(normalized_input, [])
        if len(alias_hits) == 1:
            return alias_hits[0]

        # Score substring matches across titles and aliases so longer, more
        # specific matches beat vague single-word overlaps.
        scored_candidates: list[tuple[int, str]] = []
        for document_slug, document in documents.items():
            candidate_strings = [document["document_title"], document_slug.replace("_", " ")] + list(
                document.get("aliases", [])
            )
            best_score = 0
            for candidate in candidate_strings:
                normalized_candidate = self._normalize_lookup_value(candidate)
                if not normalized_candidate:
                    continue
                owner_boost = 20 if user_id and str(document.get("owner_user_id") or "") == str(user_id) else 0
                if normalized_input == normalized_candidate:
                    best_score = max(best_score, 100 + owner_boost)
                elif normalized_candidate in normalized_input:
                    best_score = max(best_score, 80 + min(len(normalized_candidate), 15) + owner_boost)
                elif normalized_input in normalized_candidate:
                    best_score = max(best_score, 65 + min(len(normalized_input), 15) + owner_boost)
            if best_score > 0:
                scored_candidates.append((best_score, document_slug))

        scored_candidates.sort(reverse=True)
        return scored_candidates[0][1] if scored_candidates else None

    def detect_section_filters(self, query: str) -> list[str]:
        """Extract exact section identifiers such as `Sec. 1-2` from a user query."""

        seen: set[str] = set()
        section_filters: list[str] = []

        for raw_match in self.SECTION_REFERENCE_PATTERN.findall(query or ""):
            normalized = f"Sec. {raw_match.strip()}"
            lowered = normalized.lower()
            if lowered not in seen:
                seen.add(lowered)
                section_filters.append(normalized)

        return section_filters

    def detect_subsection_filters(self, query: str) -> list[dict]:
        """Extract exact `(a)`-style subsection references tied to a section number."""

        seen: set[tuple[str, str]] = set()
        subsection_filters: list[dict] = []

        for section_token, subsection_token in self.SUBSECTION_REFERENCE_PATTERN.findall(query or ""):
            section_number = f"Sec. {section_token.strip()}"
            subsection_number = f"({subsection_token.strip().lower()})"
            key = (section_number.lower(), subsection_number.lower())
            if key in seen:
                continue
            seen.add(key)
            subsection_filters.append(
                {
                    "section_number": section_number,
                    "subsection_number": subsection_number,
                }
            )

        return subsection_filters

    def detect_summary_intent(self, query: str) -> bool:
        """Detect whether the user is asking for a summary-style response."""

        lowered = (query or "").lower()
        return any(keyword in lowered for keyword in ("summarize", "summary", "overview", "synopsis"))

    def summarize_sections(
        self,
        document_slug: str,
        section_numbers: Sequence[str],
        user_id: str | None = None,
    ) -> dict | None:
        """Summarize one or more exact sections from the structured database."""

        section_rows = self.db_manager.find_sections(document_slug, section_numbers=section_numbers, user_id=user_id)
        if not section_rows:
            return None

        text_blocks: list[str] = []
        sources: list[dict] = []

        for section_row in section_rows:
            section_text = self._compose_section_text(section_row)
            if section_text:
                text_blocks.append(section_text)
            sources.append(
                {
                    "section": section_row["section_number"],
                    "chapter_number": section_row["chapter_number"],
                    "chapter_name": section_row["chapter_name"],
                }
            )

        return {
            "summary": self.summary_builder.summarize_many(text_blocks),
            "section_count": len(section_rows),
            "sources": sources,
        }

    def run_tool_chain(
        self,
        query: str,
        jurisdiction: str | None = None,
        top_k: int = 5,
        user_id: str | None = None,
    ) -> dict:
        """Execute the retrieval tools in a deterministic order before prompting the LLM."""

        navigation_map = self.get_navigation_map(user_id=user_id)

        # Resolve the code focus from either the explicit filter or the query itself.
        resolved_document_slug = self.resolve_document_slug(jurisdiction, user_id=user_id) or self.resolve_document_slug(query, user_id=user_id)
        resolved_document = navigation_map.get("documents", {}).get(resolved_document_slug or "")

        tool_trace: list[dict] = []
        if resolved_document is not None:
            tool_trace.append(
                {
                    "tool": "resolve_document",
                    "input": jurisdiction or query,
                    "output": resolved_document["document_title"],
                }
            )

        section_filters = self.detect_section_filters(query)
        if section_filters:
            tool_trace.append(
                {
                    "tool": "detect_section_filters",
                    "input": query,
                    "output": section_filters,
                }
            )

        subsection_filters = self.detect_subsection_filters(query)
        if subsection_filters:
            tool_trace.append(
                {
                    "tool": "detect_subsection_filters",
                    "input": query,
                    "output": subsection_filters,
                }
            )

        exact_results = self._lookup_exact_matches(
            document_slug=resolved_document_slug,
            section_filters=section_filters,
            subsection_filters=subsection_filters,
            navigation_map=navigation_map,
            user_id=user_id,
        )
        if exact_results:
            tool_trace.append(
                {
                    "tool": "lookup_exact_matches",
                    "output_count": len(exact_results),
                }
            )

        semantic_results = self.semantic_search(
            query=query,
            document_slug=resolved_document_slug,
            limit=max(top_k, 8),
            user_id=user_id,
        )
        if semantic_results:
            tool_trace.append(
                {
                    "tool": "semantic_search",
                    "output_count": len(semantic_results),
                }
            )

        keyword_results = self.keyword_search(
            query=query,
            document_slug=resolved_document_slug,
            navigation_map=navigation_map,
            limit=max(top_k, 8),
            user_id=user_id,
        )
        if keyword_results:
            tool_trace.append(
                {
                    "tool": "keyword_search",
                    "output_count": len(keyword_results),
                }
            )

        merged_results = self._merge_results(
            query=query,
            exact_results=exact_results,
            keyword_results=keyword_results,
            semantic_results=semantic_results,
            top_k=top_k,
        )

        summary_preview = None
        if self.detect_summary_intent(query) and section_filters:
            summary_target_slug = resolved_document_slug
            if summary_target_slug is None and merged_results:
                summary_target_slug = merged_results[0]["meta"].get("document_slug")
            if summary_target_slug:
                summary_preview = self.summarize_sections(summary_target_slug, section_filters, user_id=user_id)
                if summary_preview:
                    tool_trace.append(
                        {
                            "tool": "summarize_sections",
                            "output_count": summary_preview["section_count"],
                        }
                    )

        navigation = self._build_navigation_payload(
            resolved_document=resolved_document,
            results=merged_results,
            section_filters=section_filters,
            summary_preview=summary_preview,
            tool_trace=tool_trace,
        )

        return {
            "results": merged_results,
            "navigation": navigation,
            "tool_trace": tool_trace,
            "resolved_document_slug": resolved_document_slug,
            "resolved_document_title": resolved_document["document_title"] if resolved_document else None,
            "summary_preview": summary_preview,
        }

    def semantic_search(
        self,
        query: str,
        document_slug: str | None = None,
        limit: int = 8,
        user_id: str | None = None,
    ) -> list[dict]:
        """Query Chroma section/subsection collections and hydrate results from SQL."""

        where_filters = self._semantic_where_filters(document_slug=document_slug, user_id=user_id)
        combined_results: list[dict] = []

        for collection_name in (
            ChromaCollectionFactory.SECTION_COLLECTION,
            ChromaCollectionFactory.SUBSECTION_COLLECTION,
        ):
            for where_filter in where_filters:
                chroma_rows = self.chroma_manager.query_collection(
                    collection_name=collection_name,
                    query_text=query,
                    n_results=limit,
                    where=where_filter,
                )
                for chroma_row in chroma_rows:
                    if not self._vector_row_visible_to_user(chroma_row, user_id=user_id):
                        continue
                    hydrated = self._hydrate_chroma_result(chroma_row, user_id=user_id)
                    if hydrated is not None:
                        combined_results.append(hydrated)

        return self._dedupe_results(combined_results)[:limit]

    def keyword_search(
        self,
        query: str,
        document_slug: str | None,
        navigation_map: dict,
        limit: int = 8,
        user_id: str | None = None,
    ) -> list[dict]:
        """Run a lightweight lexical section search before falling back to the LLM."""

        candidate_document_slugs = (
            [document_slug]
            if document_slug
            else list(navigation_map.get("documents", {}).keys())
        )

        keyword_results: list[dict] = []
        for candidate_slug in candidate_document_slugs:
            if not candidate_slug:
                continue

            section_rows = self.db_manager.search_sections_by_query_terms(
                document_title_or_slug=candidate_slug,
                query=query,
                limit=limit,
                user_id=user_id,
            )
            for section_row in section_rows:
                lexical_score = float(section_row.get("lexical_score", 0.0))
                keyword_results.append(
                    self._section_row_to_result(
                        section_row,
                        score=min(0.82, 0.28 + (min(lexical_score, 1.8) * 0.22)),
                        matched_by="keyword_section",
                        lexical_score=lexical_score,
                    )
                )

        keyword_results.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        return self._dedupe_results(keyword_results)[:limit]

    def _lookup_exact_matches(
        self,
        document_slug: str | None,
        section_filters: Sequence[str],
        subsection_filters: Sequence[dict],
        navigation_map: dict,
        user_id: str | None = None,
    ) -> list[dict]:
        # Exact lookups are run against the SQL layer because those matches are
        # cheaper and more trustworthy than a semantic query.
        candidate_document_slugs = (
            [document_slug]
            if document_slug
            else list(navigation_map.get("documents", {}).keys())
        )

        exact_results: list[dict] = []
        for candidate_slug in candidate_document_slugs:
            if not candidate_slug:
                continue

            for subsection_filter in subsection_filters:
                subsection_rows = self.db_manager.find_subsections(
                    document_title_or_slug=candidate_slug,
                    section_number=subsection_filter["section_number"],
                    subsection_numbers=[subsection_filter["subsection_number"]],
                    user_id=user_id,
                )
                for subsection_row in subsection_rows:
                    exact_results.append(
                        self._subsection_row_to_result(
                            subsection_row,
                            score=1.0,
                            matched_by="exact_subsection",
                        )
                    )

            if section_filters:
                section_rows = self.db_manager.find_sections(
                    document_title_or_slug=candidate_slug,
                    section_numbers=section_filters,
                    user_id=user_id,
                )
                for section_row in section_rows:
                    exact_results.append(
                        self._section_row_to_result(
                            section_row,
                            score=0.99,
                            matched_by="exact_section",
                        )
                    )

        return self._dedupe_results(exact_results)

    def _hydrate_chroma_result(self, chroma_row: dict, user_id: str | None = None) -> dict | None:
        metadata = chroma_row.get("metadata", {})
        node_type = metadata.get("node_type")
        document_slug = metadata.get("document_slug")
        score = float(chroma_row.get("score", 0.0))

        if node_type == "section":
            section_rows = self.db_manager.find_sections(
                document_title_or_slug=str(document_slug),
                section_numbers=[metadata.get("section_number", "")],
                user_id=user_id,
            )
            if section_rows:
                return self._section_row_to_result(
                    section_rows[0],
                    score=score,
                    matched_by="semantic_section",
                )

        if node_type == "subsection":
            subsection_rows = self.db_manager.find_subsections(
                document_title_or_slug=str(document_slug),
                section_number=str(metadata.get("section_number", "")),
                subsection_numbers=[str(metadata.get("subsection_number", ""))],
                user_id=user_id,
            )
            if subsection_rows:
                return self._subsection_row_to_result(
                    subsection_rows[0],
                    score=score,
                    matched_by="semantic_subsection",
                )

        return None

    def _section_row_to_result(
        self,
        section_row: dict,
        score: float,
        matched_by: str,
        lexical_score: float | None = None,
    ) -> dict:
        section_text = self._compose_section_text(section_row)
        section_summary = section_row.get("section_summary") or self.summary_builder.summarize(section_text)

        return {
            "text": section_text,
            "summary": section_summary,
            "score": score,
            "rerank_score": score,
            "matched_by": matched_by,
            "matched_methods": [matched_by],
            "lexical_score": lexical_score,
            "meta": {
                "jurisdiction": section_row["document_title"],
                "document_slug": section_row["document_slug"],
                "source": section_row.get("source_filename"),
                "section": section_row["section_number"],
                "subsection": None,
                "title": section_row["chapter_name"],
                "chapter_number": section_row["chapter_number"],
                "chapter_name": section_row["chapter_name"],
                "page": section_row.get("toc_page"),
                "node_type": "section",
                "owner_user_id": section_row.get("owner_user_id"),
                "visibility": section_row.get("visibility") or "public",
            },
        }

    def _subsection_row_to_result(self, subsection_row: dict, score: float, matched_by: str) -> dict:
        subsection_text = self._compose_subsection_text(subsection_row)
        subsection_summary = subsection_row.get("subsection_summary") or self.summary_builder.summarize(subsection_text)

        return {
            "text": subsection_text,
            "summary": subsection_summary,
            "score": score,
            "rerank_score": score,
            "matched_by": matched_by,
            "matched_methods": [matched_by],
            "lexical_score": None,
            "meta": {
                "jurisdiction": subsection_row["document_title"],
                "document_slug": subsection_row["document_slug"],
                "source": subsection_row.get("source_filename"),
                "section": subsection_row["section_number"],
                "subsection": subsection_row["subsection_number"],
                "title": subsection_row["chapter_name"],
                "chapter_number": subsection_row["chapter_number"],
                "chapter_name": subsection_row["chapter_name"],
                "page": subsection_row.get("toc_page"),
                "node_type": "subsection",
                "owner_user_id": subsection_row.get("owner_user_id"),
                "visibility": subsection_row.get("visibility") or "public",
            },
        }

    @staticmethod
    def _vector_row_visible_to_user(chroma_row: dict, user_id: str | None = None) -> bool:
        metadata = chroma_row.get("metadata", {})
        visibility = str(metadata.get("visibility") or "public")
        owner_user_id = str(metadata.get("owner_user_id") or "")
        if visibility == "public":
            return True
        return bool(user_id and owner_user_id == str(user_id))

    @staticmethod
    def _semantic_where_filters(document_slug: str | None, user_id: str | None) -> list[dict | None]:
        if document_slug:
            return [{"document_slug": document_slug}]
        if user_id:
            return [{"visibility": "public"}, {"owner_user_id": str(user_id)}]
        return [None]

    def _compose_section_text(self, section_row: dict) -> str:
        # Prefer the section body itself. If the section body is empty, use the
        # subsection text as a fallback so the LLM still gets the substantive rule.
        section_text = (section_row.get("section_text") or "").strip()
        if section_text:
            return section_text

        fallback = " ".join(
            (
                subsection.get("subsection_text")
                or subsection.get("subsection_summary")
                or ""
            ).strip()
            for subsection in section_row.get("subsections", [])
            if (
                subsection.get("subsection_text")
                or subsection.get("subsection_summary")
                or ""
            ).strip()
        )
        return fallback.strip()

    def _compose_subsection_text(self, subsection_row: dict) -> str:
        return (
            subsection_row.get("subsection_text")
            or subsection_row.get("subsection_summary")
            or subsection_row.get("section_summary")
            or ""
        ).strip()

    def _merge_results(
        self,
        query: str,
        exact_results: Sequence[dict],
        keyword_results: Sequence[dict],
        semantic_results: Sequence[dict],
        top_k: int,
    ) -> list[dict]:
        query_terms = self._extract_query_terms(query)
        aggregated: dict[tuple[str, str, str], dict] = {}

        for result in [*exact_results, *keyword_results, *semantic_results]:
            key = self._result_key(result)
            current = aggregated.get(key)
            if current is None:
                current = {
                    **result,
                    "matched_methods": list(result.get("matched_methods", [result.get("matched_by", "")])),
                    "channel_scores": {str(result.get("matched_by", "")): float(result.get("score", 0.0))},
                    "lexical_score": result.get("lexical_score"),
                }
                aggregated[key] = current
                continue

            candidate_score = float(result.get("score", 0.0))
            current_score = float(current.get("score", 0.0))
            if candidate_score > current_score:
                preserved_methods = current.get("matched_methods", [])
                channel_scores = current.get("channel_scores", {})
                lexical_score = current.get("lexical_score")
                current.update(result)
                current["matched_methods"] = preserved_methods
                current["channel_scores"] = channel_scores
                current["lexical_score"] = lexical_score

            matched_by = str(result.get("matched_by", ""))
            if matched_by and matched_by not in current["matched_methods"]:
                current["matched_methods"].append(matched_by)
            current["channel_scores"][matched_by] = max(
                candidate_score,
                float(current["channel_scores"].get(matched_by, 0.0)),
            )

            incoming_lexical = result.get("lexical_score")
            if incoming_lexical is not None:
                existing_lexical = current.get("lexical_score")
                if existing_lexical is None or float(incoming_lexical) > float(existing_lexical):
                    current["lexical_score"] = incoming_lexical

        reranked_results: list[dict] = []
        for result in aggregated.values():
            rerank_score = self._compute_result_rank(result, query_terms)
            result["score"] = rerank_score
            result["rerank_score"] = rerank_score
            result["matched_by"] = self._select_primary_match_method(result.get("matched_methods", []))
            reranked_results.append(result)

        reranked_results.sort(
            key=lambda item: (
                float(item.get("rerank_score", 0.0)),
                self._match_method_priority(item.get("matched_by", "")),
                len(item.get("text", "") or ""),
            ),
            reverse=True,
        )
        return reranked_results[:top_k]

    def _dedupe_results(self, results: Sequence[dict]) -> list[dict]:
        # Deduplicate by the most specific citation key so an exact match and a
        # semantic match for the same section do not both crowd the context.
        deduped: dict[tuple[str, str, str], dict] = {}
        for result in results:
            meta = result.get("meta", {})
            key = (
                str(meta.get("document_slug") or ""),
                str(meta.get("section") or ""),
                str(meta.get("subsection") or ""),
            )
            current = deduped.get(key)
            if current is None or float(result.get("score", 0.0)) > float(current.get("score", 0.0)):
                deduped[key] = result

        return list(deduped.values())

    def _compute_result_rank(self, result: dict, query_terms: Sequence[str]) -> float:
        """Blend channel agreement and topic overlap into one sortable rank."""

        matched_methods = [str(method) for method in result.get("matched_methods", []) if method]
        channel_scores = {
            str(method): float(score)
            for method, score in (result.get("channel_scores") or {}).items()
        }
        base_score = max(channel_scores.values(), default=float(result.get("score", 0.0)))
        lexical_score = float(result.get("lexical_score") or 0.0)

        text = " ".join(
            [
                str(result.get("summary") or ""),
                str(result.get("text") or ""),
                str(result.get("meta", {}).get("chapter_name") or ""),
                str(result.get("meta", {}).get("title") or ""),
            ]
        ).lower()
        coverage = 0.0
        if query_terms:
            coverage = sum(1 for term in query_terms if term in text) / len(query_terms)

        semantic_present = any(method.startswith("semantic") for method in matched_methods)
        keyword_present = any(method.startswith("keyword") for method in matched_methods)
        exact_present = any(method.startswith("exact") for method in matched_methods)

        rerank_score = base_score
        rerank_score += min(coverage * 0.18, 0.18)
        rerank_score += min(lexical_score * 0.04, 0.08)

        if exact_present:
            rerank_score += 0.18
        if semantic_present and keyword_present:
            rerank_score += 0.14
        elif semantic_present:
            rerank_score += 0.06
        elif keyword_present:
            rerank_score += 0.02

        return min(rerank_score, 1.0)

    @staticmethod
    def _select_primary_match_method(matched_methods: Sequence[str]) -> str:
        """Pick the strongest retrieval label for downstream explanations."""

        methods = [str(method) for method in matched_methods if method]
        for prefix in ("exact", "semantic", "keyword"):
            for method in methods:
                if method.startswith(prefix):
                    return method
        return methods[0] if methods else ""

    @staticmethod
    def _match_method_priority(matched_by: str) -> int:
        if str(matched_by).startswith("exact"):
            return 3
        if str(matched_by).startswith("semantic"):
            return 2
        if str(matched_by).startswith("keyword"):
            return 1
        return 0

    @staticmethod
    def _result_key(result: dict) -> tuple[str, str, str]:
        meta = result.get("meta", {})
        return (
            str(meta.get("document_slug") or ""),
            str(meta.get("section") or ""),
            str(meta.get("subsection") or ""),
        )

    @staticmethod
    def _extract_query_terms(query: str) -> list[str]:
        stop_words = {
            "what",
            "does",
            "about",
            "that",
            "this",
            "with",
            "from",
            "into",
            "when",
            "where",
            "which",
            "summarize",
            "summary",
            "section",
            "city",
            "county",
            "code",
            "ordinance",
            "ordinances",
            "after",
            "before",
            "during",
            "between",
            "within",
            "without",
            "says",
            "say",
        }
        return [
            term
            for term in re.findall(r"[a-z0-9]+", (query or "").lower())
            if len(term) > 2 and term not in stop_words
        ]

    def _build_navigation_payload(
        self,
        resolved_document: dict | None,
        results: Sequence[dict],
        section_filters: Sequence[str],
        summary_preview: dict | None,
        tool_trace: Sequence[dict],
    ) -> dict:
        top_chapters: list[dict] = []
        seen_chapters: set[tuple[str, str]] = set()
        for result in results:
            meta = result.get("meta", {})
            chapter_key = (
                str(meta.get("chapter_number") or ""),
                str(meta.get("chapter_name") or ""),
            )
            if chapter_key in seen_chapters or not chapter_key[0]:
                continue
            seen_chapters.add(chapter_key)
            top_chapters.append(
                {
                    "chapter_number": chapter_key[0],
                    "chapter_name": chapter_key[1],
                }
            )

        return {
            "document_slug": resolved_document["document_slug"] if resolved_document else None,
            "document_title": resolved_document["document_title"] if resolved_document else None,
            "matched_sections": list(section_filters),
            "top_chapters": top_chapters,
            "summary_preview": summary_preview["summary"] if summary_preview else None,
            "tool_trace": list(tool_trace),
        }

    def _normalize_lookup_value(self, raw_value: str) -> str:
        value = re.sub(r"[^a-z0-9]+", " ", (raw_value or "").lower()).strip()
        return re.sub(r"\s+", " ", value)
