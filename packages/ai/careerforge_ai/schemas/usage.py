"""Token usage and its provenance — the envelope every provider call returns.

Kept apart from the run and step records in :mod:`careerforge_ai.schemas.observability` for the same
reason the two concerns are apart in the code: a *record* describes what a workflow did, and a *usage
envelope* describes what a model call cost and how well that is known. The second is what makes the
first's numbers readable, and it is the only place that decides how those numbers reach SQL.

The distinction this module exists to keep is one line long: **``0`` is a measurement, ``None`` is an
absence of one.** :class:`TokenUsage` holds counters, where zero means the provider said zero.
:class:`LLMUsage` holds the envelope, where the counts are nullable and ``usage_status`` says which
kind of fact they are.
"""

from __future__ import annotations

from pydantic import Field

from careerforge_ai.schemas.common import CFBaseModel, UsageStatus

__all__ = [
    "Cost",
    "LLMUsage",
    "TokenUsage",
    "usage_status_of",
]


class Cost(CFBaseModel):
    """Dual-currency cost so the dashboard works for both CNY and USD pricing."""

    usd: float = Field(default=0.0, ge=0.0)
    cny: float = Field(default=0.0, ge=0.0)
    currency: str = "USD"
    price_table_version: str = "pricing@1.0.0"

    def __add__(self, other: Cost) -> Cost:
        return Cost(
            usd=round(self.usd + other.usd, 8),
            cny=round(self.cny + other.cny, 8),
            currency=self.currency,
            price_table_version=self.price_table_version,
        )


class TokenUsage(CFBaseModel):
    """A token count, as counters.

    ``0`` here means the provider **said** zero. It never means "unknown" — an unknown
    count is :data:`LLMUsage.unavailable`, whose fields are ``None``. Keeping that
    distinction in the type system is the whole point: the cost dashboard's honesty
    rests on it.
    """

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    #: Prompt tokens the provider served from its own cache. Only some vendors report it
    #: (OpenAI and DeepSeek do, via ``prompt_tokens_details.cached_tokens``), so ``0``
    #: means "not reported" for every provider that does not — see
    #: :meth:`LLMUsage.from_token_usage`, which carries the provider's cache support
    #: forward rather than letting the two cases look identical.
    cached_tokens: int = Field(default=0, ge=0)
    estimated: bool = Field(
        default=False,
        description="True when tokens were estimated rather than reported by the provider",
    )

    def merged(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
            estimated=self.estimated or other.estimated,
        )


def usage_status_of(usage: TokenUsage | None) -> UsageStatus:
    """Which kind of fact a :class:`TokenUsage` carries. ``None`` is genuinely unknown."""
    if usage is None:
        return UsageStatus.UNAVAILABLE
    return UsageStatus.ESTIMATED if usage.estimated else UsageStatus.REPORTED


class LLMUsage(CFBaseModel):
    """The usage envelope every provider call returns, whatever shape it was called in.

    ``chat``, ``stream`` and ``structured_output`` all produce one of these, which is what
    makes the cost page add up. Before PHASE 13 only ``chat`` did: the structured path
    returned the parsed schema and dropped the provider's usage object, so
    ``agent_runs.total_tokens`` was structurally zero for every agent in the product (all of
    them use the structured path) — a paid deployment's cost page read ``$0.00``.

    ``input_tokens``/``output_tokens`` are the vendor-neutral names the API and the UI use
    (``prompt_tokens``/``completion_tokens`` are the OpenAI dialect and stay on
    :class:`TokenUsage`, where they are the provider's own vocabulary).

    **Every count is nullable, and ``None`` is not ``0``.** When ``usage_status`` is
    ``UNAVAILABLE`` the counts are ``None`` by construction, and they are stored as SQL
    ``NULL`` rather than ``0`` — see :meth:`projection`, which is the single place that
    decides this for the database, so the API, the columns and the UI cannot disagree.
    """

    usage_status: UsageStatus = UsageStatus.UNAVAILABLE
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0.0)
    estimated_cost_cny: float | None = Field(default=None, ge=0.0)
    provider: str | None = None
    model: str | None = None
    request_id: str | None = None
    #: ``True`` only when the provider's response actually carried a cached-token count.
    #: ``cached_tokens=0`` with this ``False`` reads as "we were not told how much was
    #: cached", which is what most providers truthfully amount to.
    cached_tokens_reported: bool = False
    #: Locally counted tokens, kept beside an ``UNAVAILABLE`` verdict rather than inside it.
    #: The zero-key heuristic provider computes these from character counts; they are not
    #: usage and must never be summed into a cost, but throwing them away would lose the
    #: only observable about that path.
    estimated_input_tokens: int | None = Field(default=None, ge=0)
    #: Whether any call in this envelope had counters at all. The distinction between
    #: "nothing was reported, so the counts are ``None``" and "one call was not reported and these
    #: counters are therefore incomplete" — kept as a flag so the columns can still store ``NULL``
    #: for the first case without discarding the measurements the second case does have. Not
    #: serialised into API payloads; the schema is strict, so an extra key would be a contract
    #: change nobody asked for.
    counters_present: bool = Field(default=False, exclude=True)

    # ── constructors ─────────────────────────────────────────────────────────

    @classmethod
    def unavailable(
        cls,
        *,
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
        estimated_input_tokens: int | None = None,
    ) -> LLMUsage:
        """The honest answer when nobody reported usage. Counts stay ``None``."""
        return cls(
            usage_status=UsageStatus.UNAVAILABLE,
            provider=provider,
            model=model,
            request_id=request_id,
            estimated_input_tokens=estimated_input_tokens,
        )

    @classmethod
    def partial(
        cls,
        *,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        cached_tokens: int,
        cost_usd: float,
        cost_cny: float,
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
    ) -> LLMUsage:
        """Some calls reported usage and at least one did not.

        The counters are the *known* part — enough to say "at least this much" — and the status says
        they are not the whole story. Discarding them would throw away real, paid-for measurements;
        presenting them as complete is the defect this whole envelope exists to fix.
        """
        return cls(
            usage_status=UsageStatus.UNAVAILABLE,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cached_tokens=cached_tokens,
            estimated_cost_usd=cost_usd,
            estimated_cost_cny=cost_cny,
            provider=provider,
            model=model,
            request_id=request_id,
            counters_present=True,
        )

    @classmethod
    def from_token_usage(
        cls,
        usage: TokenUsage | None,
        cost: Cost | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
        cached_tokens_reported: bool = False,
        status: UsageStatus | None = None,
    ) -> LLMUsage:
        """Build an envelope from the counters a provider returned.

        ``usage=None`` yields :meth:`unavailable` rather than a zeroed envelope, which is the
        rule the whole file exists to enforce.
        """
        if usage is None:
            return cls.unavailable(provider=provider, model=model, request_id=request_id)
        resolved = status or usage_status_of(usage)
        resolved_cost = cost or Cost()
        return cls(
            usage_status=resolved,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            cached_tokens=usage.cached_tokens,
            estimated_cost_usd=resolved_cost.usd,
            estimated_cost_cny=resolved_cost.cny,
            provider=provider,
            model=model,
            request_id=request_id,
            cached_tokens_reported=cached_tokens_reported,
            estimated_input_tokens=usage.prompt_tokens
            if resolved is UsageStatus.ESTIMATED
            else None,
            counters_present=True,
        )

    @classmethod
    def cached(
        cls,
        *,
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
    ) -> LLMUsage:
        """A cache hit: real, cheap, and not a measurement of anything."""
        return cls(
            usage_status=UsageStatus.CACHED,
            provider=provider,
            model=model,
            request_id=request_id,
            counters_present=True,
        )

    # ── reads ────────────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self.usage_status is not UsageStatus.UNAVAILABLE

    @property
    def is_estimated(self) -> bool:
        """Whether these numbers were computed locally rather than reported."""
        return self.usage_status is UsageStatus.ESTIMATED

    @property
    def cost_usd(self) -> float:
        """The money, or ``0.0`` when the cost is unknown.

        ``0.0`` for unknown is safe *only* because :attr:`usage_status` travels beside it and
        the API exposes it; a reader that needs the distinction must read the status, not this.
        """
        return float(self.estimated_cost_usd or 0.0)

    @property
    def cost_cny(self) -> float:
        return float(self.estimated_cost_cny or 0.0)

    @property
    def tokens(self) -> TokenUsage:
        """The counters, for consumers that predate the envelope (``TokenUsage`` is additive)."""
        return TokenUsage(
            prompt_tokens=self.input_tokens or 0,
            completion_tokens=self.output_tokens or 0,
            total_tokens=self.total_tokens or 0,
            cached_tokens=self.cached_tokens or 0,
            estimated=self.is_estimated,
        )

    def with_request(self, request_id: str | None, model: str | None) -> LLMUsage:
        """Attach the correlation facts a provider cannot know.

        A provider sees a prompt; it does not see the HTTP request that caused it, and the
        model name is only known for sure at the layer that chose it. Filling them in here
        keeps one envelope per call rather than two half-filled ones.
        """
        return self.model_copy(
            update={
                "request_id": self.request_id or request_id,
                "model": self.model or model,
            }
        )

    def projection(self) -> dict[str, object]:
        """How this envelope is written to ``agent_runs``/``llm_calls``.

        One function, so the columns cannot drift from the payload:

        * an **unavailable** envelope whose counts are ``None`` stores ``None`` in every count column
          — SQL ``NULL``, which the aggregate queries skip via ``SUM``/``COALESCE``. Storing ``0``
          would claim a measurement nobody took; storing a sentinel such as ``-1`` would break the
          ``>= 0`` CHECK constraints and put a magic value in the API payload;
        * an **unavailable** envelope that *does* hold partial counters (see :meth:`partial`) stores
          those counts: they are real measurements covering part of the work, and the status says so.
          This is the one case a ``NULL`` would destroy information rather than protect honesty;
        * a **cached** envelope stores ``0`` counts and ``0.0`` cost: nothing was billed, and that is
          a fact rather than an unknown;
        * a **reported**/**estimated** envelope stores the numbers and the status, so a reader can
          tell an estimate from a measurement.
        """
        if self.usage_status is UsageStatus.UNAVAILABLE and not self.counters_present:
            return {
                "usage_status": self.usage_status.value,
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "cached_tokens": None,
                "cost_usd": None,
                "cost_cny": None,
            }
        return {
            "usage_status": self.usage_status.value,
            "prompt_tokens": self.input_tokens or 0,
            "completion_tokens": self.output_tokens or 0,
            "total_tokens": self.total_tokens or 0,
            "cached_tokens": self.cached_tokens or 0,
            "cost_usd": self.cost_usd,
            "cost_cny": self.cost_cny,
        }

    def merge(self, other: LLMUsage) -> LLMUsage:
        """Accumulate a second envelope into this one.

        Counters add among the calls that have counters. The status becomes the **weakest fact that
        is still a fact**, which is what makes a total honest rather than merely plausible:

        * a reported call plus an unaccounted one is ``unavailable`` — reporting a partial sum as
          the whole figure is exactly the defect ``docs/QUALITY.md`` §7.1 describes, one level up.
          The counters that *are* known are kept (see :meth:`partial`): discarding them would throw
          away real, paid-for measurements, and the status is what makes them readable as partial;
        * a reported call plus an estimated one is ``estimated`` — bounded, not measured.

        ``cached`` is the exception, and deliberately so: a cache hit billed nothing, so folding it
        into a reported total leaves the counters correct as they stand. Treating it as "unknown"
        would make every run that ever hit the cache report unknown spend, which is a worse lie than
        the one it would avoid.
        """
        if (
            self.usage_status is UsageStatus.UNAVAILABLE
            or other.usage_status is UsageStatus.UNAVAILABLE
        ):
            unknown, known = (
                (self, other) if self.usage_status is UsageStatus.UNAVAILABLE else (other, self)
            )
            if unknown.counters_present or known.counters_present:
                return LLMUsage.partial(
                    input_tokens=(self.input_tokens or 0) + (other.input_tokens or 0),
                    output_tokens=(self.output_tokens or 0) + (other.output_tokens or 0),
                    total_tokens=(self.total_tokens or 0) + (other.total_tokens or 0),
                    cached_tokens=(self.cached_tokens or 0) + (other.cached_tokens or 0),
                    cost_usd=round(self.cost_usd + other.cost_usd, 8),
                    cost_cny=round(self.cost_cny + other.cost_cny, 6),
                    provider=self.provider or other.provider,
                    model=self.model or other.model,
                    request_id=self.request_id or other.request_id,
                )
            return LLMUsage.unavailable(
                provider=self.provider or other.provider,
                model=self.model or other.model,
                request_id=self.request_id or other.request_id,
            )
        if self.usage_status is UsageStatus.CACHED:
            return other.model_copy(deep=True)
        if other.usage_status is UsageStatus.CACHED:
            return self.model_copy(deep=True)
        status = (
            UsageStatus.ESTIMATED
            if UsageStatus.ESTIMATED in (self.usage_status, other.usage_status)
            else UsageStatus.REPORTED
        )
        return LLMUsage(
            usage_status=status,
            input_tokens=(self.input_tokens or 0) + (other.input_tokens or 0),
            output_tokens=(self.output_tokens or 0) + (other.output_tokens or 0),
            total_tokens=(self.total_tokens or 0) + (other.total_tokens or 0),
            cached_tokens=(self.cached_tokens or 0) + (other.cached_tokens or 0),
            estimated_cost_usd=round(self.cost_usd + other.cost_usd, 8),
            estimated_cost_cny=round(self.cost_cny + other.cost_cny, 6),
            provider=self.provider or other.provider,
            model=self.model or other.model,
            request_id=self.request_id or other.request_id,
            cached_tokens_reported=(self.cached_tokens_reported and other.cached_tokens_reported),
            estimated_input_tokens=(
                (self.estimated_input_tokens or 0) + (other.estimated_input_tokens or 0)
                if status is UsageStatus.ESTIMATED
                else None
            ),
        )
