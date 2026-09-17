"""LLM provider abstraction: Groq, Gemini, or a deterministic mock.

The rest of the system (planner, synthesizer) only calls `LLMClient.complete`.
Swapping providers is a matter of changing LLM_PROVIDER / LLM_MODEL in the
environment; no other code changes. Mirrors the SearchProvider pattern for
consistency.

The "mock" provider exists so the full pipeline (including synthesis) is
exercisable in tests and in environments with no LLM credentials configured,
without ever pretending a mock is a validated real-API integration. It is
clearly logged as active whenever used.
"""
from __future__ import annotations

import abc
import logging

import httpx

logger = logging.getLogger("research_agent.synthesis.llm_client")


class LLMCallError(Exception):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMClient(abc.ABC):
    @abc.abstractmethod
    async def complete(
        self, *, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float = 0.0
    ) -> str:
        raise NotImplementedError


class GroqLLMClient(LLMClient):
    """Groq's OpenAI-compatible chat completions API."""

    _URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str | None, model: str, timeout_seconds: float = 30.0) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    async def complete(
        self, *, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float = 0.0
    ) -> str:
        if not self._api_key:
            raise LLMCallError("GROQ_API_KEY is not configured", retryable=False)

        headers = {"Authorization": f"Bearer {self._api_key}"}
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._URL, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMCallError(f"Groq request timed out: {exc}", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise LLMCallError(f"Groq request failed: {exc}", retryable=True) from exc

        if response.status_code in (401, 403):
            raise LLMCallError("Groq authentication failed - check GROQ_API_KEY", retryable=False)
        if response.status_code == 429:
            raise LLMCallError("Groq rate limit exceeded", retryable=True)
        if response.status_code >= 500:
            raise LLMCallError(f"Groq server error ({response.status_code})", retryable=True)
        if response.status_code != 200:
            raise LLMCallError(f"Groq unexpected status ({response.status_code})", retryable=False)

        try:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMCallError(f"Malformed Groq response: {exc}", retryable=False) from exc


class GeminiLLMClient(LLMClient):
    """Google Gemini generateContent API."""

    def __init__(self, api_key: str | None, model: str, timeout_seconds: float = 30.0) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    def _url(self) -> str:
        return f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent"

    async def complete(
        self, *, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float = 0.0
    ) -> str:
        if not self._api_key:
            raise LLMCallError("GEMINI_API_KEY is not configured", retryable=False)

        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
        params = {"key": self._api_key}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._url(), params=params, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMCallError(f"Gemini request timed out: {exc}", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise LLMCallError(f"Gemini request failed: {exc}", retryable=True) from exc

        if response.status_code in (401, 403):
            raise LLMCallError("Gemini authentication failed - check GEMINI_API_KEY", retryable=False)
        if response.status_code == 429:
            raise LLMCallError("Gemini rate limit exceeded", retryable=True)
        if response.status_code >= 500:
            raise LLMCallError(f"Gemini server error ({response.status_code})", retryable=True)
        if response.status_code != 200:
            raise LLMCallError(f"Gemini unexpected status ({response.status_code})", retryable=False)

        try:
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMCallError(f"Malformed Gemini response: {exc}", retryable=False) from exc


class MockLLMClient(LLMClient):
    """Deterministic, offline stand-in used for tests and credential-free runs.

    It does NOT call any network API. It performs a naive extractive
    summary over whatever evidence text is present in `user_prompt`, purely
    so the pipeline is runnable end-to-end without secrets. This is clearly
    distinct from a real LLM integration and is logged loudly whenever active.
    """

    async def complete(
        self, *, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float = 0.0
    ) -> str:
        logger.warning("mock_llm_client_active", extra={"note": "no LLM_PROVIDER credentials configured"})
        # Planner calls: return no subquestions (let deterministic fallback handle decomposition).
        if "sub-question" in system_prompt.lower() or "subquestions" in system_prompt.lower():
            return '{"subquestions": []}'
        # Synthesis calls: return a minimal, clearly-labeled placeholder so
        # downstream JSON parsing / citation validation still exercise real
        # code paths in tests and demos.
        return (
            '{"answer": "Mock synthesis: no real LLM configured. '
            'This is a placeholder answer generated without model reasoning.", '
            '"claims": []}'
        )


def build_llm_client(
    *, provider: str, model: str, groq_api_key: str | None, gemini_api_key: str | None, timeout_seconds: float
) -> LLMClient:
    if provider == "groq":
        return GroqLLMClient(api_key=groq_api_key, model=model, timeout_seconds=timeout_seconds)
    if provider == "gemini":
        return GeminiLLMClient(api_key=gemini_api_key, model=model, timeout_seconds=timeout_seconds)
    return MockLLMClient()
