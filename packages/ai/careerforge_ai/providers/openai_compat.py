"""OpenAI-compatible providers (DeepSeek, OpenAI, and Ollama's ``/v1`` endpoint).

One implementation covers every vendor that speaks the OpenAI chat-completions
protocol. Vendor differences that actually matter here are the price table, the
default model name and whether a key is required — all injected, not branched on.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
import json
import time
from typing import Any

import httpx
from pydantic import ValidationError

from careerforge_ai.errors import (
    ProviderError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    SchemaValidationError,
)
from careerforge_ai.observability.pricing import price_for
from careerforge_ai.providers.base import (
    ChatMessage,
    ChatResult,
    ChatRole,
    EmbeddingResult,
    ProviderCapabilities,
    SchemaT,
    StreamChunk,
    StructuredContext,
    StructuredResult,
)
from careerforge_ai.providers.openai_responses import (
    first_choice_content,
    first_choice_finish,
    first_delta,
    loads_json_object,
    reports_cached_tokens,
    usage_from,
)
from careerforge_ai.providers.tokens import estimate_messages_tokens, estimate_tokens
from careerforge_ai.schemas.observability import LLMUsage, TokenUsage

__all__ = ["OllamaProvider", "OpenAICompatProvider"]

#: Attempts at coercing a model into valid JSON before giving up. One repair
#: round-trip is worth it; more than one is a sign the prompt or schema is wrong.
_MAX_SCHEMA_ATTEMPTS = 2


class OpenAICompatProvider:
    """Chat, streaming, embeddings and structured output over the OpenAI protocol."""

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        model: str,
        api_key: str = "",
        embedding_model: str = "",
        embedding_dim: int = 1536,
        timeout_s: float = 60.0,
        requires_api_key: bool = True,
        supports_native_json_schema: bool = True,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._name = name
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._embedding_model = embedding_model or model
        self._embedding_dim = embedding_dim
        self._timeout_s = timeout_s
        self._requires_api_key = requires_api_key
        self._supports_native_json_schema = supports_native_json_schema
        self._client = client
        #: A provider that needs no key is running on this machine (Ollama), where there is no
        #: vendor-side prompt cache to report and no bill to attribute. Derived rather than
        #: passed, so a new local deployment cannot forget to declare it.
        self._is_local = not requires_api_key

    @property
    def model(self) -> str:
        """The default model this provider was configured with."""
        return self._model

    # ── port surface ─────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self._name,
            supports_streaming=True,
            supports_embeddings=True,
            supports_native_json_schema=self._supports_native_json_schema,
            requires_api_key=self._requires_api_key,
            deterministic=False,
            # OpenAI ``prompt_tokens_details.cached_tokens`` and DeepSeek's
            # ``prompt_cache_hit_tokens`` are both read below. Ollama does not report either,
            # which is why this is a property of the provider and not a global constant.
            reports_cached_tokens=not self._is_local,
            supports_usage_envelope=True,
        )

    # ── HTTP plumbing ────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        stream: bool = False,
    ) -> Any:
        url = f"{self._base_url}{path}"
        try:
            if self._client is not None:
                response = await self._client.request(
                    method, url, headers=self._headers(), json=payload, timeout=self._timeout_s
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                    response = await client.request(
                        method, url, headers=self._headers(), json=payload
                    )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"{self._name} request timed out after {self._timeout_s:g}s",
                details={"url": url},
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"{self._name} transport error: {exc}", details={"url": url}
            ) from exc

        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            raise ProviderRateLimitedError(
                f"{self._name} rate limited",
                retry_after_seconds=float(retry_after) if retry_after else None,
                details={"status": 429},
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"{self._name} returned HTTP {response.status_code}",
                details={"status": response.status_code, "body": response.text[:500]},
            )
        if stream:
            return response
        return response.json()

    # ── chat ─────────────────────────────────────────────────────────────────

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> ChatResult:
        started = time.perf_counter()
        resolved_model = model or self._model
        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": [message.as_dict() for message in messages],
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        data = await self._request("POST", "/chat/completions", payload=payload)
        content = first_choice_content(data)
        usage = usage_from(data, messages, content)
        latency_ms = int((time.perf_counter() - started) * 1000)
        cost = price_for(self._name, resolved_model).cost_for(usage)

        return ChatResult(
            content=content,
            provider=self._name,
            model=resolved_model,
            tokens=usage,
            cost=cost,
            latency_ms=latency_ms,
            finish_reason=first_choice_finish(data),
            usage=LLMUsage.from_token_usage(
                usage,
                cost,
                provider=self._name,
                model=resolved_model,
                cached_tokens_reported=reports_cached_tokens(data) and not self._is_local,
            ),
        )

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        resolved_model = model or self._model
        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": [message.as_dict() for message in messages],
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        url = f"{self._base_url}/chat/completions"
        collected = ""
        streamed_usage: TokenUsage | None = None
        try:
            async with (
                httpx.AsyncClient(timeout=self._timeout_s) as client,
                client.stream("POST", url, headers=self._headers(), json=payload) as response,
            ):
                if response.status_code >= 400:
                    body = await response.aread()
                    raise ProviderError(
                        f"{self._name} stream failed with HTTP {response.status_code}",
                        details={
                            "status": response.status_code,
                            "body": body[:300].decode(errors="replace"),
                        },
                    )
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_text = line[5:].strip()
                    if data_text == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_text)
                    except json.JSONDecodeError:
                        continue
                    # Some vendors (OpenAI with ``stream_options``, DeepSeek always) put the
                    # usage object on the last data frame. When it is there, the stream reports
                    # measured usage instead of the character-count estimate.
                    if chunk.get("usage"):
                        streamed_usage = usage_from(chunk, messages, collected)
                    delta = first_delta(chunk)
                    if delta:
                        collected += delta
                        yield StreamChunk(
                            delta=delta,
                            provider=self._name,
                            model=resolved_model,
                            request_id=response.headers.get("x-request-id"),
                        )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"{self._name} stream timed out") from exc

        usage = streamed_usage or TokenUsage(
            prompt_tokens=estimate_messages_tokens([message.content for message in messages]),
            completion_tokens=estimate_tokens(collected),
            total_tokens=estimate_messages_tokens([message.content for message in messages])
            + estimate_tokens(collected),
            estimated=True,
        )
        cost = price_for(self._name, resolved_model).cost_for(usage)
        yield StreamChunk(
            delta="",
            done=True,
            provider=self._name,
            model=resolved_model,
            tokens=usage,
            cost=cost,
            usage=LLMUsage.from_token_usage(
                usage,
                cost,
                provider=self._name,
                model=resolved_model,
                cached_tokens_reported=not self._is_local and streamed_usage is not None,
            ),
            usage_reported=True,
        )

    # ── embeddings ───────────────────────────────────────────────────────────

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> EmbeddingResult:
        started = time.perf_counter()
        if not texts:
            return EmbeddingResult(
                vectors=[],
                provider=self._name,
                model=model or self._embedding_model,
                dim=self._embedding_dim,
            )
        resolved_model = model or self._embedding_model
        payload: dict[str, Any] = {"model": resolved_model, "input": list(texts)}
        data = await self._request("POST", "/embeddings", payload=payload)

        vectors: list[list[float]] = []
        for item in data.get("data", []):
            vector = item.get("embedding")
            if isinstance(vector, list):
                vectors.append([float(value) for value in vector])

        dim = len(vectors[0]) if vectors else self._embedding_dim
        usage = usage_from(
            data, [ChatMessage(role=ChatRole.USER, content=text) for text in texts], ""
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        return EmbeddingResult(
            vectors=vectors,
            provider=self._name,
            model=resolved_model,
            dim=dim,
            tokens=usage,
            cost=price_for(self._name, resolved_model).cost_for(usage),
            latency_ms=latency_ms,
        )

    # ── structured output ────────────────────────────────────────────────────

    async def structured_output(
        self,
        messages: Sequence[ChatMessage],
        schema: type[SchemaT],
        *,
        context: StructuredContext | None = None,
        temperature: float = 0.0,
        model: str | None = None,
    ) -> SchemaT:
        """Generate JSON conforming to ``schema``, with one repair attempt.

        The repair attempt feeds the validation error back to the model, which
        resolves the overwhelming majority of near-misses. If it still fails we
        raise :class:`SchemaValidationError` and let the orchestrator degrade —
        never silently coercing a malformed answer into a plausible one.
        """
        result = await self.structured_output_envelope(
            messages, schema, context=context, temperature=temperature, model=model
        )
        return result.value

    async def structured_output_envelope(
        self,
        messages: Sequence[ChatMessage],
        schema: type[SchemaT],
        *,
        context: StructuredContext | None = None,
        temperature: float = 0.0,
        model: str | None = None,
    ) -> StructuredResult[SchemaT]:
        """The same call as :meth:`structured_output`, carrying what it cost.

        This is the method that closes ``docs/QUALITY.md`` §7.1: the parsed schema used to be
        the only thing this path returned, so the provider's ``usage`` object was discarded on
        the floor and every run in the product recorded zero tokens. Usage is accumulated across
        the repair attempt as well — a second request really was sent, and pretending it was
        free would under-report exactly the calls that are most worth watching.
        """
        resolved_model = model or self._model
        json_schema = schema.model_json_schema()
        conversation = list(messages)
        last_error: str = ""
        spent = LLMUsage.unavailable(provider=self._name, model=resolved_model)

        for attempt in range(_MAX_SCHEMA_ATTEMPTS):
            payload: dict[str, Any] = {
                "model": resolved_model,
                "messages": [message.as_dict() for message in conversation],
                "temperature": temperature,
            }
            if self._supports_native_json_schema:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "schema": json_schema,
                        "strict": False,
                    },
                }
            else:
                payload["response_format"] = {"type": "json_object"}

            data = await self._request("POST", "/chat/completions", payload=payload)
            content = first_choice_content(data)
            usage = usage_from(data, conversation, content)
            cost = price_for(self._name, resolved_model).cost_for(usage)
            spent = spent.merge(
                LLMUsage.from_token_usage(
                    usage,
                    cost,
                    provider=self._name,
                    model=resolved_model,
                    cached_tokens_reported=(reports_cached_tokens(data) and not self._is_local),
                )
            )
            try:
                parsed = loads_json_object(content)
                return StructuredResult(value=schema.model_validate(parsed), usage=spent)
            except (ValidationError, ValueError) as exc:
                last_error = str(exc)[:800]
                if attempt + 1 >= _MAX_SCHEMA_ATTEMPTS:
                    break
                conversation = [
                    *conversation,
                    ChatMessage(role=ChatRole.ASSISTANT, content=content[:2000]),
                    ChatMessage(
                        role=ChatRole.USER,
                        content=(
                            "Your previous response did not match the required JSON schema. "
                            f"Validation error:\n{last_error}\n"
                            "Return ONLY a corrected JSON object. Do not add commentary."
                        ),
                    ),
                ]

        raise SchemaValidationError(
            f"{self._name} failed to produce valid {schema.__name__}",
            details={"schema": schema.__name__, "model": resolved_model, "error": last_error},
        )


class OllamaProvider(OpenAICompatProvider):
    """Local inference through Ollama's OpenAI-compatible endpoint.

    This is the provider a privacy-conscious user selects: with it, and with
    Local Mode enabled, no resume content leaves the machine.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b",
        embedding_model: str = "nomic-embed-text",
        embedding_dim: int = 768,
        timeout_s: float = 180.0,
    ) -> None:
        super().__init__(
            name="ollama",
            base_url=f"{base_url.rstrip('/')}/v1",
            model=model,
            api_key="",
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
            timeout_s=timeout_s,
            requires_api_key=False,
            supports_native_json_schema=False,
        )


# ── response helpers ─────────────────────────────────────────────────────────
