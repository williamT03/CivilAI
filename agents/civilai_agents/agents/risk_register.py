from __future__ import annotations

import json
from pathlib import Path

from ..base import BaseAgent
from ..models import CheckResult


class RiskRegisterAgent(BaseAgent):
    name = "risk-register"
    description = (
        "Maintains a living CivilAI risk register mapped to concrete tests and mitigations."
    )

    def run(self) -> list[CheckResult]:
        risks = [
            self._risk(
                "RISK-001",
                "JWT secret missing in production",
                "high",
                "backend/app/auth.py",
                "Require JWT_SECRET_KEY for production/server environments.",
                ["deployment-gate", "security"],
            ),
            self._risk(
                "RISK-002",
                "Cross-user chat or upload access",
                "critical",
                "backend/app/auth.py",
                "Tenant isolation tests for chats, uploads, jobs, and API keys.",
                ["tenant-isolation"],
            ),
            self._risk(
                "RISK-003",
                "Sensitive data leaks in API errors or frontend bundle",
                "high",
                "backend/main.py",
                "Sanitize HTTP details and scan frontend/server artifacts.",
                ["data-leak"],
            ),
            self._risk(
                "RISK-004",
                "Prompt injection or private context exfiltration",
                "high",
                "backend/app/api/v1.py",
                "Run opt-in LLM safety probes and keep answers grounded.",
                ["llm-safety"],
            ),
            self._risk(
                "RISK-005",
                "Missing security event audit trail",
                "medium",
                "backend/app/security.py",
                "Log auth, upload, API key, query, and rate-limit events.",
                ["audit-log"],
            ),
            self._risk(
                "RISK-006",
                "Server dependency or service drift",
                "medium",
                "docker-compose.yml",
                "Validate systemd, cloudflared, compose, health, and dependencies.",
                ["server-runtime", "server-connections"],
            ),
        ]
        report_path = Path(self.context.report_dir) / "risk-register.json"
        report_path.write_text(json.dumps({"risks": risks}, indent=2), encoding="utf-8")
        return [
            self.pass_result(
                "risk-register",
                "Risk register generated.",
                count=len(risks),
                report=str(report_path),
            )
        ]

    @staticmethod
    def _risk(
        risk_id: str, title: str, severity: str, area: str, mitigation: str, covered_by: list[str]
    ) -> dict:
        return {
            "id": risk_id,
            "title": title,
            "severity": severity,
            "area": area,
            "mitigation": mitigation,
            "covered_by_agents": covered_by,
            "status": "tracked",
        }
