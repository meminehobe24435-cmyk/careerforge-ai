"""Evaluation suites.

Each suite measures one capability of the product against a labelled dataset and returns a
:class:`~evals.report.SuiteOutcome`. The runner owns the CLI and the artefacts; the measurement
lives here so a metric can be read (and unit-reasoned about) without wading through argument
parsing.

Split out of a single ``evals/suites.py`` when that file reached 484 lines, and split by
capability rather than by size: the four suites import different parts of the core (JD parsing,
the claim gate, the retriever, the interview planner), and one module importing all four made it
impossible to see which suite depended on what.

A suite never reimplements the thing it measures. It calls the same functions the API calls, with
the same configured provider, so a number that moves here moved in production too.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from careerforge_ai.parsing.skill_taxonomy import normalize_skill
from careerforge_ai.providers.base import LLMProvider
from evals.report import SuiteOutcome

__all__ = [
    "DATASET_FOR_SUITE",
    "SUITES",
    "SuiteCallable",
    "canonical_skill",
    "dataset_for",
]

SuiteCallable = Callable[[LLMProvider, list[dict[str, Any]]], Awaitable[SuiteOutcome]]


def canonical_skill(name: str) -> str | None:
    """Normalise an extracted skill name the same way the service layer does.

    Shared by every suite that compares skills, so "the same normalisation the product uses" is
    one function rather than a claim repeated in four places.
    """
    skill = normalize_skill(name)
    return skill.canonical_id if skill else None


def dataset_for(suite_name: str) -> str:
    """Dataset file stem used by a suite."""
    return DATASET_FOR_SUITE[suite_name]


def _registry() -> tuple[dict[str, SuiteCallable], dict[str, str]]:
    # Imported inside the function so that importing one suite does not drag in the others'
    # dependencies (the interview suite builds schemas the JD suite never touches).
    from evals.suites.evidence_validation import (
        SUITE_NAME as EVIDENCE_NAME,
        suite_evidence_validation,
    )
    from evals.suites.interview_relevance import (
        SUITE_NAME as INTERVIEW_NAME,
        suite_interview_relevance,
    )
    from evals.suites.jd_extraction import SUITE_NAME as JD_NAME, suite_jd_extraction
    from evals.suites.rag_retrieval import SUITE_NAME as RAG_NAME, suite_rag_retrieval

    suites: dict[str, SuiteCallable] = {
        JD_NAME: suite_jd_extraction,
        EVIDENCE_NAME: suite_evidence_validation,
        RAG_NAME: suite_rag_retrieval,
        INTERVIEW_NAME: suite_interview_relevance,
    }
    datasets = {
        JD_NAME: "jd_extraction",
        EVIDENCE_NAME: "evidence_validation",
        RAG_NAME: "rag_retrieval",
        INTERVIEW_NAME: "interview_relevance",
    }
    return suites, datasets


SUITES, DATASET_FOR_SUITE = _registry()
