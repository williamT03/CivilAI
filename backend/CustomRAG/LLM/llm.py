import requests
import textwrap
import os
from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL      = os.getenv("OLLAMA_MODEL", "llama3")   # swap for mistral, phi3, etc.

# llama3 has an 8k-token window (~4 chars/token → ~32k chars).
# Leave ~2k chars for the prompt wrapper and model's answer.
MAX_CONTEXT_CHARS = 28_000


# -----------------------------
# BUILD CONTEXT
# Formats retrieved chunks into numbered source blocks.
# Truncates if the total would overflow the model's context window.
# -----------------------------
def build_context(results: list[dict], max_chars: int = MAX_CONTEXT_CHARS) -> str:
    blocks = []
    used   = 0

    for i, r in enumerate(results):
        meta = r["meta"]
        sec  = meta.get("section")  or "Unknown"
        sub  = meta.get("subsection") or ""
        page = meta.get("page")     or "?"
        text = r["text"].strip()

        header = (
            f"[Source {i+1}]  {sec} {sub}  (page {page})"
        )
        block = f"{header}\n{text}"

        if used + len(block) > max_chars:
            remaining = max_chars - used - len(header) - 10
            if remaining > 80:
                block = f"{header}\n{text[:remaining]}…"
                blocks.append(block)
            break

        blocks.append(block)
        used += len(block) + 4   # separator

    return "\n\n---\n\n".join(blocks)


# -----------------------------
# PROMPT
# -----------------------------
def build_prompt(query: str, context: str, jurisdiction_label: str | None = None) -> str:
    if jurisdiction_label:
        assistant_scope = f"a civil engineering and municipal law assistant for {jurisdiction_label}"
    else:
        assistant_scope = "a civil engineering and municipal law assistant for municipal code research"

    return textwrap.dedent(f"""\
        You are {assistant_scope}.

        Answer the question using ONLY the provided Code of Ordinances context below.

        Rules:
        - Cite the exact section and subsection for every claim, e.g. Sec. 2-4 (a).
        - Be precise and technical. Use the language of the code where possible.
        - If the answer is not found in the provided context, respond exactly:
          "Not found in provided code sections."
        - Do NOT fabricate dollar amounts, time limits, vote thresholds or other specifics.

        CONTEXT:
        ════════════════════════════════════════
        {context}
        ════════════════════════════════════════

        QUESTION:
        {query}

        ANSWER:
    """)


# -----------------------------
# CALL OLLAMA  (timeout + structured error returns)
# -----------------------------
def call_ollama(prompt: str, timeout: int = 120) -> str:
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model":  MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.05,  # near-deterministic for legal text
                    "num_predict": 600,
                },
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["response"].strip()

    except requests.exceptions.Timeout:
        return "Error: Ollama request timed out. Is `ollama serve` running?"
    except requests.exceptions.ConnectionError:
        return f"Error: Cannot connect to Ollama at {OLLAMA_URL}."
    except (KeyError, ValueError) as e:
        return f"Error: Unexpected Ollama response — {e}"
    except requests.exceptions.HTTPError as e:
        return f"Error: Ollama HTTP error — {e}"


# -----------------------------
# MAIN ENTRY POINT
# -----------------------------
def generate_answer(query: str, retrieval_results: list[dict]) -> str:
    if not retrieval_results:
        return "No relevant sections retrieved from the municipal code."

    jurisdictions = {
        r["meta"].get("jurisdiction")
        for r in retrieval_results
        if r.get("meta", {}).get("jurisdiction")
    }
    jurisdiction_label = next(iter(jurisdictions)) if len(jurisdictions) == 1 else None

    context = build_context(retrieval_results)
    prompt  = build_prompt(query, context, jurisdiction_label=jurisdiction_label)
    return call_ollama(prompt)
