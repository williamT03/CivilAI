from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class CheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    summary: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentContext:
    repo_root: str
    backend_url: str
    frontend_url: str
    report_dir: str
    skip_frontend_build: bool = False
    skip_dependency_audit: bool = False


@dataclass(frozen=True)
class AgentReport:
    agent: str
    generated_at: str
    results: list[CheckResult]

    @classmethod
    def from_results(cls, agent: str, results: list[CheckResult]) -> "AgentReport":
        return cls(
            agent=agent,
            generated_at=datetime.now(timezone.utc).isoformat(),
            results=results,
        )
