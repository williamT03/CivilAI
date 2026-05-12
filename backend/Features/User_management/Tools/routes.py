"""FastAPI routes and dependencies for authentication and account data."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

try:
    from backend.Features.Runtime_management.Tools.security import audit_event
except ImportError:  # pragma: no cover
    from backend.Features.Runtime_management.Tools.security import audit_event

from .database import AuthDatabase
from .models import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_token,
    extract_user_id,
)
from .schemas import (
    ApiKeyCreate,
    ApiKeyResponse,
    ChatThreadCreate,
    ChatThreadDetailResponse,
    ChatThreadResponse,
    ChatTurnCreate,
    SubscriptionResponse,
    Token,
    UploadedDocumentResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)

auth_db = AuthDatabase()

router = APIRouter(prefix="/auth", tags=["authentication"])


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
        audit_event("auth.register.success", user_id=user.id, username=user.username)
        return user
    except ValueError as e:
        audit_event("auth.register.failure", username=user_data.username, reason=str(e))
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

        audit_event("auth.login.success", user_id=user.id, username=user.username)
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    except ValueError as e:
        audit_event("auth.login.failure", username=form_data.username, reason=str(e))
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
        audit_event("auth.refresh.success", user_id=user.id)

        return Token(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    except jwt.InvalidTokenError:
        audit_event("auth.refresh.failure", reason="invalid_token")
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
    audit_event("auth.logout")

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

    audit_event("auth.profile.update", user_id=current_user.id)
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

    audit_event("chat.thread.create", user_id=current_user.id)
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
        audit_event("chat.thread.delete.failure", user_id=current_user.id, thread_id=thread_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat thread not found")
    audit_event("chat.thread.delete.success", user_id=current_user.id, thread_id=thread_id)
    return None


@router.post("/chats/{thread_id}/turns", response_model=ChatThreadResponse)
def save_chat_turn(
    thread_id: int,
    payload: ChatTurnCreate,
    current_user: UserResponse = Depends(get_current_user),
):
    """Persist one full user/assistant exchange into a saved chat thread."""

    try:
        audit_event("chat.turn.save", user_id=current_user.id, thread_id=thread_id)
        return auth_db.save_chat_turn(
            user_id=current_user.id,
            thread_id=thread_id,
            turn_data=payload,
        )
    except ValueError as exc:
        audit_event("chat.turn.save.failure", user_id=current_user.id, thread_id=thread_id)
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

    audit_event("api_key.create", user_id=current_user.id, name=payload.name)
    return auth_db.create_api_key(current_user.id, payload.name)


@router.delete("/api-keys/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    api_key_id: int,
    current_user: UserResponse = Depends(get_current_user),
):
    """Revoke one API key owned by the current user."""

    if not auth_db.revoke_api_key(current_user.id, api_key_id):
        audit_event("api_key.revoke.failure", user_id=current_user.id, api_key_id=api_key_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    audit_event("api_key.revoke.success", user_id=current_user.id, api_key_id=api_key_id)
    return None
