"""
inference_service.app.ollama_client
=====================================

LLM provider abstraction — Ollama (local) and Groq (cloud) behind
one interface.
"""

from __future__ import annotations

import abc
from functools import lru_cache
from typing import AsyncIterator

import httpx
from groq import AsyncGroq

from aletheia_core.config import get_settings
from aletheia_core.exceptions import InferenceError
from aletheia_core.logging import get_logger

log = get_logger(__name__)


# --- Abstract base class — the shared interface --------------------------

class LLMProvider(abc.ABC):
    """
    Every LLM provider implements exactly these two methods.
    `abc.ABC` and `@abc.abstractmethod` make this contract enforced
    by Python itself
    """

    @abc.abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None,
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, int | None, int | None]:
        """
        Returns (content, prompt_tokens, completion_tokens).
        """
        ...


    @abc.abstractmethod
    async def stream(
        self,
        prompt: str,
        system_prompt: str | None,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        """Yields text chunks as they stream from the provider."""
        ...


# --- Ollama implementation -----------------------------------------------

class OllamaProvider(LLMProvider):
    """
    Calls the local Ollama server via its REST API.
    """

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=120.0)

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None,
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, int | None, int | None]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self._client.post(
                "/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["message"]["content"]
            prompt_tokens = data.get("prompt_eval_count")
            completion_tokens = data.get("eval_count")
            return content, prompt_tokens, completion_tokens
        except httpx.HTTPError as e:
            raise InferenceError(
                message=f"Ollama request failed: {e}",
                error_code="ollama_request_failed",
            ) from e

    async def stream(
        self,
        prompt: str,
        system_prompt: str | None,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            async with self._client.stream(
                "POST",
                "/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": True,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    import json
                    chunk = json.loads(line)
                    if token := chunk.get("message", {}).get("content", ""):
                        yield token
        except httpx.HTTPError as e:
            raise InferenceError(
                message=f"Ollama stream failed: {e}",
                error_code="ollama_stream_failed",
            ) from e


# --- Groq implementation -------------------------------------------------

class GroqProvider(LLMProvider):
    """
    Calls Groq's API via their official async SDK.
    Groq is the cloud/speed option — requires GROQ_API_KEY and an
    internet connection
    """

    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._client = AsyncGroq(api_key=api_key)

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None,
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, int | None, int | None]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = response.choices[0].message.content or ""
            prompt_tokens = response.usage.prompt_tokens if response.usage else None
            completion_tokens = response.usage.completion_tokens if response.usage else None
            return content, prompt_tokens, completion_tokens
        except Exception as e:
            raise InferenceError(
                message=f"Groq request failed: {e}",
                error_code="groq_request_failed",
            ) from e

    async def stream(
        self,
        prompt: str,
        system_prompt: str | None,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            async with await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            ) as response:
                async for chunk in response:
                    if token := chunk.choices[0].delta.content:
                        yield token
        except Exception as e:
            raise InferenceError(
                message=f"Groq stream failed: {e}",
                error_code="groq_stream_failed",
            ) from e


# --- Provider factory -----------------------------------------------------

@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    """
    Returns the configured LLM provider singleton.
    LLM_PROVIDER in .env controls which one — "ollama" (default,
    offline) or "groq" (cloud, fast). The rest of the system calls
    this function and never needs to know which concrete class it got.
    """
    settings = get_settings()
    provider = getattr(settings, "llm_provider", "ollama")

    if provider == "groq":
        if not getattr(settings, "groq_api_key", None):
            raise InferenceError(
                message="LLM_PROVIDER=groq but GROQ_API_KEY is not set.",
                error_code="groq_missing_api_key",
            )
        log.info("llm_provider_selected", provider="groq", model=settings.groq_model)
        return GroqProvider(api_key=settings.groq_api_key, model=settings.groq_model)

    log.info("llm_provider_selected", provider="ollama", model=settings.ollama_model)
    return OllamaProvider(base_url=settings.ollama_url, model=settings.ollama_model)