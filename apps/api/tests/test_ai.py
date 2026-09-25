"""Tests for the AI endpoints.

Verified by making real requests rather than by inspecting the route table: FastAPI
0.141 no longer flattens ``include_router`` into ``app.routes`` (a nested
``_IncludedRouter`` entry stands in for the whole router), so an introspection-based
check reports zero routes for endpoints that work perfectly. Behaviour is the only
honest source of truth here.

The assertions concentrate on the properties the product promises: the job description is parsed
into normalised skills, the score's five dimensions are measured rather than derived, and the
degradation of a run is stated in the response rather than hidden.

**Claim validation is no longer here.** ``POST /ai/validate/claim`` was removed in PHASE 14 and
its behaviour lives in ``test_resume.py``, which drives the canonical ``POST /evidence/validate``
against a real evidence base. What remains below is the pin on the removal itself.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
import pytest
from sqlalchemy import func, select

from careerforge_api.models.observability import AgentRun

JD_TEXT = """某科技
嵌入式软件工程师
工作地点：深圳

岗位职责：
1. 负责嵌入式软件的设计、开发与调试；

任职要求：
1. 本科及以上学历，3 年嵌入式开发经验；
2. 熟悉 STM32、FreeRTOS，掌握 C 语言；
3. 熟悉 CAN、SPI 通信协议。

加分项：了解 AUTOSAR。
"""

MATERIAL = (
    "使用 STM32 与 FreeRTOS 开发电机控制固件。"
    "项目基于 FreeRTOS 实现多任务实时控制，任务按优先级划分并周期调度。"
)


def _analyze_payload() -> dict[str, Any]:
    return {"text": JD_TEXT}


class TestCapabilities:
    async def test_lists_every_agent(self, client: AsyncClient, demo, envelope) -> None:
        response = await client.get("/api/v1/ai/capabilities", headers=demo.headers)
        assert response.status_code == 200, response.text
        data = envelope(response)["data"]
        names = {agent["agent"] for agent in data["agents"]}
        assert {
            "profile",
            "job",
            "match",
            "validator",
            "resume",
            "interview",
            "coach",
            "recruiter",
        } <= names

    async def test_reports_its_own_limitations(self, client: AsyncClient, demo, envelope) -> None:
        response = await client.get("/api/v1/ai/capabilities", headers=demo.headers)
        data = envelope(response)["data"]
        # A capabilities endpoint that only lists capabilities invites a caller to
        # assume the missing half works.
        assert data["limitations"]
        assert data["retrieval_available"] is False
        assert data["session_store"] == "in-process"

    async def test_requires_authentication(self, client: AsyncClient, envelope) -> None:
        response = await client.get("/api/v1/ai/capabilities")
        assert response.status_code == 401
        envelope(response, success=False)


class TestAnalyzeJob:
    async def test_parses_a_job_description(self, client: AsyncClient, demo, envelope) -> None:
        response = await client.post(
            "/api/v1/ai/analyze/jd", json=_analyze_payload(), headers=demo.headers
        )
        assert response.status_code == 200, response.text
        data = envelope(response)["data"]
        analysis = data["analysis"]
        assert analysis["role"]
        assert analysis["location"] == "深圳"
        assert analysis["years_experience_min"] == 3.0
        canonical = {skill["canonical_id"] for skill in analysis["required_skills"]}
        assert {"stm32", "free_rtos", "c"} <= canonical

    async def test_company_blurb_is_not_a_requirement(
        self, client: AsyncClient, demo, envelope
    ) -> None:
        text = JD_TEXT.replace(
            "岗位职责：", "公司简介\n我们使用 Kubernetes 与 React 构建内部平台。\n\n岗位职责："
        )
        response = await client.post(
            "/api/v1/ai/analyze/jd", json={"text": text}, headers=demo.headers
        )
        data = envelope(response)["data"]
        required = {skill["canonical_id"] for skill in data["analysis"]["required_skills"]}
        assert "kubernetes" not in required

    async def test_reports_the_provider_and_degradation(
        self, client: AsyncClient, demo, envelope
    ) -> None:
        response = await client.post(
            "/api/v1/ai/analyze/jd", json=_analyze_payload(), headers=demo.headers
        )
        meta = envelope(response)["data"]["meta"]
        assert meta["provider"] == "heuristic"
        # No API key is configured in tests, and the response must say so.
        assert meta["degraded"] is True
        assert meta["degraded_reason"] == "no_api_key"
        assert meta["prompt_version"] == "jd_analysis@v1"

    async def test_rejects_a_too_short_payload(self, client: AsyncClient, demo, envelope) -> None:
        response = await client.post(
            "/api/v1/ai/analyze/jd", json={"text": "hi"}, headers=demo.headers
        )
        assert response.status_code == 400
        payload = envelope(response, success=False)
        assert payload["error"]["code"] == "VALIDATION_ERROR"

    async def test_requires_authentication(self, client: AsyncClient, envelope) -> None:
        response = await client.post("/api/v1/ai/analyze/jd", json=_analyze_payload())
        assert response.status_code == 401


class TestValidateClaimRemoved:
    """``POST /ai/validate/claim`` is gone, and its absence is the point (PHASE 14).

    The endpoint ran the real gate with ``app.state.retriever`` — a property nothing in this
    repository ever sets — and with no material, so it retrieved nothing, cited nothing, and
    answered ``unsupported`` with ``confidence: 0.0`` even for a sentence the candidate's own
    evidence supports. ``supported`` was structurally unreachable through it. Measured live in
    PHASE 13: "使用 STM32 与 FreeRTOS 开发电机控制固件" over a populated evidence base came back
    ``unsupported`` with zero sources.

    It is not repaired, it is **removed**: the canonical gate is ``POST /evidence/validate``
    (``routers/resume.py``), which the Validator page, the E2E specs and ``docs/API.md`` all use,
    and which builds a real hybrid retriever per request. Keeping a second entry point would mean
    a second copy of the gating logic or a second, permanently wrong answer to the same question.
    """

    async def test_the_endpoint_is_not_mounted(self, client: AsyncClient, demo) -> None:
        response = await client.post(
            "/api/v1/ai/validate/claim", json={"claim": "使用 Docker 部署"}, headers=demo.headers
        )
        assert response.status_code == 404, (
            "the stateless claim endpoint is back; if it is deliberate, it must delegate to "
            "ResumeService.validate rather than run the gate itself"
        )

    async def test_the_canonical_endpoint_is_the_one_that_answers(
        self, client: AsyncClient, demo, envelope
    ) -> None:
        """The claim shapes the removed endpoint used to take are refused, not half-honoured."""
        response = await client.post(
            "/api/v1/evidence/validate",
            json={
                "claim": "使用 STM32 与 FreeRTOS 开发电机控制固件",
                "evidence_text": MATERIAL,
            },
            headers=demo.headers,
        )
        # ``extra="forbid"``: the canonical body is ``{text, section, jobId}``, and a client
        # sending the old body must be told rather than have its material silently dropped.
        assert response.status_code == 400, response.text
        assert envelope(response, success=False)["error"]["code"] == "VALIDATION_ERROR"


class TestMatch:
    @staticmethod
    def _payload() -> dict[str, Any]:
        return {
            "job": {
                "company": "某科技",
                "role": "嵌入式软件工程师",
                "education_requirement": "本科",
                "years_experience_min": 1.0,
                "required_skills": [
                    {
                        "canonical_id": "stm32",
                        "raw_text": "STM32",
                        "requirement": "required",
                        "jd_evidence": "熟悉 STM32",
                    },
                    {
                        "canonical_id": "can",
                        "raw_text": "CAN",
                        "requirement": "required",
                        "jd_evidence": "熟悉 CAN",
                    },
                ],
            },
            "profile": {
                "slug": "alex",
                "headline": "Embedded Engineer",
                "years_experience": 1.0,
                "educations": [{"school": "某某大学", "degree": "Bachelor of Engineering"}],
                "experiences": [
                    {
                        "company": "某科技",
                        "title": "嵌入式实习生",
                        "description": "使用 STM32 开发电机控制固件",
                    }
                ],
                "projects": [
                    {
                        "name": "Balance Robot",
                        "summary": "基于 STM32 的两轮自平衡小车",
                        "tech_stack": ["STM32", "FreeRTOS"],
                    }
                ],
                "skills": [
                    {
                        "skill": {
                            "canonical_id": "stm32",
                            "display_name": "STM32",
                            "category": "embedded",
                        },
                        "level": "strong",
                        "evidence_count": 3,
                    }
                ],
            },
        }

    async def test_scores_with_a_full_derivation(self, client: AsyncClient, demo, envelope) -> None:
        response = await client.post("/api/v1/ai/match", json=self._payload(), headers=demo.headers)
        assert response.status_code == 200, response.text
        data = envelope(response)["data"]
        assert 0.0 <= data["score"] <= 100.0
        assert set(data["dimensions"]) == {
            "skill",
            "experience",
            "project",
            "education",
            "evidence",
        }
        assert data["why"]["formula"]
        assert data["why"]["explanation"]

    async def test_dimensions_sum_to_the_total(self, client: AsyncClient, demo, envelope) -> None:
        response = await client.post("/api/v1/ai/match", json=self._payload(), headers=demo.headers)
        data = envelope(response)["data"]
        weighted = sum(dimension["weighted"] for dimension in data["dimensions"].values())
        assert weighted == pytest.approx(data["score"], abs=0.05)

    async def test_separates_gaps_from_unknowns(self, client: AsyncClient, demo, envelope) -> None:
        response = await client.post("/api/v1/ai/match", json=self._payload(), headers=demo.headers)
        data = envelope(response)["data"]
        gap_ids = {gap["canonical_id"] for gap in data["gaps"]}
        unknown_ids = {unknown["canonical_id"] for unknown in data["unknowns"]}
        assert gap_ids.isdisjoint(unknown_ids)


class TestInterview:
    @staticmethod
    def _start_payload() -> dict[str, Any]:
        return {
            "mode": "technical",
            "job": {
                "role": "嵌入式软件工程师",
                "required_skills": [
                    {
                        "canonical_id": "free_rtos",
                        "raw_text": "FreeRTOS",
                        "requirement": "required",
                        "jd_evidence": "熟悉 FreeRTOS",
                    }
                ],
            },
            "profile": {
                "slug": "alex",
                "headline": "Embedded Engineer",
                "projects": [
                    {
                        "name": "Balance Robot",
                        "summary": "基于 STM32 的两轮自平衡小车",
                        "tech_stack": ["STM32", "FreeRTOS"],
                    }
                ],
            },
            "difficulty": 1,
        }

    async def test_start_returns_a_plan_and_a_question(
        self, client: AsyncClient, demo, envelope
    ) -> None:
        response = await client.post(
            "/api/v1/ai/interview/start", json=self._start_payload(), headers=demo.headers
        )
        assert response.status_code == 200, response.text
        data = envelope(response)["data"]
        assert data["status"] == "in_progress"
        assert data["plan"]
        assert data["turns"]
        assert data["turns"][0]["role"] == "interviewer"
        assert data["turns"][0]["content"]

    async def test_answer_evaluates_adapts_and_asks_again(
        self, client: AsyncClient, demo, envelope
    ) -> None:
        started = await client.post(
            "/api/v1/ai/interview/start", json=self._start_payload(), headers=demo.headers
        )
        session_id = envelope(started)["data"]["session_id"]

        response = await client.post(
            f"/api/v1/ai/interview/{session_id}/answer",
            json={
                "answer": (
                    "我们使用 FreeRTOS 的队列在中断与任务之间传递数据，"
                    "因为直接操作全局变量会带来竞态；任务按优先级划分，共享资源用互斥量保护。"
                )
            },
            headers=demo.headers,
        )
        assert response.status_code == 200, response.text
        data = envelope(response)["data"]
        assert data["evaluation"]["score"] >= 0.0
        assert data["difficulty_change"]["reason"]
        assert data["next_question"]["content"]

    async def test_finish_produces_a_seven_dimension_scorecard(
        self, client: AsyncClient, demo, envelope
    ) -> None:
        started = await client.post(
            "/api/v1/ai/interview/start", json=self._start_payload(), headers=demo.headers
        )
        session_id = envelope(started)["data"]["session_id"]
        for _ in range(3):
            await client.post(
                f"/api/v1/ai/interview/{session_id}/answer",
                json={"answer": "我用 FreeRTOS 做了任务划分，并用队列在中断与任务之间传递数据。"},
                headers=demo.headers,
            )

        response = await client.post(
            f"/api/v1/ai/interview/{session_id}/finish", headers=demo.headers
        )
        assert response.status_code == 200, response.text
        data = envelope(response)["data"]
        assert data["status"] == "completed"
        scorecard = data["scorecard"]
        assert scorecard is not None
        keys = {dimension["key"] for dimension in scorecard["dimensions"]}
        assert keys == {
            "technical_accuracy",
            "communication",
            "depth",
            "problem_solving",
            "engineering_thinking",
            "confidence",
            "evidence_consistency",
        }

    async def test_session_can_be_resumed(self, client: AsyncClient, demo, envelope) -> None:
        started = await client.post(
            "/api/v1/ai/interview/start", json=self._start_payload(), headers=demo.headers
        )
        session_id = envelope(started)["data"]["session_id"]
        response = await client.get(f"/api/v1/ai/interview/{session_id}", headers=demo.headers)
        assert response.status_code == 200
        assert envelope(response)["data"]["session_id"] == session_id

    async def test_unknown_session_is_404(self, client: AsyncClient, demo, envelope) -> None:
        response = await client.get(
            "/api/v1/ai/interview/00000000-0000-0000-0000-000000000000", headers=demo.headers
        )
        assert response.status_code == 404
        envelope(response, success=False)

    async def test_another_users_session_is_404(
        self, client: AsyncClient, demo, make_user, envelope
    ) -> None:
        started = await client.post(
            "/api/v1/ai/interview/start", json=self._start_payload(), headers=demo.headers
        )
        session_id = envelope(started)["data"]["session_id"]

        other = await make_user()
        response = await client.get(f"/api/v1/ai/interview/{session_id}", headers=other.headers)
        # 404 rather than 403: the API must not confirm that the session exists.
        assert response.status_code == 404

    async def test_abandon_returns_204(self, client: AsyncClient, demo, envelope) -> None:
        started = await client.post(
            "/api/v1/ai/interview/start", json=self._start_payload(), headers=demo.headers
        )
        session_id = envelope(started)["data"]["session_id"]
        response = await client.delete(f"/api/v1/ai/interview/{session_id}", headers=demo.headers)
        assert response.status_code == 204
        assert (
            await client.get(f"/api/v1/ai/interview/{session_id}", headers=demo.headers) is not None
        )


class TestRunObservability:
    async def test_an_ai_call_writes_an_agent_run(
        self, client: AsyncClient, app, demo, envelope
    ) -> None:
        before = await self._run_count(app)
        response = await client.post(
            "/api/v1/ai/analyze/jd", json=_analyze_payload(), headers=demo.headers
        )
        assert response.status_code == 200
        after = await self._run_count(app)
        assert after > before, "an AI endpoint must leave a trace"

    async def test_the_run_records_its_workflow_and_steps(
        self, client: AsyncClient, app, demo, envelope
    ) -> None:
        await client.post("/api/v1/ai/analyze/jd", json=_analyze_payload(), headers=demo.headers)
        async with app.state.session_factory() as session:
            row = (
                await session.execute(
                    select(AgentRun)
                    .where(AgentRun.workflow == "jd_analysis")
                    .order_by(AgentRun.created_at.desc())
                    .limit(1)
                )
            ).scalar_one()
        assert row.status in {"succeeded", "degraded"}
        assert row.steps, "the trace must record the steps that ran"
        step_names = [step["name"] for step in row.steps]
        assert step_names == ["clean", "extract", "normalise", "assess"]

    @staticmethod
    async def _run_count(app) -> int:
        async with app.state.session_factory() as session:
            return int(
                (await session.execute(select(func.count()).select_from(AgentRun))).scalar_one()
            )
