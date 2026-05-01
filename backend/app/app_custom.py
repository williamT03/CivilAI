from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Optional

import os
import re
import shutil
import subprocess
import sys
import threading
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from CustomRAG.LLM.rag import ask
from CustomRAG.db_scripts import ParserPipelineBuilder
from CustomRAG.tools import StructuredToolFactory

app = FastAPI(title="Civil AI — Custom RAG")
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PDF_DIR = os.path.join(PROJECT_ROOT, "Data", "PDF")
INDEX_LOCK = threading.Lock()
ENABLE_LLAMA_SERVER = os.getenv("ENABLE_LLAMA_SERVER", "false").lower() == "true"
TOOLKIT = StructuredToolFactory.create_toolkit()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/pdf", StaticFiles(directory=PDF_DIR), name="pdf")


def _safe_pdf_name(filename: str) -> str:
    base = os.path.basename(filename or "").strip()
    if not base:
        raise HTTPException(status_code=400, detail="A PDF filename is required.")
    safe = re.sub(r"[^A-Za-z0-9._ -]", "_", base)
    if not safe.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
    return safe
def _run_index_command(script_path: str, label: str) -> None:
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        raise HTTPException(
            status_code=500,
            detail=f"{label} failed. {details}" if details else f"{label} failed.",
        )


def _run_optional_llama_index() -> None:
    if not ENABLE_LLAMA_SERVER:
        return
    _run_index_command(os.path.join("LlamaIndexRAG", "build_index.py"), "LlamaIndex indexing")


def _run_custom_parse(pdf_path: str) -> dict:
    # Build the parser on demand so uploads always use the current storage pipeline.
    parser = ParserPipelineBuilder().build()
    return parser.parse_uploaded_pdf(pdf_path)


@app.get("/query")
def query(
    q:            str,
    jurisdiction: Optional[str] = Query(
        default=None,
        description="Filter by jurisdiction: 'cooper city', 'broward county', or omit for all"
    ),
):
    """
    Query the custom RAG system.

    Examples:
      /query?q=what+is+the+equipment+fund&jurisdiction=broward+county
      /query?q=general+penalty&jurisdiction=cooper+city
      /query?q=capital+improvements+fund   ← searches all jurisdictions
    """
    result = ask(q, jurisdiction=jurisdiction)
    return {
        "answer":       result["answer"],
        "accuracy":     result["accuracy"],
        "navigation":   result["navigation"],
        "system":       "custom",
        "jurisdiction": result["jurisdiction"],
        "sources":      result["sources"],
    }


@app.get("/jurisdictions")
def list_jurisdictions():
    return {"jurisdictions": TOOLKIT.list_jurisdictions()}


@app.get("/navigation-map")
def navigation_map():
    return TOOLKIT.get_navigation_map()


@app.get("/structure")
def structure(
    jurisdiction: Optional[str] = Query(
        default=None,
        description="Optional jurisdiction to return one structured document map.",
    ),
):
    full_map = TOOLKIT.get_navigation_map()
    if not jurisdiction:
        return full_map

    document_slug = TOOLKIT.resolve_document_slug(jurisdiction)
    if not document_slug:
        raise HTTPException(status_code=404, detail="Jurisdiction not found in structured map.")

    document = full_map.get("documents", {}).get(document_slug)
    if not document:
        raise HTTPException(status_code=404, detail="Structured document map not found.")

    return {
        "document_slug": document_slug,
        "document": document,
    }


@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    filename = _safe_pdf_name(file.filename or "")
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in {"application/pdf", "application/x-pdf"}:
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF.")

    os.makedirs(PDF_DIR, exist_ok=True)

    target_path = os.path.join(PDF_DIR, filename)
    name_root, ext = os.path.splitext(filename)
    suffix = 1
    while os.path.exists(target_path):
        target_path = os.path.join(PDF_DIR, f"{name_root}_{suffix}{ext}")
        suffix += 1

    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    with INDEX_LOCK:
        parse_result = _run_custom_parse(target_path)
        TOOLKIT.refresh_navigation_cache()
        _run_optional_llama_index()

    return {
        "message": "PDF uploaded and indexed successfully.",
        "filename": os.path.basename(target_path),
        "path": target_path,
        "parse_result": parse_result,
    }
