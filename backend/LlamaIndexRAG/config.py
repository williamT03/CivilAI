import os
from dotenv import load_dotenv
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.openai_like import OpenAILike

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# -----------------------------
# EMBEDDING
# -----------------------------
embed_model = HuggingFaceEmbedding(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# -----------------------------
# DEEPSEEK V3 via OpenAILike
# OpenAILike accepts any model name and custom base URL,
# bypassing LlamaIndex's OpenAI model name whitelist.
# -----------------------------
llm = OpenAILike(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    api_base=os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com"),
    temperature=0.1,
    is_chat_model=True,        # DeepSeek uses the /chat/completions endpoint
    context_window=65536,      # DeepSeek V3 context window
    max_tokens=1024,
)

STORAGE_DIR = os.path.join(PROJECT_ROOT, "LlamaIndexRAG", "storage")
PDF_DIR     = os.path.join(PROJECT_ROOT, "Data", "PDF")
