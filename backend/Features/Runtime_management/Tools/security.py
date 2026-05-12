from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

security_logger = logging.getLogger("civilai.security")

SENSITIVE_DETAIL_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]+"),
    re.compile(r"civilai_[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[^,\s]+"),
    re.compile(r"[A-Za-z]:\\[^\s]+"),
    re.compile(r"/(?:home|app|var|tmp)/[^\s]+"),
]


def is_production_environment(environment: str | None = None) -> bool:
    value = (environment or os.getenv("ENVIRONMENT", "development")).strip().lower()
    return value in {"prod", "production", "server", "staging"}


def require_production_secret(name: str, value: str | None) -> str:
    if is_production_environment() and not value:
        raise RuntimeError(
            f"{name} must be set when ENVIRONMENT is production, staging, or server."
        )
    return value or ""


def sanitize_detail(detail: Any) -> Any:
    if isinstance(detail, dict):
        return {key: sanitize_detail(value) for key, value in detail.items()}
    if isinstance(detail, list):
        return [sanitize_detail(item) for item in detail]
    if not isinstance(detail, str):
        return detail

    sanitized = detail
    for pattern in SENSITIVE_DETAIL_PATTERNS:
        sanitized = pattern.sub("[redacted]", sanitized)
    return sanitized


def audit_event(event: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **{key: value for key, value in fields.items() if value is not None},
    }
    security_logger.info(json.dumps(payload, sort_keys=True, default=str))
