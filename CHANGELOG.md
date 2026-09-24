# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — PHASE 11a · Metering every model call, and a cache that outlives the request

`llm_calls` and `ai_caches` have had models, migrations and indexes since PHASE 1 — and **no
writer**. The AI Runs page PHASE 1 promised would have shown runs with no calls beneath them, and
`/cache/stats` would have read an empty table. This phase closes the loop:

- `MeteredProvider` records one row per model call, from **what the provider reported**: tokens,
  cost, latency, and whether the answer came from the cache. It wraps the shared chain rather than
  rebuilding it, so the cache and the resilience state the app built once are the ones in use.
- `DatabaseCacheStore` gives the AI core's cache — synchronous, because a provider's hot path
  cannot await — a durable layer: it serves from memory and buffers events that `RunRecorder`
  flushes into `ai_caches` at the end of the request that owns the session.
- Seven endpoints: `/ai-runs`, `/ai-runs/{id}` (step chain plus every call), `/ai-costs`,
  `/ai-costs/by-agent`, `/ai-costs/by-feature`, `/cache/stats`, `/prompts`.
- The **budget guardrail is wired**: `Budget(daily_usd=…)` is built with the provider chain at
  startup, so exhaustion now degrades to the next provider instead of the ceiling being a
  configuration field nobody reads. `/ai-costs` reports the same number the guardrail enforces.
- Step traces carry **digests** of their inputs and outputs, not the payloads: an operator browsing
  runs should not be reading candidate material.

### Fixed — PHASE 11a

- **The metering decorator swallowed the degradation signal.** `MeteredProvider` forwarded only the
  protocol members, while the orchestrator reads `provider.last_chain_info` after every structured
  call to decide whether a run was degraded — so on the zero-key path a run flipped from `degraded`
  to `succeeded`. That exposed a **latent bug** too: `job_service` asked the executor for
  `executor.provider.name` on the _not-degraded_ branch only, which had therefore never run, and
  crashed with `AttributeError` the first time it did. The wrapper now delegates unknown attributes
  to the provider it wraps — a decorator that measures must not change what it measures — and the
  service reads the run record's own `model`/`provider`.
- **One flush inserted the same cache key twice.** A `set` followed by a `get` produced two events,
  and looking each up individually could not see the row the first had just added but not yet
  flushed: `UNIQUE constraint failed: ai_caches.cache_key`. Now fetched in one statement and updated
  in memory.
- **`_NOTES` was a string, not a tuple.** `list("…")` exploded the explanation into single
  characters, so `/ai-costs` served `notes: ["t","o","k",…]`. A parenthesised string is not a tuple.
- **A run said "no cache hit" while the cache page said otherwise.** `agent_runs.cache_hit` only
  reflected the executor's step cache; a provider-level hit now raises it too, and the difference
  between the two caches is documented rather than left to the reader.
- **`vector` health still claimed `not_implemented`**, which stopped being true in PHASE 3: the
  hybrid retriever answers retrieval today. It now reports `in_memory_index` and states both halves —
  what serves retrieval, and that the durable index is still missing. Under-reporting is as wrong as
  over-reporting.
- **An environment fault disguised as a regression**: the C: drive filled to zero bytes, so pytest
  could not create `tmp_path` (`OSError: could not create numbered dir … after 10 tries`) and 15
  tests failed with 16 errors. Regenerable caches were cleared and pytest's basetemp moved to D:.
  Recorded here because the failure looked exactly like a code regression.

### Known limitation — PHASE 11a

Most agent work goes through `structured_output`, whose provider returns the parsed schema and
discards its usage envelope, so **that path has no token count to record** — a limit of the core
interface rather than a gap in the metering. Those calls still record provider, latency and prompt
version; the token/cost plumbing is covered by tests through the `chat` path, and the notes on
`/ai-costs` explain why a zero-key deployment honestly reports zero. Fixing it properly means
changing the core's return shape, which belongs in its own change.

### Added — PHASE 10 · Recruiter View, and two layers of redaction

- `GET /public/candidate/{slug}` and `GET /public/candidate/{slug}/evidence/{skillId}` take **no
  token**. That is the feature: a recruiter opening a shared link should not have to create an
  account, and a page that needs a login is not a shareable page. Everything they can reach is
  already filtered and masked by the service — there is no owner-only field left to leak.
- `POST /public/publish`, `GET/PATCH /public/settings`, and `/app/settings` for the candidate:
  the publish switch, the share link, eight per-section switches, the per-skill hide list, and
  the list of what was masked at publish time.
- `/candidate/[slug]` renders on the **server**. This is the one page whose whole purpose is to be
  shared: it must produce its content for a stranger with no account, no token and no JavaScript
  round-trip, and a link preview or a crawler should see the same page a person does.
- The page's evidence is fetched on **click**, through the same anonymous endpoint, so the first
  paint stays small and the request that expands a citation is itself the proof that no account
  is needed.
- `public_profiles` gains `public_payload` and `pii_findings` (migration `0008`).

Four decisions that are all about consent:

- **Privacy switches apply on read, not only on publish.** The stored projection is re-filtered
  through the candidate's _current_ switches every time it is served, so unchecking a section is
  true immediately rather than at the next republish. The window between "I turned that off" and
  "it is off" is exactly where a leak would live.
- **PII is scanned twice** — once while the agent builds the page, and again on the payload that
  is about to be served. The asymmetry decides it: a false negative publishes somebody's phone
  number, a false positive costs a masked string.
- **The candidate is told what was removed.** Silence about a redaction is indistinguishable from
  having had nothing to redact.
- **A public view costs no model call.** The narrative is generated once at publish and stored; a
  page a recruiter can refresh should not bill the candidate per view. And a `storage_scope=local`
  account cannot publish at all (403): a public URL contradicts "my data does not leave this
  machine".

### Fixed — PHASE 10

- **The one endpoint strangers can reach returned 500.** `row.user` is a lazy relationship, and
  touching it inside an async session raises `MissingGreenlet`; nine of sixteen tests failed with
  that error at once. Now eagerly loaded, with the reason in the docstring.
- **The "no PII published" check was passing vacuously.** The first live run produced a public page
  with zero skills and zero highlights — the résumé had been uploaded and analysed but never
  _imported as a profile_, so there was no candidate material to leak and the redaction assertion
  had nothing to prove. The live script now imports the profile and asserts the **source material
  really carries the email** before asserting that the published page does not.
- **The published page reported zero views forever.** The counter lives on the row; the page's meta
  never read it, so the footer said "0 views" while the owner's panel said 3. `public_profile` now
  returns the count alongside the projection.
- **`ALTER TABLE` cannot put a column where the model declares it.** The migrated-vs-models guard
  compares columns as an ordered list, and appending two columns to `public_profiles` broke it.
  Columns are compared as a set now (name, type, nullability, primary key) while indexes, uniques,
  foreign keys and checks are still compared in full — a deliberate narrowing, with the reason in
  the test, because column _order_ is the one thing a migration cannot preserve and no query
  depends on it.
- `packages/shared/src/api/types.ts` reached 552 lines. Split by domain into
  `types-applications.ts`, `types-analytics.ts` and `types-public.ts`, with `types.ts` keeping the
  envelope and re-exporting the rest, so every existing import path still works.

### Added — PHASE 9 · Career analytics, and the discipline of a small sample

- `careerforge_ai/analytics/` — the funnel, the rates, the correlation, the categories and the
  trend, as **pure functions in the framework-free core** (ADR-022). No model produces a number
  here: every figure is arithmetic over rows the candidate's own activity created, so one
  implementation serves the API, the tests and the eval harness. 28 unit tests pin the
  boundaries — an empty cohort, one application, every card rejected, a skill that splits the
  cohort into one group, a month with no activity.
- `GET /analytics/funnel`, `/rates`, `/skill-correlation`, `/categories`, `/timeline`
  (FR-14.1–14.5), each carrying `meta` with its window, its sample policy and the **basis of
  every stage**. Five endpoints share one cohort read, so the panels of one page cannot describe
  two different sets of applications.
- `/app/analytics`: a hand-drawn SVG funnel, the rate cards, the correlation table, the category
  table and the monthly trend, behind a 7d/30d/90d/all switcher. 21 frontend tests, including the
  two the exit criteria name — an insufficient sample says 样本不足 next to the number, and the
  switcher refetches every panel.

Three decisions the numbers forced:

- **The funnel counts what was reached, not what is current.** A card applied → interviewed →
  rejected is `rejected` on the board and _was interviewed_ in the funnel. PHASE 8b documented the
  same distinction when it defined the dashboard's `interviews` as a snapshot; this is the other
  half of it, and the live check prints both numbers beside each other.
- **A rate never travels alone.** Each card carries its numerator, denominator, a Wilson 95%
  interval and a `sufficient` flag; the minimum sample is 5 and the response says so. A rate of
  100% from one interview ships with the interval that admits how little is known, and `0/0` is
  `null` rather than 0%.
- **A step rate can be undefined.** Zero offers out of zero final rounds is `null`, not 100% — the
  first version of this engine called it a perfect conversion. The test that catches it now states
  the distinction between "a real zero" (no replies from one application) and "no denominator".

### Fixed — PHASE 9

- **The trend chart's month-prefix loop never terminated.** Extending the axis backwards from the
  earliest activity walked _further_ back each iteration, because every earlier month is also less
  than the window's first key: 36 seconds of CPU with no output, and the test that reaches that
  branch hung instead of failing. It walks forwards now, and is bounded.
- **`?range=` was silently ignored.** The handler's parameter was named `range_key`, and FastAPI
  takes the query-parameter name from the parameter — so `?range=7d` fell back to the default 30d
  and `?range=1y` answered 200 with a 30-day result. Now aliased. A defect that raises no error and
  returns the same answer for every window is the kind that survives a demo.
- **Every application appeared twice on the timeline.** The board wrote a `career_events` milestone
  when a card was created _and_ when it was actually applied to, so the trend counted each
  application twice. `wishlist` is no longer a milestone: adding a bookmark is not an act. The
  audit trail still records the creation, which is where that belongs.
- **`Counter` cannot hold fractional weights.** The category weighting multiplies by skill weight,
  and `Counter[str]` is typed over `int` — mypy flagged the assignment that would otherwise have
  silently truncated every preferred-skill weight to zero.
- **A schema comment claimed the wrong denominator.** `cohortSize` was documented as "the
  denominator of the funnel and of every rate below it"; it is really the pool (cards created in
  the window, wishlist included) while the funnel's denominator is its first stage. Found by
  comparing the docstring against live output. A wrong note about what a number means is worse than
  no note, because it reads as verified.

### Added — PHASE 8c · The board, and the frontend's first tests

- `/app/applications`: seven columns in the documented order, cards carrying the FR-13.3 fields
  (company, role, location, salary, status, match score, date, notes), a create dialog for the
  referral that has no posting yet, and a grouped list view on narrow screens where seven
  columns and page-scrolling fight each other.
- **A keyboard path that can actually change columns.** dnd-kit's stock
  `sortableKeyboardCoordinates` only walks the sortable items of the column the drag started in,
  so with it a card picked up by keyboard can be reordered within its column and never moved to
  another one — the single thing the board is for. `lib/keyboard-coordinates.ts` is ours: the
  drag's current rectangle is the origin, the nearest droppable in the pressed direction is the
  target, and because columns are droppables too an _empty_ column is reachable. `→` moves one
  column, `→→` moves two (the position accumulates), `↓` reorders within the column.
- A card menu (move / archive / delete) that calls exactly the same mutation as a drag. It is the
  primary path on touch, the discoverable path for anyone who does not know a board is draggable,
  and the only place archive and delete live.
- **Vitest + Testing Library**, the frontend's first test runner: 32 tests covering the board's
  arithmetic, its rendering, its keyboard drag, and its rollback. The runner exists because the
  phase's exit criterion is an accessibility assertion, and an a11y claim that nothing executes is
  a claim, not a guarantee.
- `smoke:api` grew from 7 checks to 11: it now creates a card through the real client, runs the
  new `isApplicationBoard` guard against the real response, asserts the seven columns arrive in
  the documented order, reorders, and deletes — cleaning up after itself, because a smoke test
  that leaves cards behind changes the numbers the next run measures.

### Fixed — PHASE 8c

- **`pnpm-workspace.yaml` carried pnpm's own error text as a value.** `allowBuilds.esbuild` was
  literally `set this to true or false`, copied from the message it was meant to silence, so every
  install failed with that same message. It is `true` now, with both dependencies that need to
  compile named and explained.
- **Value imports inside a workspace package broke one of the three runtimes that load it.**
  `packages/shared` is consumed as source by Next's bundler, by Vitest, and by Node's
  `--experimental-strip-types` loader (the smoke script). Node resolves specifiers literally, so
  turning `guards.ts`'s `./types` import from a type-only import into a value import (for
  `APPLICATION_STATUSES`) made the smoke test fail with `ERR_MODULE_NOT_FOUND` while the app and
  the tests stayed green. Package-internal imports now carry explicit `.ts` extensions, permitted
  by `allowImportingTsExtensions` (ADR-023).
- **The README claimed the demo account was seeded with a complete candidate** — "3 projects, 9
  skills, ~180 evidence records, 12 analyzed jobs, 16 applications, 5 interviews. No page is ever
  empty." A fresh database has an empty demo account; the numbers described a seed script that
  does not exist yet. The section now says what the seed actually creates and why the rest is
  deliberately absent until the surfaces it fills exist.
- The dashboard's local fallback definitions for `applications` / `interviews` / `offers` had
  drifted from the API's own wording (the `interviews` fallback described the funnel meaning while
  the API ships the snapshot meaning).

### Notes — PHASE 8c

Pointer dragging is exercised by the component tests only in its _decision_ logic: jsdom has no
layout and no `PointerEvent`, so the gesture itself — and the visual result of 280px columns on a
real screen — is verified in a real browser in PHASE 13. What is verified now: the keyboard drag
end to end, the menu path, the optimistic render before the server answers, the rollback and its
toast, and the board arithmetic against the server's rule.

### Added — PHASE 8b · The application tracker, and a dashboard that stops guessing

- `applications`, `application_events` and `career_events` (§2.7, §2.11) with migration
  `0007`, verified column-for-column against the ORM models.
- Nine endpoints: the board, list, create, detail, update, reorder, events, delete, plus
  `POST /jobs/{id}/applications` — FR-13.5, one click from "I analysed this posting" to
  "I am tracking it".
- `GET /applications/board` returns all seven columns in the documented order, empty ones
  included, with `counts` and `total`. A missing key would force the client to guess, and
  a guessed board draws the wrong columns the day a stage is added.
- **Every status change writes an `application_events` row**, which is what PHASE 9's
  funnel will read. A move to the _same_ status writes nothing: a within-column drag is a
  reorder, and an event log full of `applied → applied` makes one application look like
  several.
- `career_events` finally has a writer: the milestones a candidate would put on a CV
  timeline (applied, interviewed, offered, rejected). Intermediate board moves stay in the
  event log. A `dedupe_key` plus unique constraint means dragging a card back and forth
  cannot inflate the timeline with the same milestone.
- The dashboard's `applications` / `interviews` / `offers` are real counts. PHASE 5 shipped
  them as named zeros in `meta.unavailable` because no data source existed; that list is now
  empty and the definitions say which arithmetic each number is — including that
  `interviews` is a board snapshot, not the ever-reached funnel.

### Changed — PHASE 8b

- **The board is a snapshot, not a view over live postings.** A card copies the company,
  role, location and the system's last computed match score at creation. Deleting a
  posting therefore leaves the card standing (its `jobId` goes null) instead of erasing
  the user's history as a side effect of housekeeping.
- **A client cannot post a score.** `matchScore` is refused on input; the number on a card
  is evidence, not a claim. With no stored match it is `null`, never `0` — "never scored"
  and "scored zero" are different facts.
- **Drop positions are re-derived server-side.** A drag-and-drop client is a hostile source
  of ordering data (duplicates, gaps, a whole column in one gesture), so a position is an
  input to rendering, not a source of truth.
- No transition is forbidden. The board is dragged, so candidates mis-drop, rewind after a
  rejection and reopen an old wishlist item; rather than fight the user, every move is
  recorded. `applied_at` is stamped when a card first leaves `wishlist` and is not erased by
  a rewind, and `offer`/`rejected` clear `next_action_at`.

### Fixed — PHASE 8b

- **The JD parser could not read a company name.** `_COMPANY_RE` demanded a `公司：` label,
  while the most common Chinese layout puts the company unlabelled on line one. Every card
  came out with a blank company and every parse lost the 15% `company_found` weight. The
  parser now reads a title block — unlabelled first line, `Company — Role` on one line, or
  the labelled form — requiring a name-shaped candidate, ≤ 24 characters, free of prose
  words, and neither a role line nor a section header; `我们是一家专注于工业智能化的公司`
  is therefore still not read as a company.
- **The eval corpus labelled a company for all 120 postings and nothing scored it.** The
  gold field was dead data. `jd.company_accuracy` now measures it in both directions —
  inventing a company for a posting that names none is exactly the error the rule exists to
  prevent. Measured 1.0000 on 120 samples, with `required_skill_f1` (0.8832) and
  `distractor_leakage_rate` (0.0000) unmoved.
- `/applications/board` and `/applications/reorder` are declared before
  `/applications/{id}`: registered the other way round, a literal path is unreachable and
  the endpoint answers "Application not found" for its own documented URL. There is a test
  that would catch it.
- Three test assertions counted rows across the whole session-shared test database instead
  of one account's. Each passed in isolation and failed in the full run — the argument for
  running the whole suite every phase, and for tenant-scoping every assertion.

### Added — PHASE 6b · The claim gate, made durable

- `resume_versions`, `resume_claims` and `claim_evidence` (§2.9) with migration `0006`,
  verified column-for-column against the ORM models.
- `POST /resume/optimize`, `GET /resume/versions`, `GET /resume/versions/{id}`,
  `DELETE /resume/versions/{id}`, plus the documented `POST /evidence/validate` and
  `/evidence/validate/batch` (≤ 20).
- Every bullet is gated and stored with its verdict: status, confidence, the rules that fired,
  the safer rewrite, and — for a supported claim — the citations that support it. The
  candidate's own wording is kept beside the rewrite so a reviewer can judge whether the
  optimised version invented something.
- A claim can exist without a résumé version, which is what makes the Validator page possible:
  a sentence someone is _considering_, checked before it reaches a document.

### Fixed — PHASE 6b

- **Without a retriever the gate did not degrade — it rejected everything.** The retrieval phase
  reported "no retriever configured" and returned zero hits, so "使用 STM32 与 FreeRTOS 开发电机
  控制固件" came back unsupported with `skill_not_in_graph`, while the graph held eight pieces of
  evidence for those skills. The API now builds the project's own hybrid retriever (BM25 +
  vectors, RRF-fused, ADR-0006) over the caller's stored evidence.
- **The rules phase runs before retrieval and reads caller-supplied material**, which the API was
  not passing — so every technical noun in a claim was reported as unmentioned, in the same
  response that cited a document naming it. The single-claim path now supplies the candidate's
  material, which is what the contract asks of a caller that holds it.
- The API's bullet field is `original` while the engine reads `text`; the mismatch made every
  bullet look empty and the optimiser politely reported having nothing to rewrite. Mapped
  explicitly — a silent failure rather than an error is the worst kind here.
- `integrity_score` and `claim_stats` were copied from an engine field that can arrive empty,
  leaving a version whose summary read `{}` beside a list of claims. Both are now computed from
  the claims actually stored.

### Fixed — PHASE 6c · The three recorded limitations, closed

- **A safer rewrite is no longer offered when it would still assert something unsupported.** If
  stripping the numbers leaves a technology name the evidence cannot carry, keeping the name and
  deleting the digits states the same unsupportable thing while hiding that something was removed.
  Rule blockers now decline to rewrite in that case; a blocker that is _only_ a number still gets a
  rewrite, because removing the number is exactly the correct repair.
- **The blocking rules no longer soften under retrieval.** A rule blocker with hits used to fall
  through to `partially_supported`, which relabelled a fabricated number with a gentler verdict.
- **`contradicted` now means contradicted.** It is reserved for `timeline_conflict` and a model
  reporting `contradicting_evidence`; rule blockers — no comparable measure, missing technology,
  superlative language — are `unsupported`. Nothing refuted the fabricated sentence, so calling it
  refuted was an overclaim of the gate's own.
- **A dangling measure verb is removed wherever it lands**, not only at the end of a sentence:
  `_DANGLING_MEASURE_RE` anchors on `(?=[，,；;、]|$)` and both rewrite branches share one tidy pass.
- **The single-source downgrade explains itself**: `single_source_only` is appended to `reasons`
  (`目前只有 1 条独立来源；达到 2 条独立来源才能判为 supported。`), so the status is no longer a
  verdict without a reason.

Verified against a running API on a fresh database: the fabricated sentence returns `unsupported`
with all three reasons; the supported one gains the `single_source_only` note; neither gets a
rewrite. Every eval metric is unchanged — `numeric_rejection_rate 1.0000`,
`over_support_rate 0.0000`, `safer_rewrite_rate 0.6222`, `support_recall 1.0000` — so the three
fixes changed what the gate _says_, not how strict it is.

### Known limitations — PHASE 6c

Recorded in `docs/ROADMAP.md` rather than left implicit: after a measure verb is removed the clause
can be left as a bare noun phrase (`响应时间缩短了 40%，并完成了压测` → `响应时间，并完成了压测`);
the rule cannot honestly rebuild the deleted predicate, so it keeps the clause and leaves it to the
candidate. Separately, the heuristic extractor still splits free-form Chinese résumés imperfectly —
marked `origin=heuristic` and correctable, but imperfect.

### Added — PHASE 2b · Career entities and the profile import path

- `educations`, `experiences`, `projects`, `achievements` and `profile_skills` (§2.2) with
  migration `0005`, verified column-for-column against the ORM models.
- `POST /profile/import` extracts entities from text or from a stored document and persists
  them; `GET /profile` returns what is stored. Both are the _assembled_ profile every other
  feature reads, so what a client shows and what the system scores cannot diverge.
- `origin` is returned on every entity and every declared skill: a row a model extracted and
  nobody has checked stays visibly different from one a candidate corrected.
- Three consumers were rewired to read real entities — the graph builder, the match engine and
  the dashboard — which is what the tables were for.

### Fixed — PHASE 2b

- **A declared skill with evidence was reported as a gap.** Declarations come from résumé
  extraction with an `evidence_count` of zero, and the match engine reads that as "claimed but
  unproven" — so STM32, FreeRTOS and CAN were all listed as gaps while the graph held eight
  pieces of evidence for each. The declared skills and the evidence graph are now merged: levels
  are kept, counts are corrected, and skills that have evidence but were never declared are
  added. Measured on a fresh database: `skill` 0.0 → **39.16**, `evidence` 0.0 → **87.0**, total
  score 16.4 → **40.76**, and the gap list went from three false gaps to `['autosar']`.
- **Re-importing a profile orphaned its graph edges.** The writers deleted and re-inserted rows,
  so every project and experience got a new UUID and the edges pointing at the old ones stopped
  resolving — the canvas showed `project:de6dd367`, a node nobody can open. `dedupe_key` exists to
  identify the same entity across imports; the writers now upsert on it, and an entity the source
  really dropped is deleted together with its edges. Verified live: a second import leaves the
  graph and the score identical, with zero placeholder nodes.
- **The documented `origin` CHECK could not express the extractor's own vocabulary.** §2.2 lists
  `llm` / `user_corrected` / `import`, while the AI core's `Origin` enum also carries
  `heuristic` — the zero-key path. Written as documented, every heuristic extraction would have
  violated the constraint; recording it as `llm` would have been a false claim about provenance.
  The value is added in all three places (model, migration, docs), with the reasoning recorded.

### Added — PHASE 5 · Dashboard endpoint and the first live frontend↔API run

- `GET /dashboard` implements the `DashboardResponse` contract the frontend has carried since
  PHASE 0: profile strength from the deterministic engine, the six documented metrics derived
  from stored rows, a skill radar built from the evidence graph, and concrete next actions.
- `meta.unavailable` names the metrics whose data source does not exist yet (the application
  tracker belongs to PHASE 8). A zero on a dashboard reads as "you have none", which for a
  system that has never seen an application would be a claim it cannot make; the UI renders
  "尚未接入" for those cards instead of the zero.
- `meta.definitions` ships each metric's actual 口径 with the number, and the UI prefers it
  over its local copy, so the label and the arithmetic cannot drift apart.
- `pnpm --filter @careerforge/web smoke:api` runs the **real** frontend client and runtime
  guards against a live API — the first time the two halves of this project were executed
  against each other. Seven checks: demo login, the dashboard guard, health normalisation,
  the evidence graph, the job list, a match, and the error envelope with its requestId.

### Notes — PHASE 5

- `/dashboard` is deliberately uncached, unlike the documented "含缓存": every number comes
  from rows a user may have changed seconds earlier, and a cached home page that disagrees
  with the page you just left is worse than a 30 ms query. The cache belongs on the expensive
  `/analytics/*` aggregations.
- Browser verification (hydration, interaction) still has not run: it needs Playwright, which
  is PHASE 12. What is verified here is the build, every route serving, the client/server
  contract, and the dashboard strings reaching the client bundle.

### Added — PHASE 4 · JD Analyzer and explainable matching

- `jobs`, `job_skills` and `job_matches` (§2.6) with migration `0004`, verified
  column-for-column against the ORM models. `job_skills` carries an application-generated
  `dedupe_key` because the documented uniqueness spans a **nullable** column, and `NULL`
  never compares equal in a unique index on either backend.
- `POST /jobs/analyze`, `GET /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/skill-tree`,
  `DELETE /jobs/{id}`, `POST /jobs/{id}/match` and `GET /jobs/{id}/match`.
- Every requirement carries the posting's own sentence (`jdEvidence`), so a reader can check
  that the parser did not invent it. Analysis and matching are synchronous, as documented.
- The match payload keeps the documented shape: five dimensions with their weights and
  weighted contributions, `why.formula` holding the actual formula, and the strengths, gaps
  and unknowns as explicit camelCase models. Each run is stored, so a changed score has a
  before and after.
- Pasting the same posting twice updates one job (`description_sha256`), keeping its match
  history on a single card.

### Fixed — PHASE 4

- **The evidence dimension measured the wrong list.** It was computed over the _highlighted_
  skills — those whose effective level clears 0.5 — so a candidate satisfying five
  requirements, each with evidence behind it, scored **0.00** on the dimension whose entire
  purpose is to measure that evidence. Measured live: evidence 0.0 → 87.0, total score
  11.56 → 20.26. A regression test now covers the most common shape (one piece of evidence,
  MODERATE level).
- A freshly inserted job triggered a synchronous lazy load of its skills relationship and
  returned a 500 (`MissingGreenlet`); the repository refreshes the relationship it just
  wrote.
- `strengths``/`gaps`/`unknowns` leaked the engine's snake_case keys into an otherwise
  camelCase payload — the same class of defect as the locator in PHASE 3.
- `test_models.py` outgrew the 500-line guard; split into `test_schema_inventory.py` (what
  the schema declares) and `test_models.py` (what the database enforces) rather than
  allowlisted.

### Added — PHASE 3 · Evidence Graph

- `evidence` and `evidence_links` (§2.5) with migration `0003`, verified column-for-column
  against the ORM models. The confidence formula is a database `CHECK`: the stored score
  must equal the formula applied to the stored five factors, so the number a UI shows can
  be recomputed in SQL. The cap is spelled with `CASE` rather than PostgreSQL's `least()`,
  because SQLite spells it `min()` and CI runs both dialects.
- `GET /evidence`, `GET /evidence/{id}`, `GET /evidence/{id}/trace`, `POST /evidence`
  (manual, with the confidence computed server-side and unknown fields refused),
  `DELETE /evidence/{id}`, `GET /evidence-graph`, and `POST /documents/{id}/analyze`.
- `analyze` builds evidence and skill edges from a stored document's chunks. It is
  synchronous — a documented exception to the 202 convention — because it is deterministic,
  CPU-only and bounded by the chunks already in the database. Re-running it is idempotent.
- Evidence is de-duplicated on `(user_id, kind, content_hash)` and edges on their
  five-tuple, so re-analysis cannot inflate the graph.

### Fixed — PHASE 3

- **Hand-typed evidence was scored as an uploaded document** (0.80), letting a candidate
  type a claim and receive near-document-grade confidence. It now carries the self-report
  tier (0.55), with a measured test pinning the gap to the authority weight.
- **Five relations existed as in-memory edges with no stored link**, including every
  candidate `HAS` edge. The in-memory graph looked complete; the persisted one lost its
  root and every education/experience/achievement node. An invariant test now asserts the
  edge set equals the link set.
- **`include_orphans` was silently ignored** whenever a `GraphQuery` was passed — which is
  every API call — so `includeOrphans=true` did nothing.
- The `stats` block described the whole graph while the payload carried a subgraph, so a UI
  could show "129 nodes" above a ten-node canvas. `stats` describes the response now and
  `totals` describes the graph.
- The locator leaked the store's snake_case keys (`char_start`) into an otherwise camelCase
  payload, and engine-derived evidence ids were not remapped onto the stored rows, leaving
  edges that no query could resolve.

### Added — PHASE 2 · Candidate Profile (documents)

- `documents` and `document_chunks` tables (`docs/DATABASE.md` §2.3) with the migration
  `0002_documents`, verified column-for-column against the ORM models by
  `tests/test_migrations.py`.
- Document ingestion in the AI core: PDF (pypdf), DOCX (python-docx), Markdown and plain
  text, with a GB18030/Big5 decoding ladder for résumés saved by Chinese Windows editors,
  YAML front-matter stripping, and honest reporting of what could not be read — a scanned
  PDF is reported as needing OCR rather than returned as an empty document.
- `POST /documents` (multipart, `202` + task id), `GET /documents`,
  `GET /documents/{id}`, `GET /documents/{id}/chunks`, `GET /documents/{id}/text`,
  `DELETE /documents/{id}`. Uploads are spooled and parsed by the queued
  `document.ingest` worker, which registers the same handler set in both the API process
  and the standalone worker.
- Re-uploading identical bytes is idempotent (`sha256` unique per user), so a résumé
  cannot fork the evidence graph.
- Local Mode (`storage_scope = 'local'`) and `retainRawText: false` store neither the text
  nor the chunks; the API says which of the two applies instead of showing an empty box.

### Fixed

- `DELETE` no longer returns a JSON envelope body on `204` (RFC 9110 §6.4.1 forbids a body
  on that status).
- A failed parse is now a stored fact (`parse_status` / `parse_error`), committed before
  the request transaction would roll it back.
- Unknown document kinds and unreadable file types are refused with `400` at upload time
  rather than accepted and failed later in the worker.
- The `status` filter on `GET /documents` is applied in SQL; filtering after a `LIMIT`
  returned short pages whose total disagreed with their items.

### Added — PHASE 1 · Platform, AI core and API

- `packages/ai`: deterministic orchestration (custom DAG executor), 4 provider
  implementations including a zero-key heuristic provider, hybrid retrieval (BM25 + RRF +
  exact vectors), the evidence graph with a five-factor confidence formula, and 9 agents.
- `apps/api`: application factory, response envelope, error taxonomy, request-id,
  rate limiting, JWT auth with a demo account, and an idempotent background queue.
- `apps/web`: Next.js 15 shell with the design tokens, AppShell and six routes.
- `evals/`: three labelled suites with committed results and documented weaknesses.

### Added — PHASE 0 · Product design

- `docs/PRD.md` — product definition: personas, evidence-graph concept, deterministic
  confidence formula, 18 requirement groups with acceptance criteria, non-goals, risks.
- `docs/ARCHITECTURE.md` — layered architecture, custom agent orchestrator design,
  9 agents, 10 workflows, hybrid RAG pipeline, scoring engine, security architecture.
- `docs/DATABASE.md` — 32-table schema, index strategy, pgvector configuration,
  SQLite/PostgreSQL compatibility layer, seed-data self-consistency requirements.
- `docs/API.md` — REST surface with response envelope, error-code table, SSE contracts,
  rate limits, and a full demo call chain.
- `docs/UI.md` — design system (tokens, typography, motion), 54-component inventory,
  sitemap, page-by-page specifications, accessibility and responsive matrices.
- `docs/ROADMAP.md` — 16 phases with exit criteria, dependency graph, risk register.
- `docs/DECISIONS.md` — 22 ADRs including rejected alternatives.
- Repository skeleton, `README.md`, `.env.example`, community health files.

### Notes

- Every metric quoted in the README and `evals/README.md` comes from a committed artifact
  (`reports/eval-report.json`), and unmet targets are reported as unmet.
