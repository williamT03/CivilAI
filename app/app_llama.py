from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from llama_index.core import StorageContext, load_index_from_storage
from llama_index.core.prompts import PromptTemplate
from LlamaIndexRAG.config import embed_model, llm, STORAGE_DIR

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Load persisted index once at startup ──────────────────────────────────────
storage_context = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
index = load_index_from_storage(storage_context, embed_model=embed_model)

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

# Build the query engine with the custom prompt
query_engine = index.as_query_engine(
    llm=llm,
    text_qa_template=QA_PROMPT,
    similarity_top_k=5,
)


@app.get("/query")
def query(q: str):
    response = query_engine.query(q)
    return {
        "answer": str(response),
        "system": "llamaindex",
    }