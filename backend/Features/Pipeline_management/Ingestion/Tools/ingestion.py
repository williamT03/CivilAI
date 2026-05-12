from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
    update,
)

try:
    from backend.Features.Runtime_management.Config.Tools.settings import get_settings
except ImportError:  # pragma: no cover
    from backend.Features.Runtime_management.Config.Tools.settings import get_settings

metadata = MetaData()

ingestion_jobs = Table(
    "ingestion_jobs_runtime",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(64), nullable=True),
    Column("filename", String(511), nullable=False),
    Column("local_path", Text, nullable=False),
    Column("storage_key", Text, nullable=True),
    Column("checksum_sha256", String(64), nullable=True),
    Column("status", String(32), nullable=False, default="queued"),
    Column("stage", String(64), nullable=False, default="upload"),
    Column("progress", Integer, nullable=False, default=0),
    Column("error", Text, nullable=True),
    Column("result_json", Text, nullable=True),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
)


@dataclass(slots=True)
class IngestionJob:
    id: str
    user_id: Optional[str]
    filename: str
    local_path: str
    storage_key: Optional[str]
    checksum_sha256: Optional[str]
    status: str
    stage: str
    progress: int
    error: Optional[str]
    result: Optional[dict]
    created_at: datetime
    updated_at: datetime


class IngestionJobStore:
    """Small runtime job store for upload/indexing status tracking."""

    def __init__(self, database_url: str | None = None) -> None:
        settings = get_settings()
        self.engine = create_engine(database_url or settings.database_url, future=True)
        metadata.create_all(self.engine)

    def create_job(
        self,
        *,
        user_id: str | None,
        filename: str,
        local_path: str,
        storage_key: str | None,
        checksum_sha256: str | None,
    ) -> IngestionJob:
        job_id = str(uuid.uuid4())
        now = datetime.utcnow()
        with self.engine.begin() as connection:
            connection.execute(
                insert(ingestion_jobs).values(
                    id=job_id,
                    user_id=user_id,
                    filename=filename,
                    local_path=local_path,
                    storage_key=storage_key,
                    checksum_sha256=checksum_sha256,
                    status="queued",
                    stage="upload",
                    progress=5,
                    created_at=now,
                    updated_at=now,
                )
            )
        return self.get_job(job_id)  # type: ignore[return-value]

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        stage: str | None = None,
        progress: int | None = None,
        error: str | None = None,
        result: dict | None = None,
    ) -> Optional[IngestionJob]:
        values = {"updated_at": datetime.utcnow()}
        if status is not None:
            values["status"] = status
        if stage is not None:
            values["stage"] = stage
        if progress is not None:
            values["progress"] = max(0, min(100, int(progress)))
        if error is not None:
            values["error"] = error
        if result is not None:
            values["result_json"] = json.dumps(result)

        with self.engine.begin() as connection:
            connection.execute(
                update(ingestion_jobs).where(ingestion_jobs.c.id == job_id).values(**values)
            )

        return self.get_job(job_id)

    def get_job(self, job_id: str, *, user_id: str | None = None) -> Optional[IngestionJob]:
        with self.engine.begin() as connection:
            statement = select(ingestion_jobs).where(ingestion_jobs.c.id == job_id)
            if user_id is not None:
                statement = statement.where(ingestion_jobs.c.user_id == user_id)
            row = connection.execute(statement).mappings().first()
        return self._row_to_job(row) if row else None

    def list_jobs(self, *, user_id: str | None = None, limit: int = 25) -> list[IngestionJob]:
        with self.engine.begin() as connection:
            statement = (
                select(ingestion_jobs).order_by(ingestion_jobs.c.created_at.desc()).limit(limit)
            )
            if user_id is not None:
                statement = statement.where(ingestion_jobs.c.user_id == user_id)
            rows = connection.execute(statement).mappings().all()
        return [self._row_to_job(row) for row in rows]

    @staticmethod
    def _row_to_job(row) -> IngestionJob:
        result = None
        if row.get("result_json"):
            try:
                result = json.loads(row["result_json"])
            except json.JSONDecodeError:
                result = None
        return IngestionJob(
            id=row["id"],
            user_id=row.get("user_id"),
            filename=row["filename"],
            local_path=row["local_path"],
            storage_key=row.get("storage_key"),
            checksum_sha256=row.get("checksum_sha256"),
            status=row["status"],
            stage=row["stage"],
            progress=int(row["progress"] or 0),
            error=row.get("error"),
            result=result,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


_job_store: IngestionJobStore | None = None


def get_ingestion_job_store() -> IngestionJobStore:
    global _job_store
    if _job_store is None:
        _job_store = IngestionJobStore()
    return _job_store
