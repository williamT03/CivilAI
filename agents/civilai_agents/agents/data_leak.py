from __future__ import annotations

import re

from ..base import BaseAgent
from ..http import request
from ..models import CheckResult
from ..static_checks import auth_source_files, read_existing

SECRET_PATTERNS = {
    "openai_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "civilai_api_key": re.compile(r"civ_[A-Za-z0-9_-]{20,}"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    "windows_path": re.compile(r"[A-Za-z]:\\Users\\"),
    "linux_path": re.compile(r"/(?:home|app|var)/[A-Za-z0-9_./-]+"),
}


class DataLeakAgent(BaseAgent):
    name = "data-leak"
    description = "Scans frontend, config examples, and runtime API errors for secrets and internal data leaks."

    def run(self) -> list[CheckResult]:
        return [
            self._check_committed_secret_patterns(),
            self._check_frontend_public_env_boundary(),
            self._check_runtime_error_sanitization(),
            self._check_api_key_listing_hides_secret(),
        ]

    def _scan_text(self, text: str) -> dict[str, int]:
        return {
            name: len(pattern.findall(text))
            for name, pattern in SECRET_PATTERNS.items()
            if pattern.findall(text)
        }

    def _check_committed_secret_patterns(self) -> CheckResult:
        candidates = [
            *self.repo_root.glob("*.md"),
            *self.repo_root.glob("*.yml"),
            *self.repo_root.glob("*.yaml"),
            *self.repo_root.glob("backend/app/**/*.py"),
            *self.repo_root.glob("frontend/Website/civil-ai-web/app/**/*.*"),
        ]
        findings: dict[str, dict[str, int]] = {}
        high_confidence: dict[str, dict[str, int]] = {}
        for path in candidates:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            matches = self._scan_text(text)
            if matches:
                relative = str(path.relative_to(self.repo_root))
                findings[relative] = matches
                critical_matches = {
                    name: count
                    for name, count in matches.items()
                    if name not in {"windows_path", "linux_path"}
                }
                if critical_matches:
                    high_confidence[relative] = critical_matches
        if high_confidence:
            return self.fail_result(
                "secret-pattern-scan",
                "Potential secrets or tokens found in committed text files.",
                findings=high_confidence,
            )
        if findings:
            return self.warn_result(
                "secret-pattern-scan",
                "Path-like strings found; review if these expose local/server layout.",
                findings=findings,
            )
        return self.pass_result(
            "secret-pattern-scan", "No obvious secret patterns found in committed text files."
        )

    def _check_frontend_public_env_boundary(self) -> CheckResult:
        config = (
            self.repo_root
            / "frontend"
            / "Website"
            / "civil-ai-web"
            / "app"
            / "lib"
            / "apiConfig.ts"
        ).read_text(encoding="utf-8", errors="replace")
        forbidden = ["OPENAI_API_KEY", "DEEPSEEK_API_KEY", "JWT_SECRET_KEY", "DATABASE_URL"]
        present = [item for item in forbidden if item in config]
        if present:
            return self.fail_result(
                "frontend-env-boundary",
                "Frontend config references private server environment variables.",
                present=present,
            )
        return self.pass_result(
            "frontend-env-boundary", "Frontend config only uses public API base variables."
        )

    def _check_runtime_error_sanitization(self) -> CheckResult:
        try:
            response = request(
                "GET",
                f"{self.context.backend_url}/api/custom/structure?jurisdiction=C:\\Users\\secret\\token=abc",
            )
        except ConnectionError as exc:
            return self.skip_result(
                "runtime-error-sanitization",
                "Backend is not reachable; runtime leak check skipped.",
                error=str(exc),
            )

        matches = self._scan_text(response.body)
        if matches:
            return self.fail_result(
                "runtime-error-sanitization",
                "Runtime error response leaked sensitive-looking detail.",
                matches=matches,
                status=response.status,
            )
        return self.pass_result(
            "runtime-error-sanitization",
            "Runtime error response did not expose obvious secret/path patterns.",
        )

    def _check_api_key_listing_hides_secret(self) -> CheckResult:
        auth_source = read_existing(auth_source_files(self.repo_root))
        if "api_key=None" in auth_source and "response.api_key = secret" in auth_source:
            return self.pass_result(
                "api-key-listing", "API key secret is only returned immediately after creation."
            )
        return self.fail_result("api-key-listing", "API key list response may expose full secrets.")
