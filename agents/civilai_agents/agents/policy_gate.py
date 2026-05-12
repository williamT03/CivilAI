from __future__ import annotations

from ..base import BaseAgent
from ..models import CheckResult
from ..static_checks import auth_source_files, missing_strings, read_existing


class PolicyGateAgent(BaseAgent):
    name = "policy-gate"
    description = "Static release policy gate for critical CivilAI security controls."

    def run(self) -> list[CheckResult]:
        return [
            self._gate(
                "jwt-production-secret",
                "auth",
                ["require_production_secret", '"JWT_SECRET_KEY"'],
            ),
            self._gate(
                "error-sanitization",
                "backend/main.py",
                ["sanitized_http_exception_handler", "sanitize_detail"],
            ),
            self._gate(
                "security-audit-logger",
                "backend/app/security.py",
                ["audit_event", "sanitize_detail"],
            ),
            self._gate("tenant-chat-filter", "auth", ["chat_threads.c.user_id == user_id"]),
            self._gate("tenant-api-key-filter", "auth", ["api_keys.c.user_id == user_id"]),
            self._gate(
                "upload-pdf-signature", "backend/app/app_custom.py", ["_validate_pdf_signature"]
            ),
            self._gate(
                "rate-limit", "backend/main.py", ["rate_limit_per_minute", "security.rate_limit"]
            ),
        ]

    def _gate(self, name: str, path: str, required: list[str]) -> CheckResult:
        text = (
            read_existing(auth_source_files(self.repo_root))
            if path == "auth"
            else (self.repo_root / path).read_text(encoding="utf-8", errors="replace")
        )
        missing = missing_strings(text, required)
        if missing:
            return self.fail_result(
                name, "Required policy control is missing.", file=path, missing=missing
            )
        return self.pass_result(name, "Required policy control is present.", file=path)
