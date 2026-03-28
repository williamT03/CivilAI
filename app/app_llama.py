from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from llama_index.core import StorageContext, load_index_from_storage
from llama_index.core.prompts import PromptTemplate
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.vector_stores import MetadataFilter, MetadataFilters
from LlamaIndexRAG.config import embed_model, llm, STORAGE_DIR

JURISDICTION_ALIASES = {
    "cooper city": "Cooper City, FL",
    "cooper": "Cooper City, FL",
    "broward": "Broward County, FL",
    "broward county": "Broward County, FL",
}


def resolve_jurisdiction(name: str | None) -> str | None:
    if name is None:
        return None
    key = name.lower().strip()
    return JURISDICTION_ALIASES.get(key, name)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

index = None
default_query_engine = None
_INDEX_STAMP = None


def _current_index_stamp():
    if not os.path.isdir(STORAGE_DIR):
        return None
    files = []
    for root, _, names in os.walk(STORAGE_DIR):
        for name in names:
            full_path = os.path.join(root, name)
            files.append((full_path, os.path.getmtime(full_path)))
    if not files:
        return None
    return tuple(sorted(files))


def load_index_resources(force: bool = False):
    global index, default_query_engine, _INDEX_STAMP

    stamp = _current_index_stamp()
    if stamp is None:
        raise FileNotFoundError("LlamaIndex storage is missing. Build the index first.")
    if not force and _INDEX_STAMP == stamp and index is not None and default_query_engine is not None:
        return

    storage_context = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
    index = load_index_from_storage(storage_context, embed_model=embed_model)
    default_query_engine = index.as_query_engine(
        llm=llm,
        text_qa_template=QA_PROMPT,
        similarity_top_k=5,
    )
    _INDEX_STAMP = stamp

QA_PROMPT = PromptTemplate(
    """You are a civil engineering assistant specialized in municipal codes.

Use the provided context to answer the question accurately.

Rules:
- Cite section and subsection when possible
- Be precise and technical
- Do NOT hallucinate

Context:
{context_str}

Question:
{query_str}

Answer:
"""
)

load_index_resources(force=True)


@app.get("/query")
def query(
    q: str,
    jurisdiction: str | None = Query(default=None),
):
    load_index_resources()
    resolved = resolve_jurisdiction(jurisdiction)
    if resolved:
        retriever = index.as_retriever(
            similarity_top_k=5,
            filters=MetadataFilters(
                filters=[MetadataFilter(key="jurisdiction", value=resolved)]
            ),
        )
        query_engine = RetrieverQueryEngine.from_args(
            retriever,
            llm=llm,
            text_qa_template=QA_PROMPT,
        )
    else:
        query_engine = default_query_engine

    response = query_engine.query(q)
    return {
        "answer": str(response),
        "system": "llamaindex",
        "jurisdiction": resolved,
    }
