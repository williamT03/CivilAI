"""Readable agentic engineering feature entry points.

Imports are resolved lazily so running a concrete module with `python -m` does
not preload the same module through this facade.
"""

__all__ = [
    "AGENT_REGISTRY",
    "AgentRunPlanBuilder",
    "extract_report_failures",
    "run_agents",
]


def __getattr__(name: str):
    if name == "AGENT_REGISTRY":
        from backend.agents.Features.Checks_management.checks_run import AGENT_REGISTRY

        return AGENT_REGISTRY
    if name in {"AgentRunPlanBuilder", "run_agents"}:
        from backend.agents.Features.Runner_management import runner_run

        return getattr(runner_run, name)
    if name == "extract_report_failures":
        from backend.agents.Features.Reports_management.reports_run import (
            extract_report_failures,
        )

        return extract_report_failures
    raise AttributeError(f"module 'backend.agents.Features' has no attribute {name!r}")
