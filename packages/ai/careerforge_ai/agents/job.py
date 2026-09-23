"""JobAgent — job description → structured, normalised analysis (WF-03).

Two decisions shape this agent.

**Normalisation happens after extraction, never during it.** The model is asked to
find what the JD says; a deterministic taxonomy decides what those mentions *are*.
Letting the model emit canonical ids would invite it to map "熟悉 RTOS" onto
whichever RTOS it prefers, and every downstream score inherits that guess.

**Parse quality is reported, not hidden.** ``parse_confidence`` combines three
things the caller can act on — how many skills the taxonomy could resolve, whether
a role was found, whether a company was found — and a JD that resolves poorly is
marked for review instead of silently producing a thin skill tree.
"""

from __future__ import annotations

from typing import Any

from careerforge_ai.agents.base import (
    AgentOutcome,
    merge_workflow_warnings,
    normalise_whitespace,
    render_bullets,
    strip_markup,
    truncate_for_prompt,
)
from careerforge_ai.orchestrator import RunContext, Step, Workflow, WorkflowExecutor
from careerforge_ai.parsing.skill_taxonomy import SKILLS, normalize_skill
from careerforge_ai.schemas.common import RequirementLevel
from careerforge_ai.schemas.job import ExtractedJD, JDAnalysis, JDSkill

__all__ = ["JOB_AGENT", "JobAgent", "build_workflow", "build_jd_analysis"]

JOB_AGENT = "job"

#: Component weights of ``parse_confidence``. Skills dominate because a JD with a
#: correct skill set and a missing company name is still useful; the reverse is not.
_CONFIDENCE_WEIGHTS: dict[str, float] = {
    "skill_resolution": 0.60,
    "role_found": 0.25,
    "company_found": 0.15,
}

#: Below this, the analysis is flagged so the UI can offer a review step.
_LOW_CONFIDENCE_THRESHOLD = 0.55

_KNOWN_SKILLS_HINT = ", ".join(skill.display_name for skill in SKILLS)


def build_workflow() -> Workflow:
    """The WF-03 graph: clean → extract → normalise → assess."""
    return Workflow(
        name="jd_analysis",
        agent=JOB_AGENT,
        trigger="api",
        description="Parse a job description into a structured, taxonomy-normalised analysis",
        steps=(
            Step(
                name="clean",
                fn=_clean,
                agent=JOB_AGENT,
                description="Strip markup and normalise whitespace deterministically",
            ),
            Step(
                name="extract",
                fn=_extract,
                depends_on=("clean",),
                agent=JOB_AGENT,
                description="Structured extraction bounded by the ExtractedJD schema",
            ),
            Step(
                name="normalise",
                fn=_normalise,
                depends_on=("extract",),
                agent=JOB_AGENT,
                description="Resolve skill mentions against the taxonomy",
            ),
            Step(
                name="assess",
                fn=_assess,
                # Needs the extracted fields (company, role, salary) and the clean
                # step's truncation flag, not only the normalised skills.
                depends_on=("clean", "extract", "normalise"),
                agent=JOB_AGENT,
                description="Assemble the analysis and score parse quality",
            ),
        ),
    )


# ── steps ────────────────────────────────────────────────────────────────────


async def _clean(context: RunContext, inputs: dict[str, Any]) -> dict[str, Any]:
    raw = str(inputs.get("__text__") or context.metadata.get("jd_text") or "")
    text = normalise_whitespace(strip_markup(raw))
    truncated_text, truncated = truncate_for_prompt(text)
    if truncated:
        context.metadata.setdefault("warnings", []).append(
            "JD 文本过长，仅前 70% 与后 30% 参与解析"
        )
    return {"text": truncated_text, "original_length": len(raw), "truncated": truncated}


async def _extract(context: RunContext, inputs: dict[str, Any]) -> ExtractedJD:
    text = str(inputs["clean"]["text"])
    return await context.structured(
        "jd_analysis",
        ExtractedJD,
        context={"source_text": text},
        jd_text=text,
        known_skills=_KNOWN_SKILLS_HINT,
        locale="zh-CN",
    )


async def _normalise(context: RunContext, inputs: dict[str, Any]) -> dict[str, Any]:
    extracted: ExtractedJD = inputs["extract"]
    unmapped: list[str] = []
    resolved = 0
    total = 0

    def to_jd_skill(name: str, requirement: RequirementLevel, evidence: str) -> JDSkill:
        nonlocal resolved, total
        total += 1
        skill = normalize_skill(name)
        if skill is None:
            unmapped.append(name)
        else:
            resolved += 1
        return JDSkill(
            canonical_id=skill.canonical_id if skill else None,
            raw_text=name,
            requirement=requirement,
            weight=requirement.weight,
            jd_evidence=evidence,
        )

    required = [
        to_jd_skill(item.name, RequirementLevel.REQUIRED, item.evidence)
        for item in extracted.required_skills
    ]
    preferred = [
        to_jd_skill(item.name, RequirementLevel.PREFERRED, item.evidence)
        for item in extracted.preferred_skills
    ]
    bonus = [
        to_jd_skill(item.name, RequirementLevel.BONUS, item.evidence)
        for item in extracted.bonus_skills
    ]

    if unmapped:
        context.metadata.setdefault("warnings", []).append(
            f"{len(unmapped)} 个技能未能在分类学中归一化：{'、'.join(unmapped[:5])}"
        )

    return {
        "required": required,
        "preferred": preferred,
        "bonus": bonus,
        "resolution_rate": (resolved / total) if total else 0.0,
        "unmapped": unmapped,
        "total": total,
    }


async def _assess(context: RunContext, inputs: dict[str, Any]) -> JDAnalysis:
    extracted: ExtractedJD = inputs["extract"]
    normalised = inputs["normalise"]

    components = {
        "skill_resolution": float(normalised["resolution_rate"]) if normalised["total"] else 0.0,
        "role_found": 1.0 if extracted.role.strip() else 0.0,
        "company_found": 1.0 if (extracted.company or "").strip() else 0.0,
    }
    confidence = sum(components[key] * weight for key, weight in _CONFIDENCE_WEIGHTS.items())

    warnings: list[str] = list(context.metadata.get("warnings", []))
    if normalised["total"] == 0:
        parse_status = "heuristic_fallback"
        warnings.append("未能从 JD 中提取到任何技能，请确认文本内容完整")
    elif confidence < _LOW_CONFIDENCE_THRESHOLD:
        parse_status = "heuristic_fallback"
        warnings.append("解析置信度偏低，建议人工核对技能树")
    else:
        parse_status = "parsed"

    context.metadata["warnings"] = warnings
    context.metadata["input_ref"] = {
        "role": extracted.role,
        "skill_count": normalised["total"],
        "truncated": bool(inputs["clean"]["truncated"]),
    }
    context.metadata["output_ref"] = {
        "required": len(normalised["required"]),
        "preferred": len(normalised["preferred"]),
        "bonus": len(normalised["bonus"]),
    }

    return JDAnalysis(
        company=extracted.company,
        role=extracted.role,
        level=extracted.level,
        location=extracted.location,
        remote_type=extracted.remote_type,
        employment_type=extracted.employment_type,
        salary_min=extracted.salary_min,
        salary_max=extracted.salary_max,
        salary_currency=extracted.salary_currency,
        education_requirement=extracted.education_requirement,
        years_experience_min=extracted.years_experience_min,
        responsibilities=list(extracted.responsibilities),
        nice_to_have=list(extracted.nice_to_have),
        keywords=list(extracted.keywords),
        required_skills=normalised["required"],
        preferred_skills=normalised["preferred"],
        bonus_skills=normalised["bonus"],
        parse_confidence=round(confidence, 4),
        parse_status=parse_status,
        degraded=context.degraded,
    )


# ── agent ────────────────────────────────────────────────────────────────────


class JobAgent:
    """Parses job descriptions. Stateless; all dependencies arrive via RunContext."""

    name = JOB_AGENT

    def workflow(self) -> Workflow:
        return build_workflow()

    async def run(
        self, executor: WorkflowExecutor, *, text: str, metadata: dict[str, Any] | None = None
    ) -> AgentOutcome:
        merged_metadata = {"jd_text": text, **(metadata or {})}
        output = await executor.run(self.workflow(), trigger="api", metadata=merged_metadata)
        analysis: JDAnalysis | None = output.get("assess")
        warnings = merge_workflow_warnings(output)
        warnings.extend(str(item) for item in output.metadata.get("warnings", []))

        return AgentOutcome(
            value=analysis,
            record=output.record,
            degraded=output.degraded,
            degradation_reason=output.degradation_reason,
            warnings=warnings,
        )


async def build_jd_analysis(
    executor: WorkflowExecutor, text: str
) -> tuple[JDAnalysis | None, AgentOutcome]:
    """Convenience wrapper: parse a JD and hand back both the analysis and trace."""
    outcome = await JobAgent().run(executor, text=text)
    return outcome.value, outcome


def describe_contract() -> dict[str, Any]:
    """Serialisable description used by ``GET /system/info`` and the docs."""
    return {
        "agent": JOB_AGENT,
        "workflow": "jd_analysis",
        "steps": ["clean", "extract", "normalise", "assess"],
        "prompt": "jd_analysis@v1",
        "output": "JDAnalysis",
        "confidence_weights": dict(_CONFIDENCE_WEIGHTS),
        "low_confidence_threshold": _LOW_CONFIDENCE_THRESHOLD,
        "known_skills_hint_preview": render_bullets([_KNOWN_SKILLS_HINT[:120]]),
    }
