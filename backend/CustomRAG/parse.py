"""
parse.py — Modular municipal code ingestion pipeline.

Supports any Florida county or city code with automatic layout detection.
Each PDF gets its own jurisdiction tag stored in metadata so retrieval
can filter by source.

Currently profiled and tested against:
  - Cooper City, FL  (single-column, Sec. X-Y, subsections (a)(b)(c))
  - Broward County, FL (two-column, Sec. X-Y + X½-Y + X-Y.Z,
                        subsections (a)(b)(c) and (1)(2)(3) nested)

Adding a new jurisdiction: drop its PDF into PDF_PATH and re-run.
No code changes required unless the document uses a completely novel
section-numbering scheme (e.g. Roman numerals).
"""

import os
import json
import pickle
import hashlib
import re
import gc
import numpy as np
import faiss
import chromadb

from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

import fitz          # PyMuPDF  — single-column PDFs
import pdfplumber    # column-aware extraction for two-column layouts

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
PROJECT_ROOT     = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR         = os.path.join(PROJECT_ROOT, "Data")
PDF_PATH         = os.path.join(DATA_DIR, "PDF")
CHROMA_DIR       = os.path.join(DATA_DIR, "chroma_db")
FAISS_INDEX_PATH = os.path.join(DATA_DIR, "FAISS", "faiss.index")
FAISS_META_PATH  = os.path.join(DATA_DIR, "FAISS", "faiss_meta.pkl")
BM25_PATH        = os.path.join(DATA_DIR, "bm25", "bm25.pkl")
PROCESSED_FILE   = os.path.join(DATA_DIR, "processed_files.json")
REQUIRED_ARTIFACTS = [FAISS_INDEX_PATH, FAISS_META_PATH, BM25_PATH]

DIMENSION   = 384
MAX_WORKERS = int(os.getenv("PARSE_MAX_WORKERS", "1"))
EMBED_BATCH_SIZE = int(os.getenv("PARSE_EMBED_BATCH_SIZE", "8"))
CHROMA_BATCH_SIZE = int(os.getenv("PARSE_CHROMA_BATCH_SIZE", "1000"))
EMBED_CHUNK_GROUP_SIZE = int(os.getenv("PARSE_EMBED_CHUNK_GROUP_SIZE", "128"))

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

try:
    faiss.omp_set_num_threads(int(os.getenv("FAISS_NUM_THREADS", "1")))
except Exception:
    pass

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# ─────────────────────────────────────────────────────────────
# JURISDICTION PROFILES
# Each PDF is auto-detected against these profiles.
# A profile captures the layout and numbering quirks of one
# publisher / code style.  Add a new profile only when a new
# document genuinely doesn't fit an existing one.
# ─────────────────────────────────────────────────────────────
@dataclass
class JurisdictionProfile:
    name:          str                    # human label shown in metadata
    # Layout
    two_column:    bool   = False         # True → use pdfplumber column split
    col_split_pct: float  = 0.50         # fraction of page width for left col
    # Regex strings (compiled at detection time)
    section_pattern:    str = r"Sec\.\s*\d+[-–]\d+"
    subsection_pattern: str = r"^\(([a-z])\)\s"
    # Page header / footer patterns to strip
    header_patterns:    list[str] = field(default_factory=lambda: [
        r"^CD\d+:\d+(\.\d+)?$",              # page codes like CD2:12
        r"^COOPER CITY CODE$",
        r"^(GENERAL PROVISIONS|ADMINISTRATION|CHARTER|TAXATION|UTILITIES)$",
    ])
    # Citation line pattern (skip — not retrieval content)
    citation_pattern:   str = r"^\((?:Code \d{4}|Ord\. No\.|Sp\. Acts|State law|Charter ref)"

PROFILES: dict[str, JurisdictionProfile] = {

    "cooper_city": JurisdictionProfile(
        name           = "Cooper City, FL",
        two_column     = False,
        # Handles both "Sec. 2-21" and "Section 3.06" styles
        section_pattern    = r"(?:Sec\.\s*\d+[-–]\d+|Section\s+\d+\.\d+)",
        subsection_pattern = r"^\(([a-z])\)\s",
        header_patterns    = [
            r"^CD\d+:\d+(\.\d+)?$",
            r"^COOPER CITY CODE$",
            r"^(GENERAL PROVISIONS|ADMINISTRATION|CHARTER|TAXATION|UTILITIES|TRAFFIC)$",
        ],
    ),

    "broward_county": JurisdictionProfile(
        name           = "Broward County, FL",
        two_column     = True,
        col_split_pct  = 0.50,
        # Broward has:
        #   Sec. 1-43       (standard)
        #   Sec. 1-51.1     (decimal extensions)
        #   Sec. 8½-16      (fractional chapters — ½ is U+00BD)
        #   Sec. 3½-22
        section_pattern    = r"Sec\.\s*[\d½¼¾]+[-–]\d+(?:\.\d+)?",
        # Broward uses both (a)(b)(c) and (1)(2)(3)
        subsection_pattern = r"^\(([a-z]|\d{1,2})\)\s",
        header_patterns    = [
            r"^CD\d+:\d+(\.\d+)?$",
            r"^BROWARD COUNTY CODE$",
            r"^(ADMINISTRATION|TAXATION|CHARTER|UTILITIES|TRAFFIC|ZONING)$",
        ],
        citation_pattern   = r"^\((?:Ord\. No\.|Sp\. Acts|State law|Charter ref|Cross ref)",
    ),

    # ── Template for future jurisdictions ──────────────────────
    # "miami_dade": JurisdictionProfile(
    #     name        = "Miami-Dade County, FL",
    #     two_column  = True,   # verify with pdftotext -layout
    #     section_pattern = r"Sec\.\s*\d+-\d+",
    #     ...
    # ),
}

# ─────────────────────────────────────────────────────────────
# AUTO-DETECTION
# Inspect the first 5 pages to decide which profile fits.
# ─────────────────────────────────────────────────────────────
def detect_profile(path: str) -> JurisdictionProfile:
    """
    Heuristics:
    1. Filename keyword match (fastest)
    2. Text scan for jurisdiction-specific strings
    3. Column-layout detection via pdftotext -layout
    Falls back to a generic single-column profile.
    """
    name_lower = os.path.basename(path).lower()

    # Filename keywords
    if "broward" in name_lower:
        return PROFILES["broward_county"]
    if "cooper" in name_lower:
        return PROFILES["cooper_city"]

    # Text scan for known strings in first 5 pages
    try:
        doc = fitz.open(path)
        sample = ""
        for i in range(min(5, len(doc))):
            sample += doc[i].get_text()
        doc.close()

        if "BROWARD COUNTY CODE" in sample:
            return PROFILES["broward_county"]
        if "COOPER CITY CODE" in sample:
            return PROFILES["cooper_city"]

        # Column detection: if many lines are very short (< 45 chars)
        # and page width suggests two columns, flag as two-column
        lines = [l.strip() for l in sample.split("\n") if l.strip()]
        short_line_pct = sum(1 for l in lines if len(l) < 45) / max(len(lines), 1)
        if short_line_pct > 0.60:
            # Likely two-column; use Broward profile as closest match
            # but override the name
            p = PROFILES["broward_county"]
            return JurisdictionProfile(
                name=os.path.splitext(os.path.basename(path))[0].replace("_", " "),
                two_column=True,
                col_split_pct=p.col_split_pct,
                section_pattern=p.section_pattern,
                subsection_pattern=p.subsection_pattern,
                header_patterns=p.header_patterns,
                citation_pattern=p.citation_pattern,
            )
    except Exception:
        pass

    # Generic single-column fallback
    return JurisdictionProfile(
        name=os.path.splitext(os.path.basename(path))[0].replace("_", " "),
        two_column=False,
    )

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def get_file_hash(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def load_processed() -> dict:
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE) as f:
            return json.load(f)
    return {}

def save_processed(data: dict) -> None:
    os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)
    with open(PROCESSED_FILE, "w") as f:
        json.dump(data, f, indent=2)

def tokenize(text: str) -> list[str]:
    return re.sub(r"[^a-zA-Z0-9 ]", " ", text).lower().split()

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def normalize_section(raw: str) -> str:
    """Canonical form: 'Sec. X-Y' or 'Sec. X½-Y' or 'Sec. X-Y.Z'"""
    # Convert "Section 3.06" → "Sec. 3-06"
    m = re.match(r"Section\s+(\d+)\.(\d+)", raw, re.IGNORECASE)
    if m:
        return f"Sec. {m.group(1)}-{m.group(2)}"
    return re.sub(r"\.$", "", raw.strip())

def extract_section_title(text: str) -> str:
    m = re.search(
        r"(?:Sec\.\s*[\d½]+[-–][\d]+(?:\.\d+)?|Section\s+\d+\.\d+)\.?\s+(.+?)(?:\.|$)",
        text, re.IGNORECASE
    )
    return m.group(1).strip() if m else ""

def make_embed_text(section: str, subsection: str | None,
                    jurisdiction: str, body: str) -> str:
    """
    Prefixes the chunk with structural metadata so both the dense vector
    and BM25 have the section/subsection label baked in.
    'Broward County, FL Sec. 1-44 (b): equipment fund road bridge...'
    """
    sub = subsection or ""
    return f"{jurisdiction} {section} {sub}: {body}".strip()

# ─────────────────────────────────────────────────────────────
# PDF LOADING  (layout-aware)
# ─────────────────────────────────────────────────────────────
def load_pdf_single_column(path: str) -> list[dict]:
    """PyMuPDF — clean for single-column documents."""
    doc   = fitz.open(path)
    pages = [{"text": page.get_text(), "page": i + 1} for i, page in enumerate(doc)]
    doc.close()
    return pages

def load_pdf_two_column(path: str, split_pct: float = 0.50) -> list[dict]:
    """
    pdfplumber — splits each page at split_pct of its width, extracts
    left column then right column, and concatenates them.  This gives
    a reading order that matches how a human reads the page.
    """
    pages = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            mid_x = page.width * split_pct
            left  = page.crop((0,     0, mid_x,        page.height))
            right = page.crop((mid_x, 0, page.width,   page.height))

            left_text  = left.extract_text(x_tolerance=2, y_tolerance=2)  or ""
            right_text = right.extract_text(x_tolerance=2, y_tolerance=2) or ""

            # Interleave by paragraph: rejoin the two columns vertically
            text = left_text + "\n" + right_text
            pages.append({"text": text, "page": i + 1})
    return pages

def load_pdf(path: str, profile: JurisdictionProfile) -> list[dict]:
    try:
        if profile.two_column:
            return load_pdf_two_column(path, profile.col_split_pct)
        else:
            return load_pdf_single_column(path)
    except Exception as e:
        print(f"  WARNING: Primary loader failed ({e}), falling back to PyMuPDF")
        return load_pdf_single_column(path)

# ─────────────────────────────────────────────────────────────
# STRUCTURE PARSING  (profile-driven)
# ─────────────────────────────────────────────────────────────
def structure_parse(raw_pages: list[dict],
                    profile: JurisdictionProfile) -> list[dict]:
    """
    Converts raw page text into line-level dicts with section/subsection.
    All regex patterns come from the profile — no hardcoded values.
    """
    section_re   = re.compile(profile.section_pattern,    re.IGNORECASE)
    subsec_re    = re.compile(profile.subsection_pattern)
    citation_re  = re.compile(profile.citation_pattern,   re.IGNORECASE)
    header_res   = [re.compile(p) for p in profile.header_patterns]
    # TOC detector: 3+ section refs on one line
    toc_re       = re.compile(r"(Sec\.\s*[\d½]+[-–]\d+\.?\s*){3,}")

    current_section    = None
    current_subsection = None
    structured         = []

    for page_obj in raw_pages:
        lines = [l.strip() for l in page_obj["text"].split("\n") if l.strip()]
        for line in lines:
            line = clean_text(line)
            if not line:
                continue

            # Skip TOC lines
            if toc_re.search(line):
                continue
            # Skip page headers / footers
            if any(r.match(line) for r in header_res):
                continue
            # Skip citation-only lines
            if citation_re.match(line):
                continue

            # Detect section boundary
            sec_match = section_re.search(line)
            if sec_match:
                current_section    = normalize_section(sec_match.group(0))
                current_subsection = None

            # Detect subsection boundary
            sub_match = subsec_re.match(line)
            if sub_match:
                label = sub_match.group(1)
                current_subsection = f"({label})"

            if not current_section:
                continue

            structured.append({
                "text":       line,
                "section":    current_section,
                "subsection": current_subsection,
                "page":       page_obj["page"],
            })

    return structured

# ─────────────────────────────────────────────────────────────
# CHUNKING
# ─────────────────────────────────────────────────────────────
def chunk_sections(structured: list[dict],
                   profile: JurisdictionProfile,
                   jurisdiction: str) -> list[dict]:
    """
    One chunk per (section, subsection) pair.
    Each chunk carries both its display body and its embed_text
    (header-prefixed for FAISS + BM25 signal).
    """
    chunks             = []
    current_section    = None
    current_subsection = None
    buffer             = []
    last_page          = None

    def flush():
        if not buffer or not current_section:
            return
        body = " ".join(buffer)
        if len(body) < 40:
            return
        chunks.append({
            "body":         body,
            "section":      current_section,
            "subsection":   current_subsection,
            "page":         last_page,
            "jurisdiction": jurisdiction,
            "embed_text":   make_embed_text(
                                current_section, current_subsection,
                                jurisdiction, body
                            ),
        })

    for d in structured:
        sec = d["section"]
        sub = d["subsection"]

        if sec != current_section:
            flush()
            buffer, current_section, current_subsection = [], sec, None

        if sub != current_subsection:
            flush()
            buffer, current_subsection = [], sub

        buffer.append(d["text"])
        last_page = d["page"]

    flush()
    return chunks

# ─────────────────────────────────────────────────────────────
# PROCESS ONE PDF
# ─────────────────────────────────────────────────────────────
def process_pdf(path: str, filename: str, file_hash: str):
    profile      = detect_profile(path)
    jurisdiction = profile.name

    print(f"  FILE: {filename}")
    print(f"     Profile     : {jurisdiction} "
          f"({'two-column' if profile.two_column else 'single-column'})")

    raw_pages  = load_pdf(path, profile)
    structured = structure_parse(raw_pages, profile)
    chunks     = chunk_sections(structured, profile, jurisdiction)
    del raw_pages, structured

    if not chunks:
        print("  WARNING: No chunks extracted - check profile regex")
        return []

    print(f"     Chunks      : {len(chunks):,}")
    return chunks

# ─────────────────────────────────────────────────────────────
# STORAGE INIT
# ─────────────────────────────────────────────────────────────
for d in [os.path.dirname(FAISS_INDEX_PATH),
          os.path.dirname(BM25_PATH), CHROMA_DIR]:
    os.makedirs(d, exist_ok=True)

chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
collection    = chroma_client.get_or_create_collection(name="pdf_docs")

storage_ready = all(os.path.exists(path) for path in REQUIRED_ARTIFACTS)

if storage_ready:
    print("Loading existing FAISS index...")
    faiss_index    = faiss.read_index(FAISS_INDEX_PATH)
    with open(FAISS_META_PATH, "rb") as f:
        faiss_metadata = pickle.load(f)
    with open(BM25_PATH, "rb") as f:
        bm25_corpus, bm25_texts = pickle.load(f)
else:
    missing = [path for path in REQUIRED_ARTIFACTS if not os.path.exists(path)]
    if missing:
        print("Creating FAISS index...")
        print("   Missing storage artifacts detected; rebuilding index files.")
    faiss_index    = faiss.IndexHNSWFlat(DIMENSION, 32)
    faiss_metadata = []
    bm25_texts  = []
    bm25_corpus = []


def store_result(store_texts, embs, metas, ids, tokens) -> int:
    embs = np.asarray(embs, dtype="float32")
    faiss_index.add(embs)

    for t, m, tok in zip(store_texts, metas, tokens):
        faiss_metadata.append({"text": t, "meta": m})
        bm25_texts.append(t)
        bm25_corpus.append(tok)

    for i in range(0, len(store_texts), CHROMA_BATCH_SIZE):
        collection.upsert(
            documents=store_texts[i:i + CHROMA_BATCH_SIZE],
            embeddings=embs[i:i + CHROMA_BATCH_SIZE].tolist(),
            metadatas=metas[i:i + CHROMA_BATCH_SIZE],
            ids=ids[i:i + CHROMA_BATCH_SIZE],
        )

    return len(store_texts)


def store_chunks_for_pdf(chunks: list[dict], filename: str, file_hash: str) -> int:
    total = 0

    for start in range(0, len(chunks), EMBED_CHUNK_GROUP_SIZE):
        batch = chunks[start:start + EMBED_CHUNK_GROUP_SIZE]
        embed_texts = [c["embed_text"] for c in batch]
        store_texts = [c["body"] for c in batch]
        metas = [
            {
                "source": filename,
                "jurisdiction": c["jurisdiction"],
                "section": c["section"],
                "subsection": c["subsection"],
                "title": extract_section_title(c["body"]),
                "page": c["page"],
            }
            for c in batch
        ]
        ids = [f"{file_hash}_{start + i}" for i in range(len(batch))]
        tokens = [tokenize(text) for text in embed_texts]

        embeddings = embedding_model.encode(
            embed_texts,
            batch_size=min(EMBED_BATCH_SIZE, len(embed_texts)),
            show_progress_bar=False,
            convert_to_numpy=True,
        ).astype("float32", copy=False)
        faiss.normalize_L2(embeddings)

        total += store_result(store_texts, embeddings, metas, ids, tokens)

        del batch, embed_texts, store_texts, metas, ids, tokens, embeddings
        gc.collect()

    return total


def persist_state(processed: dict) -> None:
    faiss.write_index(faiss_index, FAISS_INDEX_PATH)
    with open(FAISS_META_PATH, "wb") as f:
        pickle.dump(faiss_metadata, f)
    bm25 = BM25Okapi(bm25_corpus)
    with open(BM25_PATH, "wb") as f:
        pickle.dump((bm25_corpus, bm25_texts), f)
    save_processed(processed)

# ─────────────────────────────────────────────────────────────
# INGESTION LOOP
# ─────────────────────────────────────────────────────────────
processed  = load_processed() if storage_ready else {}
new_hashes: dict[str, str] = {}
indexed_files = 0
total_chunks = 0

pending_files = []
for file in sorted(os.listdir(PDF_PATH)):
    if not file.lower().endswith(".pdf"):
        continue
    path = os.path.join(PDF_PATH, file)
    h    = get_file_hash(path)
    if h in processed:
        print(f"  SKIP: {file} (already indexed)")
        continue
    pending_files.append((path, file, h))

if MAX_WORKERS <= 1:
    for path, file, h in pending_files:
        try:
            result = process_pdf(path, file, h)
            if result:
                total_chunks += store_chunks_for_pdf(result, file, h)
                new_hashes[h] = file
                processed[h] = file
                persist_state(processed)
                indexed_files += 1
                del result
                gc.collect()
        except Exception as e:
            print(f"  ERROR: {file}: {e}")
else:
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures: dict = {
            ex.submit(process_pdf, path, file, h): (h, file)
            for path, file, h in pending_files
        }

        for future in as_completed(futures):
            h, fname = futures[future]
            try:
                result = future.result()
                if result:
                    total_chunks += store_chunks_for_pdf(result, fname, h)
                    new_hashes[h] = fname
                    processed[h] = fname
                    persist_state(processed)
                    indexed_files += 1
                    del result
                    gc.collect()
            except Exception as e:
                print(f"  ERROR: {fname}: {e}")

# ─────────────────────────────────────────────────────────────
# STORE & SAVE
# ─────────────────────────────────────────────────────────────
if indexed_files:
    persist_state(processed)
    print(f"\nIndexed {indexed_files} new file(s) - "
          f"{total_chunks:,} new chunks - "
          f"{faiss_index.ntotal:,} total vectors")
else:
    print("\nNothing new to index.")
