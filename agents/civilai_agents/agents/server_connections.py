from __future__ import annotations

from ..base import BaseAgent
from ..http import request
from ..models import CheckResult


class ServerConnectionsAgent(BaseAgent):
    name = "server-connections"
    description = "Runtime checks for backend API wiring, CORS, custom RAG endpoints, metrics, and auth connections."

    def run(self) -> list[CheckResult]:
        results: list[CheckResult] = []
        if not self._check_backend_health(results):
            return results

        results.extend(
            [
                self._check_v1_health_runtime_settings(),
                self._check_custom_jurisdictions(),
                self._check_custom_navigation_map(),
                self._check_metrics_endpoint(),
                self._check_cors_preflight(),
                self._check_auth_database_write_path(),
                self._check_frontend_reachable(),
            ]
        )
        return results

    def _check_backend_health(self, results: list[CheckResult]) -> bool:
        try:
            response = request("GET", f"{self.context.backend_url}/health")
        except ConnectionError as exc:
            results.append(self.fail_result("server-backend-health", "Backend server is not reachable.", error=str(exc)))
            return False

        if response.status != 200:
            results.append(self.fail_result("server-backend-health", "Backend health returned unexpected status.", status=response.status))
            return False

        data = response.json()
        if data.get("status") != "ok":
            results.append(self.fail_result("server-backend-health", "Backend health payload is not ok.", payload=data))
            return False

        results.append(self.pass_result("server-backend-health", "Backend server health is ok."))
        return True

    def _check_v1_health_runtime_settings(self) -> CheckResult:
        try:
            response = request("GET", f"{self.context.backend_url}/api/v1/health")
        except ConnectionError as exc:
            return self.fail_result("server-v1-health", "v1 health endpoint timed out or was unreachable.", error=str(exc))
        if response.status != 200:
            return self.fail_result("server-v1-health", "v1 health endpoint is not reachable.", status=response.status)

        data = response.json()
        expected_fields = ["environment", "ai_default_provider", "vector_store_backend", "async_ingestion_enabled"]
        missing = [field for field in expected_fields if field not in data]
        if missing:
            return self.fail_result("server-v1-health", "v1 health is missing runtime settings.", missing=missing)
        return self.pass_result("server-v1-health", "v1 health exposes expected runtime settings.", settings={field: data[field] for field in expected_fields})

    def _check_custom_jurisdictions(self) -> CheckResult:
        try:
            response = request("GET", f"{self.context.backend_url}/api/custom/jurisdictions")
        except ConnectionError as exc:
            return self.warn_result("custom-jurisdictions", "Custom jurisdictions endpoint timed out or was unreachable.", error=str(exc))
        if response.status != 200:
            return self.fail_result("custom-jurisdictions", "Custom jurisdictions endpoint failed.", status=response.status)
        data = response.json()
        jurisdictions = data.get("jurisdictions", [])
        if not isinstance(jurisdictions, list):
            return self.fail_result("custom-jurisdictions", "Jurisdictions payload is not a list.", payload=data)
        if not jurisdictions:
            return self.warn_result("custom-jurisdictions", "Jurisdictions endpoint works but returned no indexed jurisdictions.")
        return self.pass_result("custom-jurisdictions", "Jurisdictions endpoint returns indexed options.", count=len(jurisdictions))

    def _check_custom_navigation_map(self) -> CheckResult:
        try:
            response = request("GET", f"{self.context.backend_url}/api/custom/navigation-map")
        except ConnectionError as exc:
            return self.warn_result("custom-navigation-map", "Navigation map endpoint timed out or was unreachable.", error=str(exc))
        if response.status != 200:
            return self.fail_result("custom-navigation-map", "Navigation map endpoint failed.", status=response.status)
        data = response.json()
        if "documents" not in data:
            return self.warn_result("custom-navigation-map", "Navigation map responded but did not include documents.", keys=sorted(data.keys()))
        return self.pass_result("custom-navigation-map", "Navigation map endpoint returns document structure.", document_count=len(data.get("documents", {})))

    def _check_metrics_endpoint(self) -> CheckResult:
        try:
            response = request("GET", f"{self.context.backend_url}/metrics")
        except ConnectionError as exc:
            return self.warn_result("metrics", "Metrics endpoint timed out or was unreachable.", error=str(exc))
        if response.status == 200 and "civilai_http_requests_total" in response.body:
            return self.pass_result("metrics", "Prometheus metrics endpoint is available.")
        if response.status == 503:
            return self.warn_result("metrics", "Metrics endpoint exists but prometheus-client is unavailable.")
        return self.fail_result("metrics", "Metrics endpoint returned unexpected response.", status=response.status)

    def _check_cors_preflight(self) -> CheckResult:
        try:
            response = request(
                "OPTIONS",
                f"{self.context.backend_url}/api/v1/health",
                headers={
                    "Origin": self.context.frontend_url,
                    "Access-Control-Request-Method": "GET",
                },
            )
        except ConnectionError as exc:
            return self.fail_result("cors-preflight", "CORS preflight timed out or was unreachable.", error=str(exc))
        if response.status not in {200, 204}:
            return self.fail_result("cors-preflight", "CORS preflight failed for configured frontend URL.", status=response.status)
        allow_origin = response.headers.get("Access-Control-Allow-Origin")
        if not allow_origin:
            return self.fail_result("cors-preflight", "CORS preflight did not return Access-Control-Allow-Origin.")
        return self.pass_result("cors-preflight", "CORS accepts the configured frontend URL.", allow_origin=allow_origin)

    def _check_auth_database_write_path(self) -> CheckResult:
        try:
            response = request(
                "POST",
                f"{self.context.backend_url}/api/auth/register",
                json_body={"email": "bad-email", "username": "x", "password": "weak"},
            )
        except ConnectionError as exc:
            return self.fail_result("auth-db-route", "Auth validation route timed out or was unreachable.", error=str(exc))
        if response.status == 422:
            return self.pass_result("auth-db-route", "Auth route is mounted and validation works before writes.")
        return self.fail_result("auth-db-route", "Auth validation route returned unexpected status.", status=response.status)

    def _check_frontend_reachable(self) -> CheckResult:
        try:
            response = request("GET", self.context.frontend_url)
        except ConnectionError as exc:
            return self.skip_result("frontend-public-url", "Frontend URL is not reachable from this environment.", error=str(exc))

        if response.status == 200:
            return self.pass_result("frontend-public-url", "Frontend URL is reachable from the server test environment.")
        return self.warn_result("frontend-public-url", "Frontend URL returned unexpected status.", status=response.status)
