from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: str
    headers: dict[str, str]

    def json(self):
        return json.loads(self.body) if self.body else None


def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict | None = None,
    form_body: dict | None = None,
    timeout_seconds: int = 10,
) -> HttpResponse:
    payload = None
    request_headers = dict(headers or {})

    if json_body is not None:
        payload = json.dumps(json_body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    elif form_body is not None:
        payload = urlencode(form_body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    req = Request(url, data=payload, headers=request_headers, method=method.upper())
    try:
        with urlopen(req, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
            return HttpResponse(status=response.status, body=body, headers=dict(response.headers.items()))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return HttpResponse(status=exc.code, body=body, headers=dict(exc.headers.items()))
    except URLError as exc:
        raise ConnectionError(str(exc.reason)) from exc
