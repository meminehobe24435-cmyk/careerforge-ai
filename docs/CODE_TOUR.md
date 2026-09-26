# Code tour — five files, five minutes

This is a reading order, not a summary. It is written for the situation where somebody says "show me
the code" and you have one screen and a few minutes: five files, each of which carries a decision the
rest of the repository depends on. Open them in this order.

| #   | file                                              | lines | what it carries                                             |
| --- | ------------------------------------------------- | ----: | ----------------------------------------------------------- |
| 1   | `packages/ai/careerforge_ai/agents/validator.py`  |   372 | the claim gate: rules → retrieval → model verdict → decide  |
| 2   | `packages/ai/careerforge_ai/graph/builder.py`     |   446 | material → nodes, edges, and computed confidence            |
| 3   | `packages/ai/careerforge_ai/rag/retriever.py`     |   361 | hybrid BM25 + vector retrieval, fused by rank               |
| 4   | `evals/run.py`                                    |   307 | how a labelled suite becomes a gated metric and an artefact |
| 5   | `packages/ai/careerforge_ai/orchestrator/core.py` |   432 | the run: steps, injected context, usage envelope            |

Two notes before starting. Line counts are from the release-candidate tree
(`v1.0.0-rc.1`, commit `1e62fdf`) and will drift; the paths and signatures are the stable part.
`docs/DECISIONS.md` is written in Chinese, so the rejected alternatives quoted below are
translations — the ADR numbers are the citation, not the wording.

---

## 1. `packages/ai/careerforge_ai/agents/validator.py` — the claim gate

**Why this file.** It is the product's promise in one module: a sentence reaches a résumé only when
evidence supports it. The file's docstring states the design as an ordering —
`rules → retrieve → verdict → decide` (free → cheap → costly → arithmetic) — and everything else in
the file exists to hold that order in place. The decision policy itself is split into
`agents/validator_decide.py` (293 lines) because it has one reason to change: _what makes a claim
acceptable_.

**The function to read first.** `def build_workflow() -> Workflow` — it takes no arguments and returns
the four-step workflow (`claim_validate`, one step per phase) whose `optional` and `depends_on` flags
_are_ the degradation policy. Read it before the phase bodies; the bodies then read as
implementations of a shape you already know.

**Input.** A `claim: str` and an `evidence_text: str`, plus an optional `job_context`, a
`retrieval_filters` mapping and an injected `retriever` — the parameters of
`ValidatorAgent.run(executor, *, claim, evidence_text="", job_context="", retrieval_filters=None,
retriever=None, user_id=None)`. They travel to the phases through `context.metadata`. In production the
call arrives from `POST /evidence/validate` (`apps/api/src/careerforge_api/routers/resume.py:158`) via
`ResumeService.validate` (`apps/api/src/careerforge_api/services/resume_service.py:239`), and the
résumé Copilot runs the same gate per bullet through `evaluate_claim`
(`packages/ai/careerforge_ai/agents/resume.py:239`). That `evidence_text` is the candidate's own
material, assembled by `ResumeService._evidence_text`: titles and snippets of up to 60 of the most
confident evidence rows, capped at 12,000 characters, because the rules phase does token overlap —
a lexical aid, not an embedding input. The retriever is injected rather than imported, so the gate runs
with a real hybrid retriever, a fake, or none at all — and the "none" case reports itself.

**Output.** A `ClaimValidation` (`schemas/claim.py`): `status`, `confidence`, `sources`, `reasons`,
`safe_rewrite`, `unknowns`, `numeric_mentions`, `independent_source_count`, `model`,
`prompt_version`. The API serialises it into the validator page; the résumé flow reads `status` and
`is_blocking` to decide whether a bullet may be written. `AgentOutcome` wraps it together with the run
record, so the same call that judges a claim also leaves a trace.

**Design decision.** ADR-014, "rules before the LLM layer". The ADR's rejected alternatives are the
whole argument for the ordering: _"leave it entirely to the LLM — unreliable, not reproducible, and
bypassable with clever wording"_ and _"rules only — cannot handle soft claims that need semantic
mapping, such as 'participated in a drone project'."_ The status is then produced by ADR-006's
arithmetic, not by the model: `classify_claim_status(confidence, independent_sources, *,
supported_threshold=0.75, partial_threshold=0.45, min_sources=2, contradicted=False)` in
`scoring/confidence.py`, which requires **both** a score above the threshold and two independent
sources. ADR-006 rejected _"letting the LLM emit the match score directly — not reproducible, not
explainable, not regression-testable, and it drifts with the prompt."_ Two consequences are visible in
`validator_decide.py` and are worth saying out loud: a rule blocker yields `UNSUPPORTED`, never
`CONTRADICTED` (refused, not accused), and a safer rewrite is withheld when deleting the number would
leave an unsupported technology name behind.

**Test.** `packages/ai/tests/test_agents.py::TestValidatorAgent::test_rejects_a_fabricated_metric` —
the assertion that fails if the gate regresses is `assert validation.status is ClaimStatus.UNSUPPORTED`
(plus `validation.is_blocking`), on the claim `"优化算法性能，提升 70%"` against evidence that contains
no comparable measurement. `test_rejects_a_metric_even_with_no_evidence_at_all` is the same assertion
with an empty evidence set, which is the case where the rule layer must block _before_ retrieval runs.

---

## 2. `packages/ai/careerforge_ai/graph/builder.py` — the evidence graph

**Why this file.** It is where a profile and a pile of raw material become a connected graph
(`Candidate → Experience/Project → Skill → Evidence → file/commit/document`), and it is where
confidence is _computed_ rather than asserted. Its docstring names the two properties that justify a
dedicated module: node ids are derived with `uuid5` from stable keys (`project:Balance Robot`,
`skill:stm32`), so the same profile always builds the same graph; and corroboration is a second pass —
evidence is scored on its own merits first, then re-scored once the number of _independent_ sources is
known.

**The function to read first.** `def build_evidence_graph(*, profile: CandidateProfile, evidence:
Sequence[EvidenceItem], job: JDAnalysis | None = None, confidence_weights: Mapping[str, float] | None
= None, extraction_method: Mapping[EvidenceKind, str] | None = None) -> GraphBuildResult` — it takes
the structured profile and the evidence items (with `kind`, `locator` and `occurred_at` set) and
returns the built graph with confidence attached to each node, edge and evidence item.

**Input.** A `CandidateProfile` plus `EvidenceItem`s, both pure data objects with no session and no
ORM (ADR-022). Callers: the EvidenceAgent (`agents/evidence.py`), the API's
`services/evidence_service.py`, and — worth noticing — two evaluation suites
(`evals/suites/evidence_validation.py`, `evals/suites/interview_relevance.py`) build a graph to
measure against, which is only possible because this function has no database dependency.

**Output.** A `GraphBuildResult` (`graph/builder_types.py`, 58 lines): `nodes`, `edges`, `evidence`,
`links`, and three mappings keyed by canonical skill id — `skill_confidence` (mean confidence of the
skill's evidence), `skill_corroboration` (count of independent source groups) and `skill_evidence`
(evidence ids, used by the match engine) — plus `warnings`. It exposes `node_count`, `edge_count`,
`mean_confidence` and `orphan_evidence`. What persists is the `evidence` rows and the `links`
(`evidence_links`, per ADR-005); `nodes` and `edges` are the same graph in the shape the frontend draws,
and `graph/query.py` (272 lines) is what the API calls to return _a subgraph_ — the two hops around a
focused node, up to `MAX_DEPTH = 4` — rather than the whole thing.

**Design decision.** ADR-005, "the evidence graph uses an adjacency table rather than a graph
database". Rejected, in the ADR's words: _"Neo4j — a separate store and its operational cost; a single
user's graph (a few thousand nodes at most) is nowhere near the threshold where a graph database
becomes necessary, and it would lose transactional consistency with the business data"_, and
_"recursive CTE traversal over everything — unbounded depth, high performance risk."_ The confidence
this module attaches is the same arithmetic as everywhere else (ADR-006), and it is duplicated as a
database constraint — `CheckConstraint(_CONFIDENCE_CHECK, name="confidence_formula")` on the evidence
table (ADR-013), so a row cannot hold a score the formula could not produce.

**Test.** `packages/ai/tests/test_evidence_graph.py::TestCorroboration::test_two_files_in_the_same_group_do_not_count_twice`
— the assertion is `assert result.skill_corroboration["stm32"] == 1` for two evidence rows that are
both `REPO_FILE`: two files in one repository are one independent source, and a regression here would
inflate every skill's confidence. `TestBuild::test_repeated_builds_score_identically` guards the
determinism claim the file makes in its first paragraph.

---

## 3. `packages/ai/careerforge_ai/rag/retriever.py` — hybrid retrieval

**Why this file.** It is the only place the two search arms meet, and it is where degradation is
turned into a fact rather than a mystery. The arms are small enough to read beside it: `rag/lexical.py`
(137 lines) is the BM25 index, `rag/fusion.py` (77 lines) is RRF.

**The function to read first.** `async def retrieve(self, query: str, *, user_id: UUID, top_k: int |
None = None, filters: Mapping[str, Any] | None = None, semantic_weight_enabled: bool = True) ->
RetrievalResult` — it takes a query and the owner of the corpus, runs whichever arms are available,
fuses them by rank, and returns hits carrying per-arm provenance.

**Input.** A query string, a `user_id`, and the index built by `index(documents, *, user_id)`. The
documents are assembled per request by `EvidenceRetrieverService.retriever(user_id=...)`
(`apps/api/src/careerforge_api/services/retrieval_service.py`), which maps stored evidence rows onto
`RetrievalDocument`s via `document_of(row)`; the gate asks for eight hits
(`_RETRIEVAL_TOP_K = 8` in `agents/validator.py`) because corroboration needs a _second_ source, not
just one hit. The retriever is bound to one user for its lifetime and raises rather than mixing two
corpora.

**Output.** A `RetrievalResult`: `hits` (each a `RetrievalHit` with `evidence_id`, `title`, `kind`,
`locator`, `confidence`, display `relevance`, `channel`, `semantic_rank`, `keyword_rank`,
`fused_score`), the per-arm candidate counts, `rrf_k`, `took_ms`, `degraded` and `degraded_reason`.
Consumers: `retrieve_phase` in the validator, which turns hits into the claim's `sources` and
`independent_source_count`, and the `rag_retrieval` evaluation suite, which measures the hybrid and
the keyword-only arm separately.

**Design decision.** ADR-008, "hybrid retrieval + RRF fusion". Rejected: _"pure vector — poor recall on
technical nouns, high hallucination risk"_; _"weighted sum of the raw scores — scores from different
channels are not comparable, normalising them is fragile"_; and _"cross-encoder reranking only — high
latency and cost (kept as an optional v1.1 enhancement)."_ RRF uses ranks precisely to avoid that
normalisation: `score(d) = Σ_arms 1 / (k + rank_arm(d))` with `k = 60`, which is why a hit's
`channel` and per-arm ranks can be shown in the UI rather than logged and forgotten. ADR-009 is the
second half: when there is no key the embedder is `None` or cannot embed, and the retriever continues
lexically with `degraded=True` instead of failing.

**Test.** `packages/ai/tests/test_retrieval.py::TestHybridRetriever::test_works_lexically_when_no_embedder_is_configured`
— `assert result.degraded is True` **and** `assert result.hits[0].channel is RetrievalChannel.KEYWORD`:
the zero-key path must still retrieve, and must say that it degraded. `TestFusion::test_document_in_both_arms_beats_one_in_a_single_arm`
is the fusion invariant: agreement between the arms outranks a single arm's top hit.

---

## 4. `evals/run.py` — a suite becomes a gated metric

**Why this file.** It is the measurement, and it is where "a number we cannot check" is refused. It
loads a labelled dataset, runs it against the same production code the API calls, applies thresholds
that carry their own rationale, writes the artefacts, and exits non-zero when a **gate** threshold is
missed. The suite implementations live in `evals/suites/` and the threshold definitions in
`evals/config.py`; this file owns the CLI, the provenance fields and the artefacts. (One trap worth
knowing: `evals/suites.py` is shadowed by the `evals/suites/` package and is not the live registry —
the package wins on import, which is verified rather than assumed.)

**The function to read first.** `async def run_suites(settings: Settings, suite_names: list[str]) ->
dict[str, SuiteOutcome]` — it takes the resolved settings and the suite names and returns one
`SuiteOutcome` per suite, with the provider built from settings via `build_provider`. `def main() ->
int` (line 187) is the surrounding order: run → calibration → report → artefacts → exit code.

**Input.** `argv` (`--suite`, `--provider`, `--json`, `--out`, `--md-out`, `--bins`,
`--no-calibration`), the JSONL datasets in `evals/datasets/` plus their `manifest.json` (the manifest
is the authority on each dataset's `fixture_version`, so a suite cannot report a version the file does
not carry), and the ai-core settings the API builds on (`careerforge_ai.config.Settings`; the API
extends it as `APISettings`, which is why the two can share one provider chain).

**Output.** `reports/eval-report.json` and `.md`, plus `reports/confidence-calibration.json` and `.md`
when the evidence suite ran. Each report carries the commit it was generated from and whether the tree
was dirty; the calibration numbers are merged into the evidence suite's `metrics` as `evidence.ece`
and `evidence.brier` **before** the report is built, so `evals/compare.py` can see them move. Exit
codes: `0` all gates pass, `2` a gate threshold was missed, `1` infrastructure failure (a missing
dataset, a suite that raised).

**Design decision.** ADR-009, "multiple providers, and the heuristic provider as a first-class
citizen". The runner builds whatever provider the settings name, so the default run is the zero-key
deterministic one and every number here is reproducible on a machine with no API key. Rejected in that
ADR: _"support one vendor only — switching vendors means changing code, and with no key the product is
completely unusable"_, and _"with no key, return empty results — the demo value drops to zero."_
ADR-006 is the reason the metrics are stable enough to gate at all. The gate/report split is
deliberate and lives in `evals/config.py`: a threshold the project has not yet earned stays
`severity="report"` and prints as a miss without failing the run.

**Test.** `evals/tests/test_run_provenance.py::test_an_empty_porcelain_output_means_clean` — `assert
run._git("status", "--porcelain") == ""` and `assert run._tree_is_dirty(...) is False`. It looks like
a test about git and is really a test about a claim the artefact makes: before PHASE 14 the sentinel
`"unknown"` made `git_dirty` true on every run, so the provenance field that says "these numbers belong
to this commit" was always the same value. `evals/tests/test_calibration_metrics.py::test_calibration_metrics_are_named_so_compare_reads_them_as_errors`
guards the other half: a metric name `compare.py` does not read as lower-is-better would make a
calibration regression look like an improvement.

---

## 5. `packages/ai/careerforge_ai/orchestrator/core.py` — the run, its trace, and its metering

**Why this file.** It defines what a run _is_: `Step` (a pure async function with a declared name,
declared dependencies, timeout, retries, fallback, cache TTL, and an `agent` for cost attribution),
`Workflow` (an explicit DAG, validated for duplicate names, unknown dependencies and cycles before it
runs), `RunContext` (everything a step needs, injected rather than imported) and `WorkflowOutput`.
Because each step is an ordinary function and a named node at once, it is unit-testable in isolation
_and_ maps one-to-one onto a trace row. Execution semantics live next door in
`orchestrator/executor.py` (349 lines): layer-by-layer, concurrent within a layer, retries only for
transient failures, `fallback` degrades instead of failing, `optional` skips, anything else aborts.

**The function to read first.** `async def structured(self, prompt_name: str, schema: type[SchemaT],
*, prompt_version: int | None = None, context: Mapping[str, Any] | None = None, **variables) ->
SchemaT` — it takes a registered prompt name plus its variables, renders it from the prompt registry,
and returns schema-validated output while charging the usage envelope to the current step's trace. It
is the only sanctioned way for a step to talk to a model, and it keeps three guarantees in one place:
prompts come from the registry, output is validated, usage is accounted. `WorkflowExecutor.run(workflow,
*, user_id, request_id, trigger, services, metadata, parent_run_id) -> WorkflowOutput` is the entry
point around it.

**Input.** A `RunContext(user_id, request_id, provider, prompts, tracker=None, cache=None,
services={}, metadata={})` and a `Workflow`. The provider is whatever the chain resolved to — deepseek,
openai, ollama, or the heuristic provider at the end of the chain (ADR-009) — and services arrive
through `context.service(...)` / `context.maybe_service(...)`, which is why the AI core needs no
globals and no database (ADR-022).

**Output.** A `WorkflowOutput` (the terminal step's value plus `status`, `degraded`,
`degradation_reason`, `error_code`, `error_message` and the run's `metadata`), and an
`AgentRunRecord` with one `StepTrace` per step. The persistence side of that is
`apps/api/src/careerforge_api/services/metering.py` (499 lines): `MeteredProvider` wraps the request's
_shared_ provider chain and records one `llm_calls` row per model call, `RunRecorder` buffers those
rows and the cache events and writes them at the end of the request that owns the session, and
`DatabaseCacheStore` satisfies the AI core's synchronous `CacheStore` protocol while deferring the
writes for the same reason. The record lands in `agent_runs` and the calls in `llm_calls`, which is
what `/app/ai-runs` and `/app/costs` read. The usage envelope is the currency:
`providers/base.py::structured_output_envelope` (line 313) always returns a `StructuredResult`, and a
provider that cannot report usage contributes `LLMUsage.unavailable(...)` rather than a zero-filled
envelope; `RunContext.add_envelope` _records_ an unavailable envelope instead of discarding it, so a
run's merged status degrades to `unavailable` because the sum of a known part and an unknown part is
unknown.

**A failed run survives its rollback**, and this is the part worth opening
`apps/api/src/careerforge_api/services/failure_journal.py` (216 lines) for. `DatabaseRunTracker`
writes inside the request's transaction, and `get_db` rolls that transaction back on any exception —
so a 400 or a 500 used to leave no trace at all, contradicting the executor's own promise that
observability is never lost. The module records the two rejected fixes alongside the chosen one:
_"`session.begin_nested()` plus an explicit commit — rejected: a SAVEPOINT is still part of the
enclosing transaction, so the rollback discards it too; it looks like a durable write and is not one"_,
and _"writing from a second session while the request's transaction is open — rejected: SQLite has a
single writer, and PHASE 2 already paid for this lesson with 'database is locked'."_ What ships
instead: the tracker hands a `FAILED` run to a journal
(`JOURNALED_STATUSES = frozenset({AgentRunStatus.FAILED})`), and `middleware/failures.py` — deliberately
the outermost middleware — flushes it in a `finally` block, after the transaction has committed or
rolled back, in a session that never contends with the request.

**Design decision.** ADR-007, "a hand-written agent orchestrator rather than LangGraph". Rejected:
_"LangGraph — a thick abstraction layer, hard to debug; its checkpoint/state model duplicates this
project's 'a step is the unit of tracing'; and it binds observability to framework internals"_,
_"the whole LangChain stack — dependency-heavy, leaky abstractions"_, and _"plain sequential function
calls — no unified retry/cache/tracing implementation, the logic scatters into repetitions."_ The
consequence the ADR claims is the one to check while reading: the trace structure and the database
tables line up one-to-one, which is why the AI Runs page has data without a mapping layer. The context
being injected rather than imported is ADR-022, whose rejected alternative is _"querying the database
directly inside an agent — it looks easier, but it forces the evaluation to start a database and makes
a pure unit test impossible."_

**Test.** `packages/ai/tests/test_orchestrator.py::TestExecution::test_records_one_trace_row_per_step` —
`assert tracker.step_events == ["a", "b"]` and `assert [trace.name for trace in outcome.record.steps]
== ["a", "b"]`: the trace-row contract the AI Runs page depends on. For the failure path,
`apps/api/tests/test_failed_run_trace.py::test_a_failed_request_still_leaves_a_trace_behind`, and for
the envelope, `packages/ai/tests/test_usage_envelope.py::test_a_provider_that_reports_nothing_says_unavailable_not_zero`.

---

## The one-minute version

Open them in this order and say one sentence each. If the interviewer stops you, the file you are
holding is the one to talk about.

1. **`agents/validator.py`** — "The order is the design: free rules first, then retrieval, then the
   model, then deterministic arithmetic; a fabricated number never reaches the model."
2. **`graph/builder.py`** — "This is what the gate checks claims against: node ids derived from stable
   keys so builds are reproducible, and confidence re-scored in a second pass once independent-source
   count is known."
3. **`rag/retriever.py`** — "Two arms, BM25 and vector, fused by rank rather than score so nothing
   needs normalising; the whole thing degrades to lexical and says so when there is no API key."
4. **`evals/run.py`** — "This turns labelled cases into gated metrics; thresholds carry their rationale,
   gates fail the build, reports do not, and the artefacts record the commit they came from."
5. **`orchestrator/core.py`** — "A step is a pure function and a trace row at the same time, which is
   why the run page needs no mapping layer; metering rides the same object, and a failed run is
   journaled so a rollback cannot erase it."

## Where the numbers come from

Every figure in the README is one of these files, and each is regenerated by one command.

| artefact                              | what it holds                                                                 | regenerate with                                         |
| ------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------- |
| `reports/eval-report.json`            | 4 suites, 242 cases, 41 metrics, each with its threshold, severity and status | `python evals/run.py`                                   |
| `reports/confidence-calibration.json` | reliability buckets, ECE and Brier for the evidence suite                     | `python evals/run.py` (written whenever that suite ran) |
| `reports/coverage-summary.md`         | core-domain coverage with the per-area and per-file breakdown                 | `python scripts/coverage_report.py --min-core 75`       |
| `reports/release-proof.json`          | the 7-step proof of the free path, with the `NOT RUN` table                   | `python scripts/release_proof.py`                       |
| `reports/api-performance.json`        | per-endpoint P50/P95 on one laptop, explicitly not a load test                | `python scripts/perf_smoke.py`                          |
| `reports/baseline-eval-report.json`   | the committed baseline `compare.py` diffs against                             | committed on purpose; refreshed by hand                 |

Two comparisons are part of the loop rather than an afterthought: `python evals/compare.py
reports/baseline-eval-report.json reports/eval-report.json --fail-on-regression` says what moved, and
`python scripts/release_proof.py` runs the whole free path end to end (fresh database, migrations,
seed twice, production-mode API, built frontend, contract smoke, restart).

## What an interviewer should ask next

Each of these is invited by the five files, and each has an answer in the code rather than in a slide.

1. **"Why is the gate rule-first instead of model-first?"** Because the most dangerous error —
   a fabricated number — is the cheapest to detect, and a model asked to adjudicate a number it cannot
   verify is being asked to guess. ADR-014 records both rejected extremes; the ordering is in
   `build_workflow()` and the early return is `verdict_phase`'s first two lines (`if rules["blocked"]:
return None`).
2. **"What happens when retrieval is down — does the gate fail open or closed?"** Closed, and loudly:
   `retrieve_phase` catches a raising retriever, returns `degraded=True` with a reason, and
   `decide_phase` judges on the rules alone while appending a `LOW_CONFIDENCE_SOURCES` reason saying
   the model verdict was unavailable.
3. **"A rule blocker fires — is the claim refuted?"** No: `UNSUPPORTED`, not `CONTRADICTED`. The
   distinction is stated in `validator_decide.py` and is why a blocked number still gets a safer
   rewrite while a contradicted sentence never does.
4. **"Your hybrid retrieval scores worse than BM25 alone at Hit@5. Why not fix it?"** Because the
   fusion weights would be chosen on 59 queries. The two arms are measured separately in
   `evals/suites/rag_retrieval.py`, and the numbers (hybrid 0.9661 vs keyword-only 0.9831 at Hit@5) are
   published in the README's weaknesses table rather than tuned away.
5. **"A request fails at 500. What is in the database afterwards?"** A `status=failed` run with its
   step traces and error code, sanitised. `services/failure_journal.py` explains why it cannot be
   written in the request's transaction, and `middleware/failures.py` shows where it is flushed.

## Two files worth opening if there is time

- **`scripts/release_proof.py`** (127 lines) — it is unusual in that it proves the product _and_
  publishes what it could not prove: the artefact carries a `NOT RUN` table naming each step the
  machine cannot execute and why, which is the reason the README has no live URL and the release is a
  candidate rather than a release.
- **`apps/web/e2e/helpers/fixtures.ts`** (151 lines) — the browser suite's setup shows the two
  isolation problems a real end-to-end suite hits and most solve silently: `POST /auth/demo` is
  rate-limited per IP and the upload bucket is hourly, so the session and the evidence base are built
  **once per worker** rather than per test, and the specs are written to be order-independent.
