import os
import json
import pickle
import hashlib
import numpy as np
import faiss
import chromadb
import re

from concurrent.futures import ThreadPoolExecutor, as_completed
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi
from unstructured.partition.pdf import partition_pdf
import fitz

# -----------------------------
# CONFIG
# -----------------------------
PDF_PATH          = "./data/PDF"
CHROMA_DIR        = "./data/chroma_db"
FAISS_INDEX_PATH  = "./Data/FAISS/faiss.index"
FAISS_META_PATH   = "./Data/FAISS/faiss_meta.pkl"
BM25_PATH         = "./Data/bm25/bm25.pkl"
PROCESSED_FILE    = "./Data/processed_files.json"

DIMENSION   = 384
MAX_WORKERS = 4

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# -----------------------------
# INIT DB
# -----------------------------
chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
collection    = chroma_client.get_or_create_collection(name="pdf_docs")

if os.path.exists(FAISS_INDEX_PATH):
    print("🔁 Loading FAISS...")
    faiss_index    = faiss.read_index(FAISS_INDEX_PATH)
    with open(FAISS_META_PATH, "rb") as f:
        faiss_metadata = pickle.load(f)
else:
    print("🆕 Creating FAISS...")
    faiss_index    = faiss.IndexHNSWFlat(DIMENSION, 32)
    faiss_metadata = []

# BM25 corpus accumulated across all PDFs
bm25_texts  = []
bm25_corpus = []

# -----------------------------
# HELPERS
# -----------------------------
def normalize_section(sec: str | None) -> str | None:
    if not sec:
        return None
    return re.sub(r"\.$", "", sec).strip()


def clean_text(text: str) -> str:
    text = re.sub(r"\(Sp\..*?\)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    return re.sub(r"[^a-zA-Z0-9 ]", " ", text).lower().split()


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


def extract_title(text: str) -> str:
    m = re.search(r"Sec\.\s*\d+[-–]\d+\.\s*(.*)", text)
    return m.group(1) if m else ""


# -----------------------------
# REGEX
# -----------------------------
SECTION_RE = r"Sec\.\s*\d+[-–]\d+"


# -----------------------------
# STRUCTURE PARSING
# -----------------------------
def structure_parse(elements) -> list[dict]:
    current_section    = None
    current_subsection = None
    structured         = []

    for el in elements:
        text = getattr(el, "text", "") or ""
        if not text:
            continue

        text = clean_text(text)

        # Skip TOC / garbage lines that contain multiple section references
        if len(re.findall(r"Sec\.", text)) > 3:
            continue

        page = getattr(getattr(el, "metadata", None), "page_number", None)

        sec_match = re.search(SECTION_RE, text)
        if sec_match:
            current_section    = normalize_section(sec_match.group(0))
            current_subsection = None

        sub_match = re.match(r"^\(([a-z])\)", text)
        if sub_match:
            current_subsection = f"({sub_match.group(1)})"

        if not current_section:
            continue

        structured.append({
            "text":       text,
            "section":    current_section,
            "subsection": current_subsection,
            "page":       page,
        })

    return structured


# -----------------------------
# CHUNKING
# -----------------------------
def chunk_sections(structured: list[dict]) -> list[dict]:
    chunks             = []
    current_section    = None
    current_subsection = None
    buffer             = []
    last_page          = None

    def flush():
        if buffer and current_section:
            chunks.append({
                "text":       "\n\n".join(buffer),
                "section":    current_section,
                "subsection": current_subsection,
                "page":       last_page,
            })

    for d in structured:
        sec  = d["section"]
        sub  = d["subsection"]

        if sec != current_section:
            flush()
            buffer             = []
            current_section    = sec
            current_subsection = None

        if sub != current_subsection:
            flush()
            buffer             = []
            current_subsection = sub

        buffer.append(d["text"])
        last_page = d["page"]

    flush()

    # Drop tiny / sectionless chunks
    return [
        c for c in chunks
        if c["section"] and len(c["text"]) >= 50
    ]


# -----------------------------
# LOAD PDF
# -----------------------------
def load_pdf(path: str):
    try:
        return partition_pdf(filename=path, strategy="fast")
    except Exception:
        print(f"⚠️  Falling back to PyMuPDF for {path}")
        doc = fitz.open(path)
        # Return simple objects that structure_parse can handle via getattr
        class _Page:
            def __init__(self, text, page):
                self.text = text
                class _Meta:
                    page_number = page
                self.metadata = _Meta()
        return [_Page(page.get_text(), i + 1) for i, page in enumerate(doc)]


# -----------------------------
# PROCESS PDF
# -----------------------------
def process_pdf(path: str, filename: str, file_hash: str):
    elements   = load_pdf(path)
    structured = structure_parse(elements)
    chunks     = chunk_sections(structured)

    print(f"  {filename} → {len(chunks)} chunks")

    texts      = [c["text"] for c in chunks]
    embeddings = embedding_model.encode(texts, batch_size=32, show_progress_bar=False)
    faiss.normalize_L2(embeddings)

    metas  = []
    ids    = []
    tokens = []

    for i, c in enumerate(chunks):
        metas.append({
            "source":     filename,
            "section":    c["section"],
            "subsection": c["subsection"],
            "title":      extract_title(c["text"]),
            "page":       c["page"],
        })
        ids.append(f"{file_hash}_{i}")
        tokens.append(tokenize(c["text"]))

    return texts, embeddings, metas, ids, tokens


# -----------------------------
# RUN INGESTION
# -----------------------------
processed = load_processed()
results   = []
new_hashes: dict[str, str] = {}   # hash → filename

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
    futures = {}

    for file in os.listdir(PDF_PATH):
        if not file.endswith(".pdf"):
            continue
        path = os.path.join(PDF_PATH, file)
        h    = get_file_hash(path)

        if h in processed:
            print(f"  ⏭  Skipping {file} (already processed)")
            continue

        print(f"  📄 Queuing {file}…")
        futures[ex.submit(process_pdf, path, file, h)] = h

    for future in as_completed(futures):
        h = futures[future]
        try:
            results.append(future.result())
            new_hashes[h] = h   # mark as done
        except Exception as e:
            print(f"  ❌ Failed to process a file: {e}")


# -----------------------------
# STORE DATA
# -----------------------------
for texts, embs, metas, ids, tokens in results:
    embs = np.array(embs).astype("float32")
    faiss_index.add(embs)

    for t, m, tok in zip(texts, metas, tokens):
        faiss_metadata.append({"text": t, "meta": m})
        bm25_texts.append(t)
        bm25_corpus.append(tok)

    # Chroma has a 5 461-item hard limit per upsert batch
    BATCH = 4000
    for i in range(0, len(texts), BATCH):
        collection.upsert(
            documents=texts[i:i + BATCH],
            embeddings=embs[i:i + BATCH].tolist(),
            metadatas=metas[i:i + BATCH],
            ids=ids[i:i + BATCH],
        )

# -----------------------------
# SAVE  (only if anything new was processed)
# -----------------------------
if results:
    os.makedirs(os.path.dirname(FAISS_INDEX_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(BM25_PATH),         exist_ok=True)

    faiss.write_index(faiss_index, FAISS_INDEX_PATH)
    pickle.dump(faiss_metadata, open(FAISS_META_PATH, "wb"))

    bm25 = BM25Okapi(bm25_corpus)
    pickle.dump((bm25_corpus, bm25_texts), open(BM25_PATH, "wb"))

    # ✅ FIX: actually persist the newly-processed hashes
    processed.update(new_hashes)
    save_processed(processed)

    print(f"\n✅ Ingested {len(results)} new file(s).")
else:
    print("\n✅ Nothing new to ingest.")