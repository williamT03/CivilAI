from __future__ import annotations

import platform
import shutil

from ..base import BaseAgent
from ..commands import run_command
from ..models import CheckResult


class ServerRuntimeAgent(BaseAgent):
    name = "server-runtime"
    description = "Server deployment checks for systemd, Docker Compose, data directories, and deployment documentation."

    def run(self) -> list[CheckResult]:
        return [
            self._check_deploy_artifacts(),
            self._check_backend_data_directories(),
            self._check_systemd_service_template(),
            self._check_systemd_runtime_status(),
            self._check_cloudflared_runtime_status(),
            self._check_docker_compose_config(),
        ]

    def _check_deploy_artifacts(self) -> CheckResult:
        expected = [
            "DEPLOY_NOW.md",
            "docker-compose.yml",
            "docker-compose.server.yml",
            "deploy/civilai-backend.service",
            "deploy/nginx.conf",
        ]
        missing = [path for path in expected if not (self.repo_root / path).exists()]
        if missing:
            return self.fail_result(
                "deploy-artifacts", "Deployment artifacts are missing.", missing=missing
            )
        return self.pass_result("deploy-artifacts", "Expected deployment artifacts exist.")

    def _check_backend_data_directories(self) -> CheckResult:
        expected = [
            self.repo_root / "backend" / "Data",
            self.repo_root / "backend" / "Data" / "PDF",
        ]
        missing = [str(path) for path in expected if not path.exists()]
        if missing:
            return self.warn_result(
                "backend-data-dirs",
                "Backend data directories are missing; first parse/upload may need setup.",
                missing=missing,
            )
        return self.pass_result("backend-data-dirs", "Backend data directories exist.")

    def _check_systemd_service_template(self) -> CheckResult:
        service = self.repo_root / "deploy" / "civilai-backend.service"
        text = service.read_text(encoding="utf-8", errors="replace")
        expected = [
            "ExecStart=",
            "uvicorn backend.main:app",
            "--host 127.0.0.1",
            "--port 8000",
            "Restart=always",
        ]
        missing = [item for item in expected if item not in text]
        if missing:
            return self.fail_result(
                "systemd-template",
                "Backend systemd service template is missing expected settings.",
                missing=missing,
            )
        if "YOUR_LINUX_USER" in text:
            return self.warn_result(
                "systemd-template",
                "Systemd service is still a template; replace YOUR_LINUX_USER on the server.",
            )
        return self.pass_result(
            "systemd-template", "Systemd backend service template has expected settings."
        )

    def _check_systemd_runtime_status(self) -> CheckResult:
        if platform.system().lower() != "linux" or not shutil.which("systemctl"):
            return self.skip_result(
                "systemd-runtime", "systemctl is unavailable; server service status check skipped."
            )

        result = run_command(
            ["systemctl", "is-active", "civilai-backend"], self.repo_root, timeout_seconds=30
        )
        status = result.stdout.strip()
        if result.returncode == 0 and status == "active":
            return self.pass_result("systemd-runtime", "civilai-backend systemd service is active.")
        return self.warn_result(
            "systemd-runtime",
            "civilai-backend systemd service is not active.",
            status=status,
            stderr=result.stderr.strip(),
        )

    def _check_cloudflared_runtime_status(self) -> CheckResult:
        if platform.system().lower() != "linux" or not shutil.which("systemctl"):
            return self.skip_result(
                "cloudflared-runtime", "systemctl is unavailable; cloudflared status check skipped."
            )

        result = run_command(
            ["systemctl", "is-active", "cloudflared"], self.repo_root, timeout_seconds=30
        )
        status = result.stdout.strip()
        if result.returncode == 0 and status == "active":
            return self.pass_result("cloudflared-runtime", "cloudflared systemd service is active.")
        return self.warn_result(
            "cloudflared-runtime",
            "cloudflared systemd service is not active.",
            status=status,
            stderr=result.stderr.strip(),
        )

    def _check_docker_compose_config(self) -> CheckResult:
        docker = shutil.which("docker")
        if not docker:
            return self.skip_result(
                "docker-compose-config", "Docker is unavailable; compose config validation skipped."
            )

        result = run_command(
            [
                docker,
                "compose",
                "-f",
                "docker-compose.yml",
                "-f",
                "docker-compose.server.yml",
                "config",
                "--quiet",
            ],
            self.repo_root,
            timeout_seconds=120,
        )
        if result.returncode == 0:
            return self.pass_result(
                "docker-compose-config", "Docker Compose server configuration is valid."
            )
        return self.warn_result(
            "docker-compose-config",
            "Docker Compose server configuration could not be validated.",
            output=(result.stdout + result.stderr)[-2000:],
        )
