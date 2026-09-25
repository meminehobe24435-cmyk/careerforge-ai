"""The evidence base the claim gate is driven against, shared by its two suites.

Split out in PHASE 14 for the same reason ``failure_helpers.py`` was: two suites need the same
fixtures — ``test_resume.py`` (the résumé Copilot, whose bullets pass the same gate) and
``test_claim_gate.py`` (the gate itself) — and a copied ``_evidence_ready`` would drift into two
meanings of "the account has evidence".

Not named ``test_*`` so pytest does not collect it, the convention every support module here uses.

**Why the setup is this long.** ``POST /profile/import`` creates profile rows and no ``evidence``
rows, so a claim comes back unsupported until a document is uploaded, its task polled and
``POST /documents/{id}/analyze`` run. Two independent evidence *kinds* are required before the
gate will say ``supported`` at all (``scoring/confidence.py`` → ``_MIN_INDEPENDENT_SOURCES``), and
a résumé upload produces only ``document_chunk`` — which is why the specs that need the highest
verdict also store a manual row.
"""

from __future__ import annotations

import asyncio
import itertools
from typing import Any

from httpx import AsyncClient

from careerforge_ai.errors import RetrievalError
from tests.conftest import EnvelopeCheck, Session

__all__ = [
    "BROKEN_RETRIEVER_WARNING",
    "JD_TEXT",
    "RESUME",
    "UNSUPPORTED_CLAIM",
    "BrokenRetriever",
    "evidence_ready",
    "resume_bytes",
]

RESUME = """教育经历
某某大学 电子信息工程 本科 2019-2023

实习经历
某某科技 嵌入式软件实习生 2023.07-2023.12
使用 STM32 与 FreeRTOS 开发电机控制固件，负责 CAN 总线节点通信调试。

项目经历
Balance Robot 基于 STM32 与 FreeRTOS 的两轮自平衡小车。

专业技能
C/C++、Python、STM32、FreeRTOS、CAN
"""

JD_TEXT = """某某科技有限公司
岗位：嵌入式软件工程师

任职要求：
1. 熟悉 STM32 平台开发；
2. 熟悉 FreeRTOS 实时操作系统。
"""

#: A sentence the evidence cannot support: it names technologies nothing the candidate supplied
#: mentions, and it carries numbers with nothing to compare them against.
UNSUPPORTED_CLAIM = "使用 Kubernetes 将部署效率提升了 300%，并主导了 TensorFlow 模型上线。"

#: What the gate writes into ``warnings`` when retrieval could not run. Asserted by both suites,
#: so it is defined once: a reworded warning must not silently stop being checked.
BROKEN_RETRIEVER_WARNING = "检索"

_counter = itertools.count()


def resume_bytes() -> bytes:
    """The résumé payload, altered per call so two uploads are two documents."""
    return f"{RESUME}\n<!-- fixture {next(_counter)} -->\n".encode()


async def evidence_ready(client: AsyncClient, envelope: EnvelopeCheck, session: Session) -> None:
    """Upload, parse and analyse a résumé — everything the gate can cite."""
    body = await client.post(
        "/api/v1/documents",
        files={"file": ("resume.txt", resume_bytes(), "text/plain")},
        data={"kind": "resume"},
        headers=session.headers,
    )
    assert body.status_code == 202, body.text
    accepted = envelope(body)["data"]
    task: dict[str, Any] = {}
    for _ in range(200):
        task = envelope(
            await client.get(f"/api/v1/tasks/{accepted['taskId']}", headers=session.headers)
        )["data"]
        if task["status"] in {"succeeded", "failed"}:
            break
        await asyncio.sleep(0.02)
    assert task["status"] == "succeeded", task

    analyzed = await client.post(
        f"/api/v1/documents/{accepted['documentId']}/analyze", headers=session.headers
    )
    assert analyzed.status_code == 200, analyzed.text


class BrokenRetriever:
    """A retrieval backend that is reachable but broken, as a dead vector store would be.

    Injected in place of ``services/retrieval_service.build_retriever``: the canonical gate builds
    its retriever per request, so the failure is injected at the seam the endpoint actually uses
    rather than by reaching into the gate.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def retrieve(self, query: str, **kwargs: Any) -> Any:
        self.calls += 1
        raise RetrievalError("vector backend is unreachable")
