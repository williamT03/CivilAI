from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

try:
    from backend.app.core.config import get_settings
except ImportError:  # pragma: no cover
    from app.core.config import get_settings


@dataclass(slots=True)
class VectorHit:
    id: str
    text: str
    metadata: dict
    score: float


class VectorStore(Protocol):
    def upsert(
        self,
        collection: str,
        ids: list[str],
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> None: ...

    def query(
        self,
        collection: str,
        embedding: list[float],
        *,
        limit: int = 5,
        filters: dict | None = None,
    ) -> list[VectorHit]: ...


class QdrantVectorStore:
    """Qdrant adapter for the next vector migration step."""

    def __init__(self) -> None:
        from qdrant_client import QdrantClient

        settings = get_settings()
        self.client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)

    def upsert(
        self,
        collection: str,
        ids: list[str],
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> None:
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(
                id=ids[index],
                vector=embeddings[index],
                payload={**metadatas[index], "text": texts[index]},
            )
            for index in range(len(ids))
        ]
        self.client.upsert(collection_name=collection, points=points)

    def query(
        self,
        collection: str,
        embedding: list[float],
        *,
        limit: int = 5,
        filters: dict | None = None,
    ) -> list[VectorHit]:
        response = self.client.query_points(
            collection_name=collection,
            query=embedding,
            limit=limit,
            query_filter=filters,
            with_payload=True,
        )
        return [
            VectorHit(
                id=str(point.id),
                text=(point.payload or {}).get("text", ""),
                metadata={
                    key: value for key, value in (point.payload or {}).items() if key != "text"
                },
                score=float(point.score or 0),
            )
            for point in response.points
        ]
