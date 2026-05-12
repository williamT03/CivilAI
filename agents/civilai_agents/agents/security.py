from __future__ import annotations

import re
from pathlib import Path

from ..base import BaseAgent
from ..commands import run_command
from ..http import request
from ..models import CheckResult


class SecurityAgent(BaseAgent):
    name = "security"
    description = "Security checks for secrets, auth guardrails, headers, and dependency audit support."

    def run(self) -> list[CheckResult]:
        return [
            self._check_env_gitignore(),
            self._check_jwt_secret_configuration(),
            self._check_password_policy(),
            self._check_api_key_hashing(),
            self._check_security_headers(),
            self._check_protected_route_requires_auth(),
            self._check_dependency_audit(),
        ]

    def _check_env_gitignore(self) -> CheckResult:
        gitignore = self.repo_root / ".gitignore"
        if not gitignore.exists():
            return self.fail_result("env-gitignore", ".gitignore is missing.")

        text = gitignore.read_text(encoding="utf-8", errors="replace")
        ignored = ".env" in {line.strip() for line in text.splitlines()}
        if ignored:
            return self.pass_result("env-gitignore", ".env is ignored by git.")
        return self.fail_result("env-gitignore", ".env should be ignored by git.")

    def _check_jwt_secret_configuration(self) -> CheckResult:
        auth_file = self.repo_root / "backend" / "app" / "auth.py"
        text = auth_file.read_text(encoding="utf-8", errors="replace")
        if 'os.getenv("JWT_SECRET_KEY", secrets.token_hex(32))' in text:
            return self.warn_result(
                "jwt-secret",
                "JWT secret falls back to a random runtime value; good for local safety, risky for production restarts.",
                recommendation="Require JWT_SECRET_KEY in production environment validation.",
            )
        if "JWT_SECRET_KEY" in text:
            return self.pass_result("jwt-secret", "JWT secret is configurable.")
        return self.fail_result("jwt-secret", "JWT secret configuration was not found.")

    def _check_password_policy(self) -> CheckResult:
        auth_file = self.repo_root / "backend" / "app" / "auth.py"
        text = auth_file.read_text(encoding="utf-8", errors="replace")
        required_patterns = [r"min_length=8", r"\[A-Z\]", r"\[a-z\]", r"\[0-9\]"]
        missing = [pattern for pattern in required_patterns if not re.search(pattern, text)]
        if missing:
            return self.fail_result("password-policy", "Password policy is missing expected strength checks.", missing=missing)
        return self.pass_result("password-policy", "Password policy requires length, uppercase, lowercase, and number.")

    def _check_api_key_hashing(self) -> CheckResult:
        auth_file = self.repo_root / "backend" / "app" / "auth.py"
        text = auth_file.read_text(encoding="utf-8", errors="replace")
        if "hashlib.sha256" in text and "key_hash" in text:
            return self.pass_result("api-key-storage", "API keys are stored as hashes with a visible prefix.")
        return self.fail_result("api-key-storage", "API key hashing was not found.")

    def _check_security_headers(self) -> CheckResult:
        try:
            response = request("GET", f"{self.context.backend_url}/health")
        except ConnectionError as exc:
            return self.skip_result("security-headers", "Backend is not reachable; runtime header check skipped.", error=str(exc))

        expected = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "strict-origin-when-cross-origin",
        }
        missing = {
            header: value
            for header, value in expected.items()
            if response.headers.get(header) != value
        }
        if missing:
            return self.fail_result("security-headers", "Backend response is missing expected security headers.", missing=missing)
        return self.pass_result("security-headers", "Backend sends expected security headers.")

    def _check_protected_route_requires_auth(self) -> CheckResult:
        try:
            response = request("GET", f"{self.context.backend_url}/api/auth/me")
        except ConnectionError as exc:
            return self.skip_result("auth-guard", "Backend is not reachable; protected route check skipped.", error=str(exc))

        if response.status == 401:
            return self.pass_result("auth-guard", "Protected auth route rejects unauthenticated requests.")
        return self.fail_result("auth-guard", "Protected auth route did not reject unauthenticated request.", status=response.status)

    def _check_dependency_audit(self) -> CheckResult:
        if self.context.skip_dependency_audit:
            return self.skip_result("dependency-audit", "Dependency audit skipped by flag.")

        python_exe = self.repo_root / ".venv" / "Scripts" / "python.exe"
        executable = str(python_exe) if python_exe.exists() else "python"
        result = run_command([executable, "-m", "pip_audit", "-r", "requirements.txt"], self.repo_root, timeout_seconds=180)

        if result.returncode == 0:
            return self.pass_result("dependency-audit", "pip-audit completed without known vulnerabilities.")

        combined = f"{result.stdout}\n{result.stderr}".strip()
        if "No module named pip_audit" in combined:
            return self.warn_result(
                "dependency-audit",
                "pip-audit is not installed, so dependency vulnerability scanning could not run.",
                install="python -m pip install pip-audit",
            )
        return self.fail_result("dependency-audit", "pip-audit reported issues or failed.", output=combined[-4000:])
