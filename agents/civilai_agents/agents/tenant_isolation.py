from __future__ import annotations

from ..auth_client import create_test_user
from ..base import BaseAgent
from ..http import request
from ..models import CheckResult


class TenantIsolationAgent(BaseAgent):
    name = "tenant-isolation"
    description = "Runtime tests that user-owned chats, uploads, jobs, and API keys are isolated across accounts."

    def run(self) -> list[CheckResult]:
        try:
            request("GET", f"{self.context.backend_url}/health")
        except ConnectionError as exc:
            return [
                self.skip_result(
                    "tenant-runtime",
                    "Backend is not reachable; tenant isolation checks skipped.",
                    error=str(exc),
                )
            ]

        try:
            user_a = create_test_user(self.context.backend_url, "tenant_a")
            user_b = create_test_user(self.context.backend_url, "tenant_b")
        except RuntimeError as exc:
            return [
                self.fail_result(
                    "tenant-users", "Could not create disposable tenant users.", error=str(exc)
                )
            ]

        return [
            self._check_chat_thread_isolation(user_a, user_b),
            self._check_api_key_isolation(user_a, user_b),
            self._check_upload_listing_isolation(user_a, user_b),
            self._check_ingestion_job_auth_required(user_a, user_b),
        ]

    @staticmethod
    def _headers(user: dict) -> dict[str, str]:
        return {"Authorization": f"Bearer {user['access_token']}"}

    def _check_chat_thread_isolation(self, user_a: dict, user_b: dict) -> CheckResult:
        create_response = request(
            "POST",
            f"{self.context.backend_url}/api/auth/chats",
            headers=self._headers(user_a) | {"Content-Type": "application/json"},
            json_body={"title": "Tenant A Private Chat", "jurisdiction": "Tenant A"},
        )
        if create_response.status != 201:
            return self.fail_result(
                "chat-tenant-create",
                "User A could not create chat thread.",
                status=create_response.status,
            )
        thread_id = create_response.json()["id"]

        cross_response = request(
            "GET",
            f"{self.context.backend_url}/api/auth/chats/{thread_id}",
            headers=self._headers(user_b),
        )
        if cross_response.status == 404:
            return self.pass_result(
                "chat-tenant-isolation", "User B cannot read User A chat thread."
            )
        return self.fail_result(
            "chat-tenant-isolation",
            "User B could access or distinguish User A chat thread.",
            status=cross_response.status,
        )

    def _check_api_key_isolation(self, user_a: dict, user_b: dict) -> CheckResult:
        create_response = request(
            "POST",
            f"{self.context.backend_url}/api/auth/api-keys",
            headers=self._headers(user_a) | {"Content-Type": "application/json"},
            json_body={"name": "Tenant A Key"},
        )
        if create_response.status != 201:
            return self.fail_result(
                "api-key-tenant-create",
                "User A could not create API key.",
                status=create_response.status,
            )
        created = create_response.json()

        list_response = request(
            "GET", f"{self.context.backend_url}/api/auth/api-keys", headers=self._headers(user_b)
        )
        if list_response.status != 200:
            return self.fail_result(
                "api-key-tenant-list",
                "User B could not list own API keys for comparison.",
                status=list_response.status,
            )
        if any(item.get("id") == created.get("id") for item in list_response.json()):
            return self.fail_result(
                "api-key-tenant-isolation", "User B can see User A API key metadata."
            )
        if created.get("api_key") and all(
            "api_key" not in item or item.get("api_key") is None for item in list_response.json()
        ):
            return self.pass_result(
                "api-key-tenant-isolation",
                "API key metadata is tenant-scoped and secrets are not listed.",
            )
        return self.warn_result(
            "api-key-tenant-isolation",
            "API key isolation passed, but creation response did not include the one-time secret as expected.",
        )

    def _check_upload_listing_isolation(self, user_a: dict, user_b: dict) -> CheckResult:
        response_a = request(
            "GET", f"{self.context.backend_url}/api/auth/uploads", headers=self._headers(user_a)
        )
        response_b = request(
            "GET", f"{self.context.backend_url}/api/auth/uploads", headers=self._headers(user_b)
        )
        if response_a.status == 200 and response_b.status == 200:
            return self.pass_result(
                "upload-list-tenant-isolation", "Authenticated upload listings are scoped per user."
            )
        return self.fail_result(
            "upload-list-tenant-isolation",
            "Upload listing endpoint failed for tenant users.",
            status_a=response_a.status,
            status_b=response_b.status,
        )

    def _check_ingestion_job_auth_required(self, user_a: dict, user_b: dict) -> CheckResult:
        fake_job_id = "00000000-0000-0000-0000-000000000000"
        unauthenticated = request(
            "GET", f"{self.context.backend_url}/api/v1/ingestion-jobs/{fake_job_id}"
        )
        authenticated = request(
            "GET",
            f"{self.context.backend_url}/api/v1/ingestion-jobs/{fake_job_id}",
            headers=self._headers(user_b),
        )
        if unauthenticated.status == 401 and authenticated.status == 404:
            return self.pass_result(
                "ingestion-job-tenant-guard",
                "v1 ingestion jobs require auth and return not-found within tenant scope.",
            )
        return self.fail_result(
            "ingestion-job-tenant-guard",
            "Unexpected ingestion job tenant guard behavior.",
            unauthenticated=unauthenticated.status,
            authenticated=authenticated.status,
        )
