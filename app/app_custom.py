from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from CustomRAG.LLM.rag import ask

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/query")
def query(q: str):
    # ask() now returns {"answer": ..., "sources": [...]}
    # No double-retrieval — everything happens inside ask()
    result = ask(q)
    return {
        "answer":  result["answer"],
        "system":  "custom",
        "sources": result["sources"],
    }