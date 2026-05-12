"""Pydantic schemas for CivilAI authentication, chat persistence, and API keys."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, validator


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
