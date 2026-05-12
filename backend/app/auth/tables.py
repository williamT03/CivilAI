"""SQLAlchemy table definitions for CivilAI authentication storage."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTH_DB_PATH = BACKEND_ROOT / "Data" / "civilai_auth.db"
DEFAULT_AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_AUTH_DB_PATH.as_posix()}")

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String(255), nullable=False, unique=True),
    Column("username", String(100), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("full_name", String(255), nullable=True),
    Column("jurisdiction", String(255), nullable=True),
    Column("is_active", Integer, nullable=False, default=1),
    Column("is_admin", Integer, nullable=False, default=0),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("last_login", DateTime, nullable=True),
)

refresh_tokens = Table(
    "refresh_tokens",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("token", String(511), nullable=False, unique=True),
    Column("expires_at", DateTime, nullable=False),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("revoked", Integer, nullable=False, default=0),
)

chat_threads = Table(
    "chat_threads",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("title", String(255), nullable=False),
    Column("jurisdiction", String(255), nullable=True),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)

chat_messages = Table(
    "chat_messages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("thread_id", Integer, nullable=False),
    Column("role", String(20), nullable=False),
    Column("content", Text, nullable=False),
    Column("accuracy_json", Text, nullable=True),
    Column("resolved_jurisdiction", String(255), nullable=True),
    Column("navigation_json", Text, nullable=True),
    Column("sources_json", Text, nullable=True),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
)

uploaded_documents = Table(
    "uploaded_documents",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("filename", String(255), nullable=False),
    Column("document_title", String(255), nullable=True),
    Column("stored_path", Text, nullable=False),
    Column("chapter_count", Integer, nullable=True),
    Column("section_count", Integer, nullable=True),
    Column("subsection_count", Integer, nullable=True),
    Column("replaced_existing", Integer, nullable=False, default=0),
    Column("uploaded_at", DateTime, nullable=False, default=datetime.utcnow),
)

api_keys = Table(
    "api_keys",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("name", String(255), nullable=False),
    Column("key_prefix", String(32), nullable=False),
    Column("key_hash", String(255), nullable=False, unique=True),
    Column("last_used_at", DateTime, nullable=True),
    Column("revoked", Integer, nullable=False, default=0),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
)

subscriptions = Table(
    "subscriptions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False, unique=True),
    Column("tier", String(64), nullable=False, default="free"),
    Column("status", String(64), nullable=False, default="active"),
    Column("monthly_token_limit", Integer, nullable=True),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)
