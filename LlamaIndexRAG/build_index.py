import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
from llama_index.core import StorageContext

from LlamaIndexRAG.config import embed_model, STORAGE_DIR, PDF_DIR


def build():
    print("📄 Loading documents...")
    documents = SimpleDirectoryReader(PDF_DIR).load_data()

    print(f"Loaded {len(documents)} documents")

    print("🧠 Building index...")
    index = VectorStoreIndex.from_documents(
        documents,
        embed_model=embed_model
    )

    print("💾 Saving index...")
    index.storage_context.persist(persist_dir=STORAGE_DIR)

    print("✅ LlamaIndex build complete")


if __name__ == "__main__":
    build()