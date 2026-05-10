from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

try:
    from backend.app.ai.usage import get_usage_tracker
    from backend.app.auth import UserResponse, auth_db, decode_token, get_current_user
    from backend.app.core.config import get_settings
    from backend.app.ingestion import IngestionJob, get_ingestion_job_store
    from backend.app.storage import get_file_storage
    from backend.CustomRAG.LLM.llm import stream_answer
    from backend.CustomRAG.LLM.rag import ask, retrieve
except ImportError:  # pragma: no cover
    from app.ai.usage import get_usage_tracker
    from app.auth import UserResponse, auth_db, decode_token, get_current_user
    from app.core.config import get_settings
    from app.ingestion import IngestionJob, get_ingestion_job_store
    from app.storage import get_file_storage
    from CustomRAG.LLM.llm import stream_answer
    from CustomRAG.LLM.rag import ask, retrieve

from fastapi.security import OAuth2PasswordBearer


router = APIRouter(prefix="/api/v1", tags=["platform"])
OPTIONAL_OAUTH2_SCHEME = OAuth2PasswordBearer(auto_error=False, tokenUrl="/api/auth/login")


class SignedUploadRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    expires_in: int = Field(default=900, ge=60, le=3600)


class SignedUploadResponse(BaseModel):
    url: str
    storage_key: str
    expires_in: int


class IngestionJobResponse(BaseModel):
    id: str
    filename: str
    storage_key: Optional[str] = None
    checksum_sha256: Optional[str] = None
    status: str
    stage: str
    progress: int
    error: Optional[str] = None
    result: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    jurisdiction: Optional[str] = Field(default=None, max_length=255)
    top_k: int = Field(default=5, ge=1, le=12)
    save_to_thread_id: Optional[int] = None


class QuerySource(BaseModel):
    jurisdiction: Optional[str] = None
    source: Optional[str] = None
    section: Optional[str] = None
    subsection: Optional[str] = None
    title: Optional[str] = None
    page: Optional[int] = None
    score: float
    url: Optional[str] = None


class QueryResponse(BaseModel):
    request_id: str
    answer: str
    accuracy: dict
    navigation: dict
    jurisdiction: Optional[str] = None
    sources: list[QuerySource]
    tool_trace: list[dict]


class SubscriptionUsageResponse(BaseModel):
    tier: str
    status: str
    monthly_token_limit: Optional[int]
    monthly_message_limit: Optional[int]
    usage: dict
    remaining_tokens: Optional[int]
    used_messages: int
    remaining_messages: Optional[int]


def _job_to_response(job: IngestionJob) -> IngestionJobResponse:
    return IngestionJobResponse(
        id=job.id,
        filename=job.filename,
        storage_key=job.storage_key,
        checksum_sha256=job.checksum_sha256,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        error=job.error,
        result=job.result,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def get_optional_current_user(
    token: Optional[str] = Depends(OPTIONAL_OAUTH2_SCHEME),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> Optional[UserResponse]:
    if x_api_key:
        return auth_db.authenticate_api_key(x_api_key)
    if not token:
        return None
    try:
        payload = decode_token(token)
        user_id = int(payload.sub.split(":", 1)[0])
    except Exception:
        return None
    return auth_db.get_user_by_id(user_id)


def _monthly_limit_for_user(user: Optional[UserResponse]) -> Optional[int]:
    if user is None:
        return None
    subscription = auth_db.get_subscription(user.id)
    if subscription.status != "active":
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Subscription is not active.")
    if subscription.monthly_token_limit is not None:
        return subscription.monthly_token_limit

    settings = get_settings()
    tier = subscription.tier.lower()
    if tier == "pro":
        return settings.pro_monthly_token_limit or None
    if tier in {"standard", "standard_user"}:
        return settings.standard_monthly_token_limit or None
    return settings.free_monthly_token_limit or None


def _monthly_message_limit_for_user(user: Optional[UserResponse]) -> Optional[int]:
    if user is None:
        return None
    subscription = auth_db.get_subscription(user.id)
    if subscription.status != "active":
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Subscription is not active.")

    settings = get_settings()
    tier = subscription.tier.lower()
    if tier in {"pro", "standard", "standard_user"}:
        return settings.pro_monthly_message_limit or None
    return settings.free_monthly_message_limit or None


def _enforce_usage_limit(user: Optional[UserResponse]) -> None:
    if user is None:
        return
    monthly_limit = _monthly_limit_for_user(user)
    now = datetime.utcnow()
    usage = get_usage_tracker().monthly_usage_for_user(str(user.id), now.year, now.month)
    if monthly_limit is not None:
        used_tokens = usage["input_tokens"] + usage["output_tokens"] + usage["embedding_tokens"]
        if used_tokens >= monthly_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Monthly AI token limit reached for this subscription.",
            )

    monthly_message_limit = _monthly_message_limit_for_user(user)
    if monthly_message_limit is None:
        return
    used_messages = get_usage_tracker().monthly_message_count_for_user(str(user.id), now.year, now.month)
    if used_messages >= monthly_message_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Monthly message limit reached for this subscription.",
        )


@router.get("/health")
def health_v1():
    settings = get_settings()
    return {
        "status": "ok",
        "api_version": "v1",
        "environment": settings.environment,
        "ai_default_provider": settings.ai_default_provider,
        "ai_fallback_provider": settings.ai_fallback_provider,
        "vector_store_backend": settings.vector_store_backend,
        "async_ingestion_enabled": settings.async_ingestion_enabled,
    }


@router.post("/query", response_model=QueryResponse)
def query_v1(
    payload: QueryRequest,
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
):
    """Typed SaaS query endpoint with tenant-aware retrieval and provider usage tracking."""

    request_id = str(uuid.uuid4())
    user_id = str(current_user.id) if current_user else None
    _enforce_usage_limit(current_user)
    result = ask(
        payload.question,
        top_k=payload.top_k,
        jurisdiction=payload.jurisdiction,
        user_id=user_id,
        request_id=request_id,
    )

    if payload.save_to_thread_id and current_user:
        try:
            from backend.app.auth import ChatAssistantMessageCreate, ChatTurnCreate, ChatUserMessageCreate
        except ImportError:  # pragma: no cover
            from app.auth import ChatAssistantMessageCreate, ChatTurnCreate, ChatUserMessageCreate

        auth_db.save_chat_turn(
            user_id=current_user.id,
            thread_id=payload.save_to_thread_id,
            turn_data=ChatTurnCreate(
                user_message=ChatUserMessageCreate(content=payload.question),
                assistant_message=ChatAssistantMessageCreate(
                    content=result["answer"],
                    accuracy=result["accuracy"],
                    resolved_jurisdiction=result["jurisdiction"],
                    navigation=result["navigation"],
                    sources=result["sources"],
                ),
                jurisdiction=result["jurisdiction"],
            ),
        )

    return QueryResponse(
        request_id=request_id,
        answer=result["answer"],
        accuracy=result["accuracy"],
        navigation=result["navigation"],
        jurisdiction=result["jurisdiction"],
        sources=result["sources"],
        tool_trace=result["tool_trace"],
    )


@router.post("/query/stream")
def query_stream_v1(
    payload: QueryRequest,
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
):
    """Stream a grounded answer as server-sent events after tenant-aware retrieval."""

    request_id = str(uuid.uuid4())
    user_id = str(current_user.id) if current_user else None
    _enforce_usage_limit(current_user)
    retrieval = retrieve(
        query=payload.question,
        top_k=payload.top_k,
        jurisdiction=payload.jurisdiction,
        user_id=user_id,
    )

    def event_stream():
        metadata = {
            "request_id": request_id,
            "accuracy": retrieval["accuracy"],
            "navigation": retrieval["search_payload"].get("navigation", {}),
            "jurisdiction": retrieval["search_payload"].get("resolved_document_title"),
            "sources": retrieval["sources"],
            "tool_trace": retrieval["search_payload"].get("tool_trace", []),
        }
        yield f"event: metadata\ndata: {json.dumps(metadata)}\n\n"
        try:
            for chunk in stream_answer(
                payload.question,
                retrieval["search_payload"],
                user_id=user_id,
                request_id=request_id,
            ):
                yield f"event: token\ndata: {json.dumps({'text': chunk})}\n\n"
            yield f"event: done\ndata: {json.dumps({'request_id': request_id})}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'request_id': request_id, 'error': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/uploads/signed-url", response_model=SignedUploadResponse)
def create_signed_upload_url(
    payload: SignedUploadRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Create a tenant-scoped signed upload URL for R2/S3 PDF uploads."""

    if not payload.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF uploads are supported.")
    try:
        return get_file_storage().create_presigned_upload_url(
            filename=payload.filename,
            user_id=str(current_user.id),
            expires_in=payload.expires_in,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.get("/ingestion-jobs", response_model=list[IngestionJobResponse])
def list_ingestion_jobs(
    limit: int = Query(default=25, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
):
    """List current user's upload/indexing jobs."""

    jobs = get_ingestion_job_store().list_jobs(user_id=str(current_user.id), limit=limit)
    return [_job_to_response(job) for job in jobs]


@router.get("/ingestion-jobs/{job_id}", response_model=IngestionJobResponse)
def get_ingestion_job(
    job_id: str,
    current_user: UserResponse = Depends(get_current_user),
):
    """Fetch one tenant-scoped ingestion job."""

    job = get_ingestion_job_store().get_job(job_id, user_id=str(current_user.id))
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion job not found.")
    return _job_to_response(job)


@router.get("/usage/monthly")
def monthly_usage(
    year: Optional[int] = Query(default=None, ge=2020, le=2100),
    month: Optional[int] = Query(default=None, ge=1, le=12),
    current_user: UserResponse = Depends(get_current_user),
):
    """Return authenticated user's monthly AI usage aggregate."""

    now = datetime.utcnow()
    return get_usage_tracker().monthly_usage_for_user(
        str(current_user.id),
        year or now.year,
        month or now.month,
    )


@router.get("/subscription/usage", response_model=SubscriptionUsageResponse)
def subscription_usage(current_user: UserResponse = Depends(get_current_user)):
    """Return subscription, usage, and remaining token budget."""

    subscription = auth_db.get_subscription(current_user.id)
    now = datetime.utcnow()
    usage = get_usage_tracker().monthly_usage_for_user(str(current_user.id), now.year, now.month)
    monthly_limit = _monthly_limit_for_user(current_user)
    monthly_message_limit = _monthly_message_limit_for_user(current_user)
    used_tokens = usage["input_tokens"] + usage["output_tokens"] + usage["embedding_tokens"]
    remaining = None if monthly_limit is None else max(0, monthly_limit - used_tokens)
    used_messages = get_usage_tracker().monthly_message_count_for_user(str(current_user.id), now.year, now.month)
    remaining_messages = None if monthly_message_limit is None else max(0, monthly_message_limit - used_messages)
    return SubscriptionUsageResponse(
        tier=subscription.tier,
        status=subscription.status,
        monthly_token_limit=monthly_limit,
        monthly_message_limit=monthly_message_limit,
        usage=usage,
        remaining_tokens=remaining,
        used_messages=used_messages,
        remaining_messages=remaining_messages,
    )
