"""Is a claimed technology present in the candidate's material? — asked with the taxonomy.

Why this is its own module
--------------------------
``skill_not_in_graph`` used to be decided by set arithmetic on latin "technical tokens": a claim
asserting ``I2C`` with no evidence mentioning ``i2c`` produced a warning. That is *nearly* right and
dangerously wrong in one direction, because the extractor sees spellings, not skills:

* ``K8s`` and ``Kubernetes`` are the same skill and two different tokens;
* ``实时操作系统`` and ``FreeRTOS`` are the same skill and two different scripts;
* ``torch`` and ``PyTorch``, ``pg`` and ``PostgreSQL``, ``微服务`` and ``Microservices`` — the
  taxonomy in :mod:`careerforge_ai.parsing.skill_taxonomy` already knows all of them, and it is the
  one place in this codebase where a synonym is *declared* rather than guessed.

So the question "is this technology in the material" is answered in two steps, and the second step
only runs when the taxonomy can answer it confidently:

1. **Normalise.** Every skill the taxonomy recognises in the claim, and every skill it recognises in
   the material — through display names *and* aliases.
2. **Compare skills, not spellings.** A canonical id claimed and absent from the material's id set is
   a *confirmed* absence, whatever spelling either side used.

The third case is the one that decides whether this may block a claim: a technical token that the
taxonomy does **not** know (``Azure Pipelines``, ``RRF``, ``逻辑分析仪``) cannot be normalised, so
"the material never says ``azure pipelines``" is a statement about the tokeniser, not about the
candidate. Those stay warnings. ``docs/QUALITY.md`` §7.4 records the same reasoning: an honest claim
wrongly hard-rejected is a worse failure than a soft verdict.

None of this is a hardcoded skill list: the taxonomy is the list, and the routine is generic over it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from careerforge_ai.parsing.skill_taxonomy import extract_skill_mentions, normalize_skill
from careerforge_ai.parsing.tokenize import technical_tokens
from careerforge_ai.schemas.common import SkillCategory

__all__ = [
    "BLOCKING_CATEGORIES",
    "SkillPresence",
    "claimed_skills",
    "confirmed_absent_skills",
    "evidence_skills",
    "presence_of",
]

#: The skill categories a *missing* one may hard-reject a claim.
#:
#: Every category here names something a reader would call a technology: a language, a chip, a
#: protocol, a framework, a database, a service, a tool. The two excluded categories are the ones
#: the audit in ``packages/ai/tests/test_skill_presence.py`` found to be unsafe:
#:
#: * ``SOFT`` — ``problem_solving`` is the taxonomy entry behind the alias 故障排查, and 排查 appears
#:   in ordinary prose about maintenance. A claim reading "负责线上服务的日常维护与问题排查" has
#:   nothing technological to be missing, so refusing it would be a false positive with a
#:   plausible-looking reason;
#: * ``DOMAIN`` — ``system_design`` is the entry behind 架构设计 and 设计, and "设计并实现了电机控制的
#:   PID 闭环" would be *blocked* by it while its evidence is sitting right there. The taxonomy maps
#:   these words because they are useful for retrieval and gap analysis, where a near miss is cheap.
#:   A blocker needs the opposite error profile.
#:
#: This is a restriction discovered by measurement, not a preference: with both categories allowed,
#: the blocker fired on 17 of the 60 evaluation cases instead of 13, and the extra three were the
#: audit's own counterexamples.
BLOCKING_CATEGORIES: frozenset[SkillCategory] = frozenset(
    {
        SkillCategory.LANGUAGE,
        SkillCategory.FRAMEWORK,
        SkillCategory.EMBEDDED,
        SkillCategory.BACKEND,
        SkillCategory.FRONTEND,
        SkillCategory.AI,
        SkillCategory.DEVOPS,
        SkillCategory.DATABASE,
        SkillCategory.TOOL,
    }
)


def claimed_skills(text: str) -> dict[str, str]:
    """Canonical id → the alias the claim used, for every taxonomy skill ``text`` names."""
    return {
        skill.canonical_id: alias for skill, alias, _ in extract_skill_mentions(text, dedupe=True)
    }


def evidence_skills(text: str) -> set[str]:
    """Canonical ids present anywhere in the material.

    Aliases and equivalents are both covered, because the comparison happens on the canonical id:
    ``K8s`` in the material satisfies a claim about ``Kubernetes``, and ``实时操作系统`` satisfies one
    about ``FreeRTOS`` — provided the taxonomy links them, which is the only evidence of equivalence
    this codebase is willing to accept.
    """
    return {skill.canonical_id for skill, _, _ in extract_skill_mentions(text, dedupe=True)}


def confirmed_absent_skills(claim: str, evidence_text: str) -> dict[str, str]:
    """Claimed skills whose canonical id appears nowhere in the material.

    The returned mapping is ``canonical_id → the alias the claim used``, so a reason can quote the
    candidate's own wording while the judgement rests on the normalised skill. Only
    :data:`BLOCKING_CATEGORIES` are considered — see that constant for the measurement that put the
    line where it is.
    """
    present = evidence_skills(evidence_text)
    return {
        skill.canonical_id: alias
        for skill, alias, _ in extract_skill_mentions(claim, dedupe=True)
        if skill.category in BLOCKING_CATEGORIES and skill.canonical_id not in present
    }


def unknown_technical_tokens(claim: str, evidence_text: str, *, known: set[str]) -> set[str]:
    """Technical tokens the material never mentions and the taxonomy cannot normalise.

    ``known`` is the set of tokens already accounted for by a confirmed-absent *skill*; anything left
    is a token whose absence says something about the extractor. Passed in rather than recomputed
    because :func:`presence_of` is the one place that decides which set is which.
    """
    from careerforge_ai.parsing.tokenize import missing_technical_tokens

    return {token for token in missing_technical_tokens(claim, evidence_text) if token not in known}


@dataclass(slots=True)
class SkillPresence:
    """The verdict of the two-step question, with both halves kept.

    Attributes:
        confirmed_absent: claimed skills (canonical id → alias used in the claim) that the material
            does not carry. This is what a blocker may rest on.
        unconfirmed_tokens: technical tokens the material does not carry *and* the taxonomy does not
            know. Reported as a warning, never as a blocker.
        reason_rule: the token that a reader should see named in the reason — a confirmed skill when
            there is one, otherwise the first unconfirmed token.
    """

    confirmed_absent: dict[str, str] = field(default_factory=dict)
    unconfirmed_tokens: set[str] = field(default_factory=set)

    @property
    def any(self) -> bool:
        return bool(self.confirmed_absent or self.unconfirmed_tokens)

    @property
    def blocked(self) -> bool:
        """Whether this is strong enough to make the claim unsupported.

        Only a *normalised* absence counts. The product's documented rule is that a technology
        nothing mentions makes a claim unsupported; the qualification this adds is that "nothing
        mentions it" has to be established by the vocabulary that knows the synonyms, not by a
        substring match on two spellings of the same skill.
        """
        return bool(self.confirmed_absent)


def presence_of(claim: str, evidence_text: str) -> SkillPresence:
    """Ask whether the claim's technologies are in the material.

    An empty ``evidence_text`` yields an empty verdict: the caller's contract is that it supplies the
    material, and a misconfigured caller would otherwise have every claim in the product rejected.
    That contract is why ``resume_service.validate`` passes the candidate's evidence *and* why
    ``retrieve_phase`` no longer discards it once retrieval has run.
    """
    if not evidence_text.strip():
        return SkillPresence()
    absent = confirmed_absent_skills(claim, evidence_text)
    present = evidence_skills(evidence_text)
    # Tokens the claim uses for skills that *are* present must not be reported as missing: "K8s" and
    # "Kubernetes" differ as tokens and are one skill, and "Free RTOS" vs "FreeRTOS" is the same
    # story. Without this, a claim and its material could name the same skill twice and still be
    # told the skill is unmentioned.
    already_matched = {
        token
        for token in technical_tokens(claim)
        if (skill := normalize_skill(token)) is not None and skill.canonical_id in present
    }
    return SkillPresence(
        confirmed_absent=absent,
        unconfirmed_tokens=unknown_technical_tokens(
            claim, evidence_text, known=set(already_matched)
        ),
    )


def _normalised_skill_of(token: str) -> str | None:
    skill = normalize_skill(token)
    return skill.canonical_id if skill is not None else None
