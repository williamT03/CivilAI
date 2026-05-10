from __future__ import annotations

from celery import Celery

try:
    from backend.app.core.config import get_settings
except ImportError:  # pragma: no cover
    from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "civilai_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
)


@celery_app.task(name="civilai.ingestion.parse_pdf", bind=True, max_retries=3)
def parse_pdf_job(self, job_id: str) -> dict:
    """Run the municipal-code parser/indexer for one queued upload."""

    try:
        from backend.app.ingestion import get_ingestion_job_store
        from backend.app.auth import auth_db
        from backend.CustomRAG.db_scripts import ParserPipelineBuilder
        from backend.CustomRAG.tools import StructuredToolFactory
    except ImportError:  # pragma: no cover
        from app.ingestion import get_ingestion_job_store
        from app.auth import auth_db
        from CustomRAG.db_scripts import ParserPipelineBuilder
        from CustomRAG.tools import StructuredToolFactory

    store = get_ingestion_job_store()
    job = store.get_job(job_id)
    if job is None:
        return {"job_id": job_id, "status": "missing"}

    try:
        store.update_job(job_id, status="running", stage="parse", progress=20)
        parser = ParserPipelineBuilder().build()
        parse_result = parser.parse_uploaded_pdf(
            job.local_path,
            owner_user_id=job.user_id,
            visibility="private" if job.user_id else "public",
        )

        store.update_job(job_id, status="running", stage="navigation_refresh", progress=85)
        StructuredToolFactory.create_toolkit().refresh_navigation_cache()

        if job.user_id:
            try:
                auth_db.record_uploaded_document(
                    int(job.user_id),
                    filename=job.filename,
                    document_title=parse_result.get("document_title"),
                    stored_path=job.local_path,
                    chapter_count=parse_result.get("chapter_count"),
                    section_count=parse_result.get("section_count"),
                    subsection_count=parse_result.get("subsection_count"),
                    replaced_existing=False,
                )
            except Exception:
                pass

        store.update_job(job_id, status="succeeded", stage="complete", progress=100, result=parse_result)
        return {"job_id": job_id, "status": "succeeded", "parse_result": parse_result}
    except Exception as exc:
        store.update_job(job_id, status="failed", stage="failed", progress=100, error=str(exc))
        raise self.retry(exc=exc, countdown=10)
