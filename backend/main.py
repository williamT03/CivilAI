import os
import sys
import logging
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
ENABLE_LLAMA_SERVER = os.getenv("ENABLE_LLAMA_SERVER", "false").lower() == "true"

for path in (CURRENT_DIR, PARENT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
except ImportError:  # pragma: no cover
    CONTENT_TYPE_LATEST = "text/plain"
    Counter = Histogram = None
    generate_latest = None

try:
    from backend.app.api.v1 import router as api_v1_router
    from backend.app.core.config import get_settings
    from backend.app.security import audit_event, sanitize_detail
except ImportError:
    from app.api.v1 import router as api_v1_router
    from app.core.config import get_settings
    from app.security import audit_event, sanitize_detail

try:
    from backend.app.app_custom import app as custom_app
except ImportError:
    from app.app_custom import app as custom_app

# Try to import auth module
auth_available = False
auth_router = None
try:
    try:
        from backend.app.auth import router as auth_router
    except ImportError:
        from app.auth import router as auth_router
    auth_available = True
except Exception as exc:
    logger.warning("Auth module could not be loaded: %s", exc)

llama_app = None
if ENABLE_LLAMA_SERVER:
    try:
        try:
            from backend.app.app_llama import app as llama_app
        except ImportError:
            from app.app_llama import app as llama_app
    except Exception as exc:
        logger.warning("LlamaIndex app could not be loaded: %s", exc)


settings = get_settings()
app = FastAPI(title="Civil AI Backend", version="1.0.0")

REQUEST_COUNT = Counter(
    "civilai_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
) if Counter else None
REQUEST_LATENCY = Histogram(
    "civilai_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
) if Histogram else None


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            latency = time.perf_counter() - start
            logger.exception("request_failed method=%s path=%s latency=%.4f", request.method, request.url.path, latency)
            raise

        latency = time.perf_counter() - start
        route_path = request.scope.get("route").path if request.scope.get("route") else request.url.path
        logger.info(
            "request_complete method=%s path=%s status=%s latency=%.4f",
            request.method,
            route_path,
            response.status_code,
            latency,
        )
        if REQUEST_COUNT:
            REQUEST_COUNT.labels(request.method, route_path, str(response.status_code)).inc()
        if REQUEST_LATENCY:
            REQUEST_LATENCY.labels(request.method, route_path).observe(latency)
        return response


class SecurityBoundaryMiddleware(BaseHTTPMiddleware):
    """Apply app-level request size, throttle, and security header guardrails."""

    def __init__(self, app, *, max_request_bytes: int, rate_limit_per_minute: int) -> None:
        super().__init__(app)
        self.max_request_bytes = max_request_bytes
        self.rate_limit_per_minute = rate_limit_per_minute
        self._request_times: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_request_bytes:
                    return Response("Request body too large\n", status_code=413, media_type="text/plain")
            except ValueError:
                return Response("Invalid Content-Length\n", status_code=400, media_type="text/plain")

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = self._request_times[client_ip]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.rate_limit_per_minute:
            audit_event("security.rate_limit", client_ip=client_ip, path=request.url.path)
            return Response("Rate limit exceeded\n", status_code=429, media_type="text/plain")
        window.append(now)

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SecurityBoundaryMiddleware,
    max_request_bytes=settings.max_request_bytes,
    rate_limit_per_minute=settings.rate_limit_per_minute,
)
app.add_middleware(RequestObservabilityMiddleware)


@app.exception_handler(HTTPException)
async def sanitized_http_exception_handler(request: Request, exc: HTTPException):
    exc.detail = sanitize_detail(exc.detail)
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def sanitized_validation_exception_handler(request: Request, exc: RequestValidationError):
    return await request_validation_exception_handler(request, exc)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "custom_api": True,
        "llama_api": llama_app is not None,
        "auth_api": auth_available,
        "api_version": "v1",
    }


@app.get("/metrics")
def metrics():
    if generate_latest is None:
        return Response("prometheus-client is not installed\n", media_type="text/plain", status_code=503)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Include auth router at `/api/auth/...` so the frontend can share one stable
# backend contract alongside the mounted custom and llama apps.
if auth_available:
    app.include_router(auth_router, prefix="/api")

app.include_router(api_v1_router)
app.mount("/api/custom", custom_app)
if llama_app is not None:
    app.mount("/api/llama", llama_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
