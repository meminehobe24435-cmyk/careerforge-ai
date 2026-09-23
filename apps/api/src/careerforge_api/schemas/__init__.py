"""Pydantic models of the HTTP contract.

One file per concern, mirroring ``docs/API.md`` section by section. The wire format
of every response is the envelope from :mod:`careerforge_api.schemas.envelope`,
applied by middleware; the models here describe the ``data`` payload inside it.
"""

from __future__ import annotations

from careerforge_api.schemas.auth import (
    AuthResponse,
    AuthTokens,
    LoginRequest,
    LogoutRequest,
    LogoutResponse,
    RefreshRequest,
    RegisterRequest,
    UserPublic,
)
from careerforge_api.schemas.envelope import (
    ApiEnvelope,
    ApiErrorDetail,
    ApiErrorPayload,
    ApiMeta,
)
from careerforge_api.schemas.pagination import CursorPage, PageParams
from careerforge_api.schemas.system import (
    HealthStatus,
    ServiceHealthEntry,
    SystemHealthResponse,
    SystemInfoResponse,
)
from careerforge_api.schemas.task import (
    TaskAccepted,
    TaskCancelResponse,
    TaskResponse,
    TaskStatusValue,
)

__all__ = [
    "ApiEnvelope",
    "ApiErrorDetail",
    "ApiErrorPayload",
    "ApiMeta",
    "AuthResponse",
    "AuthTokens",
    "CursorPage",
    "HealthStatus",
    "LoginRequest",
    "LogoutRequest",
    "LogoutResponse",
    "PageParams",
    "RefreshRequest",
    "RegisterRequest",
    "ServiceHealthEntry",
    "SystemHealthResponse",
    "SystemInfoResponse",
    "TaskAccepted",
    "TaskCancelResponse",
    "TaskResponse",
    "TaskStatusValue",
    "UserPublic",
    "AiMeta",
    "AnalyzeJobRequest",
    "AnalyzeJobResponse",
    "CapabilitiesResponse",
    "InterviewAnswerRequest",
    "InterviewQuestion",
    "InterviewSessionResponse",
    "InterviewTurnResponse",
    "MatchRequest",
    "MatchResponse",
    "StartInterviewRequest",
    "ValidateClaimRequest",
    "ValidateClaimResponse",
]

from careerforge_api.schemas.ai import (
    AiMeta,
    AnalyzeJobRequest,
    AnalyzeJobResponse,
    CapabilitiesResponse,
    InterviewAnswerRequest,
    InterviewSessionResponse,
    InterviewTurnResponse,
    MatchRequest,
    MatchResponse,
    StartInterviewRequest,
    ValidateClaimRequest,
    ValidateClaimResponse,
)
