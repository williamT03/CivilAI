from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .agents import AGENT_REGISTRY
from .models import AgentContext

AGENT_GROUPS = {
    "all": list(AGENT_REGISTRY.keys()),
    "server-safe": [
        "risk-register",
        "policy-gate",
        "deployment-gate",
        "server-runtime",
        "server-connections",
        "security",
        "data-leak",
        "threat-model",
        "audit-log",
        "llm-safety",
    ],
    "runtime-deep": [
        "api-contract",
        "tenant-isolation",
        "server-connections",
        "deployment-gate",
        "data-leak",
        "llm-safety",
    ],
    "frontend": [
        "feature-flow",
        "frontend-features",
    ],
}


@dataclass(frozen=True)
class AgentRunPlan:
    """Resolved execution plan for one agent runner invocation."""

    context: AgentContext
    selected_agents: list[str]


class AgentRunPlanBuilder:
    """Builder that converts CLI/env inputs into a concrete agent run plan."""

    def __init__(self) -> None:
        self._repo_root: Path | None = None
        self._report_dir: Path | None = None
        self._agent = "all"
        self._backend_url = "http://127.0.0.1:8000"
        self._frontend_url = "http://localhost:3000"
        self._skip_frontend_build = False
        self._skip_dependency_audit = False

    def with_repo_root(self, value: str) -> "AgentRunPlanBuilder":
        self._repo_root = Path(value).resolve()
        return self

    def with_report_dir(self, value: str) -> "AgentRunPlanBuilder":
        self._report_dir = Path(value).resolve() if value else None
        return self

    def with_agent(self, value: str) -> "AgentRunPlanBuilder":
        self._agent = value
        return self

    def with_backend_url(self, value: str) -> "AgentRunPlanBuilder":
        self._backend_url = value.rstrip("/")
        return self

    def with_frontend_url(self, value: str) -> "AgentRunPlanBuilder":
        self._frontend_url = value.rstrip("/")
        return self

    def with_skip_frontend_build(self, value: bool) -> "AgentRunPlanBuilder":
        self._skip_frontend_build = value
        return self

    def with_skip_dependency_audit(self, value: bool) -> "AgentRunPlanBuilder":
        self._skip_dependency_audit = value
        return self

    def build(self) -> AgentRunPlan:
        if self._repo_root is None:
            raise ValueError("repo root is required")

        report_dir = self._report_dir or self._repo_root / "agents" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)

        context = AgentContext(
            repo_root=str(self._repo_root),
            backend_url=self._backend_url,
            frontend_url=self._frontend_url,
            report_dir=str(report_dir),
            skip_frontend_build=self._skip_frontend_build,
            skip_dependency_audit=self._skip_dependency_audit,
        )
        selected_agents = AGENT_GROUPS.get(self._agent, [self._agent])
        return AgentRunPlan(context=context, selected_agents=selected_agents)
