from __future__ import annotations

# Standard library imports keep the module dependency-light and easy to test.
import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

# Pandas is still useful as a read convenience layer for inspection/debugging.
import pandas as pd

# SQLAlchemy Core gives us a clean, explicit schema definition without requiring ORM models.
import sqlalchemy
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    insert,
    select,
    text,
)


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------
# These immutable-ish dataclasses represent the *logical* hierarchy of a parsed
# ordinance document. They are the in-memory shape that the parser/builder will
# hand to the database manager before anything is persisted.


@dataclass(slots=True)
class SubsectionDefinition:
    # The subsection label as it appears in the code, for example "(a)".
    subsection_number: str
    # A generated or human-authored summary for that subsection.
    subsection_summary: str = ""
    # The exact parsed text that belongs to this subsection.
    subsection_text: str = ""


@dataclass(slots=True)
class SectionDefinition:
    # The full section identifier, for example "Sec. 20-1".
    section_number: str
    # The number of subsections expected under this section.
    subsection_count: int = 0
    # A generated or human-authored section summary.
    section_summary: str = ""
    # The exact parsed text for the section body outside subsection granularity.
    section_text: str = ""
    # The subsection rows that belong to this section.
    subsections: list[SubsectionDefinition] = field(default_factory=list)


@dataclass(slots=True)
class ChapterDefinition:
    # The chapter number as it appears in the code, for example "20".
    chapter_number: str
    # The chapter name/title.
    chapter_name: str
    # The page where the chapter appears in the table of contents.
    toc_page: int | None = None
    # The expected number of sections in the chapter.
    section_count: int = 0
    # The section rows that belong to this chapter.
    sections: list[SectionDefinition] = field(default_factory=list)


@dataclass(slots=True)
class DocumentDefinition:
    # The human title of the document, for example "Cooper City, FL Code of Ordinances".
    document_title: str
    # A normalized key we can safely index and query by.
    document_slug: str
    # Optional original filename so uploads/parsers can preserve provenance.
    source_filename: str | None = None
    # The chapter rows that belong to this document.
    chapters: list[ChapterDefinition] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------
# The builder pattern is a good fit here because the parser will likely discover
# a document incrementally: document -> chapters -> sections -> subsections.
# This builder also gives us a single place to normalize raw dictionaries into
# strongly structured dataclasses before we ever touch the database.


class DocumentSchemaBuilder:
    """Build a normalized document hierarchy from parser-friendly nested payloads."""

    def __init__(self) -> None:
        # The builder starts empty and accumulates chapter/section/subsection nodes.
        self._document_title: str | None = None
        self._document_slug: str | None = None
        self._source_filename: str | None = None
        self._chapters: list[ChapterDefinition] = []

    def set_document(self, document_title: str, source_filename: str | None = None) -> "DocumentSchemaBuilder":
        # Store the root document metadata once so every child node rolls up under it.
        self._document_title = document_title.strip()
        self._document_slug = DatabaseManager.make_slug(document_title)
        self._source_filename = source_filename
        return self

    def add_chapter(
        self,
        chapter_number: str,
        chapter_name: str,
        toc_page: int | None = None,
        section_count: int = 0,
        sections: Sequence[SectionDefinition] | None = None,
    ) -> "DocumentSchemaBuilder":
        # Create one chapter node and attach any prebuilt section nodes to it.
        chapter = ChapterDefinition(
            chapter_number=str(chapter_number),
            chapter_name=(chapter_name or "").strip(),
            toc_page=toc_page,
            section_count=int(section_count),
            sections=list(sections or []),
        )
        self._chapters.append(chapter)
        return self

    def from_nested_payload(
        self,
        document_title: str,
        chapters: Iterable[dict],
        source_filename: str | None = None,
    ) -> "DocumentSchemaBuilder":
        # Reset the document context so one builder instance can be reused cleanly.
        self._document_title = None
        self._document_slug = None
        self._source_filename = None
        self._chapters = []

        # Seed the root document node first.
        self.set_document(document_title=document_title, source_filename=source_filename)

        # Walk the nested parser payload and normalize it into dataclasses.
        for raw_chapter in chapters:
            sections: list[SectionDefinition] = []

            for raw_section in raw_chapter.get("sections", []):
                subsections = [
                    SubsectionDefinition(
                        subsection_number=str(raw_subsection["subsection_number"]),
                        subsection_summary=raw_subsection.get("subsection_summary", ""),
                        subsection_text=raw_subsection.get("subsection_text", ""),
                    )
                    for raw_subsection in raw_section.get("subsections", [])
                ]

                sections.append(
                    SectionDefinition(
                        section_number=str(raw_section["section_number"]),
                        subsection_count=int(raw_section.get("subsection_count", len(subsections))),
                        section_summary=raw_section.get("section_summary", ""),
                        section_text=raw_section.get("section_text", ""),
                        subsections=subsections,
                    )
                )

            self.add_chapter(
                chapter_number=str(raw_chapter["chapter_number"]),
                chapter_name=raw_chapter.get("chapter_name", ""),
                toc_page=raw_chapter.get("toc_page"),
                section_count=int(raw_chapter.get("section_count", len(sections))),
                sections=sections,
            )

        return self

    def build(self) -> DocumentDefinition:
        # Refuse to build an incomplete document because downstream persistence
        # should never have to guess whether the root metadata exists.
        if not self._document_title or not self._document_slug:
            raise ValueError("Document title must be set before build().")

        # If the caller omitted counts, we derive them here so the persisted rows
        # always reflect the actual child collections.
        finalized_chapters: list[ChapterDefinition] = []
        for chapter in self._chapters:
            finalized_sections: list[SectionDefinition] = []
            for section in chapter.sections:
                finalized_sections.append(
                    SectionDefinition(
                        section_number=section.section_number,
                        subsection_count=section.subsection_count or len(section.subsections),
                        section_summary=section.section_summary,
                        section_text=section.section_text,
                        subsections=[
                            SubsectionDefinition(
                                subsection_number=subsection.subsection_number,
                                subsection_summary=subsection.subsection_summary,
                                subsection_text=subsection.subsection_text,
                            )
                            for subsection in section.subsections
                        ],
                    )
                )

            finalized_chapters.append(
                ChapterDefinition(
                    chapter_number=chapter.chapter_number,
                    chapter_name=chapter.chapter_name,
                    toc_page=chapter.toc_page,
                    section_count=chapter.section_count or len(finalized_sections),
                    sections=finalized_sections,
                )
            )

        return DocumentDefinition(
            document_title=self._document_title,
            document_slug=self._document_slug,
            source_filename=self._source_filename,
            chapters=finalized_chapters,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
# The factory owns the *physical* relational schema. This is intentionally
# separate from the builder so we do not mix parsing/build concerns with SQL
# table construction concerns.


class RelationalSchemaFactory:
    """Create the fixed relational tables used by the normalized storage model."""

    @staticmethod
    def build(metadata: MetaData) -> dict[str, Table]:
        # The documents table is the root lookup table. One row = one uploaded PDF.
        documents = Table(
            "documents",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("document_title", String(255), nullable=False),
            Column("document_slug", String(255), nullable=False, unique=True),
            Column("source_filename", String(255), nullable=True),
        )

        # The chapters table hangs off documents and stores the top-level TOC view.
        chapters = Table(
            "chapters",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("document_id", Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
            Column("chapter_number", String(100), nullable=False),
            Column("chapter_name", String(255), nullable=False),
            Column("toc_page", Integer, nullable=True),
            Column("section_count", Integer, nullable=False, default=0),
            UniqueConstraint("document_id", "chapter_number", name="uq_chapters_document_number"),
        )

        # The sections table stores one row per section and points back to its chapter.
        sections = Table(
            "sections",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("chapter_id", Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False),
            Column("section_number", String(150), nullable=False),
            Column("subsection_count", Integer, nullable=False, default=0),
            Column("section_summary", Text, nullable=True),
            Column("section_text", Text, nullable=True),
            UniqueConstraint("chapter_id", "section_number", name="uq_sections_chapter_number"),
        )

        # The subsections table stores the most granular structural rows in this first pass.
        subsections = Table(
            "subsections",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("section_id", Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False),
            Column("subsection_number", String(150), nullable=False),
            Column("subsection_summary", Text, nullable=True),
            Column("subsection_text", Text, nullable=True),
            UniqueConstraint("section_id", "subsection_number", name="uq_subsections_section_number"),
        )

        return {
            "documents": documents,
            "chapters": chapters,
            "sections": sections,
            "subsections": subsections,
        }


# ---------------------------------------------------------------------------
# Database manager
# ---------------------------------------------------------------------------
# This class is the single entry point callers should use. It knows how to:
# 1. build/open the fixed schema,
# 2. persist one document hierarchy at a time,
# 3. replace a document cleanly when a PDF is re-parsed,
# 4. fetch helpful inspection views.


class DatabaseManager:
    """Persist ordinance structure into a normalized relational database."""

    def __init__(self, db_url: str = "sqlite:///civilai.db") -> None:
        # Store the connection string mostly for debugging and downstream reuse.
        self.db_url = db_url

        # `future=True` keeps us on the modern SQLAlchemy execution model.
        self.engine = create_engine(db_url, future=True)

        # Metadata holds the in-memory description of the fixed relational schema.
        self.metadata = MetaData()

        # The factory returns the four physical tables we use everywhere else.
        self.tables = RelationalSchemaFactory.build(self.metadata)

        # Ensure the database actually contains those tables.
        self.create_core_schema()

    def create_core_schema(self) -> None:
        """Create the normalized base tables if they do not already exist."""

        # This is idempotent, so calling it repeatedly is safe.
        self.metadata.create_all(self.engine)

    def close(self) -> None:
        """Release pooled DB connections, which is especially important for SQLite on Windows."""

        self.engine.dispose()

    def read_query(self, query: str, params: dict | None = None) -> pd.DataFrame:
        """Run an arbitrary read query and return the result as a DataFrame."""

        return pd.read_sql(text(query), self.engine, params=params)

    def build_document_blueprint(
        self,
        document_title: str,
        chapters: Iterable[dict],
        source_filename: str | None = None,
    ) -> DocumentDefinition:
        """Normalize a raw nested parser payload into a validated document blueprint."""

        return (
            DocumentSchemaBuilder()
            .from_nested_payload(
                document_title=document_title,
                chapters=chapters,
                source_filename=source_filename,
            )
            .build()
        )

    def create_document_schema(
        self,
        document_title: str,
        chapters: Iterable[dict],
        replace_existing: bool = True,
        source_filename: str | None = None,
    ) -> dict:
        """
        Persist one document hierarchy into the normalized schema.

        This method keeps the old external API name for convenience, but under the
        hood it now writes into fixed tables instead of creating one SQL table per
        document/chapter/section.
        """

        # Build one clean, validated hierarchy object from the raw nested payload.
        blueprint = self.build_document_blueprint(
            document_title=document_title,
            chapters=chapters,
            source_filename=source_filename,
        )

        return self.persist_document_blueprint(blueprint, replace_existing=replace_existing)

    def persist_document_blueprint(
        self,
        blueprint: DocumentDefinition,
        replace_existing: bool = True,
    ) -> dict:
        """Persist a prebuilt document blueprint into the normalized schema."""

        # If we are replacing the document, remove its existing hierarchy first.
        if replace_existing:
            self.drop_document_schema(blueprint.document_title)

        documents = self.tables["documents"]
        chapters_table = self.tables["chapters"]
        sections_table = self.tables["sections"]
        subsections_table = self.tables["subsections"]

        with self.engine.begin() as connection:
            # Insert the root document row first so child tables can reference it.
            document_id = connection.execute(
                insert(documents).values(
                    document_title=blueprint.document_title,
                    document_slug=blueprint.document_slug,
                    source_filename=blueprint.source_filename,
                )
            ).inserted_primary_key[0]

            # Insert each chapter, then each section, then each subsection in order.
            for chapter in blueprint.chapters:
                chapter_id = connection.execute(
                    insert(chapters_table).values(
                        document_id=document_id,
                        chapter_number=chapter.chapter_number,
                        chapter_name=chapter.chapter_name,
                        toc_page=chapter.toc_page,
                        section_count=chapter.section_count,
                    )
                ).inserted_primary_key[0]

                for section in chapter.sections:
                    section_id = connection.execute(
                        insert(sections_table).values(
                            chapter_id=chapter_id,
                            section_number=section.section_number,
                            subsection_count=section.subsection_count,
                            section_summary=section.section_summary,
                            section_text=section.section_text,
                        )
                    ).inserted_primary_key[0]

                    for subsection in section.subsections:
                        connection.execute(
                            insert(subsections_table).values(
                                section_id=section_id,
                                subsection_number=subsection.subsection_number,
                                subsection_summary=subsection.subsection_summary,
                                subsection_text=subsection.subsection_text,
                            )
                        )

        # Return IDs/names that are handy to the caller for logging or follow-up work.
        return {
            "document_title": blueprint.document_title,
            "document_slug": blueprint.document_slug,
            "chapter_count": len(blueprint.chapters),
            "section_count": sum(len(chapter.sections) for chapter in blueprint.chapters),
            "subsection_count": sum(
                len(section.subsections)
                for chapter in blueprint.chapters
                for section in chapter.sections
            ),
        }

    def drop_document_schema(self, document_title_or_slug: str) -> None:
        """Delete one document and let cascading foreign keys remove its children."""

        documents = self.tables["documents"]
        document_slug = self.make_slug(document_title_or_slug)

        with self.engine.begin() as connection:
            # We match on either the exact title or the normalized slug so callers can use whichever is easier.
            connection.execute(
                delete(documents).where(
                    (documents.c.document_title == document_title_or_slug)
                    | (documents.c.document_slug == document_slug)
                )
            )

    def fetch_document_hierarchy(self, document_title_or_slug: str) -> dict | None:
        """Return one document as a nested dictionary for debugging or API responses."""

        documents = self.tables["documents"]
        chapters = self.tables["chapters"]
        sections = self.tables["sections"]
        subsections = self.tables["subsections"]
        document_slug = self.make_slug(document_title_or_slug)

        with self.engine.begin() as connection:
            # Resolve the root document row first.
            document_row = connection.execute(
                select(documents).where(
                    (documents.c.document_title == document_title_or_slug)
                    | (documents.c.document_slug == document_slug)
                )
            ).mappings().first()

            if document_row is None:
                return None

            # Fetch all chapters under the document in chapter-number order.
            chapter_rows = connection.execute(
                select(chapters)
                .where(chapters.c.document_id == document_row["id"])
                .order_by(chapters.c.id)
            ).mappings().all()

            chapter_payloads: list[dict] = []
            for chapter_row in chapter_rows:
                # Fetch all sections under the chapter before moving on.
                section_rows = connection.execute(
                    select(sections)
                    .where(sections.c.chapter_id == chapter_row["id"])
                    .order_by(sections.c.id)
                ).mappings().all()

                section_payloads: list[dict] = []
                for section_row in section_rows:
                    # Fetch all subsections for the section to complete the hierarchy.
                    subsection_rows = connection.execute(
                        select(subsections)
                        .where(subsections.c.section_id == section_row["id"])
                        .order_by(subsections.c.id)
                    ).mappings().all()

                    section_payloads.append(
                        {
                            "section_number": section_row["section_number"],
                            "subsection_count": section_row["subsection_count"],
                            "section_summary": section_row["section_summary"],
                            "section_text": section_row["section_text"],
                            "subsections": [
                                {
                                    "subsection_number": subsection_row["subsection_number"],
                                    "subsection_summary": subsection_row["subsection_summary"],
                                    "subsection_text": subsection_row["subsection_text"],
                                }
                                for subsection_row in subsection_rows
                            ],
                        }
                    )

                chapter_payloads.append(
                    {
                        "chapter_number": chapter_row["chapter_number"],
                        "chapter_name": chapter_row["chapter_name"],
                        "toc_page": chapter_row["toc_page"],
                        "section_count": chapter_row["section_count"],
                        "sections": section_payloads,
                    }
                )

        return {
            "document_title": document_row["document_title"],
            "document_slug": document_row["document_slug"],
            "source_filename": document_row["source_filename"],
            "chapters": chapter_payloads,
        }

    def list_documents(self) -> list[dict]:
        """Return a compact list of documents currently stored in the database."""

        documents = self.tables["documents"]
        chapters = self.tables["chapters"]

        with self.engine.begin() as connection:
            # Join chapters so we can expose a quick chapter count per stored document.
            rows = connection.execute(
                select(
                    documents.c.document_title,
                    documents.c.document_slug,
                    documents.c.source_filename,
                    sqlalchemy.func.count(chapters.c.id).label("chapter_count"),
                )
                .select_from(documents.outerjoin(chapters, chapters.c.document_id == documents.c.id))
                .group_by(documents.c.id)
                .order_by(documents.c.document_title)
            ).mappings().all()

        return [dict(row) for row in rows]

    def resolve_document(self, document_title_or_slug: str) -> dict | None:
        """Resolve one stored document row from either its human title or its slug."""

        documents = self.tables["documents"]
        document_slug = self.make_slug(document_title_or_slug)

        with self.engine.begin() as connection:
            # Accept either the original title or the normalized slug so callers
            # do not need to care which representation they currently have.
            row = connection.execute(
                select(documents).where(
                    (documents.c.document_title == document_title_or_slug)
                    | (documents.c.document_slug == document_slug)
                )
            ).mappings().first()

        return dict(row) if row is not None else None

    def find_sections(
        self,
        document_title_or_slug: str,
        section_numbers: Sequence[str] | None = None,
        chapter_number: str | None = None,
    ) -> list[dict]:
        """Return section rows joined with their document and chapter context."""

        document_row = self.resolve_document(document_title_or_slug)
        if document_row is None:
            return []

        documents = self.tables["documents"]
        chapters = self.tables["chapters"]
        sections = self.tables["sections"]
        subsections = self.tables["subsections"]

        normalized_section_numbers = [
            str(section_number).strip()
            for section_number in (section_numbers or [])
            if str(section_number).strip()
        ]

        with self.engine.begin() as connection:
            # Build one joined section query so every row already carries the
            # chapter and document labels the retrieval layer needs later.
            section_query = (
                select(
                    documents.c.document_title,
                    documents.c.document_slug,
                    documents.c.source_filename,
                    chapters.c.id.label("chapter_id"),
                    chapters.c.chapter_number,
                    chapters.c.chapter_name,
                    chapters.c.toc_page,
                    sections.c.id.label("section_id"),
                    sections.c.section_number,
                    sections.c.subsection_count,
                    sections.c.section_summary,
                    sections.c.section_text,
                )
                .select_from(
                    sections.join(chapters, sections.c.chapter_id == chapters.c.id).join(
                        documents, chapters.c.document_id == documents.c.id
                    )
                )
                .where(documents.c.id == document_row["id"])
                .order_by(chapters.c.id, sections.c.id)
            )

            if chapter_number:
                section_query = section_query.where(chapters.c.chapter_number == str(chapter_number).strip())

            if normalized_section_numbers:
                section_query = section_query.where(sections.c.section_number.in_(normalized_section_numbers))

            section_rows = connection.execute(section_query).mappings().all()

            payloads: list[dict] = []
            for section_row in section_rows:
                # Subsections are fetched per section so the caller gets a ready-
                # to-use nested payload without having to perform extra joins.
                subsection_rows = connection.execute(
                    select(
                        subsections.c.subsection_number,
                        subsections.c.subsection_summary,
                        subsections.c.subsection_text,
                    )
                    .where(subsections.c.section_id == section_row["section_id"])
                    .order_by(subsections.c.id)
                ).mappings().all()

                payloads.append(
                    {
                        "document_title": section_row["document_title"],
                        "document_slug": section_row["document_slug"],
                        "source_filename": section_row["source_filename"],
                        "chapter_number": section_row["chapter_number"],
                        "chapter_name": section_row["chapter_name"],
                        "toc_page": section_row["toc_page"],
                        "section_id": section_row["section_id"],
                        "section_number": section_row["section_number"],
                        "subsection_count": section_row["subsection_count"],
                        "section_summary": section_row["section_summary"],
                        "section_text": section_row["section_text"],
                        "subsections": [dict(subsection_row) for subsection_row in subsection_rows],
                    }
                )

        return payloads

    def find_subsections(
        self,
        document_title_or_slug: str,
        section_number: str,
        subsection_numbers: Sequence[str] | None = None,
    ) -> list[dict]:
        """Return subsection rows joined with their parent section, chapter, and document."""

        document_row = self.resolve_document(document_title_or_slug)
        if document_row is None:
            return []

        documents = self.tables["documents"]
        chapters = self.tables["chapters"]
        sections = self.tables["sections"]
        subsections = self.tables["subsections"]

        normalized_subsection_numbers = [
            str(subsection_number).strip().lower()
            for subsection_number in (subsection_numbers or [])
            if str(subsection_number).strip()
        ]

        with self.engine.begin() as connection:
            subsection_query = (
                select(
                    documents.c.document_title,
                    documents.c.document_slug,
                    documents.c.source_filename,
                    chapters.c.chapter_number,
                    chapters.c.chapter_name,
                    chapters.c.toc_page,
                    sections.c.section_number,
                    sections.c.section_summary,
                    sections.c.section_text,
                    subsections.c.subsection_number,
                    subsections.c.subsection_summary,
                    subsections.c.subsection_text,
                )
                .select_from(
                    subsections.join(sections, subsections.c.section_id == sections.c.id)
                    .join(chapters, sections.c.chapter_id == chapters.c.id)
                    .join(documents, chapters.c.document_id == documents.c.id)
                )
                .where(
                    documents.c.id == document_row["id"],
                    sections.c.section_number == str(section_number).strip(),
                )
                .order_by(subsections.c.id)
            )

            if normalized_subsection_numbers:
                subsection_query = subsection_query.where(
                    sqlalchemy.func.lower(subsections.c.subsection_number).in_(normalized_subsection_numbers)
                )

            subsection_rows = connection.execute(subsection_query).mappings().all()

        return [dict(subsection_row) for subsection_row in subsection_rows]

    def list_sections_for_chapter(self, document_title_or_slug: str, chapter_number: str) -> list[dict]:
        """Return every section stored under one chapter number for a document."""

        return self.find_sections(
            document_title_or_slug=document_title_or_slug,
            chapter_number=chapter_number,
        )

    def list_tables(self) -> list[str]:
        """Return the physical SQL tables that exist in the current database."""

        return sorted(sqlalchemy.inspect(self.engine).get_table_names())

    @staticmethod
    def make_slug(raw_value: str) -> str:
        """Normalize a free-text title into a stable document slug."""

        value = raw_value.strip().lower()
        value = re.sub(r"[^a-z0-9]+", "_", value)
        value = value.strip("_")
        return value or "untitled_document"
