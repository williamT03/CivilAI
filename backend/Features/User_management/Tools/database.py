"""Database access layer for users, saved chats, uploads, API keys, and subscriptions."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime
from typing import Optional

import bcrypt
from sqlalchemy import create_engine, delete, func, insert, select, update

from .schemas import (
    ApiKeyResponse,
    ChatThreadResponse,
    ChatTurnCreate,
    SubscriptionResponse,
    UploadedDocumentResponse,
    UserCreate,
    UserResponse,
)
from .tables import (
    DB_URL,
    api_keys,
    chat_messages,
    chat_threads,
    metadata,
    refresh_tokens,
    subscriptions,
    uploaded_documents,
    users,
)


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

        password_hash = bcrypt.hashpw(user_data.password.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

        with self.engine.begin() as connection:
            existing = connection.execute(
                select(users).where(
                    (users.c.email == user_data.email) | (users.c.username == user_data.username)
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

            row = connection.execute(select(users).where(users.c.id == user_id)).first()

        return self._row_to_user_response(row)

    def authenticate_user(self, username: str, password: str) -> UserResponse:
        """Authenticate a user with username and password."""

        with self.engine.begin() as connection:
            row = connection.execute(select(users).where(users.c.username == username)).first()

            if not row:
                raise ValueError("Invalid username or password")

            (
                user_id,
                email,
                db_username,
                password_hash,
                full_name,
                jurisdiction,
                is_active,
                is_admin,
                created_at,
                updated_at,
                last_login,
            ) = row

            if not bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8")):
                raise ValueError("Invalid username or password")

            if not is_active:
                raise ValueError("Account is disabled")

            connection.execute(
                update(users).where(users.c.id == user_id).values(last_login=datetime.utcnow())
            )

        return self._row_to_user_response(row)

    def get_user_by_id(self, user_id: int) -> Optional[UserResponse]:
        """Get user by ID."""

        with self.engine.begin() as connection:
            row = connection.execute(select(users).where(users.c.id == user_id)).first()

            if row:
                return self._row_to_user_response(row)

        return None

    def get_user_by_username(self, username: str) -> Optional[UserResponse]:
        """Get user by username."""

        with self.engine.begin() as connection:
            row = connection.execute(select(users).where(users.c.username == username)).first()

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
            connection.execute(update(users).where(users.c.id == user_id).values(**update_values))

            row = connection.execute(select(users).where(users.c.id == user_id)).first()

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
                update(refresh_tokens).where(refresh_tokens.c.token == token).values(revoked=1)
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
                delete(refresh_tokens).where(refresh_tokens.c.expires_at < datetime.utcnow())
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
            thread_row = (
                connection.execute(select(chat_threads).where(chat_threads.c.id == thread_id))
                .mappings()
                .first()
            )

        if thread_row is None:
            raise ValueError("Thread could not be created.")

        return self._thread_row_to_response(thread_row, preview=None, message_count=0)

    def list_chat_threads(self, user_id: int) -> list[ChatThreadResponse]:
        """Return saved chat thread summaries for one authenticated user."""

        with self.engine.begin() as connection:
            thread_rows = (
                connection.execute(
                    select(chat_threads)
                    .where(chat_threads.c.user_id == user_id)
                    .order_by(chat_threads.c.updated_at.desc(), chat_threads.c.id.desc())
                )
                .mappings()
                .all()
            )

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

    def get_chat_thread_detail(
        self, user_id: int, thread_id: int
    ) -> Optional[ChatThreadDetailResponse]:
        """Return one saved chat thread plus all persisted messages."""

        with self.engine.begin() as connection:
            thread_row = (
                connection.execute(
                    select(chat_threads).where(
                        chat_threads.c.id == thread_id,
                        chat_threads.c.user_id == user_id,
                    )
                )
                .mappings()
                .first()
            )

            if thread_row is None:
                return None

            message_rows = (
                connection.execute(
                    select(chat_messages)
                    .where(chat_messages.c.thread_id == thread_id)
                    .order_by(chat_messages.c.created_at.asc(), chat_messages.c.id.asc())
                )
                .mappings()
                .all()
            )

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

    def save_chat_turn(
        self, user_id: int, thread_id: int, turn_data: ChatTurnCreate
    ) -> ChatThreadResponse:
        """Persist one full user/assistant turn inside a saved chat thread."""

        now = datetime.utcnow()
        user_timestamp = turn_data.user_message.timestamp or now
        assistant_timestamp = turn_data.assistant_message.timestamp or now

        with self.engine.begin() as connection:
            thread_row = (
                connection.execute(
                    select(chat_threads).where(
                        chat_threads.c.id == thread_id,
                        chat_threads.c.user_id == user_id,
                    )
                )
                .mappings()
                .first()
            )

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
            if int(existing_message_count or 0) == 0 or self._looks_like_default_thread_title(
                next_title
            ):
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

            updated_thread_row = (
                connection.execute(select(chat_threads).where(chat_threads.c.id == thread_id))
                .mappings()
                .first()
            )

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
            existing_row = (
                connection.execute(
                    select(uploaded_documents).where(
                        uploaded_documents.c.user_id == user_id,
                        uploaded_documents.c.filename == filename,
                    )
                )
                .mappings()
                .first()
            )

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

            upload_row = (
                connection.execute(
                    select(uploaded_documents).where(uploaded_documents.c.id == upload_id)
                )
                .mappings()
                .first()
            )

        if upload_row is None:
            raise ValueError("Uploaded document could not be recorded.")

        return self._upload_row_to_response(upload_row)

    def list_uploaded_documents(self, user_id: int) -> list[UploadedDocumentResponse]:
        """Return the authenticated user's uploaded PDF records, newest first."""

        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    select(uploaded_documents)
                    .where(uploaded_documents.c.user_id == user_id)
                    .order_by(
                        uploaded_documents.c.uploaded_at.desc(), uploaded_documents.c.id.desc()
                    )
                )
                .mappings()
                .all()
            )

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
            row = (
                connection.execute(select(api_keys).where(api_keys.c.id == api_key_id))
                .mappings()
                .first()
            )

        response = self._api_key_row_to_response(row)
        response.api_key = secret
        return response

    def list_api_keys(self, user_id: int) -> list[ApiKeyResponse]:
        """List non-revoked API keys for one user without exposing secrets."""

        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    select(api_keys)
                    .where(api_keys.c.user_id == user_id, api_keys.c.revoked == 0)
                    .order_by(api_keys.c.created_at.desc())
                )
                .mappings()
                .all()
            )

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
                update(api_keys).where(api_keys.c.id == api_key_id).values(revoked=1)
            )
        return True

    def authenticate_api_key(self, raw_api_key: str) -> Optional[UserResponse]:
        """Authenticate an API key and return its active owner."""

        if not raw_api_key:
            return None

        key_hash = self._hash_api_key(raw_api_key)
        with self.engine.begin() as connection:
            key_row = (
                connection.execute(
                    select(api_keys).where(
                        api_keys.c.key_hash == key_hash,
                        api_keys.c.revoked == 0,
                    )
                )
                .mappings()
                .first()
            )
            if key_row is None:
                return None

            connection.execute(
                update(api_keys)
                .where(api_keys.c.id == key_row["id"])
                .values(last_used_at=datetime.utcnow())
            )

            user_row = connection.execute(
                select(users).where(users.c.id == key_row["user_id"])
            ).first()

        if not user_row:
            return None
        user = self._row_to_user_response(user_row)
        return user if user.is_active else None

    def get_subscription(self, user_id: int) -> SubscriptionResponse:
        """Return or create the user's subscription row."""

        with self.engine.begin() as connection:
            self._ensure_subscription_for_user(connection, user_id)
            row = (
                connection.execute(select(subscriptions).where(subscriptions.c.user_id == user_id))
                .mappings()
                .first()
            )

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
