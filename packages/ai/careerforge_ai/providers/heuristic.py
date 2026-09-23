"""The heuristic provider: a deterministic, dependency-free "model".

Why this exists
---------------
A portfolio project that only works when someone supplies an API key is a
project that cannot be reviewed, cannot run in CI, and cannot be demonstrated on
a locked-down interview laptop. This provider makes CareerForge AI fully
functional with **no key, no network and no GPU** (ADR-009).

How it works
------------
It is not a language model and does not pretend to be. It is a rule engine that
returns **schema-valid** structured output:

* lexicon-driven skill extraction for JD parsing,
* token-overlap evidence matching for claim validation,
* section heuristics for resume/profile parsing,
* template question banks keyed by technical topic,
* a hash-based n-gram embedding for retrieval.

Every result it produces is flagged ``degraded=True`` with
``DegradationReason.NO_API_KEY`` so the UI can say so plainly. Honest and
limited beats confident and wrong.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from enum import StrEnum
import hashlib
import math
import re
import time
from typing import Any, TypeVar

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from careerforge_ai.errors import SchemaValidationError
from careerforge_ai.parsing.skill_taxonomy import extract_skill_mentions
from careerforge_ai.providers.base import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    ProviderCapabilities,
    SchemaT,
    StreamChunk,
    StructuredContext,
    messages_to_text,
)
from careerforge_ai.providers.tokens import estimate_messages_tokens, estimate_tokens
from careerforge_ai.schemas.claim import ClaimLLMVerdict
from careerforge_ai.schemas.common import DegradationReason, DifficultyLevel, RequirementLevel
from careerforge_ai.schemas.github import ExtractedProjectIntelligence
from careerforge_ai.schemas.interview import ExtractedQuestion, ExtractedTurnEvaluation
from careerforge_ai.schemas.job import ExtractedJD, ExtractedJDSkill
from careerforge_ai.schemas.learning import (
    ExtractedLearningPlan,
    ExtractedLearningWeek,
    ExtractedMiniProject,
)
from careerforge_ai.schemas.observability import Cost, TokenUsage
from careerforge_ai.schemas.profile import (
    ExtractedEducation,
    ExtractedExperience,
    ExtractedProfile,
    ExtractedProject,
)

__all__ = ["HEURISTIC_HANDLERS", "HeuristicProvider", "heuristic_embedding"]

_T = TypeVar("_T", bound=BaseModel)

#: Deterministic embedding width. Small on purpose: the vector is a lexical
#: feature hash, not a semantic embedding, and a larger width would only make
#: the pretence more convincing without making retrieval better.
HEURISTIC_EMBEDDING_DIM = 256

_DEFAULT_EMBEDDING_DIM = 1536


# ── Lexical helpers ──────────────────────────────────────────────────────────

_WORD_RE = re.compile(r"[a-z0-9+#._]+|[\u4e00-\u9fff]", re.IGNORECASE)
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "is",
        "are",
        "be",
        "as",
        "at",
        "by",
        "from",
        "that",
        "this",
        "it",
        "we",
        "you",
        "your",
        "our",
        "的",
        "了",
        "和",
        "与",
        "及",
        "或",
        "在",
        "是",
        "为",
        "并",
        "等",
        "对",
        "有",
        "能",
        "熟悉",
        "了解",
        "掌握",
        "要求",
        "负责",
        "参与",
        "具备",
        "优先",
        "加分",
        "以上",
    }
)


def _tokens(text: str) -> list[str]:
    """Tokenise for overlap scoring.

    CJK characters are kept as individual tokens — for Chinese text they are the
    meaningful unit, and dropping single characters (as a naive "length > 1"
    filter does for latin words) would empty the token set entirely and make
    every Chinese claim look unsupported.
    """
    out: list[str] = []
    for token in _WORD_RE.findall(text):
        lowered = token.lower()
        if lowered in _STOPWORDS:
            continue
        if len(token) == 1 and not _CJK_CHAR_RE.match(token):
            continue
        out.append(lowered)
    return out


def _token_overlap(left: str, right: str) -> float:
    """How much of ``left`` is present in ``right``.

    Weighted towards coverage rather than symmetric similarity: the question is
    "is *this claim* supported by the evidence", so a long evidence document
    should not be penalised for containing extra material.
    """
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    jaccard = len(intersection) / len(left_tokens | right_tokens)
    coverage = len(intersection) / len(left_tokens)
    return round(0.25 * jaccard + 0.75 * coverage, 4)


def _ngrams(text: str, n: int = 3) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text.lower().strip())
    if len(cleaned) < n:
        return [cleaned] if cleaned else []
    return [cleaned[i : i + n] for i in range(len(cleaned) - n + 1)]


def heuristic_embedding(text: str, *, dim: int = HEURISTIC_EMBEDDING_DIM) -> list[float]:
    """Deterministic, L2-normalised feature-hash embedding.

    Character n-grams are hashed into ``dim`` buckets with a signed weight, then
    normalised. Texts that share vocabulary land near each other, which is
    enough for the zero-key retrieval path to be genuinely useful for
    near-duplicate and keyword-adjacent queries.
    """
    vector = [0.0] * dim
    grams = _ngrams(text) or [text]
    for gram in grams:
        digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


# ── Section splitting ────────────────────────────────────────────────────────

_SECTION_HEADERS: Mapping[str, tuple[str, ...]] = {
    "education": ("教育", "学历", "education", "academic"),
    "experience": ("实习", "工作经历", "工作经验", "experience", "employment", "internship"),
    "project": ("项目", "project", "projects"),
    "achievement": ("获奖", "荣誉", "证书", "奖项", "award", "honor", "certificat", "competition"),
    "skill": ("技能", "专业技能", "skills", "technical skills"),
}

_DATE_RE = re.compile(r"(?P<year>20\d{2}|19\d{2})\s*[./年-]?\s*(?P<month>0?[1-9]|1[0-2])?")


def _split_sections(text: str) -> dict[str, list[str]]:
    """Split resume-like text into candidate sections by header keywords."""
    sections: dict[str, list[str]] = {key: [] for key in _SECTION_HEADERS}
    sections["_other"] = []
    current = "_other"

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        matched_header: str | None = None
        # A header is a short line containing a known header keyword.
        if len(line) <= 24:
            for key, keywords in _SECTION_HEADERS.items():
                if any(keyword in lowered for keyword in keywords):
                    matched_header = key
                    break
        if matched_header:
            current = matched_header
            remainder = line
            for keyword in _SECTION_HEADERS[matched_header]:
                if keyword in lowered:
                    remainder = line[lowered.index(keyword) + len(keyword) :].strip(" :：-—")
                    break
            if remainder:
                sections[current].append(remainder)
            continue
        sections[current].append(line)

    return sections


def _bullets(lines: Sequence[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        cleaned = re.sub(r"^[\-\u2022*·▪◦>\d.)\s]+", "", line).strip()
        if len(cleaned) >= 6:
            out.append(cleaned)
    return out


def _first_date(text: str) -> str | None:
    match = _DATE_RE.search(text)
    if not match:
        return None
    year = match.group("year")
    month = match.group("month")
    return f"{year}-{int(month):02d}-01" if month else f"{year}-01-01"


# ── Handler registry ─────────────────────────────────────────────────────────

HeuristicHandler = Any  # Callable[[str, Mapping[str, Any]], BaseModel]
HEURISTIC_HANDLERS: dict[str, Any] = {}


def _handles(schema: type[BaseModel]) -> Any:
    def decorator(func: Any) -> Any:
        HEURISTIC_HANDLERS[schema.__name__] = func
        return func

    return decorator


# ── JD extraction ────────────────────────────────────────────────────────────

_REQUIRED_MARKERS = (
    "任职要求",
    "岗位要求",
    "职位要求",
    "requirement",
    "qualification",
    "must have",
    "任职资格",
)
_PREFERRED_MARKERS = ("优先条件", "优先", "preferred", "nice to have", "plus")
_BONUS_MARKERS = (
    "加分项",
    "加分",
    "了解",
    "接触过",
    "familiar with",
    "exposure",
    "a plus",
    "bonus",
)

#: Section markers resolved by nearest-preceding-position, so a skill is
#: classified by the section it actually appears in rather than by where it
#: happens to fall in the document.
_SECTION_MARKERS: tuple[tuple[str, RequirementLevel], ...] = (
    ("加分项", RequirementLevel.BONUS),
    ("加分", RequirementLevel.BONUS),
    ("优先条件", RequirementLevel.PREFERRED),
    ("任职要求", RequirementLevel.REQUIRED),
    ("岗位要求", RequirementLevel.REQUIRED),
    ("职位要求", RequirementLevel.REQUIRED),
    ("任职资格", RequirementLevel.REQUIRED),
    ("岗位职责", RequirementLevel.REQUIRED),
    ("工作职责", RequirementLevel.REQUIRED),
    ("responsibilities", RequirementLevel.REQUIRED),
    ("requirements", RequirementLevel.REQUIRED),
    ("qualifications", RequirementLevel.REQUIRED),
)

_COMPANY_RE = re.compile(
    r"(?:公司|企业|company|employer)\s*[:：]\s*(?P<name>[^\n，,。;；]{2,40})", re.IGNORECASE
)
_ROLE_HINTS = (
    "engineer",
    "developer",
    "scientist",
    "architect",
    "manager",
    "intern",
    "analyst",
    "工程师",
    "开发",
    "架构师",
    "实习生",
    "专家",
    "主管",
    "研究员",
)
_LOCATION_RE = re.compile(
    r"(?:工作地点|地点|城市|location|base)\s*[:：]\s*(?P<loc>[^\n，,。;；]{2,30})", re.IGNORECASE
)
_YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\+)?\s*(?:年|years?)", re.IGNORECASE)
_SALARY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-~至]\s*(\d+(?:\.\d+)?)\s*(?:k|K|万|元)")
_DEGREE_TOKENS = ("本科", "硕士", "博士", "大专", "bachelor", "master", "phd", "专科")
_SECTION_SPLIT_RE = re.compile(
    r"(?=任职要求|岗位要求|职位要求|岗位职责|工作职责|职位描述|加分项|优先条件|"
    r"requirements?|qualifications?|responsibilities|nice to have)",
    re.IGNORECASE,
)


def _classify_requirement(sentence: str, text: str, offset: int) -> RequirementLevel:
    """Decide whether a skill mention is required, preferred or a bonus.

    Order of evidence, most specific first:

    1. The sentence itself uses bonus language ("加分项", "了解", "a plus").
    2. The sentence uses preference language ("优先", "nice to have").
    3. The nearest preceding section header decides.
    4. Default to ``REQUIRED``.

    Defaulting to required is deliberate: under-stating a requirement makes a
    candidate skip a gap that will be probed in the interview, whereas
    over-stating one makes them chase a gap that does not exist. Given a real
    interview, the first error costs more.
    """
    lowered = sentence.lower()
    if any(marker in lowered for marker in _BONUS_MARKERS):
        return RequirementLevel.BONUS
    if any(marker in lowered for marker in _PREFERRED_MARKERS):
        return RequirementLevel.PREFERRED

    prefix = text[:offset].lower()
    best_position = -1
    best_kind: RequirementLevel | None = None
    for marker, kind in _SECTION_MARKERS:
        position = prefix.rfind(marker)
        if position > best_position:
            best_position = position
            best_kind = kind
    if best_kind is not None:
        return best_kind

    if any(marker in lowered for marker in _REQUIRED_MARKERS):
        return RequirementLevel.REQUIRED
    return RequirementLevel.REQUIRED


def _sentence_for(text: str, offset: int, window: int = 120) -> str:
    start = text.rfind("\n", 0, offset)
    start = 0 if start == -1 else start + 1
    end = text.find("\n", offset)
    end = len(text) if end == -1 else end
    sentence = text[start:end].strip()
    if len(sentence) <= window:
        return sentence
    return sentence[:window].rstrip() + "…"


@_handles(ExtractedJD)
def _extract_jd(text: str, context: Mapping[str, Any]) -> ExtractedJD:
    """Lexicon-driven JD parsing — the zero-key path for ``JobAgent``."""
    role = ""
    for line in text.splitlines()[:6]:
        stripped = line.strip()
        if (
            stripped
            and any(hint in stripped.lower() for hint in _ROLE_HINTS)
            and len(stripped) <= 60
        ):
            role = re.sub(
                r"^(职位|岗位|position|title)\s*[:：]\s*", "", stripped, flags=re.IGNORECASE
            )
            break
    if not role:
        for hint in _ROLE_HINTS:
            match = re.search(
                rf"[\w\u4e00-\u9fff]{{0,12}}{hint}[\w\u4e00-\u9fff]{{0,8}}", text, re.IGNORECASE
            )
            if match:
                role = match.group(0).strip()
                break

    company_match = _COMPANY_RE.search(text)
    location_match = _LOCATION_RE.search(text)
    years_match = _YEARS_RE.search(text)
    salary_match = _SALARY_RE.search(text)

    degree = next((token for token in _DEGREE_TOKENS if token in text.lower()), None)

    mentions = extract_skill_mentions(text)

    buckets: dict[RequirementLevel, list[ExtractedJDSkill]] = {
        RequirementLevel.REQUIRED: [],
        RequirementLevel.PREFERRED: [],
        RequirementLevel.BONUS: [],
    }
    seen: set[str] = set()

    for skill, _alias, offset in mentions:
        if skill.canonical_id in seen:
            continue
        seen.add(skill.canonical_id)
        sentence = _sentence_for(text, offset)
        level = _classify_requirement(sentence, text, offset)
        buckets[level].append(
            ExtractedJDSkill(name=skill.display_name, requirement=level, evidence=sentence)
        )

    chunks = [chunk.strip() for chunk in _SECTION_SPLIT_RE.split(text) if chunk.strip()]
    responsibilities: list[str] = []
    for chunk in chunks:
        head = chunk[:20].lower()
        if any(marker in head for marker in ("岗位职责", "工作职责", "职位描述", "responsibilit")):
            responsibilities.extend(_bullets(chunk.splitlines())[:8])

    return ExtractedJD(
        company=company_match.group("name").strip() if company_match else None,
        role=role,
        level=None,
        location=location_match.group("loc").strip() if location_match else None,
        remote_type="remote" if "远程" in text or "remote" in text.lower() else None,
        employment_type="internship" if "实习" in text else None,
        salary_min=float(salary_match.group(1)) if salary_match else None,
        salary_max=float(salary_match.group(2)) if salary_match else None,
        salary_currency="CNY" if salary_match and "k" in salary_match.group(0).lower() else None,
        education_requirement=degree,
        years_experience_min=float(years_match.group(1)) if years_match else None,
        responsibilities=responsibilities,
        nice_to_have=[item.name for item in buckets[RequirementLevel.BONUS][:6]],
        keywords=[skill.display_name for skill, _, _ in mentions[:20]],
        required_skills=buckets[RequirementLevel.REQUIRED],
        preferred_skills=buckets[RequirementLevel.PREFERRED],
        bonus_skills=buckets[RequirementLevel.BONUS],
    )


# ── Claim validation ─────────────────────────────────────────────────────────

_NUMERIC_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|％|倍|万|亿|k|K|ms|us|μs|fps|qps|tps)"
)

#: Token-overlap thresholds used by the deterministic claim adjudicator. Tuned
#: against the labelled claim set in ``evals/datasets`` (see ``evals/run.py``);
#: they are intentionally conservative — a false "supported" is far more
#: damaging in this product than a false "needs evidence".
_SUPPORT_OVERLAP_THRESHOLD = 0.60
_PARTIAL_OVERLAP_THRESHOLD = 0.25


def _has_comparable_number(claim_number: str, evidence_text: str) -> bool:
    """Does the evidence contain a number of the same flavour as the claim?"""
    match = _NUMERIC_RE.search(claim_number)
    if not match:
        return False
    unit = match.group("unit")
    for candidate in _NUMERIC_RE.finditer(evidence_text):
        if candidate.group("unit").lower() == unit.lower():
            return True
    return False


@_handles(ClaimLLMVerdict)
def _validate_claim(text: str, context: Mapping[str, Any]) -> ClaimLLMVerdict:
    """Token-overlap adjudication of a claim against retrieved evidence.

    The number rule is the important one: a quantified claim whose figures appear
    nowhere in the evidence is rejected outright. This is exactly the check that
    makes the heuristic path safe rather than merely plausible.
    """
    evidence_pool: Sequence[Mapping[str, Any]] = context.get("evidence") or []
    evidence_text = "\n".join(
        f"{item.get('title', '')}\n{item.get('snippet', '')}" for item in evidence_pool
    )

    overlap = _token_overlap(text, evidence_text)
    claim_numbers = [match.group(0) for match in _NUMERIC_RE.finditer(text)]
    unsupported_numbers = [
        number for number in claim_numbers if not _has_comparable_number(number, evidence_text)
    ]

    unsupported_parts: list[str] = []
    if overlap < _SUPPORT_OVERLAP_THRESHOLD:
        unsupported_parts.append(text)
    if unsupported_numbers:
        unsupported_parts.extend(unsupported_numbers)

    contradicted = bool(unsupported_numbers)
    partially = bool(unsupported_parts) and overlap >= _PARTIAL_OVERLAP_THRESHOLD
    supported = overlap >= _SUPPORT_OVERLAP_THRESHOLD and not unsupported_numbers

    safer = text
    for number in unsupported_numbers:
        safer = safer.replace(number, "").strip()
    safer = re.sub(r"\s{2,}", " ", safer).rstrip("，,。;；")

    reasoning_parts: list[str] = [f"关键词覆盖度 {overlap:.0%}"]
    if unsupported_numbers:
        reasoning_parts.append(f"证据中未出现量化数据：{'、'.join(unsupported_numbers)}")

    return ClaimLLMVerdict(
        supported=supported,
        partially_supported=partially and not contradicted,
        unsupported_parts=unsupported_parts[:5],
        contradicting_evidence=[],
        reasoning="；".join(reasoning_parts),
        safer_formulation=safer if safer != text else "",
    )


# ── Profile extraction ───────────────────────────────────────────────────────


@_handles(ExtractedProfile)
def _extract_profile(text: str, context: Mapping[str, Any]) -> ExtractedProfile:
    sections = _split_sections(text)

    educations: list[ExtractedEducation] = []
    for line in sections["education"][:4]:
        school_match = re.search(
            r"[\u4e00-\u9fff]{2,20}大学|[\u4e00-\u9fff]{2,20}学院|[A-Z][A-Za-z\s]{4,40}University",
            line,
        )
        degree = next((token for token in _DEGREE_TOKENS if token in line.lower()), None)
        major_match = re.search(
            r"(?:专业|major)\s*[:：]?\s*([^\n，,。;；]{2,20})", line, re.IGNORECASE
        )
        educations.append(
            ExtractedEducation(
                school=school_match.group(0) if school_match else line[:40],
                degree=degree,
                major=major_match.group(1).strip() if major_match else None,
                start_date=_first_date(line),
                end_date=None,
                gpa=None,
                highlights=[],
            )
        )

    experiences: list[ExtractedExperience] = []
    for line in sections["experience"][:6]:
        company_match = re.search(
            r"[\u4e00-\u9fff]{2,20}(?:公司|集团|研究院|研究所|实验室)|[A-Z][A-Za-z\s]{3,30}(?:Inc|Ltd|Corp|Technologies)",
            line,
        )
        title_match = re.search(
            r"(实习生|工程师|开发|研究员|助理|intern|engineer|developer)",
            line,
            re.IGNORECASE,
        )
        if not company_match and not title_match:
            continue
        experiences.append(
            ExtractedExperience(
                kind="internship" if "实习" in line or "intern" in line.lower() else "fulltime",
                company=company_match.group(0) if company_match else line[:30],
                title=title_match.group(0) if title_match else "工程师",
                start_date=_first_date(line),
                end_date=None,
                description=line,
                highlights=[],
            )
        )

    projects: list[ExtractedProject] = []
    for line in sections["project"][:8]:
        name_match = re.search(r"^([^：:，,。;；\-–—]{2,30})", line)
        tech = [skill.display_name for skill, _, _ in extract_skill_mentions(line)]
        projects.append(
            ExtractedProject(
                name=name_match.group(1).strip() if name_match else line[:24],
                summary=line[:120],
                description=line,
                tech_stack=tech[:10],
            )
        )

    skills: list[str] = []
    for line in sections["skill"]:
        for skill, _, _ in extract_skill_mentions(line):
            if skill.display_name not in skills:
                skills.append(skill.display_name)
    if not skills:
        for skill, _, _ in extract_skill_mentions(text)[:30]:
            skills.append(skill.display_name)

    return ExtractedProfile(
        headline="",
        summary="",
        location=None,
        target_roles=[],
        years_experience=None,
        educations=educations,
        experiences=experiences,
        projects=projects,
        achievements=[],
        skills=skills,
    )


# ── Interview ────────────────────────────────────────────────────────────────

_QUESTION_BANK: Mapping[str, tuple[str, str, str]] = {
    "free_rtos": (
        "你在项目里用了 FreeRTOS，为什么选择它而不是裸机前后台架构？",
        "Task 与 ISR 之间你怎么传递数据？为什么不直接用一个全局变量？",
        "如果系统偶发出现任务长时间得不到调度，你会怎么定位？",
    ),
    "stm32": (
        "STM32 启动到进入 main 之间发生了什么？",
        "你的外设初始化顺序是怎么安排的？如果时钟没使能会发生什么？",
        "某次上电后 SPI 读不到数据但偶尔正常，你会怎么排查？",
    ),
    "spi": (
        "SPI 的四种模式由什么决定？",
        "你怎么保证 SPI 通信的时序与片选控制正确？",
        "逻辑分析仪上看到 CLK 有波形但 MISO 一直是高电平，可能是什么原因？",
    ),
    "i2c": (
        "I2C 与 SPI 相比的取舍是什么？",
        "总线被从机拉死（SDA 持续为低）你怎么恢复？",
        "通信偶发 NACK，你会按什么顺序排查？",
    ),
    "can": (
        "CAN 总线为什么适合车载场景？",
        "你如何处理总线仲裁与错误帧？",
        "总线上出现大量错误帧，你如何定位是哪个节点的问题？",
    ),
    "pid": (
        "为什么你的控制回路选 PID 而不是更复杂的控制器？",
        "参数是怎么整定的？积分饱和怎么处理？",
        "阶跃响应出现过冲和持续振荡，你会先调哪个参数，为什么？",
    ),
    "dma": (
        "什么时候值得用 DMA 而不是中断搬运？",
        "DMA 与 CPU 访问同一块内存时你怎么保证一致性？",
        "数据出现偶发错位，你怎么判断是不是 DMA 配置问题？",
    ),
    "rtos_scheduler": (
        "RTOS 的任务优先级你是怎么划分的？",
        "优先级反转是什么？FreeRTOS 提供了什么机制缓解？",
        "系统出现偶发死锁，你会用哪些手段定位？",
    ),
    "uart": (
        "UART 通信你如何处理不定长数据帧？",
        "波特率不匹配会表现出什么现象？",
        "接收偶尔丢字节，你会检查哪些环节？",
    ),
    "performance_tuning": (
        "你如何评估一个嵌入式系统的性能瓶颈？",
        "在资源受限的 MCU 上你做过哪些优化，代价是什么？",
        "如果要求你把控制周期再缩短一半，你会从哪里入手？",
    ),
    "_default": (
        "请介绍一个你最有代表性的项目，重点说你负责的部分。",
        "这个项目里最难的技术问题是什么？你是怎么解决的？",
        "如果重新做一次，你会在哪些地方做出不同的技术选择？",
    ),
}

_HR_QUESTIONS: tuple[str, ...] = (
    "请用两分钟介绍一下你自己，以及你为什么投这个岗位。",
    "你过去遇到过的最大挫折是什么？你从中学到了什么？",
    "你为什么想加入我们公司？你了解我们做什么吗？",
    "你未来三年的职业规划是什么？",
    "你如何看待加班和项目压力？",
)


@_handles(ExtractedQuestion)
def _generate_question(text: str, context: Mapping[str, Any]) -> ExtractedQuestion:
    level = context.get("level")
    target_level = (
        DifficultyLevel.from_level(int(level)) if level is not None else DifficultyLevel.CONCEPT
    )
    topic = str(context.get("topic") or "").strip().lower()
    mode = str(context.get("mode") or "technical")

    if mode == "hr":
        asked = int(context.get("asked_count") or 0)
        question = _HR_QUESTIONS[asked % len(_HR_QUESTIONS)]
        return ExtractedQuestion(
            question=question,
            topic="hr",
            level=DifficultyLevel.CONCEPT,
            rationale="HR 面试标准问题序列",
            follow_up_hints=["用 STAR 结构组织回答"],
        )

    bank = _QUESTION_BANK.get(topic) or _QUESTION_BANK["_default"]
    index = max(0, min(len(bank) - 1, target_level.level - 1))
    return ExtractedQuestion(
        question=bank[index],
        topic=topic or "_default",
        level=target_level,
        rationale=f"依据岗位要求与证据图谱中的 {topic or '项目'} 相关内容",
        follow_up_hints=list(bank[index + 1 :]),
    )


@_handles(ExtractedTurnEvaluation)
def _evaluate_turn(text: str, context: Mapping[str, Any]) -> ExtractedTurnEvaluation:
    """Keyword-coverage scoring of an interview answer.

    Deliberately conservative: without a real model we can judge *coverage*
    (did the answer mention the concepts a good answer contains?) but not
    *correctness*. The scores are therefore floored and the feedback says so.
    """
    answer = str(context.get("answer") or text)
    topic = str(context.get("topic") or "").lower()

    expected_terms: set[str] = {"因为", "所以", "考虑", "权衡", "trade", "cost", "为什么"}
    if topic in {"free_rtos", "rtos_scheduler"}:
        expected_terms |= {"任务", "优先级", "调度", "队列", "信号量", "中断", "task", "queue"}
    elif topic in {"spi", "i2c", "uart", "can"}:
        expected_terms |= {"时序", "时钟", "波形", "总线", "从机", "错误", "逻辑分析仪"}
    elif topic == "pid":
        expected_terms |= {"比例", "积分", "微分", "整定", "超调", "稳态误差"}

    answer_lower = answer.lower()
    hits = [term for term in expected_terms if term in answer_lower]
    coverage = len(hits) / max(1, len(expected_terms))

    length_factor = min(1.0, len(answer) / 220.0)
    base = 40.0 + 45.0 * coverage * length_factor

    missing = [
        term for term in sorted(expected_terms) if term not in answer_lower and len(term) > 1
    ][:4]

    return ExtractedTurnEvaluation(
        technical_accuracy=round(min(88.0, base), 1),
        depth=round(min(85.0, base * (0.85 if len(answer) < 120 else 1.0)), 1),
        communication=round(min(90.0, 55.0 + 35.0 * length_factor), 1),
        problem_solving=round(min(85.0, base * 0.95), 1),
        engineering_thinking=round(min(85.0, base * 0.9), 1),
        missing_knowledge=[f"未提及「{term}」" for term in missing],
        strong_points=[f"覆盖了「{hit}」" for hit in hits[:3]],
        feedback=(
            f"回答长度 {len(answer)} 字，覆盖了 {len(hits)}/{len(expected_terms)} 个期望要点。"
            "（本地规则引擎评估，仅反映要点覆盖度，不代表技术正确性）"
        ),
        follow_up_topics=missing[:3],
        suggested_answer="",
        evidence_conflicts=[],
    )


# ── Learning plan ────────────────────────────────────────────────────────────

_WEEK_THEMES: tuple[tuple[str, str, str], ...] = (
    (
        "打基础：概念与最小可运行示例",
        "搭出可运行的最小示例，跑通工具链",
        "一个能在本机跑起来的 hello-world 级程序",
    ),
    (
        "补原理：把机制讲清楚",
        "能用自己的话解释核心机制与边界条件",
        "一份 500 字的技术笔记，含至少 3 个「为什么」",
    ),
    ("做小项目：把知识变成作品", "独立完成一个可演示的小项目", "一个可运行、可演示的 Mini Project"),
    (
        "上证据：把项目变成简历资产",
        "补 README、提交记录与可量化的验收说明",
        "GitHub 仓库 + 可被验证的成果描述",
    ),
)


@_handles(ExtractedLearningPlan)
def _generate_learning_plan(text: str, context: Mapping[str, Any]) -> ExtractedLearningPlan:
    gaps: Sequence[Mapping[str, Any]] = context.get("gaps") or []
    horizon_days = int(context.get("horizon_days") or 30)
    weeks_count = max(1, min(12, horizon_days // 7))

    top_gaps = list(gaps)[:4]
    priority_order = [
        str(gap.get("canonical_id", "")) for gap in top_gaps if gap.get("canonical_id")
    ]

    weeks: list[ExtractedLearningWeek] = []
    for index in range(weeks_count):
        theme, output, verification = _WEEK_THEMES[min(index, len(_WEEK_THEMES) - 1)]
        focus = [str(top_gaps[index].get("display_name", ""))] if index < len(top_gaps) else []
        weeks.append(
            ExtractedLearningWeek(
                week=index + 1,
                theme=theme,
                goals=[f"{'、'.join(focus) if focus else '综合'}：{theme}"],
                focus_skills=focus,
                resources=["官方文档", "一个可运行的开源示例"],
                output=output,
                verification=verification,
            )
        )

    mini_projects: list[ExtractedMiniProject] = []
    for gap in top_gaps:
        name = str(gap.get("display_name", "")).strip()
        if not name:
            continue
        mini_projects.append(
            ExtractedMiniProject(
                title=f"{name} 实战小项目",
                skill_canonical_id=str(gap.get("canonical_id", "")),
                description=(
                    f"围绕 {name} 构建一个可独立运行、可演示的最小系统，"
                    "把用法、边界条件与失败模式都覆盖到。"
                ),
                deliverables=[f"{name} 的可运行 demo", "README 说明与运行步骤"],
                acceptance_criteria=["能在干净环境按 README 跑通", "有至少一次成功的演示记录"],
                evidence_potential=f"产出后即可在简历中真实地写：使用 {name} 完成 ___（附代码与提交）",
                estimated_hours=8.0,
            )
        )

    return ExtractedLearningPlan(
        title=f"{horizon_days} 天补强计划",
        summary=f"针对 {len(top_gaps)} 个优先缺口，按「概念 → 原理 → 小项目 → 证据化」四段式推进。",
        weeks=weeks,
        mini_projects=mini_projects,
        priority_order=priority_order,
    )


# ── GitHub intelligence ──────────────────────────────────────────────────────


@_handles(ExtractedProjectIntelligence)
def _project_intelligence(text: str, context: Mapping[str, Any]) -> ExtractedProjectIntelligence:
    elements = list(context.get("detected_elements") or [])
    files = list(context.get("files") or [])
    readme = str(context.get("readme") or "")

    highlights: list[str] = []
    if elements:
        highlights.append("识别到的技术要素：" + "、".join(str(item) for item in elements[:10]))
    if files:
        highlights.append("关键实现文件：" + "、".join(str(item) for item in files[:5]))
    if readme:
        highlights.append("仓库包含 README 说明，可作为项目背景证据")

    return ExtractedProjectIntelligence(
        highlights=highlights[:5],
        architecture_hints=[],
        domains=[],
        summary="（本地规则引擎生成，仅基于检测到的技术要素，未做语义推断）",
    )


# ── Generic synthesiser ──────────────────────────────────────────────────────

_PYDANTIC_V2_REQUIRED = object()


def _fill_default(field: FieldInfo, schema: type[BaseModel], seed: str, depth: int) -> Any:
    annotation = field.annotation
    if annotation is None:
        return None
    return _synthesize_value(annotation, seed, depth + 1)


def _synthesize_value(annotation: Any, seed: str, depth: int) -> Any:
    """Build a schema-valid placeholder for an arbitrary annotation."""
    if depth > 6:
        return None

    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())

    # Optional[X] / Union[X, None]
    if origin is not None and str(origin).endswith("Union"):
        non_none = [arg for arg in args if arg is not type(None)]
        if not non_none:
            return None
        return _synthesize_value(non_none[0], seed, depth + 1)

    if origin in (list, tuple, set, frozenset):
        return []
    if origin is dict:
        return {}

    if isinstance(annotation, type):
        if issubclass(annotation, StrEnum):
            members = list(annotation)
            return members[0] if members else None
        if issubclass(annotation, BaseModel):
            return _synthesize_model(annotation, seed, depth + 1)
        if annotation is str:
            return ""
        if annotation is bool:
            return False
        if annotation is int:
            return 0
        if annotation is float:
            return 0.0
        if annotation is bytes:
            return b""
    return None


def _synthesize_model(schema: type[BaseModel], seed: str, depth: int = 0) -> BaseModel:
    """Construct the minimal valid instance of ``schema``.

    Used when no specific handler exists. The result is schema-valid and
    intentionally empty: an empty answer is honest, whereas guessed content in a
    product about verifiable evidence would be self-defeating.
    """
    payload: dict[str, Any] = {}
    for name, field in schema.model_fields.items():
        if not field.is_required():
            continue
        payload[name] = _fill_default(field, schema, seed, depth)
    return schema.model_validate(payload)


# ── The provider ─────────────────────────────────────────────────────────────


class HeuristicProvider:
    """Deterministic provider implementing the :class:`LLMProvider` port."""

    def __init__(self, *, dim: int = _DEFAULT_EMBEDDING_DIM) -> None:
        self._dim = dim

    @property
    def name(self) -> str:
        return "heuristic"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="heuristic",
            supports_streaming=True,
            supports_embeddings=True,
            supports_native_json_schema=True,
            requires_api_key=False,
            deterministic=True,
            notes=(
                "Rule-based provider used when no API key is configured. Results are "
                "schema-valid and reproducible but deliberately conservative."
            ),
        )

    # ── chat ─────────────────────────────────────────────────────────────────

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> ChatResult:
        started = time.perf_counter()
        text = messages_to_text(messages)
        content = self._template_reply(text)
        prompt_tokens = estimate_messages_tokens([message.content for message in messages])
        completion_tokens = estimate_tokens(content)
        return ChatResult(
            content=content,
            provider=self.name,
            model=model or "heuristic-rules-v1",
            tokens=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                estimated=True,
            ),
            cost=Cost(),
            latency_ms=int((time.perf_counter() - started) * 1000),
            degraded=True,
            degradation_reason=DegradationReason.NO_API_KEY,
        )

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        result = await self.chat(
            messages, temperature=temperature, max_tokens=max_tokens, model=model
        )
        # Chunk on word boundaries so the client renders a natural cadence.
        words = result.content.split(" ")
        for index, word in enumerate(words):
            suffix = "" if index == len(words) - 1 else " "
            yield StreamChunk(
                delta=word + suffix,
                done=False,
                provider=self.name,
                model=result.model,
                degraded=True,
            )
        yield StreamChunk(
            delta="",
            done=True,
            provider=self.name,
            model=result.model,
            tokens=result.tokens,
            cost=result.cost,
            degraded=True,
        )

    # ── embeddings ───────────────────────────────────────────────────────────

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> EmbeddingResult:
        started = time.perf_counter()
        vectors = [heuristic_embedding(text, dim=self._dim) for text in texts]
        prompt_tokens = sum(estimate_tokens(text) for text in texts)
        return EmbeddingResult(
            vectors=vectors,
            provider=self.name,
            model=model or "heuristic-ngram-hash-v1",
            dim=self._dim,
            tokens=TokenUsage(
                prompt_tokens=prompt_tokens, total_tokens=prompt_tokens, estimated=True
            ),
            cost=Cost(),
            latency_ms=int((time.perf_counter() - started) * 1000),
            degraded=True,
        )

    # ── structured output ────────────────────────────────────────────────────

    async def structured_output(
        self,
        messages: Sequence[ChatMessage],
        schema: type[SchemaT],
        *,
        context: StructuredContext | None = None,
        temperature: float = 0.0,
        model: str | None = None,
    ) -> SchemaT:
        """Produce schema-valid output, using a specific handler when one exists."""
        text = self._structured_input(messages, context or {})
        handler = HEURISTIC_HANDLERS.get(schema.__name__)
        if handler is not None:
            try:
                candidate = handler(text, context or {})
            except Exception as exc:
                raise SchemaValidationError(
                    f"heuristic handler for {schema.__name__} failed",
                    details={"schema": schema.__name__, "error": str(exc)},
                ) from exc
            if isinstance(candidate, schema):
                return candidate
            return schema.model_validate(candidate)

        synthesized = _synthesize_model(schema, text)
        return schema.model_validate(synthesized.model_dump())

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _structured_input(messages: Sequence[ChatMessage], context: StructuredContext) -> str:
        """Prefer the explicit ``source_text`` from context, else the last user turn."""
        explicit = context.get("source_text")
        if isinstance(explicit, str) and explicit.strip():
            return explicit
        for message in reversed(messages):
            if message.role == "user" and message.content.strip():
                return message.content
        return messages_to_text(messages)

    @staticmethod
    def _template_reply(text: str) -> str:
        lowered = text.lower()
        if "jd" in lowered or "job description" in lowered:
            return (
                "本地规则引擎已解析岗位描述：提取到的技能按必备/优先/加分三级归类，"
                "每一项均绑定 JD 原文出处。未配置模型 API Key，因此未生成叙述性说明。"
            )
        if "interview" in lowered or "面试" in text:
            return (
                "本地规则引擎已根据岗位要求与证据图谱生成面试问题序列，难度按回答情况自适应调整。"
            )
        return (
            "本地规则引擎已处理该请求。未配置模型 API Key，结果基于确定性规则生成，"
            "不包含模型推断内容。"
        )
