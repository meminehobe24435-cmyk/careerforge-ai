"""Evidence the candidate typed themselves — the ``manual`` kind, created idempotently.

Split out of ``evidence_service.py`` in PHASE 14 (the file-length guard, and a real seam: the
service there turns *stored material* into a graph, while this module owns the one write path that
starts from a request body).

**Idempotent on purpose.** ``evidence`` carries ``UNIQUE (user_id, kind, content_hash)``, and the
insert here used to ignore it: a second identical ``POST /evidence`` raised ``IntegrityError`` and
the client got a ``500 INTERNAL_ERROR`` for a request that had already succeeded once. An ingestion
pipeline is *expected* to replay, so the honest answer to "store this" is the row that already holds
it — ``(row, created=False)`` — not a server error. Both clients that add manual evidence had worked
around this by reading first and writing only when nothing matched
(``apps/web/e2e/helpers/pages.ts``, ``apps/web/scripts/capture-pages.mts``, which also reported it
as a backend bug); this is the fix they were waiting for.

**Confidence is computed, never accepted.** A manual entry is the weakest tier that still counts
(``AUTHORITY_SCORES[RESUME_SELF_REPORT]``), and letting a client choose its own score would make the
number meaningless exactly where the product claims it is not.
"""

from __future__ import annotations

import hashlib

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_ai.schemas.common import EvidenceKind
from careerforge_ai.schemas.evidence import EvidenceLocator
from careerforge_ai.scoring.confidence import compute_confidence
from careerforge_api.models.evidence import Evidence
from careerforge_api.models.user import User
from careerforge_api.repositories.evidence_repository import EvidenceRepository

__all__ = ["content_hash_of_manual", "get_or_create_manual"]


def content_hash_of_manual(title: str, snippet: str, locator: EvidenceLocator) -> str:
    """The de-duplication key for a hand-entered row — the third column of the constraint.

    A pure function so the key that decides "same evidence" is testable on its own, and so the
    lookup before the insert cannot drift from the value the row is written with.
    """
    payload = f"{title}:{snippet}:{locator.model_dump_json()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def get_or_create_manual(
    session: AsyncSession,
    *,
    user: User,
    title: str,
    snippet: str = "",
    locator: EvidenceLocator | None = None,
    occurred_at: object = None,
) -> tuple[Evidence, bool]:
    """Store a hand-entered evidence row, or return the one it duplicates.

    Returns ``(row, created)``. The insert runs inside a **savepoint** so that losing a race to a
    concurrent request fails only the savepoint: the outer transaction — and any other work in this
    request — survives, and the loser simply reads the winner's row.
    """
    resolved_locator = locator or EvidenceLocator()
    content_hash = content_hash_of_manual(title, snippet, resolved_locator)
    repository = EvidenceRepository(session)

    existing = await repository.by_content_hash(
        user_id=user.id, kind=EvidenceKind.MANUAL.value, content_hash=content_hash
    )
    if existing is not None:
        return existing, False

    breakdown = compute_confidence(
        kind=EvidenceKind.MANUAL,
        occurred_at=occurred_at,  # type: ignore[arg-type]
        locator=resolved_locator,
        independent_sources=1,
        extraction_method="user_corrected",
    )
    row = Evidence(
        user_id=user.id,
        kind=EvidenceKind.MANUAL.value,
        title=title[:300],
        snippet=snippet[:2000],
        locator=resolved_locator.model_dump(exclude_none=True),
        source_authority=float(breakdown.inputs.source_authority),
        specificity=float(breakdown.inputs.specificity),
        extraction_quality=float(breakdown.inputs.extraction_quality),
        recency_score=float(breakdown.inputs.recency),
        corroboration_count=1,
        confidence=float(breakdown.score),
        occurred_at=occurred_at,
        content_hash=content_hash,
        metadata_={"source": "manual"},
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError:
        # Somebody else inserted the same content between the read and the write. The savepoint
        # is already rolled back, so this session is still usable and the winner's row is readable.
        raced = await repository.by_content_hash(
            user_id=user.id, kind=EvidenceKind.MANUAL.value, content_hash=content_hash
        )
        if raced is None:  # pragma: no cover - the constraint that fired is this one
            raise
        return raced, False
    return row, True
