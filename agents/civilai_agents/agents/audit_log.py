from __future__ import annotations

from ..base import BaseAgent
from ..models import CheckResult


class AuditLogAgent(BaseAgent):
    name = "audit-log"
    description = "Static coverage checks for security audit events across auth, uploads, queries, API keys, and rate limits."

    REQUIRED_EVENTS = {
        "auth.register.success": "backend/app/auth.py",
        "auth.login.success": "backend/app/auth.py",
        "auth.login.failure": "backend/app/auth.py",
        "auth.refresh.success": "backend/app/auth.py",
        "auth.logout": "backend/app/auth.py",
        "api_key.create": "backend/app/auth.py",
        "api_key.revoke.success": "backend/app/auth.py",
        "api.query": "backend/app/api/v1.py",
        "api.query.stream": "backend/app/api/v1.py",
        "custom.query": "backend/app/app_custom.py",
        "upload.pdf.start": "backend/app/app_custom.py",
        "upload.pdf.success": "backend/app/app_custom.py",
        "security.rate_limit": "backend/main.py",
    }

    def run(self) -> list[CheckResult]:
        results: list[CheckResult] = []
        for event, path in self.REQUIRED_EVENTS.items():
            text = (self.repo_root / path).read_text(encoding="utf-8", errors="replace")
            if event in text:
                results.append(self.pass_result(f"audit-{event}", f"{event} is logged."))
            else:
                results.append(
                    self.fail_result(f"audit-{event}", f"{event} is not logged.", file=path)
                )
        return results
