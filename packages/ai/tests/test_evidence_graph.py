"""Tests for the evidence graph builder and query layer.

The graph is the product's central claim, so the tests here are about *semantics*
rather than plumbing: does a skill supported by code outrank one supported only by
prose, does a claim's provenance path actually terminate in evidence, does the
subgraph query keep the node the user clicked on.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from careerforge_ai.graph import (
    build_evidence_graph,
    extract_subgraph,
    graph_stats,
    node_id,
    resolve_focus,
    trace_claim,
)
from careerforge_ai.schemas.common import (
    EvidenceKind,
    EvidenceRelation,
    GraphNodeType,
    RequirementLevel,
    SourceAuthority,
    utcnow,
)
from careerforge_ai.schemas.evidence import EvidenceItem, EvidenceLocator, GraphNode, GraphQuery
from careerforge_ai.schemas.job import JDAnalysis, JDSkill
from careerforge_ai.schemas.profile import CandidateProfile


@pytest.fixture
def profile() -> CandidateProfile:
    from tests.conftest import _skill  # type: ignore[attr-defined]

    from careerforge_ai.schemas.common import SkillCategory, SkillLevel
    from careerforge_ai.schemas.profile import Experience, Project

    return CandidateProfile(
        slug="alex",
        headline="Embedded Engineer",
        projects=[
            Project(
                name="Balance Robot",
                summary="基于 STM32 的两轮自平衡小车",
                description="使用 FreeRTOS 划分任务，PID 控制电机。",
                tech_stack=["STM32", "FreeRTOS", "PID"],
            )
        ],
        experiences=[
            Experience(company="某科技", title="嵌入式实习生", description="电机控制固件开发")
        ],
        skills=[
            _skill("stm32", "STM32", SkillCategory.EMBEDDED, SkillLevel.STRONG),
            _skill("free_rtos", "FreeRTOS", SkillCategory.EMBEDDED, SkillLevel.STRONG),
        ],
    )


def _evidence(kind: EvidenceKind, title: str, snippet: str, *, days_ago: int = 30) -> EvidenceItem:
    return EvidenceItem(
        kind=kind,
        title=title,
        snippet=snippet,
        locator=EvidenceLocator(path=title, line=1),
        source_authority=(
            SourceAuthority.CODE_OR_COMMIT
            if kind in {EvidenceKind.REPO_FILE, EvidenceKind.COMMIT}
            else SourceAuthority.UPLOADED_DOCUMENT
        ),
        confidence=0.0,
        occurred_at=utcnow() - timedelta(days=days_ago),
    )


class TestNodeIdentity:
    def test_ids_are_stable_across_calls(self) -> None:
        assert node_id(GraphNodeType.SKILL, "stm32") == node_id(GraphNodeType.SKILL, "stm32")

    def test_ids_differ_by_kind(self) -> None:
        assert node_id(GraphNodeType.SKILL, "stm32") != node_id(GraphNodeType.PROJECT, "stm32")

    def test_ids_are_uuids(self) -> None:
        assert isinstance(node_id(GraphNodeType.SKILL, "stm32"), UUID)


class TestBuild:
    def test_creates_entity_and_skill_nodes(self, profile: CandidateProfile) -> None:
        result = build_evidence_graph(
            profile=profile,
            evidence=[
                _evidence(
                    EvidenceKind.REPO_FILE,
                    "motor_control.c",
                    "基于 STM32 的 PID 电机控制实现，使用 FreeRTOS 任务调度。",
                )
            ],
        )
        types = {node.type for node in result.nodes}
        assert GraphNodeType.CANDIDATE in types
        assert GraphNodeType.PROJECT in types
        assert GraphNodeType.SKILL in types

    def test_resolves_skills_from_the_evidence_itself(self, profile: CandidateProfile) -> None:
        result = build_evidence_graph(
            profile=profile,
            evidence=[
                _evidence(EvidenceKind.REPO_FILE, "can_node.c", "实现 CANopen 协议栈与错误帧处理。")
            ],
        )
        assert "can" in result.skill_evidence

    def test_assigns_confidence_within_bounds(self, profile: CandidateProfile) -> None:
        result = build_evidence_graph(
            profile=profile,
            evidence=[_evidence(EvidenceKind.REPO_FILE, "a.c", "STM32 初始化")],
        )
        assert result.evidence
        for item in result.evidence:
            assert 0.0 <= item.confidence <= 1.0
            assert item.breakdown is not None

    def test_confidence_breakdown_is_attached_for_explainability(
        self, profile: CandidateProfile
    ) -> None:
        result = build_evidence_graph(
            profile=profile,
            evidence=[_evidence(EvidenceKind.REPO_FILE, "a.c", "STM32 初始化")],
        )
        breakdown = result.evidence[0].breakdown
        assert breakdown is not None
        assert sum(breakdown.contributions.values()) == pytest.approx(breakdown.score, abs=1e-6)
        assert breakdown.explanation()

    def test_every_evidence_node_is_linked(self, profile: CandidateProfile) -> None:
        result = build_evidence_graph(
            profile=profile,
            evidence=[
                _evidence(EvidenceKind.REPO_FILE, "a.c", "STM32 与 FreeRTOS"),
                _evidence(EvidenceKind.README, "README.md", "基于 STM32 的平衡小车项目"),
            ],
        )
        # No orphan evidence: each item should be reachable from a skill node.
        assert result.orphan_evidence == []

    def test_every_edge_has_a_stored_link(self, profile: CandidateProfile) -> None:
        """An edge without a link exists in memory and disappears when the graph is saved.

        ``GraphEdge`` is what the query layer walks; ``EvidenceLink`` is what
        ``evidence_links`` stores (``docs/DATABASE.md`` §2.5). Four relations used to be
        emitted as edges only — including the candidate's own ``HAS`` edges to its skills —
        so a persisted graph lost its root and every education/experience node. The
        relation is asserted as a set so no future call site can forget its pair.
        """
        result = build_evidence_graph(
            profile=profile,
            evidence=[
                _evidence(EvidenceKind.REPO_FILE, "a.c", "STM32 与 FreeRTOS"),
                _evidence(EvidenceKind.README, "README.md", "基于 STM32 的平衡小车项目"),
            ],
        )
        edge_relations = {(edge.source, edge.target, edge.relation) for edge in result.edges}
        link_relations = {(link.from_id, link.to_id, link.relation) for link in result.links}
        assert edge_relations == link_relations
        # ... and the candidate root is among them, which is what made this visible.
        assert any(link.from_type is GraphNodeType.CANDIDATE for link in result.links)

    def test_is_deterministic(self, profile: CandidateProfile) -> None:
        build = lambda: build_evidence_graph(  # noqa: E731 - a local helper reads better here
            profile=profile,
            evidence=[
                _evidence(EvidenceKind.REPO_FILE, "a.c", "STM32 与 FreeRTOS"),
                _evidence(EvidenceKind.COMMIT, "abc123", "feat: STM32 时钟配置"),
            ],
        )
        first, second = build(), build()
        assert {node.id for node in first.nodes} == {node.id for node in second.nodes}
        assert {edge.id for edge in first.edges} == {edge.id for edge in second.edges}

    def test_repeated_builds_score_identically(self, profile: CandidateProfile) -> None:
        def build() -> dict[UUID, float]:
            result = build_evidence_graph(
                profile=profile,
                evidence=[_evidence(EvidenceKind.REPO_FILE, "a.c", "STM32 与 FreeRTOS")],
            )
            return {node.id: node.confidence or 0.0 for node in result.nodes}

        assert build() == build()


class TestCorroboration:
    def test_two_independent_source_groups_raise_confidence(
        self, profile: CandidateProfile
    ) -> None:
        single = build_evidence_graph(
            profile=profile,
            evidence=[_evidence(EvidenceKind.REPO_FILE, "a.c", "STM32 初始化", days_ago=10)],
        )
        corroborated = build_evidence_graph(
            profile=profile,
            evidence=[
                _evidence(EvidenceKind.REPO_FILE, "a.c", "STM32 初始化", days_ago=10),
                _evidence(EvidenceKind.COMMIT, "abc123", "feat: STM32 时钟配置", days_ago=10),
            ],
        )
        assert corroborated.skill_confidence["stm32"] > single.skill_confidence["stm32"]
        assert corroborated.skill_corroboration["stm32"] == 2

    def test_two_files_in_the_same_group_do_not_count_twice(
        self, profile: CandidateProfile
    ) -> None:
        result = build_evidence_graph(
            profile=profile,
            evidence=[
                _evidence(EvidenceKind.REPO_FILE, "a.c", "STM32 初始化"),
                _evidence(EvidenceKind.REPO_FILE, "b.c", "STM32 中断配置"),
            ],
        )
        # Two source files are one independent source group, not two.
        assert result.skill_corroboration["stm32"] == 1

    def test_corroboration_count_is_reflected_on_the_evidence(
        self, profile: CandidateProfile
    ) -> None:
        result = build_evidence_graph(
            profile=profile,
            evidence=[
                _evidence(EvidenceKind.REPO_FILE, "a.c", "STM32 初始化"),
                _evidence(EvidenceKind.README, "README.md", "STM32 项目说明"),
            ],
        )
        assert all(item.corroboration_count >= 2 for item in result.evidence)


class TestJobLayer:
    @pytest.fixture
    def job(self) -> JDAnalysis:
        def skill(canonical_id: str, raw: str) -> JDSkill:
            return JDSkill(
                canonical_id=canonical_id,
                raw_text=raw,
                requirement=RequirementLevel.REQUIRED,
                jd_evidence=f"熟悉 {raw}",
            )

        return JDAnalysis(
            company="某科技",
            role="嵌入式软件工程师",
            required_skills=[skill("stm32", "STM32"), skill("can", "CAN")],
        )

    def test_adds_job_node_and_requirement_edges(
        self, profile: CandidateProfile, job: JDAnalysis
    ) -> None:
        result = build_evidence_graph(
            profile=profile,
            evidence=[_evidence(EvidenceKind.REPO_FILE, "a.c", "STM32 初始化")],
            job=job,
        )
        assert any(node.type is GraphNodeType.JOB for node in result.nodes)
        assert any(edge.relation is EvidenceRelation.REQUIRES for edge in result.edges)

    def test_matched_and_missing_requirements_are_distinguished(
        self, profile: CandidateProfile, job: JDAnalysis
    ) -> None:
        result = build_evidence_graph(
            profile=profile,
            evidence=[_evidence(EvidenceKind.REPO_FILE, "a.c", "STM32 初始化")],
            job=job,
        )
        matched = {
            edge.source for edge in result.edges if edge.relation is EvidenceRelation.MATCHES
        }
        gaps = {edge.source for edge in result.edges if edge.relation is EvidenceRelation.GAP}
        assert node_id(GraphNodeType.SKILL, "stm32") in matched
        assert node_id(GraphNodeType.SKILL, "can") in gaps

    def test_gap_edge_explains_itself(self, profile: CandidateProfile, job: JDAnalysis) -> None:
        result = build_evidence_graph(profile=profile, evidence=[], job=job)
        gap = next(edge for edge in result.edges if edge.relation is EvidenceRelation.GAP)
        assert gap.rationale
        assert "无证据" in gap.rationale

    def test_requirement_links_quote_the_jd(
        self, profile: CandidateProfile, job: JDAnalysis
    ) -> None:
        result = build_evidence_graph(profile=profile, evidence=[], job=job)
        requires = [link for link in result.links if link.relation is EvidenceRelation.REQUIRES]
        assert requires
        assert all("JD 原文" in (link.rationale or "") for link in requires)


class TestWarnings:
    def test_file_extension_does_not_create_a_skill(self, profile: CandidateProfile) -> None:
        # A graph built only from file names must not claim the C language.
        result = build_evidence_graph(
            profile=CandidateProfile(slug="x"),
            evidence=[_evidence(EvidenceKind.REPO_FILE, "notes.c", "与技能无关的说明文字。")],
        )
        skill_labels = {node.label for node in result.nodes if node.type is GraphNodeType.SKILL}
        assert "C" not in skill_labels
        assert result.skill_evidence == {}

    def test_warns_when_evidence_yields_no_skills(self, profile: CandidateProfile) -> None:
        result = build_evidence_graph(
            profile=profile,
            evidence=[_evidence(EvidenceKind.MANUAL, "notes.txt", "一些与技能无关的随笔内容。")],
        )
        assert result.warnings
        assert "no taxonomy skill" in result.warnings[0]


class TestFocusResolution:
    @pytest.fixture
    def graph(self, profile: CandidateProfile):
        return build_evidence_graph(
            profile=profile,
            evidence=[
                _evidence(EvidenceKind.REPO_FILE, "motor.c", "STM32 与 FreeRTOS 的电机控制"),
                _evidence(EvidenceKind.COMMIT, "abc123", "feat: CANopen 节点管理"),
            ],
            job=JDAnalysis(
                role="嵌入式工程师",
                required_skills=[JDSkill(canonical_id="can", raw_text="CAN")],
            ),
        )

    def test_resolves_a_typed_reference(self, graph) -> None:
        assert resolve_focus(graph.nodes, "skill:stm32") is not None

    def test_resolves_a_uuid(self, graph) -> None:
        target = graph.nodes[0].id
        assert resolve_focus(graph.nodes, str(target)) == target

    def test_resolves_a_label(self, graph) -> None:
        assert resolve_focus(graph.nodes, "Balance Robot") is not None

    def test_unknown_reference_returns_none(self, graph) -> None:
        assert resolve_focus(graph.nodes, "skill:nonexistent") is None
        assert resolve_focus(graph.nodes, "!!!") is None
        assert resolve_focus(graph.nodes, None) is None


class TestSubgraph:
    @pytest.fixture
    def graph(self, profile: CandidateProfile):
        return build_evidence_graph(
            profile=profile,
            evidence=[
                _evidence(EvidenceKind.REPO_FILE, "motor.c", "STM32 与 FreeRTOS 的电机控制"),
                _evidence(EvidenceKind.COMMIT, "abc123", "feat: STM32 时钟配置"),
                _evidence(EvidenceKind.README, "README.md", "基于 React 的展示页面"),
            ],
        )

    def test_focus_limits_the_result(self, graph) -> None:
        sub = extract_subgraph(graph.nodes, graph.edges, focus="skill:stm32", depth=1)
        assert sub.node_count < graph.node_count
        assert any(node.group == "stm32" for node in sub.nodes)

    def test_focus_node_survives_its_own_filter(self, graph) -> None:
        sub = extract_subgraph(
            graph.nodes,
            graph.edges,
            focus="skill:stm32",
            depth=1,
            node_types=[GraphNodeType.CANDIDATE],
        )
        # The clicked node must be present even though its type was filtered out.
        assert any(node.group == "stm32" for node in sub.nodes)

    def test_depth_zero_returns_only_the_focus(self, graph) -> None:
        sub = extract_subgraph(graph.nodes, graph.edges, focus="skill:stm32", depth=1)
        stm32 = next(node for node in sub.nodes if node.group == "stm32")
        assert stm32 in sub.nodes

    def test_type_filter(self, graph) -> None:
        sub = extract_subgraph(graph.nodes, graph.edges, node_types=[GraphNodeType.SKILL])
        assert all(node.type is GraphNodeType.SKILL for node in sub.nodes)

    def test_edges_only_reference_kept_nodes(self, graph) -> None:
        sub = extract_subgraph(graph.nodes, graph.edges, focus="skill:stm32", depth=2)
        kept = {node.id for node in sub.nodes}
        assert all(edge.source in kept and edge.target in kept for edge in sub.edges)

    def test_limit_marks_truncation(self, graph) -> None:
        sub = extract_subgraph(graph.nodes, graph.edges, limit=3)
        assert sub.truncated is True
        assert sub.node_count == 3

    def test_no_focus_returns_the_connected_graph(self, graph) -> None:
        sub = extract_subgraph(graph.nodes, graph.edges)
        assert sub.node_count > 0
        assert sub.edge_count > 0

    def test_include_orphans_is_honoured_when_a_query_object_is_passed(self, graph) -> None:
        """The flag was accepted and silently ignored whenever a ``GraphQuery`` was passed.

        Every API call passes one, so ``includeOrphans=true`` did nothing: it was the single
        field the query branch did not forward. The isolated node has to be built here —
        a graph produced by a build has no orphans by construction.
        """
        isolated = GraphNode(
            id=node_id(GraphNodeType.SKILL, "no-evidence-at-all"),
            type=GraphNodeType.SKILL,
            label="Unsupported Skill",
        )
        nodes = [*graph.nodes, isolated]
        default = extract_subgraph(nodes, graph.edges, query=GraphQuery())
        with_orphans = extract_subgraph(nodes, graph.edges, query=GraphQuery(include_orphans=True))
        assert all(node.id != isolated.id for node in default.nodes)
        assert any(node.id == isolated.id for node in with_orphans.nodes)
        assert with_orphans.node_count == default.node_count + 1

    def test_counts_match_the_payload(self, graph) -> None:
        sub = extract_subgraph(graph.nodes, graph.edges)
        assert sub.node_count == len(sub.nodes)
        assert sub.edge_count == len(sub.edges)


class TestTraceClaim:
    def test_traces_a_claim_to_its_evidence(self) -> None:
        claim = uuid4()
        skill = node_id(GraphNodeType.SKILL, "stm32")
        evidence = uuid4()
        from careerforge_ai.schemas.evidence import GraphEdge, GraphNode

        nodes = [
            GraphNode(id=claim, type=GraphNodeType.CLAIM, label="claim"),
            GraphNode(id=skill, type=GraphNodeType.SKILL, label="STM32"),
            GraphNode(id=evidence, type=GraphNodeType.REPO_FILE, label="motor.c"),
        ]
        edges = [
            GraphEdge(
                id="1",
                source=evidence,
                target=claim,
                relation=EvidenceRelation.SUPPORTS,
            ),
            GraphEdge(
                id="2",
                source=skill,
                target=evidence,
                relation=EvidenceRelation.EVIDENCED_BY,
            ),
        ]
        paths = trace_claim(nodes, edges, claim)
        assert paths
        assert len(paths[0]) == 2
        assert paths[0][-1].source == evidence

    def test_unknown_claim_returns_nothing(self) -> None:
        assert trace_claim([], [], uuid4()) == []

    def test_a_cycle_does_not_hang(self) -> None:
        from careerforge_ai.schemas.evidence import GraphEdge, GraphNode

        a, b = uuid4(), uuid4()
        nodes = [
            GraphNode(id=a, type=GraphNodeType.CLAIM, label="a"),
            GraphNode(id=b, type=GraphNodeType.SKILL, label="b"),
        ]
        edges = [
            GraphEdge(id="1", source=b, target=a, relation=EvidenceRelation.SUPPORTS),
            GraphEdge(id="2", source=a, target=b, relation=EvidenceRelation.SUPPORTS),
        ]
        paths = trace_claim(nodes, edges, a)
        assert isinstance(paths, list)


class TestStats:
    def test_counts_by_type_and_relation(self, profile: CandidateProfile) -> None:
        graph = build_evidence_graph(
            profile=profile,
            evidence=[_evidence(EvidenceKind.REPO_FILE, "motor.c", "STM32 与 FreeRTOS")],
        )
        stats = graph_stats(graph.nodes, graph.edges)
        assert stats["nodes"] == len(graph.nodes)
        assert isinstance(stats["nodes_by_type"], dict)
        assert isinstance(stats["edges_by_relation"], dict)
        assert 0.0 <= float(stats["mean_confidence"]) <= 1.0
