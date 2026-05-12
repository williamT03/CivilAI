from __future__ import annotations

from ..base import BaseAgent
from ..http import request
from ..models import CheckResult


class DeploymentGateAgent(BaseAgent):
    name = "deployment-gate"
    description = "Server release gate for production secrets, service health, CORS, security headers, and deploy config."

    def run(self) -> list[CheckResult]:
        return [
            self._check_jwt_secret_enforced(),
            self._check_env_example_documents_secret(),
            self._check_backend_health(),
            self._check_security_headers_runtime(),
            self._check_cors_not_wildcard_static(),
            self._check_systemd_template_not_placeholder(),
        ]

    def _check_jwt_secret_enforced(self) -> CheckResult:
        auth = (self.repo_root / "backend" / "app" / "auth.py").read_text(
            encoding="utf-8", errors="replace"
        )
        if "require_production_secret" in auth and '"JWT_SECRET_KEY"' in auth:
            return self.pass_result(
                "gate-jwt-secret", "JWT_SECRET_KEY is required in production/server environments."
            )
        return self.fail_result(
            "gate-jwt-secret", "JWT_SECRET_KEY is not enforced for production/server environments."
        )

    def _check_env_example_documents_secret(self) -> CheckResult:
        env_example = self.repo_root / ".env.example"
        if not env_example.exists():
            return self.warn_result("gate-env-example", ".env.example is missing.")
        text = env_example.read_text(encoding="utf-8", errors="replace")
        if "JWT_SECRET_KEY" in text:
            return self.pass_result("gate-env-example", ".env.example documents JWT_SECRET_KEY.")
        return self.warn_result(
            "gate-env-example", ".env.example should document JWT_SECRET_KEY for production."
        )

    def _check_backend_health(self) -> CheckResult:
        try:
            response = request("GET", f"{self.context.backend_url}/health")
        except ConnectionError as exc:
            return self.skip_result(
                "gate-backend-health",
                "Backend is not reachable from this environment.",
                error=str(exc),
            )
        if response.status == 200 and response.json().get("status") == "ok":
            return self.pass_result("gate-backend-health", "Backend health is ok.")
        return self.fail_result(
            "gate-backend-health", "Backend health is not ok.", status=response.status
        )

    def _check_security_headers_runtime(self) -> CheckResult:
        try:
            response = request("GET", f"{self.context.backend_url}/health")
        except ConnectionError as exc:
            return self.skip_result(
                "gate-security-headers",
                "Backend is not reachable; header gate skipped.",
                error=str(exc),
            )
        missing = [
            header
            for header in ["X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy"]
            if not response.header(header)
        ]
        if missing:
            return self.fail_result(
                "gate-security-headers",
                "Backend is missing required security headers.",
                missing=missing,
            )
        return self.pass_result("gate-security-headers", "Backend sends required security headers.")

    def _check_cors_not_wildcard_static(self) -> CheckResult:
        config = (self.repo_root / "backend" / "app" / "core" / "config.py").read_text(
            encoding="utf-8", errors="replace"
        )
        if 'allow_origins=["*"]' in config or 'CORS_ALLOW_ORIGINS", "*"' in config:
            return self.fail_result("gate-cors", "CORS appears to allow wildcard origins.")
        return self.pass_result("gate-cors", "CORS defaults are not wildcard-open.")

    def _check_systemd_template_not_placeholder(self) -> CheckResult:
        service = (self.repo_root / "deploy" / "civilai-backend.service").read_text(
            encoding="utf-8", errors="replace"
        )
        if "YOUR_LINUX_USER" in service:
            return self.warn_result(
                "gate-systemd-template",
                "Systemd template still contains YOUR_LINUX_USER; replace on the server before release.",
            )
        return self.pass_result("gate-systemd-template", "Systemd service has no user placeholder.")
