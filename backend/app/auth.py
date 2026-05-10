"""
JWT Authentication Module for CivilAI Backend.

Provides secure user authentication with:
- User registration with hashed passwords
- JWT token-based login
- Token refresh capability
- Protected route validation
"""

from __future__ import annotations

import json
import os
import re
import secrets
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, validator
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    func,
    insert,
    select,
    update,
)

# =============================================================================
# Configuration
# =============================================================================

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTH_DB_PATH = BACKEND_ROOT / "Data" / "civilai_auth.db"
DEFAULT_AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = 30

DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_AUTH_DB_PATH.as_posix()}")

# =============================================================================
# Database Schema
# =============================================================================

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

# =============================================================================
# Pydantic Models
# =============================================================================


class UserCreate(BaseModel):
    """Schema for user registration."""

    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = None
    jurisdiction: Optional[str] = None

    @validator("username")
    def username_alphanumeric(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username must contain only letters, numbers, and underscores")
        return v

    @validator("password")
    def password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one number")
        return v


class UserResponse(BaseModel):
    """Schema for user response (without sensitive data)."""

    id: int
    email: str
    username: str
    full_name: Optional[str]
    jurisdiction: Optional[str]
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """Schema for updating an authenticated user's profile."""

    full_name: Optional[str] = Field(default=None, max_length=255)
    jurisdiction: Optional[str] = Field(default=None, max_length=255)


class Token(BaseModel):
    """Schema for authentication token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenPayload(BaseModel):
    """Schema for JWT token payload."""

    sub: str  # user_id:username
    exp: int
    type: str  # "access" or "refresh"


class ChatThreadCreate(BaseModel):
    """Schema for creating a new saved chat thread."""

    title: Optional[str] = Field(default=None, max_length=255)
    jurisdiction: Optional[str] = Field(default=None, max_length=255)


class ChatThreadResponse(BaseModel):
    """Summary view for a saved chat thread."""

    id: int
    title: str
    jurisdiction: Optional[str] = None
    preview: Optional[str] = None
    message_count: int
    created_at: datetime
    updated_at: datetime


class ChatUserMessageCreate(BaseModel):
    """User-side message payload for one saved chat turn."""

    content: str = Field(..., min_length=1)
    timestamp: Optional[datetime] = None


class ChatAssistantMessageCreate(BaseModel):
    """Assistant-side message payload for one saved chat turn."""

    content: str = Field(..., min_length=1)
    timestamp: Optional[datetime] = None
    accuracy: Optional[dict] = None
    resolved_jurisdiction: Optional[str] = None
    navigation: Optional[dict] = None
    sources: Optional[list[dict]] = None


class ChatTurnCreate(BaseModel):
    """Schema for persisting one full user/assistant exchange."""

    user_message: ChatUserMessageCreate
    assistant_message: ChatAssistantMessageCreate
    jurisdiction: Optional[str] = Field(default=None, max_length=255)


class ChatMessageResponse(BaseModel):
    """One persisted chat message row with optional assistant metadata."""

    id: int
    role: str
    content: str
    accuracy: Optional[dict] = None
    resolved_jurisdiction: Optional[str] = None
    navigation: Optional[dict] = None
    sources: Optional[list[dict]] = None
    created_at: datetime


class ChatThreadDetailResponse(BaseModel):
    """Full thread payload including all persisted messages."""

    thread: ChatThreadResponse
    messages: list[ChatMessageResponse]


class UploadedDocumentResponse(BaseModel):
    """One uploaded PDF recorded against a signed-in user."""

    id: int
    filename: str
    document_title: Optional[str] = None
    stored_path: str
    chapter_count: Optional[int] = None
    section_count: Optional[int] = None
    subsection_count: Optional[int] = None
    replaced_existing: bool
    uploaded_at: datetime


class ApiKeyCreate(BaseModel):
    """Request to create a user-scoped API key."""

    name: str = Field(..., min_length=1, max_length=255)


class ApiKeyResponse(BaseModel):
    """API key metadata. Secret is only present immediately after creation."""

    id: int
    name: str
    key_prefix: str
    api_key: Optional[str] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime


class SubscriptionResponse(BaseModel):
    """Current user's subscription and monthly token limit."""

    tier: str
    status: str
    monthly_token_limit: Optional[int] = None
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Database Manager
# =============================================================================


class AuthDatabase:
    """Manages user authentication data in the database."""

    def __init__(self, db_url: str = DB_URL) -> None:
        self.db_url = db_url
        self.engine = create_engine(db_url, future=True)
        metadata.create_all(self.engine)
        self._ensure_subscription_defaults()

    def close(self) -> None:
        """Release pooled DB connections, especially for SQLite on Windows."""

        self.engine.dispose()

    def create_user(self, user_data: UserCreate) -> UserResponse:
        """Create a new user with hashed password."""

        password_hash = bcrypt.hashpw(
            user_data.password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        with self.engine.begin() as connection:
            existing = connection.execute(
                select(users).where(
                    (users.c.email == user_data.email)
                    | (users.c.username == user_data.username)
                )
            ).first()

            if existing:
                if existing[1] == user_data.email:
                    raise ValueError("Email already registered")
                else:
                    raise ValueError("Username already taken")

            result = connection.execute(
                insert(users).values(
                    email=user_data.email,
                    username=user_data.username,
                    password_hash=password_hash,
                    full_name=user_data.full_name,
                    jurisdiction=user_data.jurisdiction,
                    is_active=1,
                    is_admin=0,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
            )

            user_id = result.inserted_primary_key[0]
            self._ensure_subscription_for_user(connection, user_id)

            row = connection.execute(
                select(users).where(users.c.id == user_id)
            ).first()

        return self._row_to_user_response(row)

    def authenticate_user(self, username: str, password: str) -> UserResponse:
        """Authenticate a user with username and password."""

        with self.engine.begin() as connection:
            row = connection.execute(
                select(users).where(users.c.username == username)
            ).first()

            if not row:
                raise ValueError("Invalid username or password")

            user_id, email, db_username, password_hash, full_name, jurisdiction, is_active, is_admin, created_at, updated_at, last_login = row

            if not bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8")):
                raise ValueError("Invalid username or password")

            if not is_active:
                raise ValueError("Account is disabled")

            connection.execute(
                update(users)
                .where(users.c.id == user_id)
                .values(last_login=datetime.utcnow())
            )

        return self._row_to_user_response(row)

    def get_user_by_id(self, user_id: int) -> Optional[UserResponse]:
        """Get user by ID."""

        with self.engine.begin() as connection:
            row = connection.execute(
                select(users).where(users.c.id == user_id)
            ).first()

            if row:
                return self._row_to_user_response(row)

        return None

    def get_user_by_username(self, username: str) -> Optional[UserResponse]:
        """Get user by username."""

        with self.engine.begin() as connection:
            row = connection.execute(
                select(users).where(users.c.username == username)
            ).first()

            if row:
                return self._row_to_user_response(row)

        return None

    def update_user(
        self,
        user_id: int,
        full_name: Optional[str] = None,
        jurisdiction: Optional[str] = None,
    ) -> UserResponse:
        """Update editable profile fields for one user."""

        update_values = {
            "updated_at": datetime.utcnow(),
        }

        # Only mutate the fields that were explicitly supplied by the caller.
        if full_name is not None:
            update_values["full_name"] = full_name or None
        if jurisdiction is not None:
            update_values["jurisdiction"] = jurisdiction or None

        with self.engine.begin() as connection:
            connection.execute(
                update(users)
                .where(users.c.id == user_id)
                .values(**update_values)
            )

            row = connection.execute(
                select(users).where(users.c.id == user_id)
            ).first()

        return self._row_to_user_response(row)

    def save_refresh_token(self, user_id: int, token: str, expires_at: datetime) -> None:
        """Save a refresh token to the database."""

        with self.engine.begin() as connection:
            connection.execute(
                insert(refresh_tokens).values(
                    user_id=user_id,
                    token=token,
                    expires_at=expires_at,
                    created_at=datetime.utcnow(),
                    revoked=0,
                )
            )

    def revoke_refresh_token(self, token: str) -> None:
        """Revoke a refresh token."""

        with self.engine.begin() as connection:
            connection.execute(
                update(refresh_tokens)
                .where(refresh_tokens.c.token == token)
                .values(revoked=1)
            )

    def get_valid_refresh_token(self, token: str) -> Optional[dict]:
        """Get a valid (non-revoked, non-expired) refresh token."""

        with self.engine.begin() as connection:
            row = connection.execute(
                select(refresh_tokens).where(
                    refresh_tokens.c.token == token,
                    refresh_tokens.c.revoked == 0,
                    refresh_tokens.c.expires_at > datetime.utcnow(),
                )
            ).first()

            if row:
                return {
                    "id": row[0],
                    "user_id": row[1],
                    "token": row[2],
                    "expires_at": row[3],
                }

        return None

    def cleanup_expired_tokens(self) -> None:
        """Remove expired refresh tokens."""

        with self.engine.begin() as connection:
            connection.execute(
                delete(refresh_tokens).where(
                    refresh_tokens.c.expires_at < datetime.utcnow()
                )
            )

    def create_chat_thread(
        self,
        user_id: int,
        title: Optional[str] = None,
        jurisdiction: Optional[str] = None,
    ) -> ChatThreadResponse:
        """Create an empty saved chat thread for one authenticated user."""

        now = datetime.utcnow()
        normalized_title = self._normalize_thread_title(title)

        with self.engine.begin() as connection:
            result = connection.execute(
                insert(chat_threads).values(
                    user_id=user_id,
                    title=normalized_title,
                    jurisdiction=jurisdiction or None,
                    created_at=now,
                    updated_at=now,
                )
            )
            thread_id = result.inserted_primary_key[0]
            thread_row = connection.execute(
                select(chat_threads).where(chat_threads.c.id == thread_id)
            ).mappings().first()

        if thread_row is None:
            raise ValueError("Thread could not be created.")

        return self._thread_row_to_response(thread_row, preview=None, message_count=0)

    def list_chat_threads(self, user_id: int) -> list[ChatThreadResponse]:
        """Return saved chat thread summaries for one authenticated user."""

        with self.engine.begin() as connection:
            thread_rows = connection.execute(
                select(chat_threads)
                .where(chat_threads.c.user_id == user_id)
                .order_by(chat_threads.c.updated_at.desc(), chat_threads.c.id.desc())
            ).mappings().all()

            thread_summaries: list[ChatThreadResponse] = []
            for thread_row in thread_rows:
                message_count = connection.execute(
                    select(func.count())
                    .select_from(chat_messages)
                    .where(chat_messages.c.thread_id == thread_row["id"])
                ).scalar_one()

                preview_row = connection.execute(
                    select(chat_messages.c.content)
                    .where(chat_messages.c.thread_id == thread_row["id"])
                    .order_by(chat_messages.c.created_at.desc(), chat_messages.c.id.desc())
                    .limit(1)
                ).first()

                thread_summaries.append(
                    self._thread_row_to_response(
                        thread_row,
                        preview=self._truncate_preview(preview_row[0] if preview_row else None),
                        message_count=int(message_count or 0),
                    )
                )

        return thread_summaries

    def get_chat_thread_detail(self, user_id: int, thread_id: int) -> Optional[ChatThreadDetailResponse]:
        """Return one saved chat thread plus all persisted messages."""

        with self.engine.begin() as connection:
            thread_row = connection.execute(
                select(chat_threads).where(
                    chat_threads.c.id == thread_id,
                    chat_threads.c.user_id == user_id,
                )
            ).mappings().first()

            if thread_row is None:
                return None

            message_rows = connection.execute(
                select(chat_messages)
                .where(chat_messages.c.thread_id == thread_id)
                .order_by(chat_messages.c.created_at.asc(), chat_messages.c.id.asc())
            ).mappings().all()

        messages = [self._message_row_to_response(message_row) for message_row in message_rows]
        preview = self._truncate_preview(messages[-1].content if messages else None)

        return ChatThreadDetailResponse(
            thread=self._thread_row_to_response(
                thread_row,
                preview=preview,
                message_count=len(messages),
            ),
            messages=messages,
        )

    def delete_chat_thread(self, user_id: int, thread_id: int) -> bool:
        """Delete one chat thread and its messages, scoped to the owning user."""

        with self.engine.begin() as connection:
            thread_row = connection.execute(
                select(chat_threads.c.id).where(
                    chat_threads.c.id == thread_id,
                    chat_threads.c.user_id == user_id,
                )
            ).first()

            if thread_row is None:
                return False

            connection.execute(delete(chat_messages).where(chat_messages.c.thread_id == thread_id))
            connection.execute(delete(chat_threads).where(chat_threads.c.id == thread_id))

        return True

    def save_chat_turn(self, user_id: int, thread_id: int, turn_data: ChatTurnCreate) -> ChatThreadResponse:
        """Persist one full user/assistant turn inside a saved chat thread."""

        now = datetime.utcnow()
        user_timestamp = turn_data.user_message.timestamp or now
        assistant_timestamp = turn_data.assistant_message.timestamp or now

        with self.engine.begin() as connection:
            thread_row = connection.execute(
                select(chat_threads).where(
                    chat_threads.c.id == thread_id,
                    chat_threads.c.user_id == user_id,
                )
            ).mappings().first()

            if thread_row is None:
                raise ValueError("Chat thread not found.")

            existing_message_count = connection.execute(
                select(func.count())
                .select_from(chat_messages)
                .where(chat_messages.c.thread_id == thread_id)
            ).scalar_one()

            connection.execute(
                insert(chat_messages).values(
                    thread_id=thread_id,
                    role="user",
                    content=turn_data.user_message.content.strip(),
                    accuracy_json=None,
                    resolved_jurisdiction=None,
                    navigation_json=None,
                    sources_json=None,
                    created_at=user_timestamp,
                )
            )

            connection.execute(
                insert(chat_messages).values(
                    thread_id=thread_id,
                    role="assistant",
                    content=turn_data.assistant_message.content.strip(),
                    accuracy_json=self._serialize_json(turn_data.assistant_message.accuracy),
                    resolved_jurisdiction=turn_data.assistant_message.resolved_jurisdiction,
                    navigation_json=self._serialize_json(turn_data.assistant_message.navigation),
                    sources_json=self._serialize_json(turn_data.assistant_message.sources),
                    created_at=assistant_timestamp,
                )
            )

            next_title = thread_row["title"]
            if int(existing_message_count or 0) == 0 or self._looks_like_default_thread_title(next_title):
                next_title = self._derive_thread_title(turn_data.user_message.content)

            next_jurisdiction = (
                turn_data.jurisdiction.strip()
                if turn_data.jurisdiction and turn_data.jurisdiction.strip()
                else thread_row.get("jurisdiction")
            )

            connection.execute(
                update(chat_threads)
                .where(chat_threads.c.id == thread_id)
                .values(
                    title=next_title,
                    jurisdiction=next_jurisdiction,
                    updated_at=max(user_timestamp, assistant_timestamp, now),
                )
            )

            updated_thread_row = connection.execute(
                select(chat_threads).where(chat_threads.c.id == thread_id)
            ).mappings().first()

        if updated_thread_row is None:
            raise ValueError("Chat thread could not be updated.")

        return self._thread_row_to_response(
            updated_thread_row,
            preview=self._truncate_preview(turn_data.assistant_message.content),
            message_count=int(existing_message_count or 0) + 2,
        )

    def record_uploaded_document(
        self,
        user_id: int,
        *,
        filename: str,
        document_title: Optional[str],
        stored_path: str,
        chapter_count: Optional[int] = None,
        section_count: Optional[int] = None,
        subsection_count: Optional[int] = None,
        replaced_existing: bool = False,
    ) -> UploadedDocumentResponse:
        """Create or refresh one uploaded-document record for a signed-in user."""

        now = datetime.utcnow()

        with self.engine.begin() as connection:
            existing_row = connection.execute(
                select(uploaded_documents).where(
                    uploaded_documents.c.user_id == user_id,
                    uploaded_documents.c.filename == filename,
                )
            ).mappings().first()

            if existing_row is None:
                result = connection.execute(
                    insert(uploaded_documents).values(
                        user_id=user_id,
                        filename=filename,
                        document_title=document_title or None,
                        stored_path=stored_path,
                        chapter_count=chapter_count,
                        section_count=section_count,
                        subsection_count=subsection_count,
                        replaced_existing=1 if replaced_existing else 0,
                        uploaded_at=now,
                    )
                )
                upload_id = result.inserted_primary_key[0]
            else:
                upload_id = existing_row["id"]
                connection.execute(
                    update(uploaded_documents)
                    .where(uploaded_documents.c.id == upload_id)
                    .values(
                        document_title=document_title or None,
                        stored_path=stored_path,
                        chapter_count=chapter_count,
                        section_count=section_count,
                        subsection_count=subsection_count,
                        replaced_existing=1 if replaced_existing else 0,
                        uploaded_at=now,
                    )
                )

            upload_row = connection.execute(
                select(uploaded_documents).where(uploaded_documents.c.id == upload_id)
            ).mappings().first()

        if upload_row is None:
            raise ValueError("Uploaded document could not be recorded.")

        return self._upload_row_to_response(upload_row)

    def list_uploaded_documents(self, user_id: int) -> list[UploadedDocumentResponse]:
        """Return the authenticated user's uploaded PDF records, newest first."""

        with self.engine.begin() as connection:
            rows = connection.execute(
                select(uploaded_documents)
                .where(uploaded_documents.c.user_id == user_id)
                .order_by(uploaded_documents.c.uploaded_at.desc(), uploaded_documents.c.id.desc())
            ).mappings().all()

        return [self._upload_row_to_response(row) for row in rows]

    def create_api_key(self, user_id: int, name: str) -> ApiKeyResponse:
        """Create and return one plaintext API key for the current user."""

        secret = f"civ_{secrets.token_urlsafe(32)}"
        key_hash = self._hash_api_key(secret)
        key_prefix = secret[:12]
        now = datetime.utcnow()

        with self.engine.begin() as connection:
            result = connection.execute(
                insert(api_keys).values(
                    user_id=user_id,
                    name=name.strip(),
                    key_prefix=key_prefix,
                    key_hash=key_hash,
                    revoked=0,
                    created_at=now,
                )
            )
            api_key_id = result.inserted_primary_key[0]
            row = connection.execute(select(api_keys).where(api_keys.c.id == api_key_id)).mappings().first()

        response = self._api_key_row_to_response(row)
        response.api_key = secret
        return response

    def list_api_keys(self, user_id: int) -> list[ApiKeyResponse]:
        """List non-revoked API keys for one user without exposing secrets."""

        with self.engine.begin() as connection:
            rows = connection.execute(
                select(api_keys)
                .where(api_keys.c.user_id == user_id, api_keys.c.revoked == 0)
                .order_by(api_keys.c.created_at.desc())
            ).mappings().all()

        return [self._api_key_row_to_response(row) for row in rows]

    def revoke_api_key(self, user_id: int, api_key_id: int) -> bool:
        """Revoke one API key owned by the user."""

        with self.engine.begin() as connection:
            row = connection.execute(
                select(api_keys.c.id).where(
                    api_keys.c.id == api_key_id,
                    api_keys.c.user_id == user_id,
                    api_keys.c.revoked == 0,
                )
            ).first()
            if row is None:
                return False
            connection.execute(
                update(api_keys)
                .where(api_keys.c.id == api_key_id)
                .values(revoked=1)
            )
        return True

    def authenticate_api_key(self, raw_api_key: str) -> Optional[UserResponse]:
        """Authenticate an API key and return its active owner."""

        if not raw_api_key:
            return None

        key_hash = self._hash_api_key(raw_api_key)
        with self.engine.begin() as connection:
            key_row = connection.execute(
                select(api_keys).where(
                    api_keys.c.key_hash == key_hash,
                    api_keys.c.revoked == 0,
                )
            ).mappings().first()
            if key_row is None:
                return None

            connection.execute(
                update(api_keys)
                .where(api_keys.c.id == key_row["id"])
                .values(last_used_at=datetime.utcnow())
            )

            user_row = connection.execute(select(users).where(users.c.id == key_row["user_id"])).first()

        if not user_row:
            return None
        user = self._row_to_user_response(user_row)
        return user if user.is_active else None

    def get_subscription(self, user_id: int) -> SubscriptionResponse:
        """Return or create the user's subscription row."""

        with self.engine.begin() as connection:
            self._ensure_subscription_for_user(connection, user_id)
            row = connection.execute(
                select(subscriptions).where(subscriptions.c.user_id == user_id)
            ).mappings().first()

        return self._subscription_row_to_response(row)

    def _ensure_subscription_defaults(self) -> None:
        with self.engine.begin() as connection:
            for row in connection.execute(select(users.c.id)).all():
                self._ensure_subscription_for_user(connection, int(row[0]))

    def _ensure_subscription_for_user(self, connection, user_id: int) -> None:
        existing = connection.execute(
            select(subscriptions.c.id).where(subscriptions.c.user_id == user_id)
        ).first()
        if existing:
            return
        connection.execute(
            insert(subscriptions).values(
                user_id=user_id,
                tier="free",
                status="active",
                monthly_token_limit=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )

    def _row_to_user_response(self, row) -> UserResponse:
        """Convert a database row to UserResponse."""

        return UserResponse(
            id=row[0],
            email=row[1],
            username=row[2],
            full_name=row[4],
            jurisdiction=row[5],
            is_active=bool(row[6]),
            is_admin=bool(row[7]),
            created_at=row[8],
            last_login=row[10],
        )

    def _thread_row_to_response(
        self,
        row: dict,
        preview: Optional[str],
        message_count: int,
    ) -> ChatThreadResponse:
        """Convert a raw thread row plus computed stats into the API summary shape."""

        return ChatThreadResponse(
            id=row["id"],
            title=row["title"],
            jurisdiction=row.get("jurisdiction"),
            preview=preview,
            message_count=message_count,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _message_row_to_response(self, row: dict) -> ChatMessageResponse:
        """Convert one persisted chat message into the API response shape."""

        return ChatMessageResponse(
            id=row["id"],
            role=row["role"],
            content=row["content"],
            accuracy=self._deserialize_json(row.get("accuracy_json")),
            resolved_jurisdiction=row.get("resolved_jurisdiction"),
            navigation=self._deserialize_json(row.get("navigation_json")),
            sources=self._deserialize_json(row.get("sources_json")),
            created_at=row["created_at"],
        )

    @staticmethod
    def _upload_row_to_response(row: dict) -> UploadedDocumentResponse:
        """Convert one uploaded-document row into the API response shape."""

        return UploadedDocumentResponse(
            id=row["id"],
            filename=row["filename"],
            document_title=row.get("document_title"),
            stored_path=row["stored_path"],
            chapter_count=row.get("chapter_count"),
            section_count=row.get("section_count"),
            subsection_count=row.get("subsection_count"),
            replaced_existing=bool(row.get("replaced_existing")),
            uploaded_at=row["uploaded_at"],
        )

    @staticmethod
    def _api_key_row_to_response(row: dict) -> ApiKeyResponse:
        return ApiKeyResponse(
            id=row["id"],
            name=row["name"],
            key_prefix=row["key_prefix"],
            api_key=None,
            last_used_at=row.get("last_used_at"),
            created_at=row["created_at"],
        )

    @staticmethod
    def _subscription_row_to_response(row: dict) -> SubscriptionResponse:
        return SubscriptionResponse(
            tier=row["tier"],
            status=row["status"],
            monthly_token_limit=row.get("monthly_token_limit"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _hash_api_key(raw_api_key: str) -> str:
        return hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_thread_title(title: Optional[str]) -> str:
        normalized = re.sub(r"\s+", " ", (title or "").strip())
        return normalized or "New Chat"

    @staticmethod
    def _looks_like_default_thread_title(title: Optional[str]) -> bool:
        return (title or "").strip().lower() in {"", "new chat", "untitled chat"}

    @staticmethod
    def _derive_thread_title(prompt: str) -> str:
        normalized = re.sub(r"\s+", " ", (prompt or "").strip())
        if not normalized:
            return "New Chat"
        if len(normalized) <= 72:
            return normalized
        return f"{normalized[:69].rstrip()}..."

    @staticmethod
    def _truncate_preview(content: Optional[str]) -> Optional[str]:
        normalized = re.sub(r"\s+", " ", (content or "").strip())
        if not normalized:
            return None
        if len(normalized) <= 120:
            return normalized
        return f"{normalized[:117].rstrip()}..."

    @staticmethod
    def _serialize_json(payload) -> Optional[str]:
        if payload in (None, "", [], {}):
            return None
        return json.dumps(payload)

    @staticmethod
    def _deserialize_json(payload: Optional[str]):
        if not payload:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None


# =============================================================================
# JWT Functions
# =============================================================================


def create_access_token(user: UserResponse) -> str:
    """Create a JWT access token."""

    now = datetime.utcnow()
    payload = {
        "sub": f"{user.id}:{user.username}",
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
        "type": "access",
        "is_admin": user.is_admin,
    }

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user: UserResponse) -> str:
    """Create a JWT refresh token."""

    token = secrets.token_urlsafe(32)

    now = datetime.utcnow()
    payload = {
        "sub": f"{user.id}:{user.username}",
        "exp": int((now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).timestamp()),
        "type": "refresh",
    }

    token_with_payload = f"{token}.{jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)}"

    return token_with_payload


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT token."""

    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def extract_user_id(token_payload: TokenPayload) -> int:
    """Extract user ID from token payload."""

    sub = token_payload.sub
    return int(sub.split(":")[0])


# =============================================================================
# FastAPI Router
# =============================================================================

router = APIRouter(prefix="/auth", tags=["authentication"])

auth_db = AuthDatabase()


def get_current_user(
    token: str = Depends(OAuth2PasswordBearer(auto_error=False, tokenUrl="/api/auth/login"))
) -> UserResponse:
    """Dependency to get the current authenticated user."""

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)

    if payload.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = extract_user_id(payload)
    user = auth_db.get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled",
        )

    return user


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserCreate):
    """Register a new user account."""

    try:
        user = auth_db.create_user(user_data)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login with username and password."""

    try:
        user = auth_db.authenticate_user(form_data.username, form_data.password)

        access_token = create_access_token(user)
        refresh_token = create_refresh_token(user)

        expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        auth_db.save_refresh_token(user.id, refresh_token, expires_at)

        auth_db.cleanup_expired_tokens()

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/refresh", response_model=Token)
def refresh(refresh_token: str = Query(..., description="Refresh token")):
    """Refresh an access token using a refresh token."""

    try:
        payload = jwt.decode(
            refresh_token.split(".")[1] if "." in refresh_token else refresh_token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        stored_token = auth_db.get_valid_refresh_token(refresh_token)
        if not stored_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked refresh token",
            )

        user = auth_db.get_user_by_id(stored_token["user_id"])
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or disabled",
            )

        access_token = create_access_token(user)
        new_refresh_token = create_refresh_token(user)

        expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        auth_db.save_refresh_token(user.id, new_refresh_token, expires_at)

        auth_db.revoke_refresh_token(refresh_token)

        return Token(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/logout")
def logout(refresh_token: Optional[str] = Query(None)):
    """Logout and revoke refresh token."""

    if refresh_token:
        auth_db.revoke_refresh_token(refresh_token)

    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: UserResponse = Depends(get_current_user)):
    """Get current user information."""

    return current_user


@router.put("/me", response_model=UserResponse)
def update_me(
    user_data: UserUpdate,
    current_user: UserResponse = Depends(get_current_user),
):
    """Update the current user's editable profile fields."""

    return auth_db.update_user(
        user_id=current_user.id,
        full_name=user_data.full_name,
        jurisdiction=user_data.jurisdiction,
    )


@router.get("/chats", response_model=list[ChatThreadResponse])
def list_saved_chats(current_user: UserResponse = Depends(get_current_user)):
    """List saved chat threads for the current authenticated user."""

    return auth_db.list_chat_threads(current_user.id)


@router.post("/chats", response_model=ChatThreadResponse, status_code=status.HTTP_201_CREATED)
def create_saved_chat(
    payload: ChatThreadCreate,
    current_user: UserResponse = Depends(get_current_user),
):
    """Create a new empty chat thread for the current authenticated user."""

    return auth_db.create_chat_thread(
        user_id=current_user.id,
        title=payload.title,
        jurisdiction=payload.jurisdiction,
    )


@router.get("/chats/{thread_id}", response_model=ChatThreadDetailResponse)
def get_saved_chat(thread_id: int, current_user: UserResponse = Depends(get_current_user)):
    """Fetch one saved chat thread and all of its persisted messages."""

    detail = auth_db.get_chat_thread_detail(current_user.id, thread_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat thread not found")
    return detail


@router.delete("/chats/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_chat(thread_id: int, current_user: UserResponse = Depends(get_current_user)):
    """Delete one saved chat thread owned by the current authenticated user."""

    deleted = auth_db.delete_chat_thread(current_user.id, thread_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat thread not found")
    return None


@router.post("/chats/{thread_id}/turns", response_model=ChatThreadResponse)
def save_chat_turn(
    thread_id: int,
    payload: ChatTurnCreate,
    current_user: UserResponse = Depends(get_current_user),
):
    """Persist one full user/assistant exchange into a saved chat thread."""

    try:
        return auth_db.save_chat_turn(
            user_id=current_user.id,
            thread_id=thread_id,
            turn_data=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/uploads", response_model=list[UploadedDocumentResponse])
def list_uploaded_documents(current_user: UserResponse = Depends(get_current_user)):
    """List uploaded ordinance PDFs that were recorded for the current user."""

    return auth_db.list_uploaded_documents(current_user.id)


@router.get("/subscription", response_model=SubscriptionResponse)
def get_subscription(current_user: UserResponse = Depends(get_current_user)):
    """Return the current user's subscription state."""

    return auth_db.get_subscription(current_user.id)


@router.get("/api-keys", response_model=list[ApiKeyResponse])
def list_api_keys(current_user: UserResponse = Depends(get_current_user)):
    """List active API keys for the current user."""

    return auth_db.list_api_keys(current_user.id)


@router.post("/api-keys", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: ApiKeyCreate,
    current_user: UserResponse = Depends(get_current_user),
):
    """Create a new API key. The secret is returned once."""

    return auth_db.create_api_key(current_user.id, payload.name)


@router.delete("/api-keys/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    api_key_id: int,
    current_user: UserResponse = Depends(get_current_user),
):
    """Revoke one API key owned by the current user."""

    if not auth_db.revoke_api_key(current_user.id, api_key_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return None
