from __future__ import annotations

# Standard library utilities are enough for deterministic test embeddings and
# basic path management.
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# ChromaDB is the vector store backing this manager.
import chromadb

# NumPy makes it easy to normalize vectors and to keep query/upsert payloads tidy.
import numpy as np

# Reuse the normalized structural blueprint from DB.py so the relational and
# vector layers always operate on the exact same in-memory hierarchy.
from .DB import DatabaseManager, DocumentDefinition, DocumentSchemaBuilder


# ---------------------------------------------------------------------------
# Vector payload objects
# ---------------------------------------------------------------------------
# These dataclasses describe the unit that will actually be inserted into Chroma.
# One node maps to one collection record.


@dataclass(slots=True)
class ChromaNode:
    # A globally unique ID that lets us replace or delete a node safely.
    node_id: str
    # The target collection name for this node.
    collection_name: str
    # The text body that should be embedded and stored in Chroma.
    document: str
    # Flat scalar metadata used for filtering and reconstruction.
    metadata: dict[str, str | int | float | bool]
    # The vector embedding for the node.
    embedding: list[float]


@dataclass(slots=True)
class ChromaDocumentPayload:
    # The normalized document slug this payload belongs to.
    document_slug: str
    # The human title of the document.
    document_title: str
    # Grouped nodes by collection so the manager can batch upserts cleanly.
    nodes_by_collection: dict[str, list[ChromaNode]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Collection factory
# ---------------------------------------------------------------------------
# The factory owns the physical Chroma collection creation step. This mirrors the
# schema factory in DB.py and keeps "how collections are created" separate from
# "how document payloads are built."


class ChromaCollectionFactory:
    """Create the fixed Chroma collections used by the normalized storage model."""

    DOCUMENT_COLLECTION = "document_nodes"
    CHAPTER_COLLECTION = "chapter_nodes"
    SECTION_COLLECTION = "section_nodes"
    SUBSECTION_COLLECTION = "subsection_nodes"

    @classmethod
    def build(cls, client: chromadb.PersistentClient) -> dict[str, object]:
        # Each collection is created once and then reused. We keep the distance
        # space explicitly set to cosine because our embeddings are normalized.
        return {
            cls.DOCUMENT_COLLECTION: client.get_or_create_collection(
                name=cls.DOCUMENT_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            ),
            cls.CHAPTER_COLLECTION: client.get_or_create_collection(
                name=cls.CHAPTER_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            ),
            cls.SECTION_COLLECTION: client.get_or_create_collection(
                name=cls.SECTION_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            ),
            cls.SUBSECTION_COLLECTION: client.get_or_create_collection(
                name=cls.SUBSECTION_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            ),
        }


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------
# This builder converts a normalized `DocumentDefinition` into Chroma-ready node
# payloads. It is intentionally separate from the manager so the creation logic
# remains easy to test in isolation.


class ChromaDocumentBuilder:
    """Build Chroma node payloads from a normalized document blueprint."""

    def __init__(
        self,
        embedding_provider: Callable[[str], list[float]] | None = None,
        embedding_dimensions: int = 64,
    ) -> None:
        # Allow a real embedding function to be injected later, while keeping a
        # deterministic fallback for local testing right now.
        self.embedding_provider = embedding_provider or self._default_embed_text
        self.embedding_dimensions = embedding_dimensions

    def from_document_blueprint(self, blueprint: DocumentDefinition) -> ChromaDocumentPayload:
        # Build one document payload grouped by the four fixed collection types.
        payload = ChromaDocumentPayload(
            document_slug=blueprint.document_slug,
            document_title=blueprint.document_title,
            nodes_by_collection={
                ChromaCollectionFactory.DOCUMENT_COLLECTION: [],
                ChromaCollectionFactory.CHAPTER_COLLECTION: [],
                ChromaCollectionFactory.SECTION_COLLECTION: [],
                ChromaCollectionFactory.SUBSECTION_COLLECTION: [],
            },
        )

        # The document-level node gives the LLM a top-of-tree summary target.
        payload.nodes_by_collection[ChromaCollectionFactory.DOCUMENT_COLLECTION].append(
            self._build_document_node(blueprint)
        )

        # Each lower node is created in order so downstream filtering remains intuitive.
        for chapter in blueprint.chapters:
            payload.nodes_by_collection[ChromaCollectionFactory.CHAPTER_COLLECTION].append(
                self._build_chapter_node(blueprint, chapter)
            )

            for section in chapter.sections:
                payload.nodes_by_collection[ChromaCollectionFactory.SECTION_COLLECTION].append(
                    self._build_section_node(blueprint, chapter, section)
                )

                for subsection in section.subsections:
                    payload.nodes_by_collection[ChromaCollectionFactory.SUBSECTION_COLLECTION].append(
                        self._build_subsection_node(blueprint, chapter, section, subsection)
                    )

        return payload

    def _build_document_node(self, blueprint: DocumentDefinition) -> ChromaNode:
        # Build a compact document overview text so document-level semantic lookup
        # can decide which ordinance the query belongs to before drilling deeper.
        chapter_preview = "; ".join(
            f"Chapter {chapter.chapter_number}: {chapter.chapter_name}"
            for chapter in blueprint.chapters[:12]
        )
        text_body = f"{blueprint.document_title}. {chapter_preview}"
        return ChromaNode(
            node_id=f"document::{blueprint.document_slug}",
            collection_name=ChromaCollectionFactory.DOCUMENT_COLLECTION,
            document=text_body,
            metadata={
                "node_type": "document",
                "document_slug": blueprint.document_slug,
                "document_title": blueprint.document_title,
                "source_filename": blueprint.source_filename or "",
                "chapter_count": len(blueprint.chapters),
            },
            embedding=self.embedding_provider(text_body),
        )

    def _build_chapter_node(self, blueprint: DocumentDefinition, chapter) -> ChromaNode:
        # Chapter nodes summarize the chapter and preview the sections under it.
        section_preview = "; ".join(section.section_number for section in chapter.sections[:20])
        text_body = (
            f"{blueprint.document_title}. "
            f"Chapter {chapter.chapter_number}: {chapter.chapter_name}. "
            f"Sections: {section_preview}"
        )
        return ChromaNode(
            node_id=f"chapter::{blueprint.document_slug}::{chapter.chapter_number}",
            collection_name=ChromaCollectionFactory.CHAPTER_COLLECTION,
            document=text_body,
            metadata={
                "node_type": "chapter",
                "document_slug": blueprint.document_slug,
                "document_title": blueprint.document_title,
                "chapter_number": chapter.chapter_number,
                "chapter_name": chapter.chapter_name,
                "toc_page": chapter.toc_page or 0,
                "section_count": chapter.section_count,
            },
            embedding=self.embedding_provider(text_body),
        )

    def _build_section_node(self, blueprint: DocumentDefinition, chapter, section) -> ChromaNode:
        # Section nodes are the main semantic navigation layer because they hold
        # the section number and its summary in one searchable unit.
        subsection_preview = "; ".join(
            subsection.subsection_number for subsection in section.subsections[:20]
        )
        fallback_subsection_text = " ".join(
            (subsection.subsection_text or subsection.subsection_summary).strip()
            for subsection in section.subsections[:8]
            if (subsection.subsection_text or subsection.subsection_summary).strip()
        )
        section_body = (section.section_text or fallback_subsection_text).strip()
        text_body = (
            f"{blueprint.document_title}. "
            f"Chapter {chapter.chapter_number}: {chapter.chapter_name}. "
            f"{section.section_number}. {section.section_summary}. "
            f"{section_body} "
            f"Subsections: {subsection_preview}"
        )
        return ChromaNode(
            node_id=f"section::{blueprint.document_slug}::{chapter.chapter_number}::{self._safe_key(section.section_number)}",
            collection_name=ChromaCollectionFactory.SECTION_COLLECTION,
            document=text_body,
            metadata={
                "node_type": "section",
                "document_slug": blueprint.document_slug,
                "document_title": blueprint.document_title,
                "chapter_number": chapter.chapter_number,
                "chapter_name": chapter.chapter_name,
                "section_number": section.section_number,
                "subsection_count": section.subsection_count,
                "has_section_text": bool(section_body),
            },
            embedding=self.embedding_provider(text_body),
        )

    def _build_subsection_node(self, blueprint: DocumentDefinition, chapter, section, subsection) -> ChromaNode:
        # Subsection nodes are the deepest structured units in this first version.
        subsection_body = (subsection.subsection_text or "").strip()
        text_body = (
            f"{blueprint.document_title}. "
            f"Chapter {chapter.chapter_number}: {chapter.chapter_name}. "
            f"{section.section_number} {subsection.subsection_number}. "
            f"{subsection.subsection_summary}. "
            f"{subsection_body}"
        )
        return ChromaNode(
            node_id=(
                f"subsection::{blueprint.document_slug}::{chapter.chapter_number}::"
                f"{self._safe_key(section.section_number)}::{self._safe_key(subsection.subsection_number)}"
            ),
            collection_name=ChromaCollectionFactory.SUBSECTION_COLLECTION,
            document=text_body,
            metadata={
                "node_type": "subsection",
                "document_slug": blueprint.document_slug,
                "document_title": blueprint.document_title,
                "chapter_number": chapter.chapter_number,
                "chapter_name": chapter.chapter_name,
                "section_number": section.section_number,
                "subsection_number": subsection.subsection_number,
                "has_subsection_text": bool(subsection_body),
            },
            embedding=self.embedding_provider(text_body),
        )

    def _default_embed_text(self, text: str) -> list[float]:
        """
        Build a deterministic lightweight embedding for local testing.

        This is not meant to be the final semantic embedding model. It simply gives
        us a stable vector representation right now so the Chroma pipeline can be
        tested end-to-end without downloading a model.
        """

        # Start with an empty fixed-width vector so every node has the same shape.
        vector = np.zeros(self.embedding_dimensions, dtype=np.float32)

        # Token hashing spreads each token across the vector while remaining deterministic.
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.embedding_dimensions
            magnitude = 1.0 + (int.from_bytes(digest[4:8], "big") % 100) / 100.0
            vector[index] += magnitude

        # Normalize to unit length so cosine distance behaves as expected.
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm

        return vector.astype(np.float32).tolist()

    def _safe_key(self, raw_value: str) -> str:
        # Reuse a readable ID-safe key for section/subsection components inside node IDs.
        value = raw_value.strip().lower()
        value = re.sub(r"[^a-z0-9]+", "_", value)
        value = value.strip("_")
        return value or "unknown"


# ---------------------------------------------------------------------------
# Chroma manager
# ---------------------------------------------------------------------------
# The manager is the operational entry point. It can:
# 1. create/open the fixed collections,
# 2. optionally persist the same document to the relational DB,
# 3. transform the blueprint into Chroma nodes,
# 4. batch upsert/query those nodes safely.


class ChromaManager:
    """Persist structured ordinance navigation data into Chroma collections."""

    def __init__(
        self,
        persist_directory: str | Path = "backend/Data/chroma_db",
        db_manager: DatabaseManager | None = None,
        builder: ChromaDocumentBuilder | None = None,
    ) -> None:
        # Persist directory controls where the Chroma SQLite/index files live.
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        # Reuse the relational manager when available so both stores can sync from one call.
        self.db_manager = db_manager

        # The builder handles creation of per-collection node payloads.
        self.builder = builder or ChromaDocumentBuilder()

        # PersistentClient gives us on-disk durability across app restarts.
        self.client = chromadb.PersistentClient(path=str(self.persist_directory))

        # Discover the client batch ceiling now so future upserts stay inside it.
        self.max_batch_size = self._resolve_max_batch_size()

        # Create/open the fixed collection set.
        self.collections = ChromaCollectionFactory.build(self.client)

    def sync_document(
        self,
        document_title: str,
        chapters: list[dict],
        source_filename: str | None = None,
        replace_existing: bool = True,
        persist_relational: bool = True,
    ) -> dict:
        """
        Create one shared blueprint, optionally persist it to SQL, then upsert it into Chroma.
        """

        # Build the normalized hierarchy exactly once so both stores stay in lockstep.
        #
        # When a relational manager is already attached, we reuse its helper to
        # guarantee the exact same blueprint shape as the SQL layer.
        if self.db_manager is not None:
            blueprint = self.db_manager.build_document_blueprint(
                document_title=document_title,
                chapters=chapters,
                source_filename=source_filename,
            )
        else:
            # If Chroma is being used on its own, we still build the hierarchy
            # through the same builder class instead of opening a SQLite
            # connection just to normalize nested dictionaries.
            blueprint = (
                DocumentSchemaBuilder()
                .from_nested_payload(
                    document_title=document_title,
                    chapters=chapters,
                    source_filename=source_filename,
                )
                .build()
            )

        # Optionally keep the relational side synchronized in the same call.
        if persist_relational:
            # Reuse the injected manager when available. Otherwise create a short-
            # lived manager just for persistence and close it immediately after.
            manager = self.db_manager or DatabaseManager()
            try:
                manager.persist_document_blueprint(blueprint, replace_existing=replace_existing)
            finally:
                if self.db_manager is None:
                    manager.close()

        # Always refresh the Chroma side from the same blueprint.
        return self.upsert_document_blueprint(blueprint, replace_existing=replace_existing)

    def upsert_document_blueprint(
        self,
        blueprint: DocumentDefinition,
        replace_existing: bool = True,
    ) -> dict:
        """Insert or replace one normalized document hierarchy in Chroma."""

        if replace_existing:
            self.delete_document(blueprint.document_slug)

        payload = self.builder.from_document_blueprint(blueprint)

        # Upsert each collection independently so structure and query scopes stay clear.
        for collection_name, nodes in payload.nodes_by_collection.items():
            self._upsert_nodes(collection_name, nodes)

        return {
            "document_title": payload.document_title,
            "document_slug": payload.document_slug,
            "collection_counts": {
                collection_name: len(nodes)
                for collection_name, nodes in payload.nodes_by_collection.items()
            },
        }

    def delete_document(self, document_title_or_slug: str) -> None:
        """Delete all Chroma nodes belonging to one document slug."""

        document_slug = DatabaseManager.make_slug(document_title_or_slug)
        for collection in self.collections.values():
            collection.delete(where={"document_slug": document_slug})

    def list_collections(self) -> list[str]:
        """Return the fixed collection names currently managed by this class."""

        return sorted(self.collections.keys())

    def collection_counts(self) -> dict[str, int]:
        """Return a quick count of records per collection."""

        return {
            collection_name: collection.count()
            for collection_name, collection in self.collections.items()
        }

    def query_collection(
        self,
        collection_name: str,
        query_text: str,
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """Query one collection with the same deterministic embedding strategy used for inserts."""

        if collection_name not in self.collections:
            raise ValueError(f"Unknown collection: {collection_name}")

        # Embed the query text with the same builder-backed embedding logic.
        query_embedding = self.builder.embedding_provider(query_text)
        response = self.collections[collection_name].query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where or None,
            include=["documents", "metadatas", "distances"],
        )

        # Repackage the raw Chroma response into a friendlier list-of-dicts shape.
        ids = response.get("ids", [[]])[0]
        documents = response.get("documents", [[]])[0]
        metadatas = response.get("metadatas", [[]])[0]
        distances = response.get("distances", [[]])[0]

        results: list[dict] = []
        for index, node_id in enumerate(ids):
            distance = float(distances[index]) if index < len(distances) else 1.0
            results.append(
                {
                    "id": node_id,
                    "document": documents[index] if index < len(documents) else "",
                    "metadata": metadatas[index] if index < len(metadatas) else {},
                    "distance": distance,
                    "score": max(0.0, 1.0 - distance),
                }
            )

        return results

    def _upsert_nodes(self, collection_name: str, nodes: list[ChromaNode]) -> None:
        """Upsert nodes in safe batches so large documents stay under Chroma's batch ceiling."""

        if not nodes:
            return

        collection = self.collections[collection_name]
        batch_size = max(1, self.max_batch_size)

        for start in range(0, len(nodes), batch_size):
            batch = nodes[start : start + batch_size]
            collection.upsert(
                ids=[node.node_id for node in batch],
                documents=[node.document for node in batch],
                metadatas=[self._normalize_metadata(node.metadata) for node in batch],
                embeddings=[node.embedding for node in batch],
            )

    def _normalize_metadata(self, metadata: dict[str, str | int | float | bool]) -> dict[str, str | int | float | bool]:
        """Coerce metadata into Chroma-safe scalar values only."""

        normalized: dict[str, str | int | float | bool] = {}
        for key, value in metadata.items():
            if value is None:
                normalized[key] = ""
            elif isinstance(value, (str, int, float, bool)):
                normalized[key] = value
            else:
                normalized[key] = str(value)
        return normalized

    def _resolve_max_batch_size(self) -> int:
        """Read Chroma's advertised max batch size so large inserts do not fail mid-run."""

        if hasattr(self.client, "get_max_batch_size"):
            try:
                value = int(self.client.get_max_batch_size())
                if value > 0:
                    return value
            except Exception:
                pass
        return 5000
