"""The providers the negative-path suites drive: one that misbehaves, one that declares an outage.

Extracted from ``failure_support.py`` when that module crossed the file-length gate, and along the seam
that was already there. Both classes exist to be *scripted* rather than configured, and they are
different in a way that matters to observability:

* :class:`ScriptedProvider` fails in a named way and, on the successful path, delegates to the real
  heuristic provider. Its ``capabilities.deterministic`` is ``False``, which is the whole reason it
  exists beside the heuristic one: ``ResilientProvider`` marks a *deterministic* primary as ``degraded``
  even when it answered, so nothing in the shipped chain can produce a ``succeeded`` run.
* :class:`DeclaredOutageProvider` raises ``ProviderUnavailableError`` — the one error the chain passes
  through with its message intact. Its message is therefore what the run stores, which is where the
  sanitiser earns its place.

Not named ``test_*`` so pytest does not collect it, the same convention as the other support modules.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

from careerforge_ai.errors import (
    BudgetExceededError,
    ProviderError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    SchemaValidationError,
)
from careerforge_ai.providers.base import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    ProviderCapabilities,
    SchemaT,
    StreamChunk,
    StructuredContext,
    StructuredResult,
)
from careerforge_ai.providers.heuristic import HeuristicProvider
from careerforge_ai.schemas.observability import Cost, LLMUsage, TokenUsage
from tests.leak_fixtures import LEAKY_ERROR

#: An upstream that never answers within the chain's timeout (a real hang, not a raise).
HANG = "hang"
#: ``ProviderTimeoutError`` — what ``openai_compat`` raises for a read timeout.
TIMEOUT = "timeout"
#: ``ProviderRateLimitedError`` — what ``openai_compat`` raises for an HTTP 429.
RATE_LIMITED = "rate_limited"
#: Truncated JSON that cannot satisfy the declared schema (ADR-007's repair case).
MALFORMED_JSON = "malformed_json"
#: A bug inside the provider layer: not a ``CareerForgeError``, so the chain flattens it.
CRASH = "crash"
#: A model answer of the wrong shape: the call succeeds and the *next* step crashes on it.
WRONG_SHAPE = "wrong_shape"
#: The spend ceiling: ``RoutedProvider`` raises this once the budget is exhausted.
BUDGET = "budget"
#: An upstream error whose *text* contains a fake API key, a bearer token and a whole document.
#: Used to prove the stored error is sanitised before it becomes a row.
LEAKY = "leaky"

#: The answer the malformed provider *intended* to send. If this string ever reaches a response,
#: a fabricated model answer has been presented as a real one and the test that watches for it
#: failed on purpose.
FABRICATED_ROLE = "FABRICATED-ROLE-XYZ"
#: Truncated on purpose: one unclosed object, which no JSON parser can turn into a schema.
GARBAGE_JSON = f'{{"role": "{FABRICATED_ROLE}", "company": "Fabricated Ltd"'

__all__ = [
    "BUDGET",
    "CRASH",
    "DeclaredOutageProvider",
    "FABRICATED_ROLE",
    "GARBAGE_JSON",
    "HANG",
    "LEAKY",
    "MALFORMED_JSON",
    "RATE_LIMITED",
    "ScriptedProvider",
    "TIMEOUT",
    "WRONG_SHAPE",
]


class ScriptedProvider:
    """A provider that reports usage when it works, and fails as told when it does not.

    ``capabilities.deterministic`` is ``False``, which is the whole reason this class exists
    beside the heuristic provider: ``ResilientProvider`` marks a *deterministic* primary as
    ``degraded`` even when it answered, so nothing in the shipped chain can produce a
    ``succeeded`` run. A non-deterministic primary that answers can.

    The successful ``structured_output`` delegates to the real :class:`HeuristicProvider` rather
    than returning a hand-built object: the answers a test asserts on are then the product's own,
    produced from the request's text.
    """

    def __init__(
        self,
        failure: str | None = None,
        *,
        name: str = "scripted",
        hang_s: float = 5.0,
        prompt_tokens: int = 120,
        completion_tokens: int = 30,
        cost_usd: float = 0.0012,
        cost_cny: float = 0.0086,
        tokens: TokenUsage | None = None,
        cached_tokens: int | None = None,
        reports_usage: bool = True,
    ) -> None:
        self.failure = failure
        self.hang_s = hang_s
        self.tokens = tokens or TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cached_tokens=cached_tokens or 0,
        )
        self.cost = Cost(usd=cost_usd, cny=cost_cny)
        #: ``None`` means this provider is configured to report *no* usage — the case a paid
        #: vendor produces when it omits the usage object. The envelope must then say
        #: ``unavailable`` rather than 0, which is what the provider-contract tests assert.
        self.cached_tokens = cached_tokens
        self.reports_usage = reports_usage
        self._name = name
        #: How many times the provider was asked. Proves whether the retry policy ran.
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self._name,
            supports_streaming=False,
            supports_embeddings=False,
            supports_native_json_schema=True,
            requires_api_key=True,
            deterministic=False,
            reports_cached_tokens=self.cached_tokens is not None,
            supports_usage_envelope=True,
        )

    def _raise(self) -> None:
        if self.failure == TIMEOUT:
            raise ProviderTimeoutError("upstream did not answer within the read timeout")
        if self.failure == RATE_LIMITED:
            raise ProviderRateLimitedError("upstream returned HTTP 429", retry_after_seconds=30)
        if self.failure == LEAKY:
            # A provider that echoes its request and its headers back in the error text — the
            # realistic shape of an SDK's transport error, and the reason the sanitiser exists.
            raise ProviderError(LEAKY_ERROR, details={"raw": LEAKY_ERROR})
        if self.failure == MALFORMED_JSON:
            raise SchemaValidationError(
                "model output did not satisfy the declared schema",
                details={"raw": GARBAGE_JSON, "schema": "ExtractedJD"},
            )
        if self.failure == CRASH:
            raise ValueError("bug inside the provider layer")
        if self.failure == BUDGET:
            raise BudgetExceededError(
                "daily AI budget exhausted", details={"limit_usd": 1.0, "spent_usd": 1.0}
            )
        assert self.failure in (None, WRONG_SHAPE), f"unknown scripted failure: {self.failure!r}"

    async def _fail_or_hang(self) -> None:
        """Hang first (so the *chain's* timeout fires), then raise if the script says so."""
        self.calls += 1
        if self.failure == HANG:
            await asyncio.sleep(self.hang_s)
        self._raise()

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> ChatResult:
        await self._fail_or_hang()
        return ChatResult(
            content="ok",
            provider=self.name,
            model="scripted-model",
            tokens=self.tokens,
            cost=self.cost,
            latency_ms=12,
            usage=self.envelope(),
        )

    def envelope(self) -> LLMUsage:
        """This provider's usage envelope, honouring ``reports_usage``.

        The three shapes a provider contract test needs: reported usage, estimated usage, and no
        usage at all. The last one is the interesting one — it must come back ``unavailable``.
        """
        if not self.reports_usage:
            return LLMUsage.unavailable(provider=self.name, model="scripted-model")
        return LLMUsage.from_token_usage(
            self.tokens,
            self.cost,
            provider=self.name,
            model="scripted-model",
            cached_tokens_reported=self.cached_tokens is not None,
        )

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        await self._fail_or_hang()
        yield StreamChunk(delta="ok", done=True, provider=self.name, model="scripted-model")

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> EmbeddingResult:
        await self._fail_or_hang()
        return EmbeddingResult(
            vectors=[[0.0, 0.1] for _ in texts],
            provider=self.name,
            model="scripted-embed",
            dim=2,
            tokens=TokenUsage(prompt_tokens=10, total_tokens=10),
            cost=Cost(usd=0.00001, cny=0.00007),
            latency_ms=5,
        )

    async def structured_output(
        self,
        messages: Sequence[ChatMessage],
        schema: type[SchemaT],
        *,
        context: StructuredContext | None = None,
        temperature: float = 0.0,
        model: str | None = None,
    ) -> SchemaT:
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
        """Structured output with an envelope, so the metered path can be measured end to end.

        The successful value is still the product's own: the same heuristic extractor the zero-key
        deployment runs, so the answer a test reads is derived from the request's text.
        """
        await self._fail_or_hang()
        if self.failure == WRONG_SHAPE:
            return StructuredResult(value=_WrongShape(), usage=self.envelope())  # type: ignore[arg-type]
        value = await HeuristicProvider().structured_output(
            messages, schema, context=context, temperature=temperature, model=model
        )
        return StructuredResult(value=value, usage=self.envelope())


class DeclaredOutageProvider:
    """A provider that declares its own outage and keeps its message.

    ``ProviderUnavailableError`` is the one error the resilience chain passes through unchanged
    (PHASE 13): the provider already decided it is unavailable, and flattening it into the chain's own
    "no provider could serve the request" would erase the upstream's status code, its request id and
    the sentence it actually said. That is the realistic shape of an SDK's transport error — and it is
    the case where the *sanitiser* is the only thing between an arbitrary exception and a browsable
    table, because the chain no longer rewrites the text.

    Used by the leak tests: the message it carries contains a fake API key, a bearer token and a whole
    document, so a stored row that contains any of them proves the sanitiser did not run.
    """

    def __init__(self, message: str, *, name: str = "declared-outage") -> None:
        self.message = message
        self._name = name
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self._name,
            supports_streaming=False,
            supports_embeddings=False,
            supports_native_json_schema=False,
            requires_api_key=True,
            deterministic=False,
        )

    def _outage(self) -> ProviderUnavailableError:
        return ProviderUnavailableError(
            self.message, details={"status": 400, "chain": [self._name]}
        )

    async def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResult:
        self.calls += 1
        raise self._outage()

    async def stream(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> AsyncIterator[StreamChunk]:
        self.calls += 1
        raise self._outage()
        yield StreamChunk()  # pragma: no cover - unreachable; makes this an async generator

    async def embed(self, texts: Sequence[str], **kwargs: Any) -> EmbeddingResult:
        self.calls += 1
        raise self._outage()

    async def structured_output(
        self,
        messages: Sequence[ChatMessage],
        schema: type[SchemaT],
        **kwargs: Any,
    ) -> SchemaT:
        self.calls += 1
        raise self._outage()


class _WrongShape:
    """What a provider returns when it ignored the schema it was handed.

    Every field the JD workflow asks for is present and of the wrong type, so the failure happens
    one step later — inside ``normalise``, on ``item.name`` — rather than at the provider
    boundary. That is the shape of a real "the model answered something else" incident.
    """

    role = "not a schema"
    company = "not a schema"
    required_skills = [object()]
    preferred_skills = [object()]
    bonus_skills = []
