import os
import sys
import logging

from fastapi import FastAPI

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
ENABLE_LLAMA_SERVER = os.getenv("ENABLE_LLAMA_SERVER", "false").lower() == "true"

for path in (CURRENT_DIR, PARENT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from backend.app.app_custom import app as custom_app
except ImportError:
    from app.app_custom import app as custom_app

llama_app = None
if ENABLE_LLAMA_SERVER:
    try:
        try:
            from backend.app.app_llama import app as llama_app
        except ImportError:
            from app.app_llama import app as llama_app
    except Exception as exc:
        logger.warning("LlamaIndex app could not be loaded: %s", exc)


app = FastAPI(title="Civil AI Backend")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "custom_api": True,
        "llama_api": llama_app is not None,
    }


app.mount("/api/custom", custom_app)
if llama_app is not None:
    app.mount("/api/llama", llama_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
