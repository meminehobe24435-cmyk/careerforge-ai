"""Task-class routing and the per-user AI budget guardrail.

Different tasks deserve different models: extraction and classification run on a
cheap model, interview turns and resume generation on a strong one. Routing that
decision through one object keeps model names out of agent code and puts the cost
control in a single auditable place.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass

from careerforge_ai.errors import BudgetExceededError
from careerforge_ai.providers.base import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    LLMProvider,
    ProviderCapabilities,
    SchemaT,
    StreamChunk,
    StructuredContext,
    StructuredResult,
    structured_output_envelope,
)
from careerforge_ai.schemas.observability import Cost

__all__ = ["TaskClass", "Budget", "RoutedProvider"]


class TaskClass(str):
    """Task classes used to route to differently-priced models."""

    EXTRACTION = "extraction"
    GENERATION = "generation"
    INTERVIEW = "interview"
    EMBEDDING = "embedding"


@dataclass(slots=True)
class Budget:
    """A spend ceiling. Exhaustion degrades to the next provider, never to a 500."""

    daily_usd: float
    spent_usd: float = 0.0

    @property
    def exhausted(self) -> bool:
        return self.daily_usd > 0 and self.spent_usd >= self.daily_usd

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.daily_usd - self.spent_usd)


class RoutedProvider:
    """Selects a model per task class and enforces the budget.

    Once the budget is exhausted the router raises :class:`BudgetExceededError`,
    which the resilience layer converts into a heuristic fallback. The user is
    told the result is degraded rather than silently receiving a lower-quality
    answer.
    """

    def __init__(
        self,
        inner: LLMProvider,
        *,
        model_by_task: Mapping[str, str] | None = None,
        budget: Budget | None = None,
        task: str = TaskClass.GENERATION,
    ) -> None:
        self._inner = inner
        self._model_by_task = dict(model_by_task or {})
        self._budget = budget
        self._task = task

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._inner.capabilities

    @property
    def budget(self) -> Budget | None:
        return self._budget

    def _model_for(self, task: str | None) -> str | None:
        return self._model_by_task.get(task or self._task) or None

    def charge(self, cost: Cost) -> None:
        if self._budget is not None:
            self._budget.spent_usd += cost.usd

    def _guard(self) -> None:
        if self._budget is not None and self._budget.exhausted:
            raise BudgetExceededError(
                "daily AI budget exhausted",
                details={
                    "limit_usd": self._budget.daily_usd,
                    "spent_usd": round(self._budget.spent_usd, 6),
                },
            )

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> ChatResult:
        self._guard()
        result = await self._inner.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model or self._model_for(self._task),
        )
        self.charge(result.cost)
        return result

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self._guard()
        async for chunk in self._inner.stream(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model or self._model_for(self._task),
        ):
            yield chunk

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> EmbeddingResult:
        self._guard()
        result = await self._inner.embed(texts, model=model or self._model_for(TaskClass.EMBEDDING))
        self.charge(result.cost)
        return result

    async def structured_output(
        self,
        messages: Sequence[ChatMessage],
        schema: type[SchemaT],
        *,
        context: StructuredContext | None = None,
        temperature: float = 0.0,
        model: str | None = None,
    ) -> SchemaT:
        self._guard()
        return await self._inner.structured_output(
            messages,
            schema,
            context=context,
            temperature=temperature,
            model=model or self._model_for(self._task or TaskClass.EXTRACTION),
        )

    async def structured_output_envelope(
        self,
        messages: Sequence[ChatMessage],
        schema: type[SchemaT],
        *,
        context: StructuredContext | None = None,
        temperature: float = 0.0,
        model: str | None = None,
    ) -> StructuredResult[SchemaT]:
        """The structured path, with the router's model choice and budget accounting.

        The budget is charged here for the same reason it is charged on ``chat``: an
        unaccounted structured call would make the spend ceiling unenforceable, and the
        structured path is the only one any agent uses (PHASE 13).
        """
        self._guard()
        resolved_model = model or self._model_for(self._task or TaskClass.EXTRACTION)
        result: StructuredResult[SchemaT] = await structured_output_envelope(
            self._inner,
            messages,
            schema,
            context=context,
            temperature=temperature,
            model=resolved_model,
        )
        self.charge(Cost(usd=result.usage.cost_usd, cny=result.usage.cost_cny))
        return result
