"""
retrieval.py — Hybrid search with jurisdiction-aware filtering.

The jurisdiction parameter lets the caller restrict results to a specific
county or city code, so when you have Cooper City + Broward + Miami-Dade
all in the same index, a query about Cooper City zoning only returns
Cooper City chunks.
"""

import pickle
import numpy as np
import faiss
import re
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder

# ─────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────
FAISS_INDEX_PATH = "./Data/FAISS/faiss.index"
FAISS_META_PATH  = "./Data/FAISS/faiss_meta.pkl"
BM25_PATH        = "./Data/bm25/bm25.pkl"

# ─────────────────────────────────────────────────────────────
# MODELS & DATA  (loaded once at import)
# ─────────────────────────────────────────────────────────────
bi_encoder    = SentenceTransformer("all-MiniLM-L6-v2")
cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

faiss_index    = faiss.read_index(FAISS_INDEX_PATH)
faiss_metadata = pickle.load(open(FAISS_META_PATH, "rb"))

bm25_corpus, bm25_texts = pickle.load(open(BM25_PATH, "rb"))
bm25 = BM25Okapi(bm25_corpus)

print(f"FAISS vectors : {faiss_index.ntotal:,}")
print(f"BM25 docs     : {len(bm25_corpus):,}")

# Build a lookup: jurisdiction name → set of faiss_metadata indices
# Used for O(1) jurisdiction filtering without scanning all vectors.
_JURISDICTION_IDX: dict[str, set[int]] = {}
for i, entry in enumerate(faiss_metadata):
    jur = entry["meta"].get("jurisdiction", "unknown")
    _JURISDICTION_IDX.setdefault(jur, set()).add(i)

print(f"Jurisdictions : {list(_JURISDICTION_IDX.keys())}")

# ─────────────────────────────────────────────────────────────
# JURISDICTION ALIASES
# Maps user-facing names / abbreviations to stored jurisdiction strings.
# ─────────────────────────────────────────────────────────────
_JURISDICTION_ALIASES: dict[str, str] = {
    "cooper city":         "Cooper City, FL",
    "cooper":              "Cooper City, FL",
    "broward":             "Broward County, FL",
    "broward county":      "Broward County, FL",
    # add more as you index more jurisdictions
}

def resolve_jurisdiction(name: str | None) -> str | None:
    if name is None:
        return None
    key = name.lower().strip()
    return _JURISDICTION_ALIASES.get(key, name)

# ─────────────────────────────────────────────────────────────
# ENTITY → SECTION MAP  (per jurisdiction)
# ─────────────────────────────────────────────────────────────
_ENTITY_MAP: dict[str, dict[str, str]] = {
    "Cooper City, FL": {
        "general penalty":       "Sec. 1-8",
        "right of entry":        "Sec. 1-9",
        "severability":          "Sec. 1-10",
        "official seal":         "Sec. 1-11",
        "official logo":         "Sec. 1-12",
        "settlement of claims":  "Sec. 2-4",
        "grant applications":    "Sec. 2-5",
        "regular meetings":      "Sec. 2-21",
        "petition for franchise":"Sec. 2-22",
        "candidates residency":  "Sec. 2-23",
        "capital improvements fund": "Sec. 2-216",
        "allocation of monies":  "Sec. 2-217",
        "monies.*separate":      "Sec. 2-219",
        "restricted.*purposes":  "Sec. 2-220",
        "special projects":      "Sec. 2-222",
    },
    "Broward County, FL": {
        "traffic association":        "Sec. 1-43",
        "equipment fund":             "Sec. 1-44",
        "economic development fund":  "Sec. 1-45",
        "tax millage":                "Sec. 1-47",
        "deposit.*county funds":      "Sec. 1-51.2",
        "claims.*county.*authority":  "Sec. 1-51.3",
    },
}

def detect_section_filter(query: str,
                           jurisdiction: str | None) -> str | None:
    q = query.lower()
    # Explicit section mention in query
    m = re.search(r"sec\.?\s*([\d½¼¾]+[-–]\d+(?:\.\d+)?)", q, re.IGNORECASE)
    if m:
        return f"Sec. {m.group(1)}"
    # Entity phrase lookup for the active jurisdiction
    if jurisdiction and jurisdiction in _ENTITY_MAP:
        for phrase, section in _ENTITY_MAP[jurisdiction].items():
            if re.search(phrase, q):
                return section
    return None

# ─────────────────────────────────────────────────────────────
# QUERY EXPANSION
# ─────────────────────────────────────────────────────────────
_EXPANSION_RULES = [
    (
        [r"\bpurpose\b", r"\bdefinition\b", r"\bwhat is\b", r"\bmeaning\b",
         r"\bwhat does\b", r"\brole of\b", r"\bestablished\b", r"\bdesignated\b",
         r"\bused for\b", r"\bauthorized\b"],
        "(a)",
        "purpose definition meaning established designated authorized subsection a",
    ),
    (
        [r"\brevenue\b", r"\bsource[s]?\b", r"\bincome\b", r"\bwhere does\b",
         r"\bcomes from\b", r"\bfunded by\b", r"\bdeposit\b", r"\breceipt\b",
         r"\bappropriat\w*\b"],
        "(b)",
        "revenue sources receipts deposits income appropriation subsection b",
    ),
    (
        [r"\bhow can\b", r"\bspend\b", r"\bspending\b", r"\balloc\w*\b",
         r"\bexpend\w*\b", r"\bdisburs\w*\b", r"\bhow is\b.*\bused\b",
         r"\bhow.*money\b", r"\blevy\b", r"\btax\b.*\bauthori\w*"],
        "(c)",
        "expenditure allocation spending disbursement levy tax subsection c",
    ),
]

def expand_query(query: str) -> tuple[str, str | None]:
    q = query.lower()
    for patterns, sub_hint, extra in _EXPANSION_RULES:
        if any(re.search(p, q) for p in patterns):
            return f"{query} {extra}", sub_hint
    return query, None

# ─────────────────────────────────────────────────────────────
# SCORING HELPERS
# ─────────────────────────────────────────────────────────────
_SUB_ORDER = {"(a)": 0, "(b)": 1, "(c)": 2, "(d)": 3, "(e)": 4,
              "(1)": 0, "(2)": 1, "(3)": 2, "(4)": 3, "(5)": 4}

def subsection_bonus(meta: dict, predicted_sub: str | None) -> float:
    if predicted_sub is None:
        return 0.0
    actual = meta.get("subsection")
    if actual == predicted_sub:
        return 0.15
    if actual is None:
        return 0.0
    dist = abs(_SUB_ORDER.get(actual, 99) - _SUB_ORDER.get(predicted_sub, 99))
    return max(0.0, 0.04 - dist * 0.02)

def rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank + 1)

def minmax(arr: np.ndarray) -> np.ndarray:
    lo, hi = arr.min(), arr.max()
    if hi - lo < 1e-9:
        return np.ones_like(arr) * 0.5
    return (arr - lo) / (hi - lo)

def tokenize(text: str) -> list[str]:
    return re.sub(r"[^a-zA-Z0-9 ]", " ", text).lower().split()

# ─────────────────────────────────────────────────────────────
# HYBRID SEARCH
# ─────────────────────────────────────────────────────────────
def hybrid_search(
    query:        str,
    top_k:        int = 5,
    candidate_k:  int = 200,
    jurisdiction: str | None = None,   # e.g. "cooper city" or "broward"
    verbose:      bool = False,
) -> list[dict]:
    """
    jurisdiction=None  → search across ALL indexed codes
    jurisdiction="broward county" → restrict to Broward County, FL only
    """
    jurisdiction = resolve_jurisdiction(jurisdiction)
    expanded, predicted_sub = expand_query(query)
    section_filter = detect_section_filter(query, jurisdiction)

    if verbose:
        print(f"  jurisdiction   : {jurisdiction or 'ALL'}")
        print(f"  expanded       : {expanded}")
        print(f"  predicted_sub  : {predicted_sub}")
        print(f"  section_filter : {section_filter}")

    # ── FAISS ──────────────────────────────────────────────────
    vecs  = bi_encoder.encode(
        [query, expanded], normalize_embeddings=True
    ).astype("float32")
    q_vec = vecs.mean(axis=0, keepdims=True).astype("float32")
    faiss.normalize_L2(q_vec)

    D, I = faiss_index.search(q_vec, candidate_k)
    faiss_ranks: dict[int, int] = {
        idx: rank for rank, idx in enumerate(I[0]) if idx >= 0
    }

    # ── BM25 ───────────────────────────────────────────────────
    bm25_orig = bm25.get_scores(tokenize(query))
    bm25_exp  = bm25.get_scores(tokenize(expanded))
    bm25_raw  = np.maximum(bm25_orig, bm25_exp)
    bm25_top  = np.argsort(bm25_raw)[::-1][:candidate_k]
    bm25_ranks: dict[int, int] = {
        idx: rank for rank, idx in enumerate(bm25_top)
    }

    # ── RRF fusion ─────────────────────────────────────────────
    all_idx = set(faiss_ranks) | set(bm25_ranks)
    fused: dict[int, float] = {}
    for idx in all_idx:
        s  = rrf_score(faiss_ranks[idx]) if idx in faiss_ranks else 0.0
        s += rrf_score(bm25_ranks[idx])  if idx in bm25_ranks  else 0.0
        fused[idx] = s

    top_idx = sorted(fused, key=fused.__getitem__, reverse=True)[:candidate_k]

    # ── Jurisdiction filter ─────────────────────────────────────
    if jurisdiction and jurisdiction in _JURISDICTION_IDX:
        allowed = _JURISDICTION_IDX[jurisdiction]
        jur_filtered = [idx for idx in top_idx if idx in allowed]
        if len(jur_filtered) >= top_k:
            top_idx = jur_filtered

    # ── Section filter ──────────────────────────────────────────
    if section_filter:
        sec_filtered = [
            idx for idx in top_idx
            if idx < len(faiss_metadata)
            and section_filter in (faiss_metadata[idx]["meta"].get("section") or "")
        ]
        if len(sec_filtered) >= top_k:
            top_idx = sec_filtered

    # ── Build candidates (dedup by section+subsection) ──────────
    seen:       set[tuple] = set()
    candidates: list[dict] = []
    pairs:      list[tuple] = []

    for idx in top_idx:
        if idx >= len(faiss_metadata):
            continue
        entry = faiss_metadata[idx]
        meta  = entry["meta"]
        key   = (meta.get("jurisdiction"), meta.get("section"), meta.get("subsection"))

        if key in seen:
            continue
        seen.add(key)

        candidates.append({
            "text":         entry["text"],
            "meta":         meta,
            "score":        fused.get(idx, 0.0),
            "rerank_score": 0.0,
        })
        pairs.append((query, entry["text"]))

    if not candidates:
        return []

    # ── Cross-encoder rerank ────────────────────────────────────
    ce_raw    = np.array(cross_encoder.predict(pairs), dtype=float)
    ce_normed = minmax(ce_raw)
    max_fused = max(fused.values()) + 1e-9

    for i, c in enumerate(candidates):
        rrf_norm  = c["score"] / max_fused
        ce_norm   = float(ce_normed[i])
        base      = 0.70 * rrf_norm + 0.30 * ce_norm
        sub_bonus = subsection_bonus(c["meta"], predicted_sub)
        c["rerank_score"] = ce_norm
        c["score"]        = base + sub_bonus

    ranked = sorted(candidates, key=lambda x: x["score"], reverse=True)

    if verbose:
        print(f"\n  Top-{top_k}:")
        for r in ranked[:top_k]:
            m = r["meta"]
            print(f"    [{m.get('jurisdiction')}] "
                  f"{m.get('section')} {m.get('subsection') or '':6s}  "
                  f"score={r['score']:.4f}  rerank={r['rerank_score']:.4f}")

    return ranked[:top_k]