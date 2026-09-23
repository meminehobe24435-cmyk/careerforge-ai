"""The heuristic provider: a deterministic, dependency-free "model".

Why this exists
---------------
A portfolio project that only works when someone supplies an API key is a project
that cannot be reviewed, cannot run in CI, and cannot be demonstrated on a
locked-down interview laptop. This provider makes CareerForge AI fully functional
with **no key, no network and no GPU** (ADR-009).

How it works
------------
It is not a language model and does not pretend to be. It is a rule engine that
returns **schema-valid** structured output: lexicon-driven skill extraction for
JD parsing, token-overlap evidence matching for claim validation, section
heuristics for resume parsing, a topic-keyed question bank for interviews, and a
feature-hash embedding for retrieval.

Everything it produces is flagged ``degraded=True`` with
``DegradationReason.NO_API_KEY`` so the UI can say so plainly. Honest and limited
beats confident and wrong.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
import time

from careerforge_ai.errors import SchemaValidationError
from careerforge_ai.providers.base import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    ProviderCapabilities,
    SchemaT,
    StreamChunk,
    StructuredContext,
    messages_to_text,
)
from careerforge_ai.providers.heuristic.registry import HEURISTIC_HANDLERS
from careerforge_ai.providers.heuristic.synthesis import synthesize_model
from careerforge_ai.providers.heuristic.text import heuristic_embedding
from careerforge_ai.providers.tokens import estimate_messages_tokens, estimate_tokens
from careerforge_ai.schemas.common import DegradationReason
from careerforge_ai.schemas.observability import Cost, TokenUsage

__all__ = ["HeuristicProvider"]

_DEFAULT_EMBEDDING_DIM = 1536
_MODEL_NAME = "heuristic-rules-v1"
_EMBEDDING_MODEL_NAME = "heuristic-ngram-hash-v1"


class HeuristicProvider:
    """Deterministic provider implementing the :class:`LLMProvider` port."""

    def __init__(self, *, dim: int = _DEFAULT_EMBEDDING_DIM) -> None:
        self._dim = dim

    @property
    def name(self) -> str:
        return "heuristic"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="heuristic",
            supports_streaming=True,
            supports_embeddings=True,
            supports_native_json_schema=True,
            requires_api_key=False,
            deterministic=True,
            notes=(
                "Rule-based provider used when no API key is configured. Results are "
                "schema-valid and reproducible but deliberately conservative."
            ),
        )

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
        text = messages_to_text(messages)
        content = self._template_reply(text)
        prompt_tokens = estimate_messages_tokens([message.content for message in messages])
        completion_tokens = estimate_tokens(content)
        return ChatResult(
            content=content,
            provider=self.name,
            model=model or _MODEL_NAME,
            tokens=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                estimated=True,
            ),
            cost=Cost(),
            latency_ms=int((time.perf_counter() - started) * 1000),
            degraded=True,
            degradation_reason=DegradationReason.NO_API_KEY,
        )

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        result = await self.chat(
            messages, temperature=temperature, max_tokens=max_tokens, model=model
        )
        # Chunk on word boundaries so the client renders a natural cadence.
        words = result.content.split(" ")
        for index, word in enumerate(words):
            suffix = "" if index == len(words) - 1 else " "
            yield StreamChunk(
                delta=word + suffix,
                done=False,
                provider=self.name,
                model=result.model,
                degraded=True,
            )
        yield StreamChunk(
            delta="",
            done=True,
            provider=self.name,
            model=result.model,
            tokens=result.tokens,
            cost=result.cost,
            degraded=True,
        )

    # ── embeddings ───────────────────────────────────────────────────────────

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> EmbeddingResult:
        started = time.perf_counter()
        vectors = [heuristic_embedding(text, dim=self._dim) for text in texts]
        prompt_tokens = sum(estimate_tokens(text) for text in texts)
        return EmbeddingResult(
            vectors=vectors,
            provider=self.name,
            model=model or _EMBEDDING_MODEL_NAME,
            dim=self._dim,
            tokens=TokenUsage(
                prompt_tokens=prompt_tokens, total_tokens=prompt_tokens, estimated=True
            ),
            cost=Cost(),
            latency_ms=int((time.perf_counter() - started) * 1000),
            degraded=True,
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
        """Produce schema-valid output, using a specific handler when one exists."""
        text = self._structured_input(messages, context or {})
        handler = HEURISTIC_HANDLERS.get(schema.__name__)
        if handler is not None:
            try:
                candidate = handler(text, context or {})
            except Exception as exc:
                raise SchemaValidationError(
                    f"heuristic handler for {schema.__name__} failed",
                    details={"schema": schema.__name__, "error": str(exc)},
                ) from exc
            if isinstance(candidate, schema):
                return candidate
            return schema.model_validate(candidate)

        synthesized = synthesize_model(schema, text)
        return schema.model_validate(synthesized.model_dump())

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _structured_input(messages: Sequence[ChatMessage], context: StructuredContext) -> str:
        """Prefer the explicit ``source_text`` from context, else the last user turn."""
        explicit = context.get("source_text")
        if isinstance(explicit, str) and explicit.strip():
            return explicit
        for message in reversed(messages):
            if message.role == "user" and message.content.strip():
                return message.content
        return messages_to_text(messages)

    @staticmethod
    def _template_reply(text: str) -> str:
        lowered = text.lower()
        if "jd" in lowered or "job description" in lowered:
            return (
                "本地规则引擎已解析岗位描述：提取到的技能按必备/优先/加分三级归类，"
                "每一项均绑定 JD 原文出处。未配置模型 API Key，因此未生成叙述性说明。"
            )
        if "interview" in lowered or "面试" in text:
            return (
                "本地规则引擎已根据岗位要求与证据图谱生成面试问题序列，难度按回答情况自适应调整。"
            )
        return (
            "本地规则引擎已处理该请求。未配置模型 API Key，结果基于确定性规则生成，"
            "不包含模型推断内容。"
        )
