import pickle
import numpy as np
import faiss
import re
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder

# -----------------------------
# PATHS
# -----------------------------
FAISS_INDEX_PATH = "./Data/FAISS/faiss.index"
FAISS_META_PATH  = "./Data/FAISS/faiss_meta.pkl"
BM25_PATH        = "./Data/bm25/bm25.pkl"

# -----------------------------
# MODELS
# -----------------------------
bi_encoder    = SentenceTransformer("all-MiniLM-L6-v2")
cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

# -----------------------------
# DATA
# -----------------------------
faiss_index    = faiss.read_index(FAISS_INDEX_PATH)
faiss_metadata = pickle.load(open(FAISS_META_PATH, "rb"))

bm25_corpus, bm25_texts = pickle.load(open(BM25_PATH, "rb"))
bm25 = BM25Okapi(bm25_corpus)

print(f"FAISS size: {faiss_index.ntotal}  |  BM25 docs: {len(bm25_corpus)}")

# -----------------------------
# HELPERS
# -----------------------------
def tokenize(text: str) -> list[str]:
    return re.sub(r"[^a-zA-Z0-9 ]", " ", text).lower().split()

def minmax(arr: np.ndarray) -> np.ndarray:
    lo, hi = arr.min(), arr.max()
    if hi - lo < 1e-9:
        return np.ones_like(arr) * 0.5
    return (arr - lo) / (hi - lo)


# -----------------------------
# QUERY EXPANSION
#
# Returns (expanded_query, predicted_subsection | None).
# Rules checked in order; first match wins.
# "fund" alone was removed as a (b) trigger — it caused false
# positives on "equipment fund used for" (expected (b) for a
# different reason) and "what is the equipment fund" (expected (a)).
# -----------------------------
_EXPANSION_RULES = [
    # (a) purpose / definition / what is it
    (
        [r"\bpurpose\b", r"\bdefinition\b", r"\bwhat is\b", r"\bdescribe\b",
         r"\bmeaning\b", r"\bused for\b", r"\bfunction\b", r"\brole of\b"],
        "(a)",
        "purpose definition established created subsection a",
    ),
    # (b) revenue / sources / where money comes from
    (
        [r"\brevenue\b", r"\bsource[s]?\b", r"\bincome\b",
         r"\bcomes from\b", r"\bfunded by\b", r"\bdeposit\b",
         r"\bwhere does\b"],
        "(b)",
        "revenue sources receipts deposits funding subsection b",
    ),
    # (c) expenditure / spending / allocation
    (
        [r"\bhow can\b", r"\bspend\b", r"\bspending\b", r"\balloc\w*\b",
         r"\bexpend\w*\b", r"\bdisburs\w*\b", r"\bappropriat\w*\b",
         r"\bhow is\b.*\ballocat\w*\b"],
        "(c)",
        "expenditure allocation spending disbursement appropriation subsection c",
    ),
]

def expand_query(query: str) -> tuple[str, str | None]:
    q = query.lower()
    for patterns, sub_hint, extra in _EXPANSION_RULES:
        if any(re.search(p, q) for p in patterns):
            return f"{query} {extra}", sub_hint
    return query, None


# -----------------------------
# BONUSES
# -----------------------------
def extract_section_mention(query: str) -> str | None:
    m = re.search(r"Sec\.\s*\d+[-–]\d+", query, re.IGNORECASE)
    return m.group(0) if m else None

_SUB_ORDER = {"(a)": 0, "(b)": 1, "(c)": 2, "(d)": 3, "(e)": 4}

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


# -----------------------------
# RRF
# -----------------------------
def rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank + 1)


# -----------------------------
# HYBRID SEARCH
# -----------------------------
def hybrid_search(
    query: str,
    top_k: int = 5,
    candidate_k: int = 200,
    verbose: bool = False,
) -> list[dict]:

    expanded, predicted_sub = expand_query(query)
    section_hint             = extract_section_mention(query)

    if verbose:
        print(f"  expanded      : {expanded}")
        print(f"  predicted_sub : {predicted_sub}")

    # ── FAISS ──────────────────────────────────────────────────────
    # Average original + expanded vectors so the suffix doesn't
    # dominate the embedding direction.
    vecs  = bi_encoder.encode(
        [query, expanded], normalize_embeddings=True
    ).astype("float32")
    q_vec = vecs.mean(axis=0, keepdims=True).astype("float32")
    faiss.normalize_L2(q_vec)

    D, I = faiss_index.search(q_vec, candidate_k)
    faiss_ranks: dict[int, int] = {
        idx: rank for rank, idx in enumerate(I[0]) if idx >= 0
    }

    # ── BM25 ───────────────────────────────────────────────────────
    # Score both original and expanded; keep the per-doc max so
    # exact term matches from either form are rewarded.
    bm25_orig = bm25.get_scores(tokenize(query))
    bm25_exp  = bm25.get_scores(tokenize(expanded))
    bm25_raw  = np.maximum(bm25_orig, bm25_exp)

    bm25_top   = np.argsort(bm25_raw)[::-1][:candidate_k]
    bm25_ranks: dict[int, int] = {
        idx: rank for rank, idx in enumerate(bm25_top)
    }

    # ── RRF fusion ─────────────────────────────────────────────────
    all_idx = set(faiss_ranks) | set(bm25_ranks)
    fused: dict[int, float] = {}
    for idx in all_idx:
        s  = rrf_score(faiss_ranks[idx]) if idx in faiss_ranks else 0.0
        s += rrf_score(bm25_ranks[idx])  if idx in bm25_ranks  else 0.0
        fused[idx] = s

    top_idx = sorted(fused, key=fused.__getitem__, reverse=True)[:candidate_k]

    # ── Build candidates (deduplicated by section+subsection) ──────
    seen:       set[tuple] = set()
    candidates: list[dict] = []
    pairs:      list[tuple] = []

    for idx in top_idx:
        if idx >= len(faiss_metadata):
            continue
        entry = faiss_metadata[idx]
        meta  = entry["meta"]
        key   = (meta.get("section"), meta.get("subsection"))

        if key in seen:
            continue
        seen.add(key)

        candidates.append({
            "text":         entry["text"],
            "meta":         meta,
            "score":        fused[idx],
            "rerank_score": 0.0,
        })
        pairs.append((query, entry["text"]))

    if not candidates:
        return []

    # ── Cross-encoder rerank ───────────────────────────────────────
    ce_raw    = np.array(cross_encoder.predict(pairs), dtype=float)
    ce_normed = minmax(ce_raw)

    max_fused = max(fused.values()) + 1e-9

    for i, c in enumerate(candidates):
        rrf_norm = c["score"] / max_fused
        ce_norm  = float(ce_normed[i])

        # 40 % retrieval + 60 % reranker
        base = 0.40 * rrf_norm + 0.60 * ce_norm

        sec_bonus = 0.0
        if section_hint and section_hint in (c["meta"].get("section") or ""):
            sec_bonus = 0.20

        sub_bonus = subsection_bonus(c["meta"], predicted_sub)

        c["rerank_score"] = ce_norm
        c["score"]        = base + sec_bonus + sub_bonus

    ranked = sorted(candidates, key=lambda x: x["score"], reverse=True)
    return ranked[:top_k]