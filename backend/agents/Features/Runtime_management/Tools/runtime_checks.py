from __future__ import annotations

from collections.abc import Callable

from backend.agents.Features.Runner_management.Tools.models import CheckResult

from .http import HttpResponse, request

ResultFactory = Callable[..., CheckResult]


def request_or_result(
    method: str,
    url: str,
    on_error: ResultFactory,
    result_name: str,
    summary: str,
    **kwargs,
) -> HttpResponse | CheckResult:
    """Run an HTTP request and convert connectivity failures into a check result."""

    try:
        return request(method, url, **kwargs)
    except ConnectionError as exc:
        return on_error(result_name, summary, error=str(exc))


def has_status(response: HttpResponse, allowed: set[int]) -> bool:
    return response.status in allowed
