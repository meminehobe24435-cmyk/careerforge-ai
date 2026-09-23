"""The response envelope and the shared AI metadata block.

``docs/API.md`` §1.1 and §1.8, mirrored field-for-field from the frozen client types
in ``packages/shared/src/api/types.ts``. The wire format is produced by
:mod:`careerforge_api.middleware.envelope`; these models exist so the contract can
be validated — in the OpenAPI document and in the test suite — rather than assumed.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ApiEnvelope", "ApiErrorDetail", "ApiErrorPayload", "ApiMeta"]

DataT = TypeVar("DataT")


class ApiErrorDetail(BaseModel):
    """One entry of ``error.details`` (``docs/API.md`` §1.1)."""

    model_config = ConfigDict(populate_by_name=True)

    field: str
    issue: str
    #: Human-readable pydantic message; the frozen client type only needs field/issue.
    message: str | None = None


class ApiErrorPayload(BaseModel):
    """The ``error`` object of a failed envelope."""

    model_config = ConfigDict(populate_by_name=True)

    code: str
    message: str
    details: list[ApiErrorDetail] = Field(default_factory=list)


class ApiMeta(BaseModel):
    """Degradation/observability block carried by AI responses (``docs/API.md`` §1.8).

    ``degraded`` must never be hidden: it is what lets the UI show the
    "answered by a fallback provider" badge instead of pretending nothing happened.
    """

    model_config = ConfigDict(populate_by_name=True)

    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = Field(default=None, alias="promptVersion")
    degraded: bool | None = None
    cache_hit: bool | None = Field(default=None, alias="cacheHit")
    confidence: float | None = None
    took_ms: int | None = Field(default=None, alias="tookMs")


class ApiEnvelope(BaseModel, Generic[DataT]):
    """``{ success, data, error, requestId }`` — the only response shape the API has."""

    model_config = ConfigDict(populate_by_name=True)

    success: bool
    data: DataT | None = None
    error: ApiErrorPayload | None = None
    request_id: str = Field(alias="requestId")

    @classmethod
    def ok(cls, data: DataT, *, request_id: str) -> ApiEnvelope[DataT]:
        return cls(success=True, data=data, error=None, requestId=request_id)

    @classmethod
    def failed(
        cls, error: ApiErrorPayload | dict[str, Any], *, request_id: str
    ) -> ApiEnvelope[Any]:
        payload = (
            error if isinstance(error, ApiErrorPayload) else ApiErrorPayload.model_validate(error)
        )
        return cls(success=False, data=None, error=payload, requestId=request_id)
