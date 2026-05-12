import os
import sys
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from llama_index.core import SimpleDirectoryReader, StorageContext, VectorStoreIndex
from LlamaIndexRAG.config import PDF_DIR, STORAGE_DIR, embed_model


def detect_jurisdiction(file_path: str) -> str:
    filename = os.path.basename(file_path).lower()
    if "broward" in filename:
        return "Broward County, FL"
    if "cooper" in filename:
        return "Cooper City, FL"
    return Path(file_path).stem.replace("_", " ")


def build_file_metadata(file_path: str) -> dict:
    return {
        "jurisdiction": detect_jurisdiction(file_path),
    }


def build():
    print("Loading documents...")
    documents = SimpleDirectoryReader(
        PDF_DIR,
        file_metadata=build_file_metadata,
    ).load_data()

    print(f"Loaded {len(documents)} documents")

    print("Building index...")
    index = VectorStoreIndex.from_documents(documents, embed_model=embed_model)

    print("Saving index...")
    index.storage_context.persist(persist_dir=STORAGE_DIR)

    print("LlamaIndex build complete")


if __name__ == "__main__":
    build()
