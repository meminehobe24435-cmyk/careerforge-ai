"""Interview scenarios for the relevance suite.

Three roles, chosen because they fail in different ways. The embedded scenario is the one the
product was built around and the topic map covers; the backend and AI-application scenarios are
deliberately *outside* that map, which is how the suite detects a question planner that has
quietly become role-blind (see the suite docstring and ``docs/QUALITY.md`` for what the first run
of this dataset showed).

Every scenario declares three things the suite needs:

* ``jd_skills`` — the requirement set, split into required/preferred, with canonical ids from the
  real taxonomy so the planner's skill→topic mapping is exercised exactly as in production.
* ``profile_skills`` — the candidate, with ``evidenced: true/false`` determining whether the
  evidence graph will carry that skill. The mix matters: a scenario where everything is evidenced
  never tests the gap-probing path, and one where nothing is evidenced never tests the
  evidence-backed path.
* ``forbidden_topics`` — subjects that would be off-topic for the role, written as the words that
  would appear in a question if the planner drifted. These are the strings the leakage metric
  searches for, so they are chosen to be unambiguous ("react", "adc", "css") rather than vague.

The scenarios are intentionally *not* generated: the value of this dataset is that a human wrote
down which questions would be reasonable for each role.
"""

from __future__ import annotations

from typing import Any

__all__ = ["FIXTURE_VERSION", "INTERVIEW_SCENARIOS", "build_interview_rows"]

FIXTURE_VERSION = "iv1.0"

#: Difficulty level requested at session start (1 = concept, 2 = engineering, 3 = debugging).
_DEFAULT_DIFFICULTY = 2

INTERVIEW_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "iv-embedded",
        "role": "嵌入式软件工程师",
        "difficulty": _DEFAULT_DIFFICULTY,
        "jd_text": (
            "招聘嵌入式软件工程师：熟悉 STM32 与 FreeRTOS，熟悉 CAN、SPI 通信协议；"
            "有 PID 闭环控制经验者优先。"
        ),
        "jd_skills": [
            {"canonical": "stm32", "raw": "STM32", "requirement": "required"},
            {"canonical": "free_rtos", "raw": "FreeRTOS", "requirement": "required"},
            {"canonical": "can", "raw": "CAN", "requirement": "required"},
            {"canonical": "spi", "raw": "SPI", "requirement": "required"},
            {"canonical": "pid", "raw": "PID 闭环控制", "requirement": "preferred"},
        ],
        "profile_skills": [
            {
                "canonical": "stm32",
                "display": "STM32",
                "category": "domain",
                "evidenced": True,
            },
            {
                "canonical": "free_rtos",
                "display": "FreeRTOS",
                "category": "domain",
                "evidenced": True,
            },
            {
                "canonical": "spi",
                "display": "SPI",
                "category": "domain",
                "evidenced": True,
            },
            # CAN is the deliberate gap: the JD requires it, the candidate has no evidence.
            {"canonical": "can", "display": "CAN", "category": "domain", "evidenced": False},
        ],
        "forbidden_topics": ["react", "vue", "css", "adc", "kubernetes", "sql"],
        "candidate_summary": "电子信息工程本科，做过两轮自平衡机器人与电机控制固件。",
        "project_name": "Balance Robot",
        "project_summary": "基于 STM32 与 FreeRTOS 的两轮自平衡小车，SPI 读取陀螺仪，PID 控制电机。",
        "project_stack": ["STM32", "FreeRTOS", "SPI", "PID", "C"],
    },
    {
        "id": "iv-backend",
        "role": "后端工程师",
        "difficulty": _DEFAULT_DIFFICULTY,
        "jd_text": (
            "招聘后端工程师：熟练 Python 与 FastAPI，熟悉 PostgreSQL 与 Redis；有 Docker 部署经验。"
        ),
        "jd_skills": [
            {"canonical": "python", "raw": "Python", "requirement": "required"},
            {"canonical": "fastapi", "raw": "FastAPI", "requirement": "required"},
            {"canonical": "postgresql", "raw": "PostgreSQL", "requirement": "required"},
            {"canonical": "redis", "raw": "Redis", "requirement": "required"},
            {"canonical": "docker", "raw": "Docker", "requirement": "preferred"},
        ],
        "profile_skills": [
            {"canonical": "python", "display": "Python", "category": "language", "evidenced": True},
            {
                "canonical": "fastapi",
                "display": "FastAPI",
                "category": "framework",
                "evidenced": True,
            },
            {
                "canonical": "postgresql",
                "display": "PostgreSQL",
                "category": "database",
                "evidenced": True,
            },
            {"canonical": "redis", "display": "Redis", "category": "database", "evidenced": False},
        ],
        "forbidden_topics": ["adc", "stm32", "freertos", "示波器", "spi", "react"],
        "candidate_summary": "服务端开发，做过订单服务与查询优化。",
        "project_name": "Order Service",
        "project_summary": "Python 与 FastAPI 实现的订单服务，PostgreSQL 存储并做了索引优化。",
        "project_stack": ["Python", "FastAPI", "PostgreSQL", "SQL"],
    },
    {
        "id": "iv-ai-app",
        "role": "AI 应用工程师",
        "difficulty": _DEFAULT_DIFFICULTY,
        "jd_text": (
            "招聘 AI 应用工程师：熟悉 RAG 与 LLM 应用开发，了解向量数据库；"
            "有 FastAPI 服务化经验者优先。"
        ),
        "jd_skills": [
            {"canonical": "rag", "raw": "RAG", "requirement": "required"},
            {"canonical": "llm", "raw": "LLM", "requirement": "required"},
            {"canonical": "vector_db", "raw": "向量数据库", "requirement": "required"},
            {"canonical": "python", "raw": "Python", "requirement": "required"},
            {"canonical": "fastapi", "raw": "FastAPI", "requirement": "preferred"},
        ],
        "profile_skills": [
            {"canonical": "rag", "display": "RAG", "category": "domain", "evidenced": True},
            {"canonical": "llm", "display": "LLM", "category": "domain", "evidenced": True},
            {"canonical": "python", "display": "Python", "category": "language", "evidenced": True},
            {
                "canonical": "vector_db",
                "display": "Vector Database",
                "category": "database",
                "evidenced": False,
            },
        ],
        "forbidden_topics": ["adc", "stm32", "can 总线", "pid", "css"],
        "candidate_summary": "做过文档问答与检索增强生成应用。",
        "project_name": "Doc QA",
        "project_summary": "RAG 文档问答：标题分块、向量与关键词混合检索、答案生成。",
        "project_stack": ["Python", "RAG", "LLM"],
    },
]


def build_interview_rows() -> list[dict[str, Any]]:
    """Render the scenarios as dataset rows, one per scenario."""
    return [
        {
            "id": scenario["id"],
            "fixture_version": FIXTURE_VERSION,
            "scenario": scenario,
        }
        for scenario in INTERVIEW_SCENARIOS
    ]
