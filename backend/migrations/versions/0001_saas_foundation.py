"""saas foundation

Revision ID: 0001_saas_foundation
Revises:
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_saas_foundation"
down_revision = None
branch_labels = None
depends_on = None


def uuid_pk() -> sa.Column:
    return sa.Column("id", sa.String(36), primary_key=True)


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        uuid_pk(),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("jurisdiction", sa.String(255), nullable=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="standard_user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login", sa.DateTime(), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "documents",
        uuid_pk(),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("document_slug", sa.String(255), nullable=False),
        sa.Column("document_title", sa.String(511), nullable=False),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("visibility", sa.String(32), nullable=False, server_default="public"),
        sa.Column("municipality", sa.String(255), nullable=True),
        sa.Column("source_filename", sa.String(511), nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_documents_user_slug", "documents", ["user_id", "document_slug"])
    op.create_index("ix_documents_owner_visibility", "documents", ["owner_user_id", "visibility"])
    op.create_index("ix_documents_municipality", "documents", ["municipality"])

    op.create_table(
        "chapters",
        uuid_pk(),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("chapter_number", sa.String(100), nullable=False),
        sa.Column("chapter_name", sa.String(511), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        *timestamps(),
    )
    op.create_index("ix_chapters_document_position", "chapters", ["document_id", "position"])

    op.create_table(
        "sections",
        uuid_pk(),
        sa.Column("chapter_id", sa.String(36), sa.ForeignKey("chapters.id"), nullable=False),
        sa.Column("section_number", sa.String(100), nullable=False),
        sa.Column("section_summary", sa.Text(), nullable=True),
        sa.Column("section_text", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        *timestamps(),
    )
    op.create_index("ix_sections_chapter_number", "sections", ["chapter_id", "section_number"])

    op.create_table(
        "subsections",
        uuid_pk(),
        sa.Column("section_id", sa.String(36), sa.ForeignKey("sections.id"), nullable=False),
        sa.Column("subsection_number", sa.String(100), nullable=False),
        sa.Column("subsection_summary", sa.Text(), nullable=True),
        sa.Column("subsection_text", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        *timestamps(),
    )
    op.create_index("ix_subsections_section_number", "subsections", ["section_id", "subsection_number"])

    op.create_table(
        "uploads",
        uuid_pk(),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String(511), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False, server_default="application/pdf"),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="uploaded"),
        *timestamps(),
    )
    op.create_index("ix_uploads_user_status", "uploads", ["user_id", "status"])

    op.create_table(
        "chat_history",
        uuid_pk(),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("thread_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_history_user_thread", "chat_history", ["user_id", "thread_id"])

    op.create_table(
        "ingestion_jobs",
        uuid_pk(),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("upload_id", sa.String(36), sa.ForeignKey("uploads.id"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(64), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_ingestion_jobs_user_status", "ingestion_jobs", ["user_id", "status"])

    op.create_table(
        "ingestion_jobs_runtime",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("filename", sa.String(511), nullable=False),
        sa.Column("local_path", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(64), nullable=False, server_default="upload"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ingestion_jobs_runtime_user_status", "ingestion_jobs_runtime", ["user_id", "status"])

    op.create_table(
        "usage_logs",
        uuid_pk(),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("endpoint", sa.String(255), nullable=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_usage_logs_user_created", "usage_logs", ["user_id", "created_at"])
    op.create_index("ix_usage_logs_request", "usage_logs", ["request_id"])

    op.create_table(
        "subscriptions",
        uuid_pk(),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tier", sa.String(64), nullable=False, server_default="free"),
        sa.Column("status", sa.String(64), nullable=False, server_default="active"),
        sa.Column("monthly_token_limit", sa.Integer(), nullable=True),
        *timestamps(),
    )

    op.create_table(
        "api_keys",
        uuid_pk(),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_prefix", sa.String(32), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_api_keys_user", "api_keys", ["user_id"])

    op.create_table(
        "ai_provider_logs",
        uuid_pk(),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_provider_logs_request", "ai_provider_logs", ["request_id"])


def downgrade() -> None:
    for table_name in [
        "ai_provider_logs",
        "api_keys",
        "subscriptions",
        "usage_logs",
        "ingestion_jobs_runtime",
        "ingestion_jobs",
        "chat_history",
        "uploads",
        "subsections",
        "sections",
        "chapters",
        "documents",
        "users",
    ]:
        op.drop_table(table_name)
