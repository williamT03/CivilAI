from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Iterable, Iterator, Optional, Protocol

import requests

try:
    from backend.app.ai.usage import UsageEvent, get_usage_tracker
    from backend.app.core.config import CivilAISettings, get_settings
except ImportError:  # pragma: no cover
    from app.ai.usage import UsageEvent, get_usage_tracker
    from app.core.config import CivilAISettings, get_settings


def estimate_tokens(text: str | Iterable[str] | None) -> int:
    if text is None:
        return 0
    if isinstance(text, str):
        joined = text
    else:
        joined = "\n".join(text)
    return max(1, int(len(joined.split()) * 1.33)) if joined.strip() else 0


@dataclass(slots=True)
class AIResponse:
    text: str
    provider: str
    model: str
    request_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    raw: dict = field(default_factory=dict)


@dataclass(slots=True)
class EmbeddingResponse:
    embeddings: list[list[float]]
    provider: str
    model: str
    request_id: str
    embedding_tokens: int = 0
    latency_ms: float = 0.0
    raw: dict = field(default_factory=dict)


class LLMProvider(Protocol):
    provider_name: str
    model: str

    def generate(self, prompt: str, *, request_id: str, user_id: str | None = None, endpoint: str | None = None) -> AIResponse:
        ...

    def stream(self, prompt: str, *, request_id: str, user_id: str | None = None, endpoint: str | None = None) -> Iterator[str]:
        ...


class EmbeddingProvider(Protocol):
    provider_name: str
    embedding_model: str

    def embed(self, text: str, *, request_id: str, user_id: str | None = None, endpoint: str | None = None) -> list[float]:
        ...

    def embed_batch(self, texts: list[str], *, request_id: str, user_id: str | None = None, endpoint: str | None = None) -> EmbeddingResponse:
        ...


class ProviderUnavailable(RuntimeError):
    pass


class OpenAICompatibleProvider:
    """Provider for OpenAI, DeepSeek, and future OpenAI-compatible APIs."""

    def __init__(
        self,
        *,
        provider_name: str,
        api_key: str | None,
        base_url: str,
        chat_model: str,
        embedding_model: str | None = None,
        timeout_seconds: float = 60,
        max_retries: int = 2,
    ) -> None:
        self.provider_name = provider_name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = chat_model
        self.embedding_model = embedding_model or chat_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._embedding_cache: dict[str, list[float]] = {}

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, *, request_id: str, user_id: str | None = None, endpoint: str | None = None) -> AIResponse:
        if not self.is_configured():
            raise ProviderUnavailable(f"{self.provider_name} API key is not configured.")

        start = time.perf_counter()
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.05,
            "max_tokens": 900,
            "stream": False,
        }
        response_json = self._request_json("post", "/chat/completions", payload)
        latency_ms = (time.perf_counter() - start) * 1000
        choice = response_json.get("choices", [{}])[0]
        text = (choice.get("message", {}) or {}).get("content", "").strip()
        usage = response_json.get("usage") or {}
        ai_response = AIResponse(
            text=text,
            provider=self.provider_name,
            model=self.model,
            request_id=request_id,
            input_tokens=int(usage.get("prompt_tokens") or estimate_tokens(prompt)),
            output_tokens=int(usage.get("completion_tokens") or estimate_tokens(text)),
            latency_ms=latency_ms,
            raw=response_json,
        )
        get_usage_tracker().record(
            UsageEvent(
                provider=self.provider_name,
                model=self.model,
                operation="chat",
                request_id=request_id,
                endpoint=endpoint,
                user_id=user_id,
                input_tokens=ai_response.input_tokens,
                output_tokens=ai_response.output_tokens,
                latency_ms=latency_ms,
                success=True,
            )
        )
        return ai_response

    def stream(self, prompt: str, *, request_id: str, user_id: str | None = None, endpoint: str | None = None) -> Iterator[str]:
        if not self.is_configured():
            raise ProviderUnavailable(f"{self.provider_name} API key is not configured.")

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.05,
            "max_tokens": 900,
            "stream": True,
        }
        with requests.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout_seconds,
            stream=True,
        ) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line or not raw_line.startswith("data:"):
                    continue
                line = raw_line.removeprefix("data:").strip()
                if line == "[DONE]":
                    break
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content
        get_usage_tracker().record(
            UsageEvent(
                provider=self.provider_name,
                model=self.model,
                operation="chat_stream",
                request_id=request_id,
                endpoint=endpoint,
                user_id=user_id,
                input_tokens=estimate_tokens(prompt),
                success=True,
            )
        )

    def embed(self, text: str, *, request_id: str, user_id: str | None = None, endpoint: str | None = None) -> list[float]:
        return self.embed_batch([text], request_id=request_id, user_id=user_id, endpoint=endpoint).embeddings[0]

    def embed_batch(self, texts: list[str], *, request_id: str, user_id: str | None = None, endpoint: str | None = None) -> EmbeddingResponse:
        if not self.is_configured():
            raise ProviderUnavailable(f"{self.provider_name} API key is not configured.")
        if not texts:
            return EmbeddingResponse([], self.provider_name, self.embedding_model, request_id)

        cached: list[list[float] | None] = [self._embedding_cache.get(text) for text in texts]
        missing_indexes = [index for index, value in enumerate(cached) if value is None]
        start = time.perf_counter()

        if missing_indexes:
            missing_texts = [texts[index] for index in missing_indexes]
            payload = {"model": self.embedding_model, "input": missing_texts}
            response_json = self._request_json("post", "/embeddings", payload)
            for item in response_json.get("data", []):
                local_index = int(item.get("index", 0))
                source_text = missing_texts[local_index]
                embedding = item["embedding"]
                self._embedding_cache[source_text] = embedding
                cached[missing_indexes[local_index]] = embedding
            usage = response_json.get("usage") or {}
            token_count = int(usage.get("prompt_tokens") or estimate_tokens(missing_texts))
        else:
            response_json = {}
            token_count = 0

        latency_ms = (time.perf_counter() - start) * 1000
        embeddings = [value or [] for value in cached]
        get_usage_tracker().record(
            UsageEvent(
                provider=self.provider_name,
                model=self.embedding_model,
                operation="embedding",
                request_id=request_id,
                endpoint=endpoint,
                user_id=user_id,
                embedding_tokens=token_count,
                latency_ms=latency_ms,
                success=True,
            )
        )
        return EmbeddingResponse(
            embeddings=embeddings,
            provider=self.provider_name,
            model=self.embedding_model,
            request_id=request_id,
            embedding_tokens=token_count,
            latency_ms=latency_ms,
            raw=response_json,
        )

    def _request_json(self, method: str, path: str, payload: dict) -> dict:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise
                time.sleep(0.25 * (attempt + 1))
        raise last_error or RuntimeError("Provider request failed.")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }


class OllamaProvider:
    provider_name = "ollama"

    def __init__(self, *, base_url: str, model: str, timeout_seconds: float = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embedding_model = model
        self.timeout_seconds = timeout_seconds

    def _raise_for_status(self, response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text.strip()
            if len(detail) > 500:
                detail = f"{detail[:500]}..."
            raise RuntimeError(
                f"Ollama request failed with HTTP {response.status_code} for model "
                f"'{self.model}' at {self.base_url}: {detail or response.reason}"
            ) from exc

    def generate(self, prompt: str, *, request_id: str, user_id: str | None = None, endpoint: str | None = None) -> AIResponse:
        start = time.perf_counter()
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.05, "num_predict": 450},
            },
            timeout=self.timeout_seconds,
        )
        self._raise_for_status(response)
        response_json = response.json()
        text = (response_json.get("response") or "").strip()
        latency_ms = (time.perf_counter() - start) * 1000
        result = AIResponse(
            text=text,
            provider=self.provider_name,
            model=self.model,
            request_id=request_id,
            input_tokens=int(response_json.get("prompt_eval_count") or estimate_tokens(prompt)),
            output_tokens=int(response_json.get("eval_count") or estimate_tokens(text)),
            latency_ms=latency_ms,
            raw=response_json,
        )
        get_usage_tracker().record(
            UsageEvent(
                provider=self.provider_name,
                model=self.model,
                operation="chat",
                request_id=request_id,
                endpoint=endpoint,
                user_id=user_id,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                latency_ms=latency_ms,
                success=True,
            )
        )
        return result

    def stream(self, prompt: str, *, request_id: str, user_id: str | None = None, endpoint: str | None = None) -> Iterator[str]:
        with requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": True,
                "options": {"temperature": 0.05, "num_predict": 450},
            },
            timeout=self.timeout_seconds,
            stream=True,
        ) as response:
            self._raise_for_status(response)
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                try:
                    chunk = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                token = chunk.get("response")
                if token:
                    yield token


class AIProviderRouter:
    """Configurable route-level AI provider selection with fallback logging."""

    def __init__(self, settings: CivilAISettings | None = None) -> None:
        self.settings = settings or get_settings()
        self.providers = {
            "openai": OpenAICompatibleProvider(
                provider_name="openai",
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                chat_model=self.settings.openai_chat_model,
                embedding_model=self.settings.openai_embedding_model,
                timeout_seconds=self.settings.ai_request_timeout_seconds,
                max_retries=self.settings.ai_max_retries,
            ),
            "deepseek": OpenAICompatibleProvider(
                provider_name="deepseek",
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
                chat_model=self.settings.deepseek_chat_model,
                timeout_seconds=self.settings.ai_request_timeout_seconds,
                max_retries=self.settings.ai_max_retries,
            ),
            "ollama": OllamaProvider(
                base_url=self.settings.ollama_url,
                model=self.settings.ollama_model,
                timeout_seconds=max(120, self.settings.ai_request_timeout_seconds),
            ),
        }

    def generate(
        self,
        prompt: str,
        *,
        purpose: str = "answer",
        request_id: str | None = None,
        user_id: str | None = None,
        endpoint: str | None = None,
    ) -> AIResponse:
        resolved_request_id = request_id or str(uuid.uuid4())
        last_error: Exception | None = None
        for provider_name in self.settings.provider_order(purpose):
            provider = self.providers.get(provider_name)
            if provider is None:
                continue
            try:
                response = provider.generate(
                    prompt,
                    request_id=resolved_request_id,
                    user_id=user_id,
                    endpoint=endpoint,
                )
                if provider_name != self.settings.provider_order(purpose)[0]:
                    get_usage_tracker().record_provider_event(
                        resolved_request_id,
                        response.provider,
                        response.model,
                        "fallback_success",
                        f"Generated after fallback from {last_error}",
                    )
                return response
            except Exception as exc:
                last_error = exc
                model = getattr(provider, "model", "unknown")
                get_usage_tracker().record_provider_event(
                    resolved_request_id,
                    provider_name,
                    model,
                    "provider_failure",
                    str(exc),
                )
        raise RuntimeError(f"All configured AI providers failed: {last_error}")

    def stream(self, prompt: str, *, purpose: str = "answer", request_id: str | None = None, user_id: str | None = None, endpoint: str | None = None) -> Iterator[str]:
        provider_name = self.settings.provider_order(purpose)[0]
        provider = self.providers[provider_name]
        return provider.stream(prompt, request_id=request_id or str(uuid.uuid4()), user_id=user_id, endpoint=endpoint)

    def embed_batch(self, texts: list[str], *, request_id: str | None = None, user_id: str | None = None, endpoint: str | None = None) -> EmbeddingResponse:
        resolved_request_id = request_id or str(uuid.uuid4())
        last_error: Exception | None = None
        for provider_name in self.settings.provider_order("embedding"):
            provider = self.providers.get(provider_name)
            if provider is None or not hasattr(provider, "embed_batch"):
                continue
            try:
                return provider.embed_batch(texts, request_id=resolved_request_id, user_id=user_id, endpoint=endpoint)
            except Exception as exc:
                last_error = exc
                get_usage_tracker().record_provider_event(
                    resolved_request_id,
                    provider_name,
                    getattr(provider, "embedding_model", getattr(provider, "model", "unknown")),
                    "embedding_provider_failure",
                    str(exc),
                )
        raise RuntimeError(f"All configured embedding providers failed: {last_error}")


_router: AIProviderRouter | None = None


def get_ai_router() -> AIProviderRouter:
    global _router
    if _router is None:
        _router = AIProviderRouter()
    return _router
