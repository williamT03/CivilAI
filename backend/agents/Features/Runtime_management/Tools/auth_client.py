from __future__ import annotations

import uuid
from dataclasses import dataclass

from .http import request


@dataclass(frozen=True)
class TestUser:
    username: str
    password: str
    email: str
    access_token: str
    refresh_token: str

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


def create_test_user(backend_url: str, prefix: str = "agent") -> TestUser:
    suffix = uuid.uuid4().hex[:10]
    username = f"{prefix}_{suffix}"
    password = "AgentPass123"
    email = f"{username}@example.test"

    register_response = request(
        "POST",
        f"{backend_url}/api/auth/register",
        json_body={
            "email": email,
            "username": username,
            "password": password,
            "full_name": "Agent Test User",
            "jurisdiction": "Agent Test",
        },
    )
    if register_response.status != 201:
        raise RuntimeError(
            f"register failed: {register_response.status} {register_response.body[:500]}"
        )

    login_response = request(
        "POST",
        f"{backend_url}/api/auth/login",
        form_body={"username": username, "password": password},
    )
    if login_response.status != 200:
        raise RuntimeError(f"login failed: {login_response.status} {login_response.body[:500]}")

    tokens = login_response.json()
    return TestUser(
        username=username,
        password=password,
        email=email,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
    )
