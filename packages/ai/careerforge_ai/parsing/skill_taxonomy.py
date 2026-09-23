"""Skill taxonomy: the controlled vocabulary that makes matching deterministic.

Everything downstream — JD parsing, evidence attribution, gap analysis, match
scoring — depends on turning free text ("STM32F407", "Free RTOS", "C++11") into
a stable ``canonical_id``. Doing that with a lexicon rather than a language model
keeps the mapping reproducible and testable; the LLM is only asked to *find
mentions*, this module decides what they *are*.

The same taxonomy is seeded into the ``skills`` table
(``infra/db/init/002_skills.sql``) and a CI test asserts the two agree.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
import re

from careerforge_ai.schemas.common import SkillCategory

__all__ = [
    "ALIAS_INDEX",
    "SKILLS",
    "SKILL_BY_ID",
    "TAXONOMY_VERSION",
    "Skill",
    "extract_skill_mentions",
    "is_known_skill",
    "normalize_skill",
    "skill_categories",
]

TAXONOMY_VERSION = "taxonomy@1.0.0"


@dataclass(frozen=True, slots=True)
class Skill:
    canonical_id: str
    display_name: str
    category: SkillCategory
    aliases: tuple[str, ...] = ()

    @property
    def all_forms(self) -> tuple[str, ...]:
        return (self.display_name, *self.aliases)


def _s(
    canonical_id: str,
    display_name: str,
    category: SkillCategory,
    *aliases: str,
) -> Skill:
    return Skill(canonical_id, display_name, category, tuple(aliases))


C = SkillCategory
_SKILL_LIST: tuple[Skill, ...] = (
    # ── Programming languages ────────────────────────────────────────────────
    _s("c", "C", C.LANGUAGE, "c language", "ansi c", "c99", "c11"),
    _s("cplusplus", "C++", C.LANGUAGE, "cpp", "c++11", "c++14", "c++17", "c++20"),
    _s("csharp", "C#", C.LANGUAGE, "csharp", ".net c#"),
    _s("python", "Python", C.LANGUAGE, "python3", "py"),
    _s("java", "Java", C.LANGUAGE),
    _s("javascript", "JavaScript", C.LANGUAGE, "js", "es6", "ecmascript"),
    _s("typescript", "TypeScript", C.LANGUAGE, "ts"),
    _s("go", "Go", C.LANGUAGE, "golang"),
    _s("rust", "Rust", C.LANGUAGE),
    _s("kotlin", "Kotlin", C.LANGUAGE),
    _s("swift", "Swift", C.LANGUAGE),
    _s("matlab", "MATLAB", C.LANGUAGE, "matlab/simulink"),
    _s("verilog", "Verilog", C.LANGUAGE, "systemverilog", "vhdl"),
    _s("assembly", "Assembly", C.LANGUAGE, "asm", "arm assembly"),
    _s("sql", "SQL", C.LANGUAGE),
    _s("bash", "Bash", C.LANGUAGE, "shell", "shell script", "shellscript"),
    _s("lua", "Lua", C.LANGUAGE),
    # ── Embedded ─────────────────────────────────────────────────────────────
    _s(
        "stm32",
        "STM32",
        C.EMBEDDED,
        "stm32f1",
        "stm32f4",
        "stm32f7",
        "stm32h7",
        "stm32f407",
        "stm32 hal",
        "hal库",
    ),
    _s("free_rtos", "FreeRTOS", C.EMBEDDED, "freertos", "free rtos", "rtos"),
    _s("rt_thread", "RT-Thread", C.EMBEDDED, "rtthread"),
    _s("zephyr", "Zephyr", C.EMBEDDED, "zephyr rtos"),
    _s("embedded_linux", "Embedded Linux", C.EMBEDDED, "嵌入式linux", "yocto", "buildroot"),
    _s("linux_driver", "Linux Driver", C.EMBEDDED, "字符设备驱动", "kernel module", "内核驱动"),
    _s("device_driver", "Device Driver", C.EMBEDDED, "驱动开发", "外设驱动"),
    _s("esp32", "ESP32", C.EMBEDDED, "esp-idf", "espressif"),
    _s("arduino", "Arduino", C.EMBEDDED),
    _s("raspberry_pi", "Raspberry Pi", C.EMBEDDED, "树莓派"),
    _s("cuda_mcu", "MCU", C.EMBEDDED, "microcontroller", "单片机", "mcu开发"),
    _s("dsp", "DSP", C.EMBEDDED, "数字信号处理", "digital signal processing"),
    _s("fpga", "FPGA", C.EMBEDDED, "zynq", "xilinx", "altera"),
    _s("pcb", "PCB Design", C.EMBEDDED, "pcb设计", "altium", "立创eda", "easyeda"),
    # ── Buses & protocols ────────────────────────────────────────────────────
    _s("uart", "UART", C.EMBEDDED, "usart", "串口", "serial port"),
    _s("spi", "SPI", C.EMBEDDED),
    _s("i2c", "I2C", C.EMBEDDED, "iic", "i²c"),
    _s("can", "CAN", C.EMBEDDED, "can bus", "canopen", "can总线", "canfd", "can fd"),
    _s("modbus", "Modbus", C.EMBEDDED, "modbus rtu", "modbus tcp"),
    _s("usb", "USB", C.EMBEDDED, "usb device", "usb hid"),
    _s("ethernet", "Ethernet", C.EMBEDDED, "以太网", "lwip"),
    _s("bluetooth", "Bluetooth", C.EMBEDDED, "ble", "低功耗蓝牙"),
    _s("mqtt", "MQTT", C.EMBEDDED, "mqtts"),
    _s("pwm", "PWM", C.EMBEDDED, "pwm输出"),
    _s("adc", "ADC", C.EMBEDDED, "dac", "模数转换"),
    _s("dma", "DMA", C.EMBEDDED, "dma传输", "dma搬运"),
    _s("interrupt", "Interrupt Handling", C.EMBEDDED, "中断", "isr", "中断服务程序"),
    _s("pid", "PID Control", C.EMBEDDED, "pid控制", "pid算法", "闭环控制"),
    _s(
        "motor_control",
        "Motor Control",
        C.EMBEDDED,
        "电机控制",
        "foc",
        "bldc",
        "步进电机",
        "直流电机",
    ),
    _s("imu", "IMU", C.EMBEDDED, "mpu6050", "icm20602", "惯性测量单元", "加速度计"),
    _s("encoder", "Encoder", C.EMBEDDED, "编码器", "霍尔传感器"),
    _s(
        "sensor_fusion",
        "Sensor Fusion",
        C.EMBEDDED,
        "姿态解算",
        "attitude estimation",
        "卡尔曼滤波",
        "kalman filter",
        "互补滤波",
    ),
    _s("autosar", "AUTOSAR", C.EMBEDDED, "autosar classic"),
    _s("bootloader", "Bootloader", C.EMBEDDED, "iap", "固件升级", "ota"),
    _s("low_power", "Low Power Design", C.EMBEDDED, "低功耗", "sleep mode"),
    _s(
        "rtos_scheduler",
        "RTOS Scheduling",
        C.EMBEDDED,
        "任务调度",
        "优先级反转",
        "priority inversion",
    ),
    # ── Robotics / autonomy ──────────────────────────────────────────────────
    _s("ros", "ROS", C.DOMAIN, "ros2", "robot operating system"),
    _s("px4", "PX4", C.DOMAIN, "px4 autopilot"),
    _s("ardupilot", "ArduPilot", C.DOMAIN, "apm"),
    _s("slam", "SLAM", C.AI, "建图定位", "cartographer"),
    _s("path_planning", "Path Planning", C.DOMAIN, "路径规划", "a*", "rrt"),
    _s("computer_vision", "Computer Vision", C.AI, "opencv", "机器视觉", "图像处理"),
    _s("control_theory", "Control Theory", C.DOMAIN, "自动控制", "状态空间", "lqr", "mpc"),
    # ── Backend ──────────────────────────────────────────────────────────────
    _s("fastapi", "FastAPI", C.BACKEND, "fast api"),
    _s("django", "Django", C.BACKEND, "drf", "django rest framework"),
    _s("flask", "Flask", C.BACKEND),
    _s("spring_boot", "Spring Boot", C.BACKEND, "spring", "springboot"),
    _s("nodejs", "Node.js", C.BACKEND, "node", "nodejs", "express", "nestjs"),
    _s("grpc", "gRPC", C.BACKEND, "protobuf", "protocol buffers"),
    _s("rest_api", "REST API", C.BACKEND, "restful", "rest 接口", "http api"),
    _s("microservices", "Microservices", C.BACKEND, "微服务"),
    _s("redis", "Redis", C.DATABASE, "redis cluster"),
    _s("kafka", "Kafka", C.BACKEND, "消息队列", "message queue", "rabbitmq", "rocketmq"),
    _s("celery", "Celery", C.BACKEND, "异步任务", "task queue"),
    _s("websocket", "WebSocket", C.BACKEND),
    _s("sqlalchemy", "SQLAlchemy", C.BACKEND, "orm"),
    # ── Databases ────────────────────────────────────────────────────────────
    _s("postgresql", "PostgreSQL", C.DATABASE, "postgres", "pg", "pgvector"),
    _s("mysql", "MySQL", C.DATABASE, "mariadb"),
    _s("sqlite", "SQLite", C.DATABASE),
    _s("mongodb", "MongoDB", C.DATABASE, "mongo"),
    _s("elasticsearch", "Elasticsearch", C.DATABASE, "es", "opensearch"),
    _s("vector_db", "Vector Database", C.AI, "faiss", "chroma", "milvus", "qdrant", "向量数据库"),
    # ── Frontend ─────────────────────────────────────────────────────────────
    _s("react", "React", C.FRONTEND, "react.js", "reactjs"),
    _s("nextjs", "Next.js", C.FRONTEND, "next", "nextjs"),
    _s("vue", "Vue", C.FRONTEND, "vue.js", "vue3", "nuxt"),
    _s("tailwind", "Tailwind CSS", C.FRONTEND, "tailwindcss"),
    _s("html_css", "HTML/CSS", C.FRONTEND, "html", "css", "scss", "less"),
    _s("vite", "Vite", C.FRONTEND, "webpack", "构建工具"),
    _s("electron", "Electron", C.FRONTEND, "tauri"),
    _s("miniprogram", "Mini Program", C.FRONTEND, "小程序", "微信小程序", "uniapp"),
    # ── AI / ML ──────────────────────────────────────────────────────────────
    _s("pytorch", "PyTorch", C.AI, "torch"),
    _s("tensorflow", "TensorFlow", C.AI, "tf", "keras"),
    _s("llm", "LLM", C.AI, "大模型", "large language model"),
    _s("rag", "RAG", C.AI, "retrieval augmented generation", "检索增强生成"),
    _s("langchain", "LangChain", C.AI, "langgraph", "llamaindex"),
    _s("prompt_engineering", "Prompt Engineering", C.AI, "提示工程", "prompt 设计"),
    _s("fine_tuning", "Fine-tuning", C.AI, "微调", "lora", "qlora", "sft"),
    _s("agent", "AI Agent", C.AI, "智能体", "multi-agent", "agent 编排"),
    _s("numpy_pandas", "NumPy/Pandas", C.AI, "numpy", "pandas", "scipy", "数据分析"),
    _s("sklearn", "scikit-learn", C.AI, "sklearn", "机器学习"),
    _s("deep_learning", "Deep Learning", C.AI, "深度学习", "神经网络", "cnn", "transformer"),
    _s("nlp", "NLP", C.AI, "自然语言处理"),
    _s("mlops", "MLOps", C.AI, "模型部署", "model serving", "vllm", "onnx"),
    # ── DevOps / infra ───────────────────────────────────────────────────────
    _s("docker", "Docker", C.DEVOPS, "docker compose", "容器化", "container"),
    _s("kubernetes", "Kubernetes", C.DEVOPS, "k8s", "k3s"),
    _s("cicd", "CI/CD", C.DEVOPS, "github actions", "jenkins", "gitlab ci", "持续集成"),
    _s("linux", "Linux", C.DEVOPS, "ubuntu", "centos", "linux 系统"),
    _s("nginx", "Nginx", C.DEVOPS, "反向代理", "reverse proxy"),
    _s("terraform", "Terraform", C.DEVOPS, "iac"),
    _s("monitoring", "Monitoring", C.DEVOPS, "prometheus", "grafana", "监控告警"),
    # ── Tools ────────────────────────────────────────────────────────────────
    _s("git", "Git", C.TOOL, "github", "gitlab", "版本控制"),
    _s("cmake", "CMake", C.TOOL, "makefile", "构建系统"),
    _s("gdb", "GDB", C.TOOL, "调试器", "jlink", "stlink", "仿真器"),
    _s("oscilloscope", "Oscilloscope", C.TOOL, "示波器", "逻辑分析仪", "logic analyzer"),
    _s("keil", "Keil MDK", C.TOOL, "keil5", "mdk"),
    _s("cubemx", "STM32CubeMX", C.TOOL, "cubemx", "cubeide", "stm32cubeide"),
    _s("matlab_simulink", "Simulink", C.TOOL, "simulink 仿真"),
    _s("swagger", "OpenAPI", C.TOOL, "swagger", "接口文档"),
    _s("unity_engine", "Unity", C.TOOL, "ue", "unreal"),
    # ── Domain / process ─────────────────────────────────────────────────────
    _s("system_design", "System Design", C.DOMAIN, "系统设计", "架构设计"),
    _s("performance_tuning", "Performance Tuning", C.DOMAIN, "性能优化", "性能调优", "profiling"),
    _s("code_review", "Code Review", C.DOMAIN, "代码评审"),
    _s("unit_testing", "Unit Testing", C.DOMAIN, "单元测试", "pytest", "gtest", "junit"),
    _s("agile", "Agile", C.SOFT, "scrum", "敏捷开发"),
    _s("technical_writing", "Technical Writing", C.SOFT, "技术文档", "文档撰写"),
    _s("communication", "Communication", C.SOFT, "沟通协作", "团队协作"),
    _s("problem_solving", "Problem Solving", C.SOFT, "问题解决", "故障排查", "debugging"),
    _s("project_management", "Project Management", C.SOFT, "项目管理", "需求分析"),
    _s("english", "English", C.SOFT, "英语", "cet-6", "cet6"),
)

SKILLS: tuple[Skill, ...] = _SKILL_LIST
SKILL_BY_ID: dict[str, Skill] = {skill.canonical_id: skill for skill in SKILLS}

#: Every alias (lower-cased) → its canonical skill. Longer aliases are matched
#: first so that "free rtos" wins over "rtos" and "c++" wins over "c".
ALIAS_INDEX: dict[str, Skill] = {}
for _skill in SKILLS:
    for _form in _skill.all_forms:
        _key = _form.strip().lower()
        ALIAS_INDEX.setdefault(_key, _skill)
    ALIAS_INDEX.setdefault(_skill.canonical_id, _skill)

_SORTED_ALIASES: tuple[str, ...] = tuple(
    sorted(ALIAS_INDEX.keys(), key=lambda alias: (-len(alias), alias))
)

#: Aliases of two characters or fewer must match a whole token, otherwise "C"
#: would fire inside every word containing the letter c.
_SHORT_ALIAS_MAXLEN = 2

_TOKEN_BOUNDARY = r"[a-z0-9]"


def _build_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias)
    if len(alias) <= _SHORT_ALIAS_MAXLEN:
        pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
    else:
        pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])" if alias.isalnum() else escaped
    return re.compile(pattern, re.IGNORECASE)


_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def _pattern_for(alias: str) -> re.Pattern[str]:
    cached = _PATTERN_CACHE.get(alias)
    if cached is None:
        cached = _build_pattern(alias)
        _PATTERN_CACHE[alias] = cached
    return cached


def normalize_skill(text: str) -> Skill | None:
    """Resolve a free-text skill name to a taxonomy entry, or ``None``.

    Normalisation is alias-table driven and never fuzzy: a miss is reported
    honestly (``unmapped_skills``) rather than guessed, because a wrong mapping
    silently corrupts every downstream score.
    """
    if not text:
        return None
    key = text.strip().lower()
    if not key:
        return None
    direct = ALIAS_INDEX.get(key)
    if direct is not None:
        return direct
    # Fall back to a scan: the text may be a phrase containing a known skill.
    cleaned = re.sub(r"[（(][^)）]*[)）]", "", key).strip()
    direct = ALIAS_INDEX.get(cleaned)
    if direct is not None:
        return direct
    for alias in _SORTED_ALIASES:
        if _pattern_for(alias).search(key):
            return ALIAS_INDEX[alias]
    return None


def extract_skill_mentions(text: str, *, dedupe: bool = True) -> list[tuple[Skill, str, int]]:
    """Find every taxonomy skill mentioned in ``text``.

    Returns ``(skill, matched_alias, char_offset)`` triples. Overlapping matches
    resolve to the longest alias, so "UART DMA" reports both UART and DMA while
    "C++" never reports C.

    Args:
        text: the material to scan.
        dedupe: when true (the default) only the earliest mention of each skill is
            returned. Callers that filter mentions by *position* must pass
            ``False``: a JD that names Kubernetes in its company blurb and again
            in its requirements section would otherwise lose the second, valid
            mention because the first one was discarded downstream.
    """
    if not text:
        return []
    lowered = text.lower()
    claimed: list[tuple[int, int, Skill, str]] = []

    for alias in _SORTED_ALIASES:
        skill = ALIAS_INDEX[alias]
        for match in _pattern_for(alias).finditer(lowered):
            claimed.append((match.start(), match.end(), skill, alias))

    # Longest match wins; ties break on earliest position.
    claimed.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    taken: list[tuple[int, int]] = []
    results: list[tuple[Skill, str, int]] = []
    seen_skills: set[str] = set()

    for start, end, skill, alias in claimed:
        if dedupe and skill.canonical_id in seen_skills:
            continue
        if any(not (end <= s or start >= e) for s, e in taken):
            continue
        taken.append((start, end))
        seen_skills.add(skill.canonical_id)
        results.append((skill, alias, start))

    results.sort(key=lambda item: item[2])
    return results


def skill_categories(skill_ids: Iterable[str]) -> dict[str, SkillCategory]:
    """Canonical id → category, for the scoring engines that need domain context."""
    out: dict[str, SkillCategory] = {}
    for skill_id in skill_ids:
        skill = SKILL_BY_ID.get(skill_id.lower())
        if skill is not None:
            out[skill.canonical_id] = skill.category
    return out


def is_known_skill(text: str) -> bool:
    return normalize_skill(text) is not None


def iter_aliases() -> Iterator[tuple[str, str]]:
    """Yield ``(alias, canonical_id)`` pairs — used to build the seed SQL."""
    for alias, skill in ALIAS_INDEX.items():
        yield alias, skill.canonical_id
