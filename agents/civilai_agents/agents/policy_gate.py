from __future__ import annotations

from ..base import BaseAgent
from ..models import CheckResult


class PolicyGateAgent(BaseAgent):
    name = "policy-gate"
    description = "Static release policy gate for critical CivilAI security controls."

    def run(self) -> list[CheckResult]:
        return [
            self._gate("jwt-production-secret", "backend/app/auth.py", ["require_production_secret(\"JWT_SECRET_KEY\""]),
            self._gate("error-sanitization", "backend/main.py", ["sanitized_http_exception_handler", "sanitize_detail"]),
            self._gate("security-audit-logger", "backend/app/security.py", ["audit_event", "sanitize_detail"]),
            self._gate("tenant-chat-filter", "backend/app/auth.py", ["chat_threads.c.user_id == user_id"]),
            self._gate("tenant-api-key-filter", "backend/app/auth.py", ["api_keys.c.user_id == user_id"]),
            self._gate("upload-pdf-signature", "backend/app/app_custom.py", ["_validate_pdf_signature"]),
            self._gate("rate-limit", "backend/main.py", ["rate_limit_per_minute", "security.rate_limit"]),
        ]

    def _gate(self, name: str, path: str, required: list[str]) -> CheckResult:
        text = (self.repo_root / path).read_text(encoding="utf-8", errors="replace")
        missing = [item for item in required if item not in text]
        if missing:
            return self.fail_result(name, "Required policy control is missing.", file=path, missing=missing)
        return self.pass_result(name, "Required policy control is present.", file=path)
