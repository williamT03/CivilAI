from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

try:
    from backend.app.core.config import get_settings
except ImportError:  # pragma: no cover
    from app.core.config import get_settings


@dataclass(slots=True)
class StoredFile:
    filename: str
    local_path: str
    storage_key: str
    checksum_sha256: str
    size_bytes: int
    content_type: str = "application/pdf"


class FileStorage:
    """Local plus optional S3/R2 storage adapter for uploaded PDFs."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.local_directory = Path(self.settings.local_upload_directory)
        if not self.local_directory.is_absolute():
            self.local_directory = self.settings.backend_root.parent / self.local_directory
        self.local_directory.mkdir(parents=True, exist_ok=True)

    def save_pdf_stream(
        self, stream: BinaryIO, *, filename: str, user_id: str | None = None
    ) -> StoredFile:
        storage_key = self.build_storage_key(filename, user_id=user_id)
        local_path = self.local_directory / filename
        checksum = hashlib.sha256()
        size_bytes = 0

        with local_path.open("wb") as output:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                size_bytes += len(chunk)
                checksum.update(chunk)
                output.write(chunk)

        stored = StoredFile(
            filename=filename,
            local_path=str(local_path),
            storage_key=storage_key,
            checksum_sha256=checksum.hexdigest(),
            size_bytes=size_bytes,
        )

        if self.settings.storage_backend.lower() in {"s3", "r2"}:
            self.upload_local_file(stored)

        return stored

    def upload_local_file(self, stored_file: StoredFile) -> None:
        if not self.settings.s3_bucket_name:
            raise RuntimeError("S3/R2 bucket is not configured.")

        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=self.settings.s3_endpoint_url,
            aws_access_key_id=self.settings.s3_access_key_id,
            aws_secret_access_key=self.settings.s3_secret_access_key,
        )
        client.upload_file(
            stored_file.local_path,
            self.settings.s3_bucket_name,
            stored_file.storage_key,
            ExtraArgs={"ContentType": stored_file.content_type},
        )

    def create_presigned_upload_url(
        self, *, filename: str, user_id: str, expires_in: int = 900
    ) -> dict:
        if self.settings.storage_backend.lower() not in {"s3", "r2"}:
            raise RuntimeError("Signed uploads require STORAGE_BACKEND=s3 or STORAGE_BACKEND=r2.")
        if not self.settings.s3_bucket_name:
            raise RuntimeError("S3/R2 bucket is not configured.")

        import boto3

        storage_key = self.build_storage_key(filename, user_id=user_id)
        client = boto3.client(
            "s3",
            endpoint_url=self.settings.s3_endpoint_url,
            aws_access_key_id=self.settings.s3_access_key_id,
            aws_secret_access_key=self.settings.s3_secret_access_key,
        )
        url = client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.settings.s3_bucket_name,
                "Key": storage_key,
                "ContentType": "application/pdf",
            },
            ExpiresIn=expires_in,
        )
        return {"url": url, "storage_key": storage_key, "expires_in": expires_in}

    @staticmethod
    def build_storage_key(filename: str, *, user_id: str | None = None) -> str:
        clean_filename = os.path.basename(filename)
        tenant = user_id or "guest"
        return f"uploads/{tenant}/{clean_filename}"


def get_file_storage() -> FileStorage:
    return FileStorage()
