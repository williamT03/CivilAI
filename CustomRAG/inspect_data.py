from retrieval import hybrid_search

def inspect_query(query):
    results = hybrid_search(query, top_k=5)

    print(f"\n🔍 QUERY: {query}\n")
    print("=" * 80)

    for i, r in enumerate(results):
        meta = r["meta"]

        print(f"\nResult #{i+1}")
        print("-" * 80)
        print(f"Score: {r['score']:.4f} | Rerank: {r['rerank_score']:.4f}")
        print(f"Section: {meta.get('section')} {meta.get('subsection')}")
        print(f"Page: {meta.get('page')}")
        print(f"Type: {meta.get('type')}")
        print("\nTEXT PREVIEW:")
        print(r["text"][:500])
        print("\n" + "=" * 80)

if __name__ == "__main__":
    while True:
        q = input("\nEnter query (or 'exit'): ")
        if q == "exit":
            break
        inspect_query(q)