import os
import re
import sys
from urllib.parse import quote

from dotenv import load_dotenv

CURRENT_DIR = os.path.dirname(__file__)
CUSTOM_RAG_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
BACKEND_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

for path in (CUSTOM_RAG_DIR, BACKEND_ROOT):
    if path not in sys.path:
        sys.path.append(path)

try:
    from CustomRAG.LLM.llm import generate_answer, stream_answer
    from CustomRAG.tools import StructuredToolFactory
except ImportError:
    from LLM.llm import generate_answer, stream_answer
    from tools import StructuredToolFactory

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

CUSTOM_RAG_BASE_URL = os.getenv("CUSTOM_RAG_BASE_URL", "http://localhost:8001")
TOOLKIT = StructuredToolFactory.create_toolkit()


# ---------------------------------------------------------------------------
# Accuracy helpers
# ---------------------------------------------------------------------------
# The old stack estimated confidence from reranker output. The new stack relies
# on a mix of exact tool hits, semantic score strength, and query-term coverage.


def _tokenize_query(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _estimate_accuracy(query: str, search_payload: dict) -> dict:
    results = search_payload.get("results", [])
    if not results:
        return {
            "score": 0,
            "label": "Low",
            "reason": "No supporting code sections were retrieved for this query.",
        }

    query_terms = {term for term in _tokenize_query(query) if len(term) > 2}
    top_match_types = [str(result.get("matched_by", "")) for result in results[:3]]
    keyword_only = bool(top_match_types) and all(
        match_type.startswith("keyword") for match_type in top_match_types
    )
    retrieved_text = " ".join(
        f"{result.get('summary', '')} {result.get('text', '')}".lower() for result in results[:3]
    )
    covered_terms = sum(1 for term in query_terms if term in retrieved_text)
    coverage = covered_terms / max(len(query_terms), 1)

    score_strength = sum(float(result.get("score", 0.0)) for result in results[:3]) / max(
        len(results[:3]), 1
    )
    support_count = min(len(results) / 5, 1.0)
    exact_match_strength = (
        1.0
        if any(str(result.get("matched_by", "")).startswith("exact") for result in results[:3])
        else 0.35
    )

    matched_sections = search_payload.get("navigation", {}).get("matched_sections", [])
    section_match = 0.65
    if matched_sections:
        top_sections = {result.get("meta", {}).get("section") for result in results[:3]}
        section_match = (
            1.0 if any(section in top_sections for section in matched_sections) else 0.25
        )

    raw_score = (
        0.40 * score_strength
        + 0.25 * coverage
        + 0.20 * exact_match_strength
        + 0.10 * support_count
        + 0.05 * section_match
    )
    if keyword_only:
        raw_score *= 0.45
    score = max(0, min(int(round(raw_score * 100)), 100))

    if score >= 80:
        label = "High"
    elif score >= 60:
        label = "Medium"
    else:
        label = "Low"

    if matched_sections and section_match >= 1.0:
        reason = (
            "The tool chain found the requested section directly and the top evidence matches it."
        )
    elif exact_match_strength >= 1.0:
        reason = "At least one exact section or subsection match was found and supported by the retrieved text."
    elif keyword_only:
        reason = (
            "Only loose keyword overlap was found, so the supporting ordinance evidence is weak."
        )
    elif coverage >= 0.7:
        reason = "Most of the important query terms appear in the strongest retrieved ordinance evidence."
    elif coverage >= 0.4:
        reason = "The retrieved ordinance evidence partially overlaps the query, but the support is mixed."
    else:
        reason = (
            "Only limited overlap was found between the query and the retrieved ordinance evidence."
        )

    return {
        "score": score,
        "label": label,
        "reason": reason,
    }


def _build_source_link(meta: dict) -> str | None:
    source = meta.get("source")
    page = meta.get("page")
    if not source:
        return None

    url = f"{CUSTOM_RAG_BASE_URL}/pdf/{quote(source)}"
    if page:
        url += f"#page={page}"
    return url


def _citation_for_result(result: dict) -> str:
    meta = result.get("meta", {})
    citation_parts = [
        meta.get("jurisdiction"),
        meta.get("section"),
        meta.get("subsection"),
    ]
    citation = " ".join(str(part) for part in citation_parts if part)
    return citation or "Retrieved code section"


def _clean_evidence_text(result: dict, max_chars: int = 420) -> str:
    text = (result.get("summary") or result.get("text") or "").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3].rstrip()}..."


def _build_extractive_answer(query: str, search_payload: dict) -> str:
    """Create a grounded fallback answer when model providers are unavailable."""

    results = search_payload.get("results", [])
    if not results:
        return "No relevant sections retrieved from the municipal code."

    lines = [
        "CivilAI found relevant ordinance evidence, but the answer generator is temporarily unavailable. "
        "Here are the strongest retrieved code sections to review:"
    ]
    for index, result in enumerate(results[:3], start=1):
        evidence = _clean_evidence_text(result)
        citation = _citation_for_result(result)
        if evidence:
            lines.append(f"{index}. {citation}: {evidence}")
        else:
            lines.append(f"{index}. {citation}.")

    navigation = search_payload.get("navigation", {})
    top_chapters = navigation.get("top_chapters") or []
    if top_chapters:
        chapter_labels = [
            f"{chapter.get('chapter_number')}: {chapter.get('chapter_name')}"
            for chapter in top_chapters[:3]
            if chapter.get("chapter_name")
        ]
        if chapter_labels:
            lines.append(f"Likely chapters: {', '.join(chapter_labels)}.")

    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Public RAG entry point
# ---------------------------------------------------------------------------


def ask(
    query: str,
    top_k: int = 5,
    jurisdiction: str | None = None,
    debug: bool = False,
    user_id: str | None = None,
    request_id: str | None = None,
) -> dict:
    """Run the new tool-driven RAG pipeline over the normalized DB/Chroma stack."""

    search_payload = TOOLKIT.run_tool_chain(
        query=query,
        jurisdiction=jurisdiction,
        top_k=top_k,
        user_id=user_id,
    )
    results = search_payload["results"]
    navigation = search_payload["navigation"]

    if debug and results:
        print(f"\nRetrieved {len(results)} evidence block(s)")
        for index, result in enumerate(results, start=1):
            meta = result.get("meta", {})
            print(
                f"  {index}. [{meta.get('jurisdiction')}] "
                f"{meta.get('section')} {meta.get('subsection') or ''} "
                f"matched_by={result.get('matched_by')} "
                f"score={float(result.get('score', 0.0)):.4f}"
            )

    answer = _generate_answer(query, search_payload, user_id=user_id, request_id=request_id)
    if answer.lstrip().lower().startswith("error:"):
        answer = _build_extractive_answer(query, search_payload)
    accuracy = _estimate_accuracy(query, search_payload)

    sources = [
        {
            "jurisdiction": result.get("meta", {}).get("jurisdiction"),
            "source": result.get("meta", {}).get("source"),
            "section": result.get("meta", {}).get("section"),
            "subsection": result.get("meta", {}).get("subsection"),
            "title": result.get("meta", {}).get("title"),
            "page": result.get("meta", {}).get("page"),
            "score": round(float(result.get("score", 0.0)), 4),
            "url": _build_source_link(result.get("meta", {})),
        }
        for result in results
    ]

    return {
        "answer": answer,
        "accuracy": accuracy,
        "sources": sources,
        "navigation": navigation,
        "jurisdiction": search_payload.get("resolved_document_title"),
        "tool_trace": search_payload.get("tool_trace", []),
    }


def retrieve(
    query: str,
    top_k: int = 5,
    jurisdiction: str | None = None,
    user_id: str | None = None,
) -> dict:
    """Return structured retrieval payload without generating an answer."""

    search_payload = TOOLKIT.run_tool_chain(
        query=query,
        jurisdiction=jurisdiction,
        top_k=top_k,
        user_id=user_id,
    )
    return {
        "search_payload": search_payload,
        "accuracy": _estimate_accuracy(query, search_payload),
        "sources": [
            {
                "jurisdiction": result.get("meta", {}).get("jurisdiction"),
                "source": result.get("meta", {}).get("source"),
                "section": result.get("meta", {}).get("section"),
                "subsection": result.get("meta", {}).get("subsection"),
                "title": result.get("meta", {}).get("title"),
                "page": result.get("meta", {}).get("page"),
                "score": round(float(result.get("score", 0.0)), 4),
                "url": _build_source_link(result.get("meta", {})),
            }
            for result in search_payload.get("results", [])
        ],
    }


def _generate_answer(
    query: str,
    search_payload: dict,
    *,
    user_id: str | None = None,
    request_id: str | None = None,
) -> str:
    """Call the answer generator while remaining compatible with older test doubles."""

    try:
        return generate_answer(query, search_payload, user_id=user_id, request_id=request_id)
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        return generate_answer(query, search_payload)


def stream_ask(
    query: str,
    top_k: int = 5,
    jurisdiction: str | None = None,
    user_id: str | None = None,
    request_id: str | None = None,
):
    """Run retrieval once, then stream the generated answer."""

    retrieval = retrieve(query=query, top_k=top_k, jurisdiction=jurisdiction, user_id=user_id)
    yield from stream_answer(
        query,
        retrieval["search_payload"],
        user_id=user_id,
        request_id=request_id,
    )


if __name__ == "__main__":
    print("Structured Civil AI RAG | type 'exit' to quit")

    while True:
        try:
            raw_query = input("Ask: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if raw_query.lower() in {"exit", "quit", ""}:
            break

        result = ask(raw_query, debug=True)
        print(f"\nANSWER:\n{result['answer']}\n")
        print("Sources:")
        for source in result["sources"]:
            print(
                f"  [{source['jurisdiction']}] "
                f"{source['section']} {source.get('subsection') or ''} "
                f"(page {source.get('page')})"
            )
        print()
