import requests
import textwrap

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = "llama3"   # swap for mistral, phi3, etc.

# Approximate character budget for context.
# llama3 has an 8k-token window; ~4 chars/token → ~28 000 chars safe limit.
# Leave ~2 000 chars for the prompt wrapper and the answer.
MAX_CONTEXT_CHARS = 26_000

# -----------------------------
# BUILD CONTEXT
# Truncates long chunks so we never silently overflow the model window.
# -----------------------------
def build_context(results: list[dict], max_chars: int = MAX_CONTEXT_CHARS) -> str:
    blocks   = []
    used     = 0

    for i, r in enumerate(results):
        meta  = r["meta"]
        text  = r["text"].strip()
        header = (
            f"[Source {i+1}]\n"
            f"Section: {meta.get('section', 'N/A')}  "
            f"Subsection: {meta.get('subsection', 'N/A')}  "
            f"Page: {meta.get('page', 'N/A')}"
        )
        block = f"{header}\n\n{text}"

        if used + len(block) > max_chars:
            # include a truncated version rather than dropping it entirely
            remaining = max_chars - used
            if remaining > len(header) + 100:
                block = f"{header}\n\n{text[:remaining - len(header) - 10]}…"
                blocks.append(block)
            break

        blocks.append(block)
        used += len(block) + 2   # +2 for the separator

    return "\n\n---\n\n".join(blocks)


# -----------------------------
# PROMPT TEMPLATE
# -----------------------------
def build_prompt(query: str, context: str) -> str:
    return textwrap.dedent(f"""\
        You are a civil engineering code assistant specializing in municipal codes.

        Answer the question using ONLY the provided context.

        Rules:
        - Be precise and technical.
        - Cite section and subsection for every claim (e.g., Sec. 1-43 (a)).
        - Do NOT fabricate information.
        - If the answer is not in the context, say exactly: "Not found in provided code."

        CONTEXT:
        ==================
        {context}
        ==================

        QUESTION:
        {query}

        ANSWER:
    """)


# -----------------------------
# CALL OLLAMA  (with timeout + error handling)
# -----------------------------
def call_ollama(prompt: str, timeout: int = 120) -> str:
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model":  MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,   # low temp for factual code answers
                    "num_predict": 512,   # cap response length
                }
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()["response"].strip()

    except requests.exceptions.Timeout:
        return "Error: Ollama request timed out. Is the server running?"
    except requests.exceptions.ConnectionError:
        return "Error: Cannot connect to Ollama at localhost:11434."
    except (KeyError, ValueError) as e:
        return f"Error: Unexpected response from Ollama — {e}"


# -----------------------------
# MAIN RAG FUNCTION
# -----------------------------
def generate_answer(query: str, retrieval_results: list[dict]) -> str:
    if not retrieval_results:
        return "No relevant sections found in the municipal code."

    context = build_context(retrieval_results)
    prompt  = build_prompt(query, context)
    return call_ollama(prompt)