import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from retrieval import hybrid_search
from LLM.llm import generate_answer


def ask(query: str, top_k: int = 5, debug: bool = False) -> dict:
    """
    Run the full RAG pipeline.

    Returns a dict with:
        answer  : str
        sources : list of {section, subsection, page, score}
    """
    results = hybrid_search(query, top_k=top_k)

    if debug:
        print(f"\n🔍 RETRIEVAL  ({len(results)} results)")
        for i, r in enumerate(results):
            m = r["meta"]
            print(
                f"  {i+1}. {m.get('section')} {m.get('subsection') or '':6s}  "
                f"score={r['score']:.4f}  rerank={r['rerank_score']:.4f}"
            )

    answer = generate_answer(query, results)

    sources = [
        {
            "section":    r["meta"].get("section"),
            "subsection": r["meta"].get("subsection"),
            "page":       r["meta"].get("page"),
            "score":      round(r["score"], 4),
        }
        for r in results
    ]

    return {"answer": answer, "sources": sources}


# -----------------------------
# CLI
# -----------------------------
if __name__ == "__main__":
    while True:
        q = input("\nAsk (or 'exit'): ").strip()
        if q.lower() in ("exit", "quit", ""):
            break

        result = ask(q, debug=True)
        print("\n💬 ANSWER:\n")
        print(result["answer"])
        print("\n📎 Sources:")
        for s in result["sources"]:
            print(f"  {s['section']} {s['subsection'] or ''}  (page {s['page']})")