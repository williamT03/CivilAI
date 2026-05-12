from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    insert,
    select,
)

try:
    from backend.Features.Runtime_management.Config.Tools.settings import get_settings
except ImportError:  # pragma: no cover
    from backend.Features.Runtime_management.Config.Tools.settings import get_settings

logger = logging.getLogger(__name__)
metadata = MetaData()

usage_logs = Table(
    "usage_logs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(64), nullable=True),
    Column("request_id", String(64), nullable=False),
    Column("endpoint", String(255), nullable=True),
    Column("provider", String(64), nullable=False),
    Column("model", String(255), nullable=False),
    Column("operation", String(64), nullable=False),
    Column("input_tokens", Integer, nullable=False, default=0),
    Column("output_tokens", Integer, nullable=False, default=0),
    Column("embedding_tokens", Integer, nullable=False, default=0),
    Column("estimated_cost_usd", Float, nullable=False, default=0.0),
    Column("latency_ms", Float, nullable=False, default=0.0),
    Column("success", Integer, nullable=False, default=1),
    Column("error", Text, nullable=True),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
)

ai_provider_logs = Table(
    "ai_provider_logs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("request_id", String(64), nullable=False),
    Column("provider", String(64), nullable=False),
    Column("model", String(255), nullable=False),
    Column("event", String(64), nullable=False),
    Column("message", Text, nullable=True),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
)


@dataclass(slots=True)
class UsageEvent:
    provider: str
    model: str
    operation: str
    request_id: str
    endpoint: Optional[str] = None
    user_id: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    embedding_tokens: int = 0
    latency_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None


class UsageTracker:
    """Durable usage logger used by all providers.

    Pricing is deliberately environment-configurable because AI prices change.
    If no `AI_PRICE_*` env var is set, cost is recorded as zero while tokens and
    latency are still stored for billing readiness.
    """

    def __init__(self, database_url: str | None = None) -> None:
        settings = get_settings()
        self.database_url = database_url or os.getenv("USAGE_DATABASE_URL") or settings.database_url
        self.engine = create_engine(self.database_url, future=True)
        metadata.create_all(self.engine)

    def record(self, event: UsageEvent) -> None:
        estimated_cost = self.estimate_cost(event)
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(usage_logs).values(
                        id=str(uuid.uuid4()),
                        user_id=event.user_id,
                        request_id=event.request_id,
                        endpoint=event.endpoint,
                        provider=event.provider,
                        model=event.model,
                        operation=event.operation,
                        input_tokens=max(0, int(event.input_tokens)),
                        output_tokens=max(0, int(event.output_tokens)),
                        embedding_tokens=max(0, int(event.embedding_tokens)),
                        estimated_cost_usd=estimated_cost,
                        latency_ms=float(event.latency_ms),
                        success=1 if event.success else 0,
                        error=event.error[:4000] if event.error else None,
                        created_at=datetime.utcnow(),
                    )
                )
        except Exception as exc:  # Usage logging must never block answers.
            logger.warning("Could not record AI usage event: %s", exc)

    def record_provider_event(
        self, request_id: str, provider: str, model: str, event: str, message: str | None = None
    ) -> None:
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(ai_provider_logs).values(
                        id=str(uuid.uuid4()),
                        request_id=request_id,
                        provider=provider,
                        model=model,
                        event=event,
                        message=message,
                        created_at=datetime.utcnow(),
                    )
                )
        except Exception as exc:
            logger.warning("Could not record provider event: %s", exc)

    def monthly_usage_for_user(self, user_id: str, year: int, month: int) -> dict:
        start = datetime(year, month, 1)
        end = datetime(year + int(month == 12), 1 if month == 12 else month + 1, 1)
        with self.engine.begin() as connection:
            row = connection.execute(
                select(
                    func.coalesce(func.sum(usage_logs.c.input_tokens), 0),
                    func.coalesce(func.sum(usage_logs.c.output_tokens), 0),
                    func.coalesce(func.sum(usage_logs.c.embedding_tokens), 0),
                    func.coalesce(func.sum(usage_logs.c.estimated_cost_usd), 0),
                    func.count(),
                ).where(
                    usage_logs.c.user_id == user_id,
                    usage_logs.c.created_at >= start,
                    usage_logs.c.created_at < end,
                )
            ).first()

        return {
            "user_id": user_id,
            "year": year,
            "month": month,
            "input_tokens": int(row[0] or 0),
            "output_tokens": int(row[1] or 0),
            "embedding_tokens": int(row[2] or 0),
            "estimated_cost_usd": float(row[3] or 0),
            "request_count": int(row[4] or 0),
        }

    def monthly_message_count_for_user(self, user_id: str, year: int, month: int) -> int:
        """Count completed answer generations for subscription message caps."""

        start = datetime(year, month, 1)
        end = datetime(year + int(month == 12), 1 if month == 12 else month + 1, 1)
        with self.engine.begin() as connection:
            count = connection.execute(
                select(func.count()).where(
                    usage_logs.c.user_id == user_id,
                    usage_logs.c.operation.in_(["chat", "chat_stream"]),
                    usage_logs.c.success == 1,
                    usage_logs.c.created_at >= start,
                    usage_logs.c.created_at < end,
                )
            ).scalar_one()

        return int(count or 0)

    @staticmethod
    def estimate_cost(event: UsageEvent) -> float:
        prefix = (
            f"AI_PRICE_{event.provider}_{event.model}".upper().replace("-", "_").replace(".", "_")
        )
        input_per_m = float(os.getenv(f"{prefix}_INPUT_PER_M", "0") or 0)
        output_per_m = float(os.getenv(f"{prefix}_OUTPUT_PER_M", "0") or 0)
        embedding_per_m = float(os.getenv(f"{prefix}_EMBEDDING_PER_M", "0") or 0)
        return round(
            (event.input_tokens / 1_000_000 * input_per_m)
            + (event.output_tokens / 1_000_000 * output_per_m)
            + (event.embedding_tokens / 1_000_000 * embedding_per_m),
            8,
        )


_tracker: UsageTracker | None = None


def get_usage_tracker() -> UsageTracker:
    global _tracker
    if _tracker is None:
        _tracker = UsageTracker()
    return _tracker
