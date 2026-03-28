import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from retrieval import hybrid_search
from LLM.llm import generate_answer


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

    sources = [
        {
            "jurisdiction": r["meta"].get("jurisdiction"),
            "section":      r["meta"].get("section"),
            "subsection":   r["meta"].get("subsection"),
            "page":         r["meta"].get("page"),
            "score":        round(r["score"], 4),
        }
        for r in results
    ]

    return {
        "answer":       answer,
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