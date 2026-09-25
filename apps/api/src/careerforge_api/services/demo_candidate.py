"""The demo candidate's career fixture — one coherent person, in one place.

``docs/DATABASE.md`` §8 specifies a demo account (``demo@careerforge.ai``, slug ``alex``) whose
profile is *self-consistent*: a headline that is a professional title, projects with real
summaries, and a skill set the rest of the product already assumes. Until this module existed the
seed wrote the identity only — name, slug, headline, target roles — so every downstream screen read
a candidate with no projects, no experience and no skills, and the demo had to be populated by hand
through ``POST /profile/import`` before it looked like anything.

Two rules decided the contents, and both are about not contradicting the fixtures the product
already ships:

* **The skills are the ones the shipped demo flows rely on.** The Jobs demo posting names CAN and
  AUTOSAR as gaps on purpose, the validator's Unsupported preset names Rust/Kubernetes/TensorFlow,
  and its Strong preset names STM32/FreeRTOS/PID/I2C — so those stay exactly as they were. The
  brief for this phase adds the AI-application half of the same person: Python, FastAPI and RAG,
  which is what "Embedded & AI Application Engineer" means and what the CareerForge AI project is.
* **Nothing here invents a contact detail.** Email, phone and address are absent or placeholders;
  the public page redacts incidental PII on publish, and a fixture is the last place to put a real
  one.

The fixture is a ``CandidateProfile`` and is written through ``ProfileService`` — the same writer an
import uses — so the seeded profile is not a special shape that only the seed can produce.
"""

from __future__ import annotations

from datetime import date

from careerforge_ai.schemas.common import (
    EvidenceStrength,
    Origin,
    SkillCategory,
    SkillLevel,
)
from careerforge_ai.schemas.profile import (
    CandidateProfile,
    Education,
    Experience,
    ProfileSkill,
    Project,
    SkillRef,
)

__all__ = [
    "DEMO_GITHUB_USERNAME",
    "DEMO_HEADLINE",
    "DEMO_LOCATION",
    "DEMO_SKILLS",
    "DEMO_SUMMARY",
    "DEMO_TARGET_ROLES",
    "demo_candidate_profile",
]

#: Headline from ``docs/DATABASE.md`` §8 — a *title*, never the person's name. The public page
#: prints the display name as its heading and this line under it; when the two are the same string
#: the page reads as duplicated data (which is what it did before).
DEMO_HEADLINE = "Embedded & AI Application Engineer"

#: Example target roles from ``docs/DATABASE.md`` §2.1.
DEMO_TARGET_ROLES: tuple[str, ...] = ("Embedded Engineer", "AI Application Engineer")

DEMO_LOCATION = "Shanghai, China"

DEMO_GITHUB_USERNAME = "alexchen"

DEMO_SUMMARY = (
    "嵌入式固件工程师，五年电机控制与实时系统经验（STM32 / FreeRTOS / PID，含现场总线调试），"
    "近两年把同样的工程方法用到 AI 应用上：用 Python 与 FastAPI 搭建检索增强（RAG）服务，"
    "把固件调试时养成的「先量测、再判断」习惯带进模型评测。偏好能同时碰到硬件与数据链路的岗位。"
)

#: The candidate's declared skills, in the taxonomy's own canonical ids.
#:
#: Every id below exists in ``careerforge_ai/parsing/skill_taxonomy.py``: a declaration the taxonomy
#: does not know is dropped by the writer, so a typo here would silently produce a candidate with
#: fewer skills and no error.
#:
#: Deliberately absent: ``kafka`` and ``autosar``. The demo posting's 加分项 names both, and the
#: validator's Unsupported preset depends on the evidence not carrying them — a demo profile that
#: claims them would turn the product's own honesty demo into a lie.
#:
#: Deliberately absent as well: ``can``. ``docs/DEMO.md`` uses CAN as the posting requirement the
#: demo profile does *not* cover, which is what makes the Jobs page show a real gap next to the
#: matched skills.
DEMO_SKILLS: tuple[tuple[str, str, SkillCategory, SkillLevel, bool], ...] = (
    ("stm32", "STM32", SkillCategory.EMBEDDED, SkillLevel.STRONG, True),
    ("free_rtos", "FreeRTOS", SkillCategory.EMBEDDED, SkillLevel.STRONG, True),
    ("pid", "PID Control", SkillCategory.EMBEDDED, SkillLevel.STRONG, False),
    ("i2c", "I2C", SkillCategory.EMBEDDED, SkillLevel.MODERATE, False),
    ("spi", "SPI", SkillCategory.EMBEDDED, SkillLevel.MODERATE, False),
    ("c", "C", SkillCategory.LANGUAGE, SkillLevel.STRONG, False),
    ("cplusplus", "C++", SkillCategory.LANGUAGE, SkillLevel.MODERATE, False),
    ("python", "Python", SkillCategory.LANGUAGE, SkillLevel.STRONG, True),
    ("fastapi", "FastAPI", SkillCategory.BACKEND, SkillLevel.STRONG, True),
    ("rest_api", "REST API", SkillCategory.BACKEND, SkillLevel.MODERATE, False),
    ("rag", "RAG", SkillCategory.AI, SkillLevel.MODERATE, True),
    ("llm", "LLM", SkillCategory.AI, SkillLevel.MODERATE, False),
    ("postgresql", "PostgreSQL", SkillCategory.DATABASE, SkillLevel.MODERATE, False),
    ("docker", "Docker", SkillCategory.DEVOPS, SkillLevel.MODERATE, False),
    ("git", "Git", SkillCategory.TOOL, SkillLevel.STRONG, False),
    ("cmake", "CMake", SkillCategory.TOOL, SkillLevel.MODERATE, False),
)


def _education() -> Education:
    return Education(
        school="上海理工大学",
        degree="本科",
        major="电子信息工程",
        start_date=date(2016, 9, 1),
        end_date=date(2020, 6, 30),
        gpa=3.6,
        highlights=[
            "主修：数字电路、模拟电路、嵌入式系统设计、自动控制原理",
            "毕业设计：基于 STM32F407 的多轴步进电机控制器（评委评分 92/100）",
        ],
        evidence_strength=EvidenceStrength.MEDIUM,
        origin=Origin.IMPORT,
    )


def _experiences() -> list[Experience]:
    """Two roles, described the way a CV describes them — not the way an extractor mangles them."""
    return [
        Experience(
            kind="fulltime",
            company="某某机器人科技有限公司",
            title="嵌入式软件工程师",
            location="上海",
            start_date=date(2022, 7, 1),
            is_current=True,
            description=(
                "负责扫地机器人主控固件的运动控制模块：维护一套 STM32F407 + FreeRTOS 的 12 任务"
                "调度框架，把控制周期稳定在 1ms。"
            ),
            highlights=[
                "用 I2C 读取 IMU 姿态，完成互补滤波与 PID 速度环整定，把直线行走偏差从 8cm 降到 1.5cm",
                "定义并实现 8 条底盘通信应用层报文，定位并修复总线偶发丢帧",
                "用 CMake 重构构建系统，固件构建时间从 6 分钟压到 90 秒",
            ],
            evidence_strength=EvidenceStrength.HIGH,
            origin=Origin.IMPORT,
        ),
        Experience(
            kind="fulltime",
            company="某某汽车电子有限公司",
            title="嵌入式软件工程师",
            location="上海",
            start_date=date(2020, 7, 1),
            end_date=date(2022, 6, 30),
            description=(
                "车身控制器（BCM）软件模块开发：在 STM32 平台上用 C 实现 UART/SPI 外设驱动，"
                "配合整车联调完成 3 个车型的软件发布。"
            ),
            highlights=[
                "编写单元测试与硬件在环测试脚本，把回归测试从人工两小时压到自动 15 分钟",
                "负责 EMC 测试阶段的固件问题定位，出具 4 份整改报告",
            ],
            evidence_strength=EvidenceStrength.MEDIUM,
            origin=Origin.IMPORT,
        ),
    ]


def _projects() -> list[Project]:
    """Three projects, each with a summary that says something the *name* does not.

    The bug this replaces: an extractor that copies the project's title line into its summary
    produced a recruiter page whose first project read "智能平衡小车（个人项目） —
    智能平衡小车（个人项目）", i.e. the same sentence twice, which is how broken data reads.
    """
    return [
        Project(
            name="双轮自平衡小车",
            role="个人项目 · 硬件与固件",
            summary=(
                "一辆两轮自平衡小车：MPU6050 采姿态，互补滤波估角，串级 PID 控制速度与直立环，"
                "用 UART 输出实时曲线做调参，整理调试笔记 12 篇。"
            ),
            description=(
                "从零搭起的最小闭环控制系统，目的是把控制理论落到一个能用手推翻的实物上。"
            ),
            tech_stack=["STM32", "FreeRTOS", "PID Control", "I2C", "UART"],
            start_date=date(2021, 3, 1),
            end_date=date(2021, 9, 30),
            links={"github": "https://github.com/alexchen/stm32-balance-car"},
            key_challenges=[
                "把 1kHz 的姿态采样与 100Hz 的控制环拆成两个 FreeRTOS 任务，用队列解耦",
                "滤波参数整定：互补滤波系数与 PID 参数互相影响，最终用阶跃响应逐项定标",
            ],
            technical_decisions=[
                "为什么不用卡尔曼滤波：MPU6050 的噪声特性用互补滤波已经够用，代价是不需要矩阵运算",
            ],
            tradeoffs=["控制周期从 2ms 提到 1ms 后抖动更小，但 CPU 余量从 60% 降到 35%"],
            evidence_strength=EvidenceStrength.HIGH,
            origin=Origin.IMPORT,
        ),
        Project(
            name="无人机云台控制系统",
            role="实验室项目 · 固件负责人",
            summary=(
                "三轴云台的增稳固件：用 SPI 读取陀螺仪，实现带限幅的串级 PID 与电机驱动时序，"
                "在 6 级风下把画面抖动压到可用的范围。"
            ),
            description=("实验室承接的横向项目，硬件由队友设计，我负责控制固件与整机联调。"),
            tech_stack=["STM32", "FreeRTOS", "SPI", "PID Control", "C"],
            start_date=date(2020, 9, 1),
            end_date=date(2021, 6, 30),
            key_challenges=[
                "电机换向噪声耦合进陀螺仪读数，靠调整采样时序与地线布局解决",
                "限幅与积分饱和：没有 anti-windup 时一次大扰动会让云台反向过冲",
            ],
            evidence_strength=EvidenceStrength.MEDIUM,
            origin=Origin.IMPORT,
        ),
        Project(
            name="CareerForge AI 证据检索服务",
            role="个人项目 · 服务端与检索",
            summary=(
                "一个把简历与代码仓索引成可检索证据库的后端服务：FastAPI 提供接口，"
                "PostgreSQL 存储切片与向量，检索用混合召回（关键词 + 语义）后再重排序，"
                "并把每条回答指回具体证据片段。"
            ),
            description=(
                "开始做 AI 应用后先解决的问题不是生成，而是「这句话凭什么成立」 —— "
                "所以服务的设计目标是每条结论都能追到一段可核对的原文。"
            ),
            tech_stack=["Python", "FastAPI", "PostgreSQL", "RAG", "LLM", "Docker"],
            start_date=date(2024, 4, 1),
            links={"github": "https://github.com/alexchen/careerforge-rag"},
            key_challenges=[
                "混合召回的权重：等权 RRF 在 59 条查询的小语料上会丢一题，最终保留可解释的等权方案并记录",
                "切片策略：按章节切比按固定长度切，召回率更稳，代价是切片长度差异大",
            ],
            technical_decisions=[
                "为什么不用 LangChain：需要的编排只有四步，自己写比读框架源码便宜",
            ],
            tradeoffs=["加一版重排序模型能提 3 个点召回，但单次查询延迟从 120ms 涨到 400ms"],
            evidence_strength=EvidenceStrength.MEDIUM,
            origin=Origin.IMPORT,
        ),
    ]


def _skills() -> list[ProfileSkill]:
    """Declared skills with **no** evidence count.

    ``evidence_count = 0`` is the honest starting state: the declarations come from the fixture, and
    the evidence rows arrive when the candidate actually uploads material. Writing a non-zero count
    here would make the graph claim corroboration nobody measured.
    """
    return [
        ProfileSkill(
            skill=SkillRef(canonical_id=canonical, display_name=display_name, category=category),
            level=level,
            evidence_score=0.0,
            evidence_count=0,
            is_target=is_target,
            origin=Origin.IMPORT,
        )
        for canonical, display_name, category, level, is_target in DEMO_SKILLS
    ]


def demo_candidate_profile(*, slug: str, github_username: str | None = None) -> CandidateProfile:
    """The whole demo candidate, assembled.

    ``headline`` is a title and ``summary`` is prose: neither repeats the person's name, which is
    what the recruiter page prints above them.
    """
    return CandidateProfile(
        slug=slug,
        headline=DEMO_HEADLINE,
        summary=DEMO_SUMMARY,
        location=DEMO_LOCATION,
        github_username=github_username or DEMO_GITHUB_USERNAME,
        target_roles=list(DEMO_TARGET_ROLES),
        years_experience=5.0,
        educations=[_education()],
        experiences=_experiences(),
        projects=_projects(),
        skills=_skills(),
    )
