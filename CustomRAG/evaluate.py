"""
evaluate.py — Retrieval evaluation for Cooper City, FL Code of Ordinances.

All test queries are grounded in sections that ACTUALLY EXIST in the PDF.
Chapter 1 ends at Sec. 1-12; the old test set used fictional Sec. 1-43/1-44.

Coverage:
  - Chapter 1  (General Provisions):  Sec. 1-8
  - Chapter 2  (Administration):      Sec. 2-4, 2-5, 2-21, 2-22
  - Ch. 2 Finance (Capital Impr.):    Sec. 2-216, 2-217, 2-219, 2-220, 2-222
  - Ch. 2 Finance (Special Proj.):    Sec. 2-222

Metrics
  Precision@1  — correct answer is rank-1
  Recall@5     — correct answer appears anywhere in top-5
  Exact Match  — section AND subsection both correct
"""

from retrieval import hybrid_search

TEST_QUERIES = [
    # ── Chapter 1: General Provisions ──────────────────────────────
    {
        "query": "what is the general penalty for violating the city code",
        "expected_section": "Sec. 1-8",
        "expected_subsection": "(a)",
        "note": "Max fine $500 or 90-day imprisonment",
    },
    {
        "query": "can a convicted person be required to perform community service for the city",
        "expected_section": "Sec. 1-8",
        "expected_subsection": "(e)",
        "note": "Work not exceeding 8 hours/day, 90 consecutive days",
    },
    {
        "query": "is each day of a continuing violation treated as a separate offense",
        "expected_section": "Sec. 1-8",
        "expected_subsection": "(d)",
        "note": "Continuing violations = separate daily offenses",
    },

    # ── Chapter 2: Settlement of Claims ────────────────────────────
    {
        "query": "what authority does the city manager have to settle lawsuits",
        "expected_section": "Sec. 2-4",
        "expected_subsection": "(a)",
        "note": "City manager may settle up to $25,000",
    },
    {
        "query": "who can settle claims between $25,000 and $50,000",
        "expected_section": "Sec. 2-4",
        "expected_subsection": "(b)",
        "note": "City manager with City Attorney concurrence",
    },
    {
        "query": "who must approve settlements exceeding $50,000",
        "expected_section": "Sec. 2-4",
        "expected_subsection": "(c)",
        "note": "Only the City Commission",
    },

    # ── Chapter 2: Grant Applications ──────────────────────────────
    {
        "query": "who is authorized to apply for federal grants on behalf of the city",
        "expected_section": "Sec. 2-5",
        "expected_subsection": "(a)",
        "note": "City Manager is authorized",
    },
    {
        "query": "when must the city commission approve a grant application",
        "expected_section": "Sec. 2-5",
        "expected_subsection": "(c)",
        "note": "When the grant becomes a binding contract upon award",
    },

    # ── Chapter 2: Regular Meetings ─────────────────────────────────
    {
        "query": "when does the city commission hold its regular meetings",
        "expected_section": "Sec. 2-21",
        "expected_subsection": "(a)",
        "note": "Second and fourth Tuesday of each month",
    },
    {
        "query": "what happens when a commission meeting falls on a holiday",
        "expected_section": "Sec. 2-21",
        "expected_subsection": "(b)",
        "note": "Date/time set by majority vote at prior meeting",
    },

    # ── Chapter 2: Petition for Franchise ──────────────────────────
    {
        "query": "how long after a franchise denial must the city wait to reconsider",
        "expected_section": "Sec. 2-22",
        "expected_subsection": "(a)",
        "note": "One year from date of denial",
    },
    {
        "query": "how can the one year franchise waiting period be waived",
        "expected_section": "Sec. 2-22",
        "expected_subsection": "(b)",
        "note": "Affirmative vote of four commission members",
    },

    # ── Chapter 2 Finance: Capital Improvements Fund ─────────────────
    {
        "query": "what is the purpose of the capital improvements fund",
        "expected_section": "Sec. 2-216",
        "expected_subsection": None,
        "note": "Established at $222,250 for capital improvements",
    },
    {
        "query": "how are monies allocated to the capital improvements fund each year",
        "expected_section": "Sec. 2-217",
        "expected_subsection": None,
        "note": "Commission allocates at annual budget adoption",
    },
    {
        "query": "can capital improvement funds be mixed with the general fund",
        "expected_section": "Sec. 2-219",
        "expected_subsection": None,
        "note": "Explicitly prohibited — must be kept separate",
    },
    {
        "query": "are capital improvement funds restricted to designated purposes",
        "expected_section": "Sec. 2-220",
        "expected_subsection": None,
        "note": "Yes — restricted fund, designated by City Commission",
    },

    # ── Chapter 2 Finance: Special Projects Account ──────────────────
    {
        "query": "what is the special projects account used for",
        "expected_section": "Sec. 2-222",
        "expected_subsection": "(a)",
        "note": "Capital equipment acquisition and capital improvements",
    },
    {
        "query": "how are transfers made into the special projects account",
        "expected_section": "Sec. 2-222",
        "expected_subsection": "(b)",
        "note": "Line item change approved in writing by City Manager",
    },
    {
        "query": "who approves disbursements from the special projects account",
        "expected_section": "Sec. 2-222",
        "expected_subsection": "(c)",
        "note": "City Manager after City Commission approval",
    },
]


def match_section(found: str | None, expected: str) -> bool:
    return bool(found and expected in found)


def evaluate(verbose: bool = True) -> dict:
    p1 = r5 = em = 0
    total = len(TEST_QUERIES)
    failures = []

    for test in TEST_QUERIES:
        res = hybrid_search(test["query"], top_k=5, verbose=False)

        found_sec   = False
        found_exact = False
        rank_exact  = None

        for i, r in enumerate(res):
            sec = r["meta"].get("section")
            sub = r["meta"].get("subsection")

            if match_section(sec, test["expected_section"]):
                found_sec = True
                # Match subsection: if expected is None, section-level hit counts
                sub_ok = (
                    test["expected_subsection"] is None
                    or sub == test["expected_subsection"]
                )
                if sub_ok:
                    found_exact = True
                    rank_exact  = i + 1
                    if i == 0:
                        p1 += 1
                    break

        if found_sec:   r5 += 1
        if found_exact: em += 1

        if not found_exact:
            failures.append(test["query"])

        if verbose:
            if found_exact:
                icon = "✅" if rank_exact == 1 else "🔶"
            elif found_sec:
                icon = "⚠️ "
            else:
                icon = "❌"

            exp_sub = test["expected_subsection"] or "(any)"
            rank_str = f"rank {rank_exact}" if found_exact else "not found"
            print(f"\n{icon}  {test['query']}")
            print(f"     Expected : {test['expected_section']} {exp_sub}")
            print(f"     Result   : {rank_str}")
            if verbose and res:
                print(f"     Top-5    :")
                for i, r in enumerate(res):
                    m   = r["meta"]
                    tag = ""
                    if (match_section(m.get("section"), test["expected_section"])
                            and (test["expected_subsection"] is None
                                 or m.get("subsection") == test["expected_subsection"])):
                        tag = "  ← TARGET"
                    sub_disp = m.get("subsection") or ""
                    print(f"       {i+1}. {m.get('section')} {sub_disp:6s}  "
                          f"score={r['score']:.4f}{tag}")

    print("\n" + "=" * 55)
    print("EVALUATION RESULTS")
    print(f"  Total queries : {total}")
    print(f"  Precision@1   : {p1}/{total} = {p1/total:.3f}")
    print(f"  Recall@5      : {r5}/{total} = {r5/total:.3f}")
    print(f"  Exact Match   : {em}/{total} = {em/total:.3f}")
    if failures:
        print(f"\n  Failed queries ({len(failures)}):")
        for f in failures:
            print(f"    - {f}")
    print("=" * 55)

    return {"p1": p1/total, "r5": r5/total, "em": em/total}


if __name__ == "__main__":
    evaluate(verbose=True)