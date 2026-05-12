from __future__ import annotations

from ..base import BaseAgent
from ..models import CheckResult
from ..static_checks import auth_source_files, read_existing


class AuditLogAgent(BaseAgent):
    name = "audit-log"
    description = "Static coverage checks for security audit events across auth, uploads, queries, API keys, and rate limits."

    REQUIRED_EVENTS = {
        "auth.register.success": "auth",
        "auth.login.success": "auth",
        "auth.login.failure": "auth",
        "auth.refresh.success": "auth",
        "auth.logout": "auth",
        "api_key.create": "auth",
        "api_key.revoke.success": "auth",
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
            if path == "auth":
                text = read_existing(auth_source_files(self.repo_root))
            else:
                text = (self.repo_root / path).read_text(encoding="utf-8", errors="replace")
            if event in text:
                results.append(self.pass_result(f"audit-{event}", f"{event} is logged."))
            else:
                results.append(
                    self.fail_result(f"audit-{event}", f"{event} is not logged.", file=path)
                )
        return results
