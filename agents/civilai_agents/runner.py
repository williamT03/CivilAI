from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict

from .agents import AGENT_REGISTRY
from .models import AgentReport, CheckResult, CheckStatus
from .run_plan import AGENT_GROUPS, AgentRunPlanBuilder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CivilAI agentic engineering checks.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument(
        "--agent", choices=[*AGENT_GROUPS.keys(), *AGENT_REGISTRY.keys()], default="all"
    )
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    parser.add_argument("--frontend-url", default="http://localhost:3000")
    parser.add_argument("--report-dir", default="")
    parser.add_argument("--skip-frontend-build", action="store_true")
    parser.add_argument("--skip-dependency-audit", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = (
        AgentRunPlanBuilder()
        .with_repo_root(args.repo_root)
        .with_report_dir(args.report_dir)
        .with_agent(args.agent)
        .with_backend_url(args.backend_url)
        .with_frontend_url(args.frontend_url)
        .with_skip_frontend_build(args.skip_frontend_build)
        .with_skip_dependency_audit(args.skip_dependency_audit)
        .build()
    )

    overall_results = []

    for agent_name in plan.selected_agents:
        agent = AGENT_REGISTRY[agent_name](plan.context)
        print(f"\n[{agent.name}] {agent.description}")
        try:
            results = agent.run()
        except Exception as exc:
            results = [
                CheckResult(
                    name="agent-exception",
                    status=CheckStatus.FAIL,
                    summary=f"{agent.name} crashed before completing.",
                    details={"error": repr(exc)},
                )
            ]
        overall_results.extend(results)
        report = AgentReport.from_results(agent.name, results)
        report_path = plan.context.report_path / f"{agent.name}.json"
        report_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")

        for result in results:
            print(f"  {result.status.value.upper():4} {result.name}: {result.summary}")
        print(f"  report: {report_path}")

    failed = [result for result in overall_results if result.status == CheckStatus.FAIL]
    warned = [result for result in overall_results if result.status == CheckStatus.WARN]
    skipped = [result for result in overall_results if result.status == CheckStatus.SKIP]

    print("\nSummary")
    print(f"  total: {len(overall_results)}")
    print(f"  failed: {len(failed)}")
    print(f"  warnings: {len(warned)}")
    print(f"  skipped: {len(skipped)}")

    if failed and os.getenv("CIVILAI_AGENT_EXIT_ZERO", "").lower() in {"1", "true", "yes"}:
        print("  exit: forced success by CIVILAI_AGENT_EXIT_ZERO")
        return 0

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
