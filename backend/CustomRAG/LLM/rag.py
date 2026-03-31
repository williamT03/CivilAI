import sys
import os
import re
from urllib.parse import quote
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from retrieval import hybrid_search, detect_section_filter, resolve_jurisdiction
from LLM.llm import generate_answer

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

CUSTOM_RAG_BASE_URL = os.getenv("CUSTOM_RAG_BASE_URL", "http://localhost:8001")


def _tokenize_query(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _estimate_accuracy(query: str, results: list[dict], jurisdiction: str | None) -> dict:
    if not results:
        return {
            "score": 0,
            "label": "Low",
            "reason": "No supporting code sections were retrieved for this query.",
        }

    query_terms = {t for t in _tokenize_query(query) if len(t) > 2}
    retrieved_text = " ".join(r["text"].lower() for r in results[:3])
    covered_terms = sum(1 for term in query_terms if term in retrieved_text)
    coverage = covered_terms / max(len(query_terms), 1)

    rerank_scores = [float(r.get("rerank_score", 0.0)) for r in results[:3]]
    rerank_strength = sum(rerank_scores) / max(len(rerank_scores), 1)

    support_count = min(len(results) / 5, 1.0)

    resolved_jurisdiction = resolve_jurisdiction(jurisdiction)
    target_section = detect_section_filter(query, resolved_jurisdiction)
    section_match = 0.75
    if target_section:
        top_sections = [r["meta"].get("section") for r in results[:3]]
        section_match = 1.0 if target_section in top_sections else 0.2

    raw_score = (
        0.45 * rerank_strength +
        0.30 * coverage +
        0.15 * support_count +
        0.10 * section_match
    )
    score = max(0, min(int(round(raw_score * 100)), 100))

    if score >= 80:
        label = "High"
    elif score >= 60:
        label = "Medium"
    else:
        label = "Low"

    if target_section and section_match >= 1.0:
        reason = f"Exact section match found for {target_section} with strong supporting text."
    elif coverage >= 0.7:
        reason = "Most of the key query terms appear in the top retrieved code sections."
    elif coverage >= 0.4:
        reason = "The retrieval partially matches the query, but the support is mixed."
    else:
        reason = "Only limited overlap was found between the query and the retrieved sections."

    return {"score": score, "label": label, "reason": reason}


def _build_source_link(meta: dict) -> str | None:
    source = meta.get("source")
    page = meta.get("page")
    if not source:
        return None
    url = f"{CUSTOM_RAG_BASE_URL}/pdf/{quote(source)}"
    if page:
        url += f"#page={page}"
    return url


def ask(query: str,
        top_k: int = 5,
        jurisdiction: str | None = None,
        debug: bool = False) -> dict:
    """
    Full RAG pipeline.

    Args:
        query        : natural language question
        top_k        : number of chunks to retrieve
        jurisdiction : optional filter — "cooper city", "broward county", or None for all
        debug        : print retrieval details to stdout

    Returns:
        {"answer": str, "sources": [...], "jurisdiction": str | None}
    """
    results = hybrid_search(
        query,
        top_k=top_k,
        jurisdiction=jurisdiction,
        verbose=debug,
    )

    if debug and results:
        print(f"\n🔍 Retrieved {len(results)} chunk(s)")
        for i, r in enumerate(results):
            m = r["meta"]
            print(f"  {i+1}. [{m.get('jurisdiction')}] "
                  f"{m.get('section')} {m.get('subsection') or '':6s}  "
                  f"score={r['score']:.4f}  page={m.get('page')}")

    answer = generate_answer(query, results)
    accuracy = _estimate_accuracy(query, results, jurisdiction)

    sources = [
        {
            "jurisdiction": r["meta"].get("jurisdiction"),
            "source":       r["meta"].get("source"),
            "section":      r["meta"].get("section"),
            "subsection":   r["meta"].get("subsection"),
            "title":        r["meta"].get("title"),
            "page":         r["meta"].get("page"),
            "score":        round(r["score"], 4),
            "url":          _build_source_link(r["meta"]),
        }
        for r in results
    ]

    return {
        "answer":       answer,
        "accuracy":     accuracy,
        "sources":      sources,
        "jurisdiction": jurisdiction,
    }


if __name__ == "__main__":
    print("Cooper City / Broward RAG  |  type 'exit' to quit")
    print("Prefix query with 'cooper:' or 'broward:' to filter jurisdiction\n")

    while True:
        try:
            raw = input("Ask: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if raw.lower() in ("exit", "quit", ""):
            break

        jur = None
        q   = raw
        if raw.lower().startswith("cooper:"):
            jur, q = "cooper city", raw[7:].strip()
        elif raw.lower().startswith("broward:"):
            jur, q = "broward county", raw[8:].strip()

        result = ask(q, jurisdiction=jur, debug=True)

        print(f"\n💬 ANSWER:\n{result['answer']}\n")
        print("📎 Sources:")
        for s in result["sources"]:
            print(f"  [{s['jurisdiction']}] "
                  f"{s['section']} {s.get('subsection') or ''}  "
                  f"(page {s['page']})")
        print()
