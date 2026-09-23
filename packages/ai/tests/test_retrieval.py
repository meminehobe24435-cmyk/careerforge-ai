"""Tests for hybrid retrieval.

The behaviours worth pinning down are the ones a demo would not reveal: tenant
isolation in the vector store, honest degradation when the dense arm is
unavailable, and the lexical arm actually carrying exact technical nouns — which
is the entire justification for having two arms instead of one.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from careerforge_ai.errors import CareerForgeError
from careerforge_ai.providers.heuristic import HeuristicProvider
from careerforge_ai.rag import (
    Bm25Index,
    ChunkingConfig,
    HybridRetriever,
    InMemoryVectorStore,
    RetrievalDocument,
    chunk_text,
    reciprocal_rank_fusion,
)
from careerforge_ai.rag.fusion import fuse_with_ranks
from careerforge_ai.schemas.common import EvidenceKind, RetrievalChannel
from careerforge_ai.schemas.evidence import EvidenceLocator

# ── chunking ─────────────────────────────────────────────────────────────────


class TestChunking:
    def test_empty_text_produces_no_chunks(self) -> None:
        assert chunk_text("") == []
        assert chunk_text("   \n\n  ") == []

    def test_short_text_is_one_chunk(self) -> None:
        chunks = chunk_text("基于 STM32 与 FreeRTOS 完成电机控制。", kind="resume")
        assert len(chunks) == 1
        assert "FreeRTOS" in chunks[0].content
        assert chunks[0].token_count > 0

    def test_heading_path_is_preserved(self) -> None:
        text = "# 项目经历\n\n## Balance Robot\n\n使用 STM32 完成电机控制。\n"
        chunks = chunk_text(text, kind="project_doc")
        assert chunks
        assert "Balance Robot" in chunks[0].heading_path
        assert "项目经历" in chunks[0].heading_path

    def test_long_text_is_split(self) -> None:
        paragraph = "这是一个用于测试分块逻辑的句子，包含足够多的字符以产生可观的 token 数。" * 6
        chunks = chunk_text("\n\n".join([paragraph] * 6), kind="project_doc")
        assert len(chunks) > 1
        assert [chunk.index for chunk in chunks] == list(range(len(chunks)))

    def test_oversized_single_block_is_split_on_sentences(self) -> None:
        sentences = "。".join(f"第{i}个测试句子，用来撑大这个块的内容" for i in range(60)) + "。"
        chunks = chunk_text(sentences, kind="project_doc")
        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.content
            assert chunk.token_count <= ChunkingConfig.for_kind("project_doc").target_tokens * 2

    def test_code_uses_smaller_windows(self) -> None:
        assert ChunkingConfig.for_kind("code").target_tokens < ChunkingConfig().target_tokens

    def test_commit_chunks_have_no_overlap(self) -> None:
        assert ChunkingConfig.for_kind("commit").overlap_tokens == 0

    def test_offsets_are_monotonic(self) -> None:
        text = "# A\n\n第一段内容足够长以便成为一块。\n\n# B\n\n第二段内容也足够长。\n"
        chunks = chunk_text(text, kind="notes")
        starts = [chunk.char_start for chunk in chunks]
        assert starts == sorted(starts)


# ── lexical arm ──────────────────────────────────────────────────────────────


class TestBm25:
    @pytest.fixture
    def index(self) -> Bm25Index:
        return Bm25Index(
            {
                "a": "在 STM32F407 上使用 UART DMA 完成不定长数据接收。",
                "b": "使用 React 与 TypeScript 构建前端组件库。",
                "c": "基于 FreeRTOS 的任务调度与优先级划分。",
                "d": "CANopen 协议栈的实现与调试记录。",
            }
        )

    def test_finds_document_by_exact_technical_noun(self, index: Bm25Index) -> None:
        ranked = index.search("STM32F407")
        assert ranked
        assert ranked[0][0] == "a"

    def test_ranks_the_relevant_document_first(self, index: Bm25Index) -> None:
        ranked = index.search("FreeRTOS 任务调度")
        assert ranked[0][0] == "c"

    def test_returns_nothing_for_an_unrelated_query(self, index: Bm25Index) -> None:
        assert index.search("量子纠缠光谱仪") == []

    def test_empty_query_returns_nothing(self, index: Bm25Index) -> None:
        assert index.search("") == []

    def test_respects_the_limit(self, index: Bm25Index) -> None:
        assert len(index.search("使用", limit=1)) <= 1

    def test_document_count(self, index: Bm25Index) -> None:
        assert len(index) == 4
        assert index.document_count == 4

    def test_score_of_unknown_document_is_zero(self, index: Bm25Index) -> None:
        assert index.score("FreeRTOS", "nope") == 0.0


# ── fusion ───────────────────────────────────────────────────────────────────


class TestFusion:
    def test_fuses_by_rank_not_by_score(self) -> None:
        fused = reciprocal_rank_fusion({"semantic": ["a", "b"], "keyword": ["b", "a"]})
        # b appears at rank 2 and 1, a at 1 and 2 — symmetric, so equal scores.
        assert fused["a"] == pytest.approx(fused["b"])

    def test_document_in_both_arms_beats_one_in_a_single_arm(self) -> None:
        fused = reciprocal_rank_fusion({"semantic": ["a", "b", "c"], "keyword": ["c", "d"]})
        assert fused["c"] > fused["a"]

    def test_records_per_arm_ranks(self) -> None:
        fused = fuse_with_ranks({"semantic": ["a"], "keyword": ["a", "b"]})
        score, ranks = fused["a"]
        assert ranks == {"semantic": 1, "keyword": 1}
        assert score > 0

    def test_k_damps_the_top_rank(self) -> None:
        small_k = reciprocal_rank_fusion({"a": ["x"]}, k=1)["x"]
        large_k = reciprocal_rank_fusion({"a": ["x"]}, k=1000)["x"]
        assert small_k > large_k

    def test_empty_input(self) -> None:
        assert reciprocal_rank_fusion({}) == {}
        assert reciprocal_rank_fusion({"a": []}) == {}


# ── vector store ─────────────────────────────────────────────────────────────


class TestVectorStore:
    @staticmethod
    def _record(owner_id: UUID, vector: list[float], **metadata: object) -> object:
        from careerforge_ai.ports import VectorRecord

        return VectorRecord(
            owner_type="evidence",
            owner_id=owner_id,
            model="test-model",
            vector=vector,
            metadata=dict(metadata),
        )

    async def test_upsert_then_search_finds_the_nearest(self) -> None:
        store = InMemoryVectorStore()
        user = uuid4()
        near, far = uuid4(), uuid4()
        await store.upsert(
            [self._record(near, [1.0, 0.0]), self._record(far, [0.0, 1.0])], user_id=user
        )
        hits = await store.search([1.0, 0.0], user_id=user)
        assert hits[0].owner_id == near
        assert hits[0].score == pytest.approx(1.0, abs=1e-5)

    async def test_tenant_isolation(self) -> None:
        store = InMemoryVectorStore()
        mine, theirs = uuid4(), uuid4()
        await store.upsert([self._record(mine, [1.0, 0.0])], user_id=mine)
        await store.upsert([self._record(theirs, [1.0, 0.0])], user_id=theirs)
        hits = await store.search([1.0, 0.0], user_id=mine)
        assert [hit.owner_id for hit in hits] == [mine]

    async def test_upsert_is_idempotent_per_owner(self) -> None:
        store = InMemoryVectorStore()
        user, owner = uuid4(), uuid4()
        await store.upsert([self._record(owner, [1.0, 0.0])], user_id=user)
        await store.upsert([self._record(owner, [0.0, 1.0])], user_id=user)
        assert store.size == 1

    async def test_dimension_mismatch_is_skipped_not_scored(self) -> None:
        store = InMemoryVectorStore()
        user = uuid4()
        await store.upsert([self._record(uuid4(), [1.0, 0.0, 0.0])], user_id=user)
        # A query from a different embedding model must not produce a meaningless
        # similarity score, so no hits is the correct answer.
        assert await store.search([1.0, 0.0], user_id=user) == []

    async def test_metadata_filter(self) -> None:
        store = InMemoryVectorStore()
        user = uuid4()
        commit, file = uuid4(), uuid4()
        await store.upsert(
            [
                self._record(commit, [1.0, 0.0], kind="commit"),
                self._record(file, [1.0, 0.0], kind="repo_file"),
            ],
            user_id=user,
        )
        hits = await store.search([1.0, 0.0], user_id=user, filters={"kind": "commit"})
        assert [hit.owner_id for hit in hits] == [commit]

    async def test_list_valued_filter_means_any_of(self) -> None:
        store = InMemoryVectorStore()
        user = uuid4()
        commit, file = uuid4(), uuid4()
        await store.upsert(
            [
                self._record(commit, [1.0, 0.0], kind="commit"),
                self._record(file, [1.0, 0.0], kind="repo_file"),
            ],
            user_id=user,
        )
        hits = await store.search(
            [1.0, 0.0], user_id=user, filters={"kind": ["commit", "repo_file"]}
        )
        assert len(hits) == 2

    async def test_delete(self) -> None:
        store = InMemoryVectorStore()
        user, owner = uuid4(), uuid4()
        await store.upsert([self._record(owner, [1.0, 0.0])], user_id=user)
        assert await store.delete(user_id=user, owner_type="evidence", owner_ids=[owner]) == 1
        assert store.size == 0

    async def test_empty_search_returns_nothing(self) -> None:
        assert await InMemoryVectorStore().search([1.0], user_id=uuid4()) == []

    async def test_scale_advisory(self) -> None:
        store = InMemoryVectorStore()
        assert store.warn_if_large() is None


# ── hybrid retriever ─────────────────────────────────────────────────────────


def _documents() -> list[RetrievalDocument]:
    return [
        RetrievalDocument(
            evidence_id=UUID("11111111-1111-1111-1111-111111111111"),
            title="motor_control.c",
            text="基于 STM32F407 与 FreeRTOS 完成电机闭环控制，使用编码器反馈与 PID 整定。",
            kind=EvidenceKind.REPO_FILE,
            confidence=0.95,
            locator=EvidenceLocator(path="Core/Src/motor_control.c", line=42),
        ),
        RetrievalDocument(
            evidence_id=UUID("22222222-2222-2222-2222-222222222222"),
            title="web_app.tsx",
            text="使用 React 与 TypeScript 构建前端组件库，采用 Tailwind 设计令牌。",
            kind=EvidenceKind.REPO_FILE,
            confidence=0.88,
        ),
        RetrievalDocument(
            evidence_id=UUID("33333333-3333-3333-3333-333333333333"),
            title="commit a1b2c3d",
            text="feat(can): 实现 CANopen 协议栈的节点管理与错误帧处理。",
            kind=EvidenceKind.COMMIT,
            confidence=0.97,
            locator=EvidenceLocator(sha="a1b2c3d"),
        ),
    ]


class TestHybridRetriever:
    async def test_indexes_and_retrieves(self) -> None:
        retriever = HybridRetriever(embedder=HeuristicProvider(dim=256))
        user = uuid4()
        await retriever.index(_documents(), user_id=user)
        result = await retriever.retrieve("FreeRTOS 电机控制", user_id=user)
        assert result.hits
        assert result.hits[0].title == "motor_control.c"
        assert result.hits[0].evidence_id == UUID("11111111-1111-1111-1111-111111111111")

    async def test_finds_an_exact_technical_noun(self) -> None:
        retriever = HybridRetriever(embedder=HeuristicProvider(dim=256))
        user = uuid4()
        await retriever.index(_documents(), user_id=user)
        result = await retriever.retrieve("CANopen 协议栈", user_id=user)
        assert result.hits
        assert result.hits[0].title.startswith("commit")

    async def test_reports_which_arm_found_each_hit(self) -> None:
        retriever = HybridRetriever(embedder=HeuristicProvider(dim=256))
        user = uuid4()
        await retriever.index(_documents(), user_id=user)
        result = await retriever.retrieve("FreeRTOS", user_id=user)
        assert result.hits
        assert result.hits[0].channel in {
            RetrievalChannel.BOTH,
            RetrievalChannel.SEMANTIC,
            RetrievalChannel.KEYWORD,
        }
        assert result.hits[0].semantic_rank or result.hits[0].keyword_rank

    async def test_works_lexically_when_no_embedder_is_configured(self) -> None:
        """The zero-key path must still retrieve, and must say it is degraded."""
        retriever = HybridRetriever(embedder=None)
        user = uuid4()
        await retriever.index(_documents(), user_id=user)
        result = await retriever.retrieve("STM32F407", user_id=user)
        assert result.degraded is True
        assert result.hits
        assert result.hits[0].title == "motor_control.c"
        assert result.hits[0].channel is RetrievalChannel.KEYWORD

    async def test_metadata_filter_restricts_results(self) -> None:
        retriever = HybridRetriever(embedder=HeuristicProvider(dim=256))
        user = uuid4()
        await retriever.index(_documents(), user_id=user)
        result = await retriever.retrieve("实现", user_id=user, filters={"kind": "commit"})
        assert result.hits
        assert all(hit.kind is EvidenceKind.COMMIT for hit in result.hits)

    async def test_rejects_mixing_two_tenants(self) -> None:
        retriever = HybridRetriever(embedder=None)
        await retriever.index(_documents(), user_id=uuid4())
        with pytest.raises(CareerForgeError):
            await retriever.index(_documents(), user_id=uuid4())

    async def test_empty_query_returns_no_hits(self) -> None:
        retriever = HybridRetriever(embedder=None)
        await retriever.index(_documents(), user_id=uuid4())
        result = await retriever.retrieve("   ", user_id=uuid4())
        assert result.hits == []

    async def test_results_are_reproducible(self) -> None:
        retriever = HybridRetriever(embedder=HeuristicProvider(dim=256))
        user = uuid4()
        await retriever.index(_documents(), user_id=user)
        first = await retriever.retrieve("FreeRTOS 电机控制", user_id=user)
        second = await retriever.retrieve("FreeRTOS 电机控制", user_id=user)
        assert [hit.evidence_id for hit in first.hits] == [hit.evidence_id for hit in second.hits]

    async def test_remove_updates_the_lexical_index(self) -> None:
        retriever = HybridRetriever(embedder=None)
        user = uuid4()
        await retriever.index(_documents(), user_id=user)
        target = UUID("11111111-1111-1111-1111-111111111111")
        assert retriever.remove([target]) == 1
        result = await retriever.retrieve("STM32F407", user_id=user)
        assert all(hit.evidence_id != target for hit in result.hits)

    async def test_top_k_is_respected(self) -> None:
        retriever = HybridRetriever(embedder=None, top_k=2)
        user = uuid4()
        await retriever.index(_documents(), user_id=user)
        result = await retriever.retrieve("使用", user_id=user)
        assert len(result.hits) <= 2

    async def test_diagnostics_are_populated(self) -> None:
        retriever = HybridRetriever(embedder=HeuristicProvider(dim=256))
        user = uuid4()
        await retriever.index(_documents(), user_id=user)
        result = await retriever.retrieve("FreeRTOS", user_id=user)
        assert result.semantic_candidates >= 0
        assert result.keyword_candidates > 0
        assert result.fused_candidates > 0
        assert result.rrf_k == 60
