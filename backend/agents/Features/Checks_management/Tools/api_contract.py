from __future__ import annotations

from backend.agents.Features.Runner_management.Tools.base import BaseAgent
from backend.agents.Features.Runner_management.Tools.models import CheckResult
from backend.agents.Features.Runtime_management.Tools.auth_client import create_test_user
from backend.agents.Features.Runtime_management.Tools.http import request


class ApiContractAgent(BaseAgent):
    name = "api-contract"
    description = (
        "Backend API contract smoke tests for health, auth, validation, and protected routes."
    )

    def run(self) -> list[CheckResult]:
        results: list[CheckResult] = []
        if not self._backend_available(results):
            return results

        results.extend(
            [
                self._check_v1_health_schema(),
                self._check_register_validation(),
                self._check_login_rejects_bad_credentials(),
                self._check_query_validation(),
                self._check_signed_upload_requires_auth(),
                self._check_subscription_usage_requires_auth(),
            ]
        )
        results.extend(self._check_auth_happy_path())
        return results

    def _backend_available(self, results: list[CheckResult]) -> bool:
        try:
            response = request("GET", f"{self.context.backend_url}/health")
        except ConnectionError as exc:
            results.append(
                self.fail_result(
                    "backend-availability", "Backend is not reachable.", error=str(exc)
                )
            )
            return False

        if response.status != 200:
            results.append(
                self.fail_result(
                    "backend-availability",
                    "Backend health endpoint is not healthy.",
                    status=response.status,
                )
            )
            return False

        results.append(self.pass_result("backend-availability", "Backend is reachable."))
        return True

    def _check_v1_health_schema(self) -> CheckResult:
        response = request("GET", f"{self.context.backend_url}/api/v1/health")
        if response.status != 200:
            return self.fail_result(
                "v1-health", "v1 health endpoint failed.", status=response.status
            )
        data = response.json()
        required = {"status", "api_version", "environment", "vector_store_backend"}
        missing = sorted(required - set(data.keys()))
        if missing:
            return self.fail_result(
                "v1-health", "v1 health response is missing fields.", missing=missing
            )
        return self.pass_result(
            "v1-health", "v1 health response contains expected contract fields."
        )

    def _check_register_validation(self) -> CheckResult:
        response = request(
            "POST",
            f"{self.context.backend_url}/api/auth/register",
            json_body={"email": "not-an-email", "username": "x", "password": "weak"},
        )
        if response.status == 422:
            return self.pass_result(
                "register-validation", "Register endpoint rejects invalid payloads."
            )
        return self.fail_result(
            "register-validation",
            "Register endpoint did not return validation error.",
            status=response.status,
        )

    def _check_login_rejects_bad_credentials(self) -> CheckResult:
        response = request(
            "POST",
            f"{self.context.backend_url}/api/auth/login",
            form_body={"username": "missing-user", "password": "WrongPassword1"},
        )
        if response.status == 401:
            return self.pass_result("login-negative", "Login rejects bad credentials.")
        return self.fail_result(
            "login-negative", "Login did not reject bad credentials.", status=response.status
        )

    def _check_query_validation(self) -> CheckResult:
        response = request(
            "POST",
            f"{self.context.backend_url}/api/v1/query",
            json_body={"question": "", "top_k": 99},
        )
        if response.status == 422:
            return self.pass_result(
                "query-validation", "Query endpoint rejects invalid request shape."
            )
        return self.fail_result(
            "query-validation",
            "Query endpoint did not reject invalid request shape.",
            status=response.status,
        )

    def _check_signed_upload_requires_auth(self) -> CheckResult:
        response = request(
            "POST",
            f"{self.context.backend_url}/api/v1/uploads/signed-url",
            json_body={"filename": "ordinance.pdf"},
        )
        if response.status == 401:
            return self.pass_result("signed-upload-auth", "Signed upload endpoint requires auth.")
        return self.fail_result(
            "signed-upload-auth",
            "Signed upload endpoint did not require auth.",
            status=response.status,
        )

    def _check_subscription_usage_requires_auth(self) -> CheckResult:
        response = request("GET", f"{self.context.backend_url}/api/v1/subscription/usage")
        if response.status == 401:
            return self.pass_result(
                "subscription-usage-auth", "Subscription usage endpoint requires auth."
            )
        return self.fail_result(
            "subscription-usage-auth",
            "Subscription usage endpoint did not require auth.",
            status=response.status,
        )

    def _check_auth_happy_path(self) -> list[CheckResult]:
        try:
            test_user = create_test_user(self.context.backend_url, "agent_contract")
        except RuntimeError as exc:
            return [
                self.fail_result(
                    "auth-happy-path",
                    "Could not create and log in disposable test user.",
                    error=str(exc),
                )
            ]

        me_response = request(
            "GET",
            f"{self.context.backend_url}/api/auth/me",
            headers=test_user.auth_headers,
        )
        if me_response.status != 200:
            return [
                self.fail_result(
                    "auth-happy-path", "Authenticated /me check failed.", status=me_response.status
                )
            ]

        return [
            self.pass_result(
                "auth-happy-path", "Register, login, and authenticated /me flow works."
            )
        ]
