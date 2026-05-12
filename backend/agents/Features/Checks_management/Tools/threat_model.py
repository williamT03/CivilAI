from __future__ import annotations

from backend.agents.Features.Runner_management.Tools.base import BaseAgent
from backend.agents.Features.Runner_management.Tools.models import CheckResult
from backend.agents.Features.Static_management.Tools.static_checks import (
    auth_source_files,
    read_existing,
)


class ThreatModelAgent(BaseAgent):
    name = "threat-model"
    description = (
        "STRIDE-style checks for CivilAI auth, uploads, RAG, APIs, and deployment boundaries."
    )

    def run(self) -> list[CheckResult]:
        return [
            self._check_spoofing_controls(),
            self._check_tampering_controls(),
            self._check_repudiation_controls(),
            self._check_information_disclosure_controls(),
            self._check_denial_of_service_controls(),
            self._check_elevation_of_privilege_controls(),
        ]

    def _read(self, path: str) -> str:
        if path == "auth":
            return read_existing(auth_source_files(self.repo_root))
        return (self.repo_root / path).read_text(encoding="utf-8", errors="replace")

    def _check_spoofing_controls(self) -> CheckResult:
        auth = self._read("auth")
        expected = ["bcrypt", "jwt.decode", 'payload.type != "access"', "refresh_tokens"]
        missing = [item for item in expected if item not in auth]
        if missing:
            return self.fail_result(
                "stride-spoofing", "Authentication controls are incomplete.", missing=missing
            )
        return self.pass_result(
            "stride-spoofing",
            "Password hashing, JWT validation, token typing, and refresh storage exist.",
        )

    def _check_tampering_controls(self) -> CheckResult:
        custom = self._read("backend/Features/RAG_management/rag_api.py")
        storage = self._read("backend/Features/Storage_management/Tools/storage.py")
        expected = [
            "_safe_pdf_name",
            "_validate_pdf_signature",
            "checksum_sha256",
            "os.path.basename",
        ]
        combined = f"{custom}\n{storage}"
        missing = [item for item in expected if item not in combined]
        if missing:
            return self.fail_result(
                "stride-tampering", "Upload tampering controls are incomplete.", missing=missing
            )
        return self.pass_result(
            "stride-tampering",
            "Upload filename normalization, PDF signature, checksum, and basename controls exist.",
        )

    def _check_repudiation_controls(self) -> CheckResult:
        security = self._read("backend/Features/Runtime_management/Tools/security.py")
        auth = self._read("auth")
        if "audit_event" in security and "auth.login.success" in auth and "api_key.create" in auth:
            return self.pass_result(
                "stride-repudiation", "Security audit events exist for auth and API-key actions."
            )
        return self.fail_result(
            "stride-repudiation", "Security audit events are missing or incomplete."
        )

    def _check_information_disclosure_controls(self) -> CheckResult:
        security = self._read("backend/Features/Runtime_management/Tools/security.py")
        main = self._read("backend/Features/Runtime_management/backend_run.py")
        if "sanitize_detail" in security and "sanitized_http_exception_handler" in main:
            return self.pass_result(
                "stride-info-disclosure", "HTTP error detail sanitization is wired."
            )
        return self.fail_result(
            "stride-info-disclosure", "HTTP error detail sanitization is not wired."
        )

    def _check_denial_of_service_controls(self) -> CheckResult:
        main = self._read("backend/Features/Runtime_management/backend_run.py")
        config = self._read("backend/Features/Runtime_management/Config/Tools/settings.py")
        expected = ["max_request_bytes", "rate_limit_per_minute", "max_upload_bytes"]
        combined = f"{main}\n{config}"
        missing = [item for item in expected if item not in combined]
        if missing:
            return self.fail_result("stride-dos", "DoS guardrails are incomplete.", missing=missing)
        return self.pass_result(
            "stride-dos", "Request size, upload size, and rate-limit guardrails exist."
        )

    def _check_elevation_of_privilege_controls(self) -> CheckResult:
        auth = self._read("auth")
        expected = [
            "current_user: UserResponse = Depends(get_current_user)",
            "user_id=current_user.id",
            "api_keys.c.user_id == user_id",
        ]
        missing = [item for item in expected if item not in auth]
        if missing:
            return self.fail_result(
                "stride-eop", "Tenant/user ownership controls may be incomplete.", missing=missing
            )
        return self.pass_result(
            "stride-eop", "Protected routes and ownership filters are represented."
        )
