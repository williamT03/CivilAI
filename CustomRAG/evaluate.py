from retrieval import hybrid_search

TEST_QUERIES = [
    {"query": "what is the purpose of the general fund",    "expected_section": "Sec. 1-43", "expected_subsection": "(a)"},
    {"query": "what revenues go into the general fund",     "expected_section": "Sec. 1-43", "expected_subsection": "(b)"},
    {"query": "how can general fund money be spent",        "expected_section": "Sec. 1-43", "expected_subsection": "(c)"},
    {"query": "what is the equipment fund used for",        "expected_section": "Sec. 1-44", "expected_subsection": "(b)"},
    {"query": "where does equipment fund revenue come from","expected_section": "Sec. 1-44", "expected_subsection": "(a)"},
    {"query": "how is equipment fund money allocated",      "expected_section": "Sec. 1-44", "expected_subsection": "(c)"},
]

def match_section(found, expected):
    return found and expected in found

def evaluate(verbose: bool = True):
    p1 = r5 = em = 0
    total = len(TEST_QUERIES)

    for test in TEST_QUERIES:
        res = hybrid_search(test["query"], top_k=5, verbose=verbose)

        found_sec   = False
        found_exact = False
        rank_exact  = None

        for i, r in enumerate(res):
            sec = r["meta"]["section"]
            sub = r["meta"]["subsection"]

            if match_section(sec, test["expected_section"]):
                found_sec = True
                if sub == test["expected_subsection"]:
                    found_exact = True
                    rank_exact  = i + 1
                    if i == 0:
                        p1 += 1
                    break

        if found_sec:   r5 += 1
        if found_exact: em += 1

        # ── Per-query report ──────────────────────────────────────
        if verbose:
            hit  = "✅" if found_exact else ("⚠️ " if found_sec else "❌")
            rank = f"rank={rank_exact}" if found_exact else "not found"
            print(f"\n{hit}  Q: {test['query']}")
            print(f"     Expected : {test['expected_section']} {test['expected_subsection']}")
            print(f"     Result   : {rank}")
            print(f"     Top-5    :")
            for i, r in enumerate(res):
                m   = r["meta"]
                tag = " ← TARGET" if (
                    match_section(m.get("section"), test["expected_section"])
                    and m.get("subsection") == test["expected_subsection"]
                ) else ""
                print(f"       {i+1}. {m.get('section')} {str(m.get('subsection')):6s}  "
                      f"score={r['score']:.4f}{tag}")

    print("\n" + "=" * 50)
    print("RESULTS")
    print(f"  Precision@1 : {p1}/{total} = {p1/total:.3f}")
    print(f"  Recall@5    : {r5}/{total} = {r5/total:.3f}")
    print(f"  Exact Match : {em}/{total} = {em/total:.3f}")
    print("=" * 50)

if __name__ == "__main__":
    evaluate(verbose=True)