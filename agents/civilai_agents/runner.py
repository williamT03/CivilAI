from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .agents import AGENT_REGISTRY
from .models import AgentContext, AgentReport, CheckStatus

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CivilAI agentic engineering checks.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--agent", choices=[*AGENT_GROUPS.keys(), *AGENT_REGISTRY.keys()], default="all")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    parser.add_argument("--frontend-url", default="http://localhost:3000")
    parser.add_argument("--report-dir", default="")
    parser.add_argument("--skip-frontend-build", action="store_true")
    parser.add_argument("--skip-dependency-audit", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    report_dir = Path(args.report_dir).resolve() if args.report_dir else repo_root / "agents" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    context = AgentContext(
        repo_root=str(repo_root),
        backend_url=args.backend_url.rstrip("/"),
        frontend_url=args.frontend_url.rstrip("/"),
        report_dir=str(report_dir),
        skip_frontend_build=args.skip_frontend_build,
        skip_dependency_audit=args.skip_dependency_audit,
    )

    selected = AGENT_GROUPS.get(args.agent, [args.agent])
    overall_results = []

    for agent_name in selected:
        agent = AGENT_REGISTRY[agent_name](context)
        print(f"\n[{agent.name}] {agent.description}")
        results = agent.run()
        overall_results.extend(results)
        report = AgentReport.from_results(agent.name, results)
        report_path = report_dir / f"{agent.name}.json"
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

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
