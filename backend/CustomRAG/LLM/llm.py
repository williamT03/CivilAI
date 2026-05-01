import os
import textwrap

import requests
from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# Leave room for the prompt wrapper and the final answer so the model does not
# lose the important citation-bearing evidence blocks near the end.
MAX_CONTEXT_CHARS = 28_000


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------
# The new retrieval stack produces structured evidence rather than anonymous
# chunks. These helpers keep that evidence readable and small before it reaches
# the model.


def build_tool_trace(tool_trace: list[dict] | None) -> str:
    """Format the deterministic tool execution steps into a compact trace."""

    if not tool_trace:
        return "No structured tools were recorded."

    lines: list[str] = []
    for index, step in enumerate(tool_trace, start=1):
        tool_name = step.get("tool", "unknown_tool")
        parts = [f"{index}. {tool_name}"]

        if "input" in step:
            parts.append(f"input={step['input']}")
        if "output" in step:
            parts.append(f"output={step['output']}")
        if "output_count" in step:
            parts.append(f"matches={step['output_count']}")

        lines.append(" | ".join(parts))

    return "\n".join(lines)


def build_context(results: list[dict], max_chars: int = MAX_CONTEXT_CHARS) -> str:
    """Format structured evidence into numbered source blocks for the LLM."""

    blocks: list[str] = []
    used = 0

    for index, result in enumerate(results, start=1):
        meta = result.get("meta", {})
        citation = meta.get("section") or "Unknown section"
        if meta.get("subsection"):
            citation = f"{citation} {meta['subsection']}"

        header = (
            f"[Source {index}] {meta.get('jurisdiction', 'Unknown jurisdiction')} | "
            f"Chapter {meta.get('chapter_number', '?')}: {meta.get('chapter_name', 'Unknown chapter')} | "
            f"{citation} | matched_by={result.get('matched_by', 'semantic')} | "
            f"score={float(result.get('score', 0.0)):.4f}"
        )

        summary = (result.get("summary") or "").strip()
        text_body = (result.get("text") or "").strip()
        body_parts = []
        if summary:
            body_parts.append(f"Summary: {summary}")
        if text_body:
            body_parts.append(f"Text: {text_body}")

        block = f"{header}\n" + "\n".join(body_parts).strip()

        if used + len(block) > max_chars:
            remaining = max_chars - used - len(header) - 16
            if remaining > 120:
                trimmed_body = "\n".join(body_parts)
                block = f"{header}\n{trimmed_body[:remaining]}…"
                blocks.append(block)
            break

        blocks.append(block)
        used += len(block) + 4

    return "\n\n---\n\n".join(blocks)


def build_prompt(
    query: str,
    context: str,
    tool_trace: str,
    jurisdiction_label: str | None = None,
    summary_preview: str | None = None,
) -> str:
    """Build the final tool-aware prompt sent to Ollama."""

    if jurisdiction_label:
        assistant_scope = f"a civil engineering and municipal law assistant for {jurisdiction_label}"
    else:
        assistant_scope = "a civil engineering and municipal law assistant for ordinance research"

    summary_block = ""
    if summary_preview:
        summary_block = textwrap.dedent(
            f"""\
            STRUCTURED SUMMARY PREVIEW:
            ════════════════════════════════════════
            {summary_preview}
            ════════════════════════════════════════
            """
        )

    return textwrap.dedent(
        f"""\
        You are {assistant_scope}.

        Answer the question using ONLY the provided ordinance evidence below.

        Rules:
        - Cite the exact section and subsection for every claim, for example `Sec. 2-4 (a)`.
        - Treat the tool trace as navigation history, not as legal authority.
        - Prefer exact matches over semantic matches when both are present.
        - If the user asks for a summary, synthesize across the cited sections but still cite them.
        - If the answer is not supported by the evidence, respond exactly:
          "Not found in provided code sections."
        - Do NOT fabricate thresholds, fees, deadlines, penalties, or vote counts.

        TOOL TRACE:
        ════════════════════════════════════════
        {tool_trace}
        ════════════════════════════════════════

        {summary_block}ORDINANCE EVIDENCE:
        ════════════════════════════════════════
        {context}
        ════════════════════════════════════════

        QUESTION:
        {query}

        ANSWER:
        """
    )


# ---------------------------------------------------------------------------
# Ollama transport
# ---------------------------------------------------------------------------


def call_ollama(prompt: str, timeout: int = 120) -> str:
    """Call the configured Ollama model with a low-temperature legal prompt."""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.05,
                    "num_predict": 700,
                },
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()["response"].strip()

    except requests.exceptions.Timeout:
        return "Error: Ollama request timed out. Is `ollama serve` running?"
    except requests.exceptions.ConnectionError:
        return f"Error: Cannot connect to Ollama at {OLLAMA_URL}."
    except (KeyError, ValueError) as error:
        return f"Error: Unexpected Ollama response — {error}"
    except requests.exceptions.HTTPError as error:
        return f"Error: Ollama HTTP error — {error}"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_answer(query: str, retrieval_payload: dict | list[dict]) -> str:
    """Generate an answer from the structured retrieval payload produced by the new stack."""

    if isinstance(retrieval_payload, dict):
        results = retrieval_payload.get("results", [])
        navigation = retrieval_payload.get("navigation", {})
        tool_trace = retrieval_payload.get("tool_trace", [])
        summary_preview = (retrieval_payload.get("summary_preview") or {}).get("summary")
    else:
        results = retrieval_payload
        navigation = {}
        tool_trace = []
        summary_preview = None

    if not results:
        return "No relevant sections retrieved from the municipal code."

    jurisdiction_label = navigation.get("document_title")
    if not jurisdiction_label:
        jurisdictions = {
            result.get("meta", {}).get("jurisdiction")
            for result in results
            if result.get("meta", {}).get("jurisdiction")
        }
        jurisdiction_label = next(iter(jurisdictions)) if len(jurisdictions) == 1 else None

    context = build_context(results)
    prompt = build_prompt(
        query=query,
        context=context,
        tool_trace=build_tool_trace(tool_trace),
        jurisdiction_label=jurisdiction_label,
        summary_preview=summary_preview,
    )
    return call_ollama(prompt)
