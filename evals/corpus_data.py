"""Corpus data for the evaluation suites.

Pure data: role families with their skill pools and phrasing templates. Split out from
the generator so the logic that consumes it stays readable, and so a change to the corpus
is obvious in review — these literals are the ground truth every metric is computed
against.

The claim corpus that used to live here was **retired in PHASE 12**: it was generated from
a handful of templates (120 rows, 22 distinct claim/kind pairs), so every claim metric was a
statement about a template rather than about the gate. Claims are now hand-authored in
``evals/corpus_evidence.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "BLURBS_EN",
    "BLURBS_ZH",
    "COMPANIES_EN",
    "COMPANIES_ZH",
    "DISTRACTOR_RATE",
    "ENGLISH_RATE",
    "FAMILIES",
    "JD_SAMPLE_COUNT",
    "LOCATIONS_EN",
    "LOCATIONS_ZH",
    "MIXED_RATE",
    "RoleFamily",
    "SEED",
]


SEED = 20260211
JD_SAMPLE_COUNT = 120

#: Fraction of JDs that include deliberately misleading boilerplate: a company
#: blurb naming technologies the role does not require. Measuring precision
#: without distractors would be measuring nothing.
DISTRACTOR_RATE = 0.65

#: Fraction written in a mixed zh/en style, which is how a great many real
#: postings from Chinese companies actually read.
MIXED_RATE = 0.17
ENGLISH_RATE = 0.33


@dataclass(frozen=True, slots=True)
class RoleFamily:
    key: str
    titles_zh: tuple[str, ...]
    titles_en: tuple[str, ...]
    core: tuple[str, ...]
    preferred: tuple[str, ...]
    bonus: tuple[str, ...]
    distractors: tuple[str, ...]
    responsibilities_zh: tuple[str, ...]
    responsibilities_en: tuple[str, ...]


FAMILIES: tuple[RoleFamily, ...] = (
    RoleFamily(
        key="embedded",
        titles_zh=("嵌入式软件工程师", "嵌入式开发工程师", "电机控制工程师"),
        titles_en=("Embedded Software Engineer", "Embedded Firmware Engineer"),
        core=("STM32", "C", "FreeRTOS", "UART", "SPI", "I2C", "CAN", "Interrupt Handling"),
        preferred=("PID Control", "Motor Control", "DMA", "Oscilloscope", "RTOS Scheduling"),
        bonus=("AUTOSAR", "Linux Driver", "Zephyr", "Bootloader", "Low Power Design"),
        distractors=("Kubernetes", "React", "MongoDB", "GraphQL"),
        responsibilities_zh=(
            "负责嵌入式软件的设计、开发与调试",
            "负责电机控制算法的实现与性能优化",
            "负责外设驱动开发与硬件联调",
            "撰写设计文档并参与代码评审",
        ),
        responsibilities_en=(
            "Design, implement and debug embedded firmware",
            "Develop and tune motor control algorithms",
            "Bring up peripheral drivers and debug hardware interfaces",
            "Write design documents and take part in code review",
        ),
    ),
    RoleFamily(
        key="backend",
        titles_zh=("后端开发工程师", "服务端研发工程师"),
        titles_en=("Backend Engineer", "Software Engineer, Backend"),
        core=("Python", "FastAPI", "PostgreSQL", "REST API", "SQL", "Docker", "Redis"),
        preferred=("SQLAlchemy", "Celery", "Kafka", "CI/CD", "Unit Testing"),
        bonus=("Kubernetes", "gRPC", "Terraform", "Monitoring", "Microservices"),
        distractors=("STM32", "FreeRTOS", "PCB Design", "Oscilloscope"),
        responsibilities_zh=(
            "负责后端服务的设计与开发",
            "负责接口性能优化与线上问题排查",
            "参与数据库设计与容量规划",
        ),
        responsibilities_en=(
            "Design and build backend services and APIs",
            "Own service performance and production troubleshooting",
            "Contribute to database design and capacity planning",
        ),
    ),
    RoleFamily(
        key="ai_app",
        titles_zh=("AI 应用工程师", "大模型应用开发工程师", "算法工程师（应用方向）"),
        titles_en=("AI Application Engineer", "LLM Application Engineer"),
        core=("Python", "LLM", "RAG", "Prompt Engineering", "FastAPI", "Vector Database"),
        preferred=("LangChain", "AI Agent", "PyTorch", "PostgreSQL", "Docker"),
        bonus=("Fine-tuning", "MLOps", "NLP", "Deep Learning", "Redis"),
        distractors=("STM32", "UART", "SPI", "PCB Design"),
        responsibilities_zh=(
            "负责基于大模型的应用功能设计与落地",
            "负责检索增强生成链路的效果优化",
            "参与评测体系搭建与效果回归",
        ),
        responsibilities_en=(
            "Design and ship LLM-powered product features",
            "Improve retrieval-augmented generation quality",
            "Build evaluation harnesses and run regression on quality",
        ),
    ),
    RoleFamily(
        key="frontend",
        titles_zh=("前端开发工程师", "Web 前端工程师"),
        titles_en=("Frontend Engineer", "Web Developer"),
        core=("TypeScript", "React", "HTML/CSS", "JavaScript", "Git"),
        preferred=("Next.js", "Tailwind CSS", "Vite", "Unit Testing"),
        bonus=("Electron", "Node.js", "GraphQL", "Mini Program"),
        distractors=("STM32", "CAN", "PostgreSQL", "Kubernetes"),
        responsibilities_zh=(
            "负责 Web 前端页面与组件库开发",
            "负责前端性能优化与体验改进",
        ),
        responsibilities_en=(
            "Build web interfaces and shared component libraries",
            "Own frontend performance and interaction quality",
        ),
    ),
    RoleFamily(
        key="devops",
        titles_zh=("DevOps 工程师", "运维开发工程师"),
        titles_en=("DevOps Engineer", "Site Reliability Engineer"),
        core=("Docker", "Kubernetes", "Linux", "CI/CD", "Monitoring"),
        preferred=("Terraform", "Nginx", "Bash", "Git"),
        bonus=("Python", "Redis", "PostgreSQL", "Microservices"),
        distractors=("STM32", "React", "SPI"),
        responsibilities_zh=(
            "负责 CI/CD 流水线建设与维护",
            "负责容器化平台与监控告警体系",
        ),
        responsibilities_en=(
            "Build and maintain CI/CD pipelines",
            "Own the container platform and observability stack",
        ),
    ),
)

COMPANIES_ZH = ("某科技", "智远科技", "恒芯电子", "云枢信息", "联启智能", "锐驰自动化")
COMPANIES_EN = ("Northwind Technologies", "Helix Systems", "Blue Harbor Labs", "Vantage Robotics")
LOCATIONS_ZH = ("深圳", "上海", "北京", "杭州", "成都", "苏州")
LOCATIONS_EN = ("Shenzhen", "Shanghai", "Beijing", "Remote")

BLURBS_ZH = (
    "我们是一家专注于工业智能化的公司，团队使用 {tech} 构建内部平台，业务覆盖多个行业。",
    "公司成立于 2016 年，业务快速增长，内部工具链基于 {tech} 搭建。",
    "我们为制造业客户提供整体解决方案，研发团队日常使用 {tech}。",
)
BLURBS_EN = (
    "We build industrial software for manufacturing customers. Our internal tooling is built on {tech}.",
    "Founded in 2016, we serve enterprise clients across several industries. Our stack includes {tech}.",
    "We deliver end-to-end solutions for industrial customers. The team works with {tech} daily.",
)
