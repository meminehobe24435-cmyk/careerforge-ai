"""Corpus data for the evaluation suites.

Pure data: role families with their skill pools, phrasing templates and the
controlled claim cases. Split out from the generator so the logic that consumes
it stays readable, and so a change to the corpus is obvious in review — these
literals are the ground truth every metric is computed against.

The claim templates are named by the verdict they are *supposed* to produce, so a
mislabel is visible at the definition site rather than buried in a metric.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "BLURBS_EN",
    "BLURBS_ZH",
    "CLAIM_SAMPLE_COUNT",
    "COMPANIES_EN",
    "COMPANIES_ZH",
    "DISTRACTOR_RATE",
    "ENGLISH_RATE",
    "FAMILIES",
    "JD_SAMPLE_COUNT",
    "LOCATIONS_EN",
    "LOCATIONS_ZH",
    "MIXED_RATE",
    "NUMERIC_CLAIM_TEMPLATES",
    "NO_EVIDENCE_CLAIM_TEMPLATES",
    "PARTIAL_CLAIM_TEMPLATES",
    "RoleFamily",
    "SEED",
    "SUPPORTED_CLAIM_TEMPLATES",
]


SEED = 20260211
JD_SAMPLE_COUNT = 120
CLAIM_SAMPLE_COUNT = 120

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


SUPPORTED_CLAIM_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    (
        "基于 FreeRTOS 开发多任务实时控制系统",
        "freertos.c",
        "项目基于 FreeRTOS 实现多任务实时控制，任务按优先级划分并周期调度，"
        "任务间通过队列通信，关键共享资源使用互斥量保护。",
    ),
    (
        "使用 STM32 HAL 库完成 UART DMA 不定长接收",
        "uart_dma.c",
        "在 STM32 上使用 HAL 库配置 UART DMA 接收，采用空闲中断加环形缓冲区的方式"
        "处理不定长数据帧，接收过程不占用 CPU 轮询。",
    ),
    (
        "实现基于编码器反馈的 PID 闭环电机控制",
        "motor_control.c",
        "通过编码器读取转速，使用 PID 控制器计算占空比并输出到电机驱动，"
        "完成闭环调速，积分项做了抗饱和处理。",
    ),
    (
        "使用 Docker Compose 编排后端服务与数据库",
        "docker-compose.yml",
        "使用 Docker Compose 编排 FastAPI 服务、PostgreSQL 与 Redis，"
        "通过 healthcheck 控制启动顺序，数据卷持久化数据库文件。",
    ),
    (
        "基于 pgvector 实现证据片段的语义检索",
        "retrieval.py",
        "使用 pgvector 存储证据向量，查询时按余弦相似度检索 Top-K 片段，"
        "并与关键词检索结果做 RRF 融合。",
    ),
    (
        "使用 pytest 编写后端单元测试与集成测试",
        "tests/test_match.py",
        "使用 pytest 覆盖匹配评分与证据验证逻辑，包含确定性断言与边界用例，"
        "集成测试基于 httpx ASGI transport 直接调用应用。",
    ),
)

#: Cases where only part of the claim is backed. Gold: partially supported.
PARTIAL_CLAIM_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    (
        "基于 FreeRTOS 开发多任务实时控制系统，并完成 CAN 总线节点通信",
        "freertos.c",
        "项目基于 FreeRTOS 实现多任务实时控制，任务按优先级划分并周期调度。",
    ),
    (
        "使用 STM32 完成 SPI 传感器驱动与 I2C EEPROM 读写",
        "spi_sensor.c",
        "在 STM32 上完成 SPI 传感器驱动的读写与寄存器配置。",
    ),
    (
        "设计并实现整站后端架构，负责数据库、缓存与消息队列选型",
        "notes.md",
        "负责后端服务开发与数据库表结构设计。",
    ),
)

#: Cases with a hard number that no evidence supports. Gold: unsupported.
#: These are the ones the gate must reject, so they dominate the suite.
NUMERIC_CLAIM_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    ("优化算法性能，提升 70%", "notes.md", "对控制回路做了重构，减少了单周期内的重复计算。"),
    ("重构后端接口，响应时间降低 3 倍", "refactor.md", "重构了接口的参数校验与数据库查询逻辑。"),
    ("支撑 10 万 QPS 的高并发架构设计", "arch.md", "参与后端服务架构讨论与接口设计。"),
    ("将系统内存占用降低 45%", "opt.md", "调整了缓冲区大小与任务栈配置。"),
    ("测试覆盖率提升至 90%", "ci.md", "补充了部分单元测试并接入 CI。"),
    ("负责的系统日均处理 500 万次请求", "ops.md", "负责线上服务的日常维护与问题排查。"),
    ("把固件启动时间从 800ms 优化到 120ms", "boot.md", "调整了外设初始化顺序，简化了启动流程。"),
    ("带领 8 人团队完成平台重构", "team.md", "参与平台重构的技术方案讨论。"),
)

#: Cases with no evidence at all. Gold: unsupported.
NO_EVIDENCE_CLAIM_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("熟练使用 Redis 与 Kafka 构建高并发架构", "项目材料中未涉及任何消息队列或缓存组件。"),
    ("精通 Kubernetes 集群运维与故障排查", "候选材料中只有单机 Docker 使用记录。"),
    ("主导 AUTOSAR 架构设计与集成", "候选材料中未出现 AUTOSAR 相关内容。"),
    ("独立完成芯片级驱动开发与流片验证", "候选材料中未涉及芯片设计或流片。"),
    ("作为技术负责人管理 20 人研发团队", "候选材料中无团队管理经历。"),
)
