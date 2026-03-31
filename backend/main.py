import os
import sys

from fastapi import FastAPI

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)

for path in (CURRENT_DIR, PARENT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from backend.app.app_custom import app as custom_app
    from backend.app.app_llama import app as llama_app
except ImportError:
    from app.app_custom import app as custom_app
    from app.app_llama import app as llama_app


app = FastAPI(title="Civil AI Backend")


@app.get("/health")
def health():
    return {"status": "ok"}


app.mount("/api/custom", custom_app)
app.mount("/api/llama", llama_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
