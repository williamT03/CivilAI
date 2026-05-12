import logging
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

from backend.Features.LLM_management.Providers.Tools.usage import get_usage_tracker
from backend.Features.LLM_management.Tools.rag import ask
from backend.Features.Pipeline_management.Ingestion.Tools.ingestion import get_ingestion_job_store
from backend.Features.Pipeline_management.Parser.parser_run import ParserPipelineBuilder
from backend.Features.RAG_management.Navigation.navigation_run import StructuredToolFactory
from backend.Features.Runtime_management.Config.Tools.settings import get_settings
from backend.Features.Runtime_management.Tools.security import audit_event
from backend.Features.Storage_management.Tools.storage import get_file_storage
from backend.Features.User_management.auth_run import UserResponse, auth_db, decode_token

app = FastAPI(title="Civil AI — Custom RAG")
BACKEND_ROOT = Path(__file__).resolve().parents[2]
PDF_DIR = str(BACKEND_ROOT / "Data" / "PDF")
settings = get_settings()
INDEX_LOCK = threading.Lock()
TOOLKIT = StructuredToolFactory.create_toolkit()
OPTIONAL_OAUTH2_SCHEME = OAuth2PasswordBearer(auto_error=False, tokenUrl="/api/auth/login")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
os.makedirs(PDF_DIR, exist_ok=True)
app.mount("/pdf", StaticFiles(directory=PDF_DIR), name="pdf")


def _safe_pdf_name(filename: str) -> str:
    base = os.path.basename(filename or "").strip()
    if not base:
        raise HTTPException(status_code=400, detail="A PDF filename is required.")
    # Keep common ordinance filename punctuation so uploaded documents remain
    # recognizable in the PDF folder and the jurisdiction list.
    safe = re.sub(r"[^A-Za-z0-9.,()'&_ -]", "_", base)
    if not safe.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
    return safe


def _run_optional_llama_index() -> None:
    """Legacy LlamaIndex refresh hook kept as a no-op during migration."""

    return


def _queue_parse_pdf_job(job_id: str) -> None:
    """Queue async parsing without making Celery a hard import-time dependency."""

    from backend.Features.Pipeline_management.Ingestion.Tools.worker import parse_pdf_job

    parse_pdf_job.delay(job_id)


def _run_custom_parse(pdf_path: str, user_id: str | None = None) -> dict:
    # Build the parser on demand so uploads always use the current storage pipeline.
    parser = ParserPipelineBuilder().build()
    return parser.parse_uploaded_pdf(
        pdf_path,
        owner_user_id=user_id,
        visibility="private" if user_id else "public",
    )


def _validate_pdf_signature(path: str) -> None:
    with open(path, "rb") as handle:
        signature = handle.read(5)
    if signature != b"%PDF-":
        try:
            os.remove(path)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF.")


def get_optional_current_user(
    token: Optional[str] = Depends(OPTIONAL_OAUTH2_SCHEME),
) -> Optional[UserResponse]:
    """Return the authenticated user when a valid bearer token is present."""

    if not token:
        return None

    try:
        payload = decode_token(token)
        user_id = int(payload.sub.split(":", 1)[0])
    except Exception:
        return None

    return auth_db.get_user_by_id(user_id)


def _monthly_message_limit_for_user(user: Optional[UserResponse]) -> Optional[int]:
    if user is None:
        return None
    subscription = auth_db.get_subscription(user.id)
    if subscription.status != "active":
        raise HTTPException(status_code=402, detail="Subscription is not active.")
    if subscription.tier.lower() in {"pro", "standard", "standard_user"}:
        return settings.pro_monthly_message_limit or None
    return settings.free_monthly_message_limit or None


def _enforce_message_limit(user: Optional[UserResponse]) -> None:
    if user is None:
        return
    monthly_limit = _monthly_message_limit_for_user(user)
    if monthly_limit is None:
        return
    now = datetime.utcnow()
    used_messages = get_usage_tracker().monthly_message_count_for_user(
        str(user.id), now.year, now.month
    )
    if used_messages >= monthly_limit:
        raise HTTPException(
            status_code=429, detail="Monthly message limit reached for this subscription."
        )


@app.get("/query")
def query(
    q: str,
    jurisdiction: Optional[str] = Query(
        default=None,
        description="Filter by jurisdiction: 'cooper city', 'broward county', or omit for all",
    ),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
):
    """
    Query the custom RAG system.

    Examples:
      /query?q=what+is+the+equipment+fund&jurisdiction=broward+county
      /query?q=general+penalty&jurisdiction=cooper+city
      /query?q=capital+improvements+fund   ← searches all jurisdictions
    """
    _enforce_message_limit(current_user)
    audit_event(
        "custom.query",
        user_id=str(current_user.id) if current_user else None,
        jurisdiction=jurisdiction,
    )
    try:
        result = ask(
            q,
            jurisdiction=jurisdiction,
            user_id=str(current_user.id) if current_user else None,
            request_id=str(uuid.uuid4()),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("custom_query_failed jurisdiction=%s", jurisdiction)
        raise HTTPException(
            status_code=503,
            detail="CivilAI query service is temporarily unavailable. Please try again in a moment.",
        )
    return {
        "answer": result["answer"],
        "accuracy": result["accuracy"],
        "navigation": result["navigation"],
        "system": "custom",
        "jurisdiction": result["jurisdiction"],
        "sources": result["sources"],
    }


@app.get("/jurisdictions")
def list_jurisdictions(current_user: Optional[UserResponse] = Depends(get_optional_current_user)):
    return {
        "jurisdictions": TOOLKIT.list_jurisdictions(
            user_id=str(current_user.id) if current_user else None
        )
    }


@app.get("/ingestion-jobs/{job_id}")
def get_upload_job(
    job_id: str,
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
):
    job = get_ingestion_job_store().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Ingestion job not found.")
    if job.user_id and (current_user is None or str(current_user.id) != job.user_id):
        raise HTTPException(status_code=404, detail="Ingestion job not found.")
    return {
        "id": job.id,
        "filename": job.filename,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "error": job.error,
        "result": job.result,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


@app.get("/navigation-map")
def navigation_map(current_user: Optional[UserResponse] = Depends(get_optional_current_user)):
    return TOOLKIT.get_navigation_map(user_id=str(current_user.id) if current_user else None)


@app.get("/structure")
def structure(
    jurisdiction: Optional[str] = Query(
        default=None,
        description="Optional jurisdiction to return one structured document map.",
    ),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
):
    user_id = str(current_user.id) if current_user else None
    full_map = TOOLKIT.get_navigation_map(user_id=user_id)
    if not jurisdiction:
        return full_map

    document_slug = TOOLKIT.resolve_document_slug(jurisdiction, user_id=user_id)
    if not document_slug:
        raise HTTPException(status_code=404, detail="Jurisdiction not found in structured map.")

    document = full_map.get("documents", {}).get(document_slug)
    if not document:
        raise HTTPException(status_code=404, detail="Structured document map not found.")

    return {
        "document_slug": document_slug,
        "document": document,
    }


@app.post("/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
):
    filename = _safe_pdf_name(file.filename or "")
    audit_event(
        "upload.pdf.start",
        user_id=str(current_user.id) if current_user else None,
        filename=filename,
    )
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in {"application/pdf", "application/x-pdf"}:
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF.")
    if file.size and file.size > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413, detail="Uploaded PDF exceeds the configured size limit."
        )

    storage = get_file_storage()
    target_path = os.path.join(PDF_DIR, filename)
    replaced_existing = os.path.exists(target_path)
    stored_file = storage.save_pdf_stream(
        file.file,
        filename=filename,
        user_id=str(current_user.id) if current_user else None,
    )
    if stored_file.size_bytes > settings.max_upload_bytes:
        try:
            os.remove(stored_file.local_path)
        except OSError:
            pass
        raise HTTPException(
            status_code=413, detail="Uploaded PDF exceeds the configured size limit."
        )
    _validate_pdf_signature(stored_file.local_path)

    job_store = get_ingestion_job_store()
    job = job_store.create_job(
        user_id=str(current_user.id) if current_user else None,
        filename=os.path.basename(stored_file.local_path),
        local_path=stored_file.local_path,
        storage_key=stored_file.storage_key,
        checksum_sha256=stored_file.checksum_sha256,
    )

    if settings.async_ingestion_enabled:
        try:
            _queue_parse_pdf_job(job.id)
        except Exception as exc:
            job_store.update_job(
                job.id, status="failed", stage="queue", progress=100, error=str(exc)
            )
            raise HTTPException(status_code=503, detail=f"Ingestion queue is unavailable: {exc}")
        return {
            "message": "PDF uploaded and queued for indexing.",
            "filename": os.path.basename(stored_file.local_path),
            "checksum_sha256": stored_file.checksum_sha256,
            "replaced_existing": replaced_existing,
            "job": {
                "id": job.id,
                "status": job.status,
                "stage": job.stage,
                "progress": job.progress,
            },
        }

    with INDEX_LOCK:
        job_store.update_job(job.id, status="running", stage="parse", progress=20)
        parse_result = _run_custom_parse(
            stored_file.local_path,
            user_id=str(current_user.id) if current_user else None,
        )
        job_store.update_job(job.id, status="running", stage="navigation_refresh", progress=85)
        TOOLKIT.refresh_navigation_cache()
        _run_optional_llama_index()
        job_store.update_job(
            job.id, status="succeeded", stage="complete", progress=100, result=parse_result
        )

    if current_user:
        try:
            auth_db.record_uploaded_document(
                current_user.id,
                filename=os.path.basename(stored_file.local_path),
                document_title=parse_result.get("document_title"),
                stored_path=stored_file.local_path,
                chapter_count=parse_result.get("chapter_count"),
                section_count=parse_result.get("section_count"),
                subsection_count=parse_result.get("subsection_count"),
                replaced_existing=replaced_existing,
            )
        except Exception:
            # Upload history should never block the parsing pipeline.
            pass

    audit_event(
        "upload.pdf.success",
        user_id=str(current_user.id) if current_user else None,
        filename=filename,
    )
    return {
        "message": "PDF uploaded and indexed successfully.",
        "filename": os.path.basename(stored_file.local_path),
        "checksum_sha256": stored_file.checksum_sha256,
        "replaced_existing": replaced_existing,
        "job": {
            "id": job.id,
            "status": "succeeded",
            "stage": "complete",
            "progress": 100,
        },
        "parse_result": parse_result,
    }
