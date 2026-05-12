"""Public Ingestion feature entry points."""

from .Tools.ingestion import IngestionJob, get_ingestion_job_store


def build_ingestion_job_response(job: IngestionJob) -> dict:
    """Create the API-safe job status payload used by upload progress endpoints."""

    return {
        "id": job.id,
        "filename": job.filename,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "error": job.error,
        "result": job.result,
    }


__all__ = ["IngestionJob", "build_ingestion_job_response", "get_ingestion_job_store"]
