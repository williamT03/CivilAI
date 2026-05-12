"""Compatibility entry point for ASGI servers.

The real backend runtime now lives in `backend.Features.Runtime_management.backend_run`.
Keep this tiny module so older commands that still import `backend.main`
continue to work while the implementation stays in the feature tree.
"""

from backend.Features.Runtime_management.backend_run import app

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.Features.Runtime_management.backend_run:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
