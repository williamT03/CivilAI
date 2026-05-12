from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from .models import AgentContext, CheckResult, CheckStatus


class BaseAgent(ABC):
    """Base class for focused validation agents."""

    name: str
    description: str

    def __init__(self, context: AgentContext) -> None:
        self.context = context
        self.repo_root = Path(context.repo_root)

    @abstractmethod
    def run(self) -> list[CheckResult]:
        """Run this agent's checks."""

    def pass_result(self, name: str, summary: str, **details) -> CheckResult:
        return CheckResult(name=name, status=CheckStatus.PASS, summary=summary, details=details)

    def warn_result(self, name: str, summary: str, **details) -> CheckResult:
        return CheckResult(name=name, status=CheckStatus.WARN, summary=summary, details=details)

    def fail_result(self, name: str, summary: str, **details) -> CheckResult:
        return CheckResult(name=name, status=CheckStatus.FAIL, summary=summary, details=details)

    def skip_result(self, name: str, summary: str, **details) -> CheckResult:
        return CheckResult(name=name, status=CheckStatus.SKIP, summary=summary, details=details)
