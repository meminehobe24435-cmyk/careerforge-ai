"""The canonical claim gate: one endpoint, and the verdicts it must produce.

**Why this file exists** (PHASE 14). Two endpoints used to validate a claim. ``POST
/evidence/validate`` (``routers/resume.py``) builds a hybrid retriever over the caller's stored
evidence, supplies the rules phase with the candidate's material and stores the claim.
``POST /ai/validate/claim`` (``routers/ai.py``) read a retriever off ``app.state.retriever``,
which **nothing in this repository ever sets**, and took its material from the request body — so
it retrieved nothing, cited nothing, and answered ``unsupported`` with ``confidence: 0.0`` even
for a sentence the candidate's own evidence supports. ``supported`` was structurally unreachable
through it. Measured live in PHASE 13: "使用 STM32 与 FreeRTOS 开发电机控制固件" over a populated
evidence base came back ``unsupported`` with zero sources.

It was removed rather than repaired, and the behaviour it was written to demonstrate moved here.
Every test below drives the canonical endpoint against a **real evidence base** — a résumé
uploaded, parsed and analysed — because a claim about traceability cannot be tested against a
fixture that already knows the answer.

``test_ai.py::TestValidateClaimRemoved`` pins the removal itself.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.claim_support import (
    BROKEN_RETRIEVER_WARNING,
    BrokenRetriever,
    evidence_ready as _evidence_ready,
)
from tests.conftest import EnvelopeCheck, UserFactory


async def test_a_supported_claim_cites_what_supports_it(
    client: AsyncClient, envelope: EnvelopeCheck, make_user: UserFactory
) -> None:
    """The measurement PHASE 13 could not obtain through the stateless endpoint.

    Over a populated evidence base, a sentence the candidate's own material states almost
    verbatim must be able to reach ``supported`` — and either way it must name its sources.
    The count and confidence are whatever the gate measured; what is asserted is that the
    verdict is *not* the old answer (``unsupported`` with ``sources: []`` and no confidence).
    """
    account = await make_user(display_name="Claim gate fixture")
    await _evidence_ready(client, envelope, account)

    response = await client.post(
        "/api/v1/evidence/validate",
        json={"text": "使用 STM32 与 FreeRTOS 开发电机控制固件"},
        headers=account.headers,
    )
    assert response.status_code == 200, response.text
    payload = envelope(response)["data"]
    claim = payload["claim"]

    assert claim["status"] in {"supported", "partially_supported"}, claim
    assert claim["sources"], "a verdict about the candidate's own evidence must cite it"
    assert claim["confidence"] > 0.0, claim
    for source in claim["sources"]:
        assert source["evidenceId"]
        assert source["title"] or source["snippet"]
    assert payload["claimId"], "the verdict is stored so it can be answered for later"


async def test_a_fabricated_metric_never_survives_a_safer_rewrite(
    client: AsyncClient, envelope: EnvelopeCheck, make_user: UserFactory
) -> None:
    """Moved here from ``test_ai.py`` when ``/ai/validate/claim`` was removed.

    The rule the docs give (§2.5): a rule-layer blocker *may* carry a ``safeRewrite`` — deleting a
    number is the correct repair for a number with nothing behind it — but if removing it still
    leaves a technology the evidence cannot support, **no rewrite is offered**. Keeping the name
    and dropping the number would assert the same unprovable thing while looking edited.
    """
    account = await make_user(display_name="Claim gate fixture")
    await _evidence_ready(client, envelope, account)

    # "87%" has nothing comparable anywhere; the rest of the sentence is supported, so the
    # honest repair is the sentence without the number.
    repairable = await client.post(
        "/api/v1/evidence/validate",
        json={"text": "使用 STM32 与 FreeRTOS 开发电机控制固件，将吞吐提升了 87%。"},
        headers=account.headers,
    )
    assert repairable.status_code == 200, repairable.text
    claim = envelope(repairable)["data"]["claim"]
    assert claim["hasQuantifiedClaim"] is True
    assert claim["status"] != "supported", claim
    assert claim["status"] != "contradicted", (
        "nothing in the evidence contradicts the 87%; it simply has no comparable measurement, "
        "and calling that a contradiction would tell the candidate their own evidence disagrees"
    )
    assert any("87%" in reason["message"] for reason in claim["reasons"]), claim["reasons"]
    rewrite = claim["safeRewrite"]
    assert rewrite is not None, "a number with no evidence behind it can always be removed"
    assert "87%" not in rewrite["text"]

    # Unsupported technology plus a fabricated number: removing the number changes nothing, so
    # there is no honest rewrite and the gate must refuse to offer one.
    unrepairable = await client.post(
        "/api/v1/evidence/validate",
        json={"text": "使用 Kubernetes 与 TensorFlow 将吞吐提升了 87%。"},
        headers=account.headers,
    )
    refused = envelope(unrepairable)["data"]["claim"]
    assert refused["safeRewrite"] is None, refused["safeRewrite"]
    assert refused["status"] in {"unsupported", "contradicted"}, refused


async def test_one_uncorroborated_source_is_not_support(
    client: AsyncClient, envelope: EnvelopeCheck, make_user: UserFactory
) -> None:
    """Moved here from ``test_ai.py``: a single source is a single source.

    ``scoring/confidence.py`` requires two *independent kinds* before ``supported``; a verdict
    that reached its highest status on one uncorroborated fragment would be a badge rather than a
    citation.
    """
    account = await make_user(display_name="Claim gate fixture")
    await _evidence_ready(client, envelope, account)

    response = await client.post(
        "/api/v1/evidence/validate",
        json={"text": "基于 FreeRTOS 开发多任务实时控制系统。"},
        headers=account.headers,
    )
    assert response.status_code == 200, response.text
    claim = envelope(response)["data"]["claim"]
    assert claim["status"] != "supported", claim
    assert claim["status"] in {"partially_supported", "unsupported"}, claim
    if claim["status"] == "partially_supported":
        assert claim["independentSourceCount"] >= 1
        assert claim["sources"], "a partially supported claim still names a source"


async def test_no_evidence_means_no_support(
    client: AsyncClient, envelope: EnvelopeCheck, make_user: UserFactory
) -> None:
    """Moved here from ``test_ai.py``, and now measured the hard way.

    The account is freshly created and has *no* evidence at all, so the gate has nothing to search
    rather than nothing supplied: the retriever is real and simply empty. The answer must refuse
    the claim and say what it could not establish, because an empty evidence set presented as a
    normal miss is the one outcome worse than a refusal.
    """
    account = await make_user(display_name="No evidence yet")
    listing = envelope(await client.get("/api/v1/evidence", headers=account.headers))["data"]
    assert listing["items"] == []

    response = await client.post(
        "/api/v1/evidence/validate",
        json={"text": "熟练使用 Redis 与 Kafka 构建高并发架构。"},
        headers=account.headers,
    )
    assert response.status_code == 200, response.text
    payload = envelope(response)["data"]
    assert payload["claimId"], "even a refused claim is stored, so the refusal is answerable later"
    claim = payload["claim"]
    assert claim["status"] in {"unsupported", "contradicted"}, claim
    assert claim["sources"] == [], "there is no evidence in this account to cite"
    assert claim["reasons"], claim
    assert claim["unknowns"], claim


async def test_a_failed_retriever_degrades_the_verdict_and_says_so(
    client: AsyncClient, envelope: EnvelopeCheck, make_user: UserFactory, monkeypatch
) -> None:
    """``warnings``/``degraded`` are on the response, not only in the run trace.

    The gate appends "证据检索降级：…" when retrieval fails, and ``ResumeService.validate`` used to
    unpack the workflow outcome into a throwaway variable and drop it — so a verdict judged
    without retrieval reached the caller looking exactly like a normal one. The retriever is
    replaced at the seam the endpoint uses (``services/retrieval_service.build_retriever``) with
    one that raises, which is how a dead vector store behaves: the answer must still be produced,
    and it must say that evidence could not be searched.
    """
    account = await make_user(display_name="Claim gate fixture")
    await _evidence_ready(client, envelope, account)

    from careerforge_api.services import resume_service

    broken = BrokenRetriever()

    async def exploding_retriever(*args: object, **kwargs: object) -> BrokenRetriever:
        return broken

    monkeypatch.setattr(resume_service, "build_retriever", exploding_retriever)

    response = await client.post(
        "/api/v1/evidence/validate",
        json={"text": "使用 STM32 与 FreeRTOS 开发电机控制固件。"},
        headers=account.headers,
    )
    assert response.status_code == 200, response.text
    payload = envelope(response)["data"]
    assert broken.calls > 0, "the injected retriever was never asked; the test proves nothing"
    warnings = " ".join(payload["warnings"])
    assert BROKEN_RETRIEVER_WARNING in warnings, payload["warnings"]
    assert payload["degraded"] is True, payload
    assert payload["claim"]["status"] != "supported", (
        "a verdict judged without retrieval cannot claim the highest status"
    )
    assert payload["claim"]["reasons"], "a verdict without reasons is indistinguishable from a bug"
