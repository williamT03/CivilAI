from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from CustomRAG.LLM.rag import ask

app = FastAPI(title="Civil AI — Custom RAG")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        "system":       "custom",
        "jurisdiction": result["jurisdiction"],
        "sources":      result["sources"],
    }


@app.get("/jurisdictions")
def list_jurisdictions():
    """Returns all indexed jurisdictions."""
    from CustomRAG.retrieval import _JURISDICTION_IDX
    return {
        "jurisdictions": [
            {"name": name, "chunks": len(indices)}
            for name, indices in _JURISDICTION_IDX.items()
        ]
    }