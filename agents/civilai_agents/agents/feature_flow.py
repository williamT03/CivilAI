from __future__ import annotations

from pathlib import Path

from ..base import BaseAgent
from ..commands import run_command
from ..http import request
from ..models import CheckResult


class FeatureFlowAgent(BaseAgent):
    name = "feature-flow"
    description = "Frontend feature flow checks for routes, API config, lint/build health, and runtime reachability."

    def run(self) -> list[CheckResult]:
        return [
            self._check_frontend_routes(),
            self._check_api_config_defaults(),
            self._check_auth_context_token_handling(),
            self._check_frontend_lint(),
            self._check_frontend_build(),
            self._check_frontend_runtime(),
        ]

    @property
    def frontend_root(self) -> Path:
        return self.repo_root / "frontend" / "Website" / "civil-ai-web"

    def _check_frontend_routes(self) -> CheckResult:
        expected_routes = {
            "home": self.frontend_root / "app" / "page.tsx",
            "login": self.frontend_root / "app" / "login" / "page.tsx",
            "register": self.frontend_root / "app" / "register" / "page.tsx",
            "chat": self.frontend_root / "app" / "chat" / "page.tsx",
            "account": self.frontend_root / "app" / "account" / "page.tsx",
            "subscription": self.frontend_root / "app" / "subscription" / "page.tsx",
        }
        missing = [name for name, path in expected_routes.items() if not path.exists()]
        if missing:
            return self.fail_result(
                "frontend-routes", "Expected feature routes are missing.", missing=missing
            )
        return self.pass_result("frontend-routes", "Expected frontend feature routes exist.")

    def _check_api_config_defaults(self) -> CheckResult:
        config_file = self.frontend_root / "app" / "lib" / "apiConfig.ts"
        text = config_file.read_text(encoding="utf-8", errors="replace")
        expected = ["NEXT_PUBLIC_API_BASE", "/api/auth", "/api/custom", "/api/llama"]
        missing = [item for item in expected if item not in text]
        if missing:
            return self.fail_result(
                "api-config",
                "Frontend API config is missing expected base URL handling.",
                missing=missing,
            )
        return self.pass_result(
            "api-config", "Frontend API config exposes expected backend base URLs."
        )

    def _check_auth_context_token_handling(self) -> CheckResult:
        auth_context = self.frontend_root / "app" / "context" / "AuthContext.tsx"
        text = auth_context.read_text(encoding="utf-8", errors="replace")
        expected = ["access_token", "refresh_token", "localStorage", "logout"]
        missing = [item for item in expected if item not in text]
        if missing:
            return self.warn_result(
                "auth-context",
                "Auth context may be missing expected token flow pieces.",
                missing=missing,
            )
        return self.pass_result(
            "auth-context", "Auth context includes expected token persistence and logout pieces."
        )

    def _check_frontend_lint(self) -> CheckResult:
        try:
            result = run_command(["npm", "run", "lint"], self.frontend_root, timeout_seconds=180)
        except FileNotFoundError:
            return self.skip_result(
                "frontend-lint", "npm was not found on PATH; frontend lint skipped."
            )
        if result.returncode == 0:
            return self.pass_result("frontend-lint", "Frontend lint passes.")
        return self.fail_result(
            "frontend-lint", "Frontend lint failed.", output=(result.stdout + result.stderr)[-4000:]
        )

    def _check_frontend_build(self) -> CheckResult:
        if self.context.skip_frontend_build:
            return self.skip_result("frontend-build", "Frontend build skipped by flag.")
        try:
            result = run_command(["npm", "run", "build"], self.frontend_root, timeout_seconds=300)
        except FileNotFoundError:
            return self.skip_result(
                "frontend-build", "npm was not found on PATH; frontend build skipped."
            )
        if result.returncode == 0:
            return self.pass_result("frontend-build", "Frontend production build passes.")
        return self.fail_result(
            "frontend-build",
            "Frontend production build failed.",
            output=(result.stdout + result.stderr)[-4000:],
        )

    def _check_frontend_runtime(self) -> CheckResult:
        try:
            response = request("GET", self.context.frontend_url, timeout_seconds=10)
        except ConnectionError as exc:
            return self.skip_result(
                "frontend-runtime",
                "Frontend dev server is not reachable; browser-level flow check skipped.",
                error=str(exc),
            )

        if response.status == 200:
            return self.pass_result("frontend-runtime", "Frontend URL is reachable.")
        return self.fail_result(
            "frontend-runtime",
            "Frontend URL returned an unexpected status.",
            status=response.status,
        )
