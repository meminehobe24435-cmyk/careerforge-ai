# Release proof — native fresh-install path

- generated: `2026-09-26T08:52:37+00:00`
- overall: **PASS** — 7 passed, 0 failed, 0 not run
- containerized: **false** — No container runtime on this machine: `docker`, `podman` and `docker-compose` are all absent (probed and recorded in the `container-runtime` step), so `docker compose up` could not be executed. Every step below was run natively.

## What this proves, and what it is not

This machine has no Docker, Podman, PostgreSQL or Redis (probed in step 1, not assumed), so
**`docker compose up` was not run and no artefact here claims it was.** The steps below are
the native equivalent: empty file → `alembic upgrade head` → seed twice → a production-mode
`uvicorn` on the zero-key provider → the built Next.js app served by `next start` → the
contract smoke test → a restart against the same database.

## Environment

| fact | value |
| --- | --- |
| os | Windows 11 (10.0.26200) |
| python | 3.12.10 |
| pythonInterpreter | D:\workspace\epan\.venv\Scripts\python.exe |
| node | v24.13.1 |
| pnpm | 11.7.0 |
| database | SQLite (aiosqlite) — no PostgreSQL server is installed |
| queue | inprocess — no Redis server is installed |
| llmProvider | heuristic (the zero-key deployment) |
| apiBase | http://127.0.0.1:8341/api/v1 |
| webBase | http://127.0.0.1:3341 |
| proofDatabase | data\release_proof.db |

## Steps

| # | step | status | result |
| --- | --- | --- | --- |
| 1 | Container runtime probe (expect: absent) | PASS | no container runtime present |
| 2 | Fresh database: delete the SQLite file, migrate 0 → head | PASS | revision=0009, tables=28 |
| 3 | Seed twice: identical row counts, no duplicates, exit 0 | PASS | seed added 161 rows across 9 tables; second run changed 0 tables |
| 4 | Production-mode API on the zero-key provider | PASS | health/ready/version answered; degraded=['llm_provider', 'vector'] |
| 5 | Built frontend served by `next start` (not `next dev`) | PASS | landing=200, login=200, system=200, authenticated-dashboard=200 |
| 6 | `smoke:api` against the production-mode API | PASS | 25 smoke checks passed |
| 7 | Restart on the same database: no migration, no re-seed | PASS | row counts and demo identity unchanged; authenticated reads OK |

### 1. Container runtime probe (expect: absent) — PASS

```json
{
  "composeFilePresent": true,
  "postgresClientInstalled": false,
  "redisServerInstalled": false,
  "runtimeProbe": {
    "docker": {
      "present": false,
      "probe": "where docker",
      "result": "not found"
    },
    "docker-compose": {
      "present": false,
      "probe": "where docker-compose",
      "result": "not found"
    },
    "podman": {
      "present": false,
      "probe": "where podman",
      "result": "not found"
    }
  }
}
```
> No container runtime: `docker compose up` cannot be executed here, so everything below is the native equivalent and no artefact claims otherwise.

### 2. Fresh database: delete the SQLite file, migrate 0 → head — PASS

```
$ D:\workspace\epan\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head    # cwd=D:\workspace\epan\apps\api
exit=0 in 1.341s
```
```text
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, PHASE 1 baseline: users, profiles, public_profiles, skills, prompt_versions,
agent_runs, llm_calls, background_jobs, ai_caches.
INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, PHASE 2: documents and document_chunks.
INFO  [alembic.runtime.migration] Running upgrade 0002 -> 0003, PHASE 3: evidence and evidence_links.
INFO  [alembic.runtime.migration] Running upgrade 0003 -> 0004, PHASE 4: jobs, job_skills and job_matches.
INFO  [alembic.runtime.migration] Running upgrade 0004 -> 0005, PHASE 2b: the structured career entities.
INFO  [alembic.runtime.migration] Running upgrade 0005 -> 0006, PHASE 6: resume versions, claims and the claim→evidence links.
INFO  [alembic.runtime.migration] Running upgrade 0006 -> 0007, PHASE 8: the application tracker, its event log and the career timeline.
INFO  [alembic.runtime.migration] Running upgrade 0007 -> 0008, PHASE 10: the stored public projection and its PII findings.
INFO  [alembic.runtime.migration] Running upgrade 0008 -> 0009, PHASE 13: usage status, cached tokens, a failure code — and counters that may be ``NULL``.
```
```
$ D:\workspace\epan\.venv\Scripts\python.exe -m alembic -c alembic.ini current    # cwd=D:\workspace\epan\apps\api
exit=0 in 1.126s
```
```text
0009 (head)
```
```text
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
```
```
$ D:\workspace\epan\.venv\Scripts\python.exe -m alembic -c alembic.ini heads    # cwd=D:\workspace\epan\apps\api
exit=0 in 0.833s
```
```text
0009 (head)
```
```json
{
  "alembicCurrent": "0009 (head)",
  "alembicHeads": "0009 (head)",
  "databasePath": "data\\release_proof.db",
  "existedBefore": true,
  "filesRemoved": [
    "release_proof.db"
  ],
  "revisionAfterUpgrade": "0009",
  "tablesCreated": 28
}
```
> The database file was deleted at the start of this step (see `filesRemoved` and `existedBefore`), so the migration ran against nothing at all: this is 0 → head, not an upgrade of an existing schema.

### 3. Seed twice: identical row counts, no duplicates, exit 0 — PASS

```
$ D:\workspace\epan\.venv\Scripts\python.exe scripts/seed.py    # cwd=D:\workspace\epan
exit=0 in 1.518s
```
```text
{"ts": "2026-09-26T08:51:15.423+00:00", "level": "INFO", "logger": "careerforge_api.services.seed", "message": "demo_user_seeded", "event": "demo_user_seeded", "detail": "profile=alex"}
{"ts": "2026-09-26T08:51:15.451+00:00", "level": "INFO", "logger": "careerforge_api.services.seed", "message": "demo_candidate_seeded", "event": "demo_candidate_seeded", "detail": "projects=3"}
seed complete
  database: sqlite+aiosqlite:///D:/workspace/epan/data/release_proof.db
  useSqlite: True
  demoUser: {'id': '6534fe47-4810-436f-b038-fdabbe87fb7a', 'created': True, 'slug': 'alex'}
  demoCandidate: {'seeded': True, 'counts': {'educations': 1, 'experiences': 2, 'projects': 3, 'achievements': 0, 'skills': 16}}
  skills: {'inserted': 126, 'updated': 0, 'deactivated': 0, 'unchanged': 0, 'total': 126, 'taxonomyVersion': 'taxonomy@1.0.0', 'categories': {'language': 17, 'embedded': 36, 'domain': 9, 'ai': 16, 'backend': 12, 'database': 6, 'frontend': 8, 'devops': 7, 'tool': 9, 'soft': 6}}
  prompts: {'inserted': 10, 'bumped': 0, 'unchanged': 0}
  warnings: []
```
```
$ D:\workspace\epan\.venv\Scripts\python.exe scripts/seed.py    # cwd=D:\workspace\epan
exit=0 in 1.496s
```
```text
seed complete
  database: sqlite+aiosqlite:///D:/workspace/epan/data/release_proof.db
  useSqlite: True
  demoUser: {'id': '6534fe47-4810-436f-b038-fdabbe87fb7a', 'created': False, 'slug': 'alex'}
  demoCandidate: {'seeded': False, 'counts': {}}
  skills: {'inserted': 0, 'updated': 0, 'deactivated': 0, 'unchanged': 126, 'total': 126, 'taxonomyVersion': 'taxonomy@1.0.0', 'categories': {'language': 17, 'embedded': 36, 'domain': 9, 'ai': 16, 'backend': 12, 'database': 6, 'frontend': 8, 'devops': 7, 'tool': 9, 'soft': 6}}
  prompts: {'inserted': 0, 'bumped': 0, 'unchanged': 10}
  warnings: []
```
```json
{
  "countsAfterFirstSeed": {
    "achievements": 0,
    "agent_runs": 0,
    "ai_caches": 0,
    "alembic_version": 1,
    "application_events": 0,
    "applications": 0,
    "background_jobs": 0,
    "career_events": 0,
    "claim_evidence": 0,
    "document_chunks": 0,
    "documents": 0,
    "educations": 1,
    "evidence": 0,
    "evidence_links": 0,
    "experiences": 2,
    "job_matches": 0,
    "job_skills": 0,
    "jobs": 0,
    "llm_calls": 0,
    "profile_skills": 16,
    "profiles": 1,
    "projects": 3,
    "prompt_versions": 10,
    "public_profiles": 1,
    "resume_claims": 0,
    "resume_versions": 0,
    "skills": 126,
    "users": 1
  },
  "countsAfterMigrations": {
    "achievements": 0,
    "agent_runs": 0,
    "ai_caches": 0,
    "alembic_version": 1,
    "application_events": 0,
    "applications": 0,
    "background_jobs": 0,
    "career_events": 0,
    "claim_evidence": 0,
    "document_chunks": 0,
    "documents": 0,
    "educations": 0,
    "evidence": 0,
    "evidence_links": 0,
    "experiences": 0,
    "job_matches": 0,
    "job_skills": 0,
    "jobs": 0,
    "llm_calls": 0,
    "profile_skills": 0,
    "profiles": 0,
    "projects": 0,
    "prompt_versions": 0,
    "public_profiles": 0,
    "resume_claims": 0,
    "resume_versions": 0,
    "skills": 0,
    "users": 0
  },
  "countsAfterSecondSeed": {
    "achievements": 0,
    "agent_runs": 0,
    "ai_caches": 0,
    "alembic_version": 1,
    "application_events": 0,
    "applications": 0,
    "background_jobs": 0,
    "career_events": 0,
    "claim_evidence": 0,
    "document_chunks": 0,
    "documents": 0,
    "educations": 1,
    "evidence": 0,
    "evidence_links": 0,
    "experiences": 2,
    "job_matches": 0,
    "job_skills": 0,
    "jobs": 0,
    "llm_calls": 0,
    "profile_skills": 16,
    "profiles": 1,
    "projects": 3,
    "prompt_versions": 10,
    "public_profiles": 1,
    "resume_claims": 0,
    "resume_versions": 0,
    "skills": 126,
    "users": 1
  },
  "demoUserAfterSeed": {
    "createdAt": "2026-09-26 08:51:15.417206",
    "email": "demo@careerforge.ai",
    "found": true,
    "id": "6534fe47-4810-436f-b038-fdabbe87fb7a"
  },
  "exitCodes": {
    "first": 0,
    "second": 0
  },
  "rowsAddedByFirstSeed": {
    "educations": 1,
    "experiences": 2,
    "profile_skills": 16,
    "profiles": 1,
    "projects": 3,
    "prompt_versions": 10,
    "public_profiles": 1,
    "skills": 126,
    "users": 1
  },
  "tablesChangedBySecondSeed": {}
}
```
> Idempotency is proved by counting every table before and after the second run: identical counts and exit code 0 mean no duplicate account, skill or taxonomy row. `docs/DATABASE.md` §6 asks for exactly this.

### 4. Production-mode API on the zero-key provider — PASS

```json
{
  "api": {
    "command": "D:\\workspace\\epan\\.venv\\Scripts\\python.exe -m uvicorn careerforge_api.main:app --host 127.0.0.1 --port 8341",
    "logFile": ".tmp\\release-proof\\api-production.log",
    "pid": 16528,
    "ready": true,
    "readyDetail": "HTTP 200"
  },
  "gitHead": {
    "command": "git rev-parse HEAD",
    "exitCode": 0,
    "stdout": "53c657867316bb020d2bfbec3e58796eb3b39465"
  },
  "health": {
    "httpStatus": 200,
    "provider": "heuristic",
    "status": "degraded",
    "url": "http://127.0.0.1:8341/api/v1/system/health",
    "version": {
      "api": "0.1.0",
      "python": "3.12.10",
      "schemas": "v1",
      "taxonomy": "taxonomy@1.0.0"
    }
  },
  "ready": {
    "degraded": [
      "llm_provider",
      "vector"
    ],
    "gate": "database",
    "httpStatus": 200,
    "ready": true,
    "status": "ready",
    "url": "http://127.0.0.1:8341/api/v1/system/ready"
  },
  "version": {
    "httpStatus": 200,
    "payload": {
      "app": "CareerForge AI",
      "buildTimestamp": null,
      "checkedAt": "2026-09-26T08:51:19.452376Z",
      "commit": "53c657867316bb020d2bfbec3e58796eb3b39465",
      "commitShort": "53c6578",
      "environment": "production",
      "nodeVersion": "24.13.1",
      "pythonVersion": "3.12.10",
      "schemaVersion": "v1",
      "taxonomyVersion": "taxonomy@1.0.0",
      "version": "0.1.0"
    },
    "url": "http://127.0.0.1:8341/api/v1/system/version"
  }
}
```
> `LLM_PROVIDER=heuristic` is the zero-key deployment: the public demo must run with no API key and no cloud account, so the deterministic provider is the honest choice. Readiness stays `ready` while naming `llm_provider` and `vector` as degraded — that is the distinction `/system/ready` exists to make.

### 5. Built frontend served by `next start` (not `next dev`) — PASS

```
$ cmd /c pnpm --filter @careerforge/web build    # cwd=D:\workspace\epan
exit=0 in 70.861s
```
```text
…ating static pages (12/17) 
 ✓ Generating static pages (17/17)
   Finalizing page optimization ...
   Collecting build traces ...

Route (app)                                 Size  First Load JS
┌ ○ /                                    4.79 kB         159 kB
├ ○ /_not-found                            132 B         103 kB
├ ○ /app                                   132 B         103 kB
├ ○ /app/ai-runs                         6.63 kB         156 kB
├ ○ /app/analytics                       9.79 kB         152 kB
├ ○ /app/applications                      28 kB         212 kB
├ ○ /app/costs                           8.42 kB         155 kB
├ ○ /app/dashboard                       8.49 kB         177 kB
├ ○ /app/evidence-graph                  26.2 kB         210 kB
├ ○ /app/interview                       23.1 kB         191 kB
├ ƒ /app/jobs                            19.3 kB         163 kB
├ ○ /app/settings                        3.68 kB         157 kB
├ ○ /app/validator                       13.9 kB         176 kB
├ ƒ /candidate/[slug]                    3.38 kB         172 kB
├ ƒ /login                               7.85 kB         194 kB
└ ○ /system                              9.64 kB         192 kB
+ First Load JS shared by all             102 kB
  ├ chunks/2041-a536b4593717faf6.js      45.7 kB
  ├ chunks/cd581867-35c463cd1d83a918.js  54.2 kB
  └ other shared chunks (total)          2.54 kB


○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand
```
```text
$ next build

 ⚠ The Next.js plugin was not detected in your ESLint configuration. See https://nextjs.org/docs/app/api-reference/config/eslint#migrating-existing-config
```
```json
{
  "buildOutput": {
    "buildId": "33kfz5KTUDQeyZTvPOMn4",
    "distDir": "apps/web/.next",
    "requiredServerFiles": true
  },
  "distExistedBefore": true,
  "nextStart": {
    "command": "cmd /c pnpm --filter @careerforge/web start --port 3341",
    "logFile": ".tmp\\release-proof\\web-start.log",
    "pid": 51044,
    "ready": true,
    "readyDetail": "HTTP 200"
  },
  "pages": {
    "authenticated-dashboard": {
      "bytes": 13886,
      "hasAppShell": true,
      "httpStatus": 200,
      "path": "/app/dashboard"
    },
    "landing": {
      "bytes": 103329,
      "hasAppShell": true,
      "httpStatus": 200,
      "path": "/"
    },
    "login": {
      "bytes": 33499,
      "hasAppShell": true,
      "httpStatus": 200,
      "path": "/login"
    },
    "system": {
      "bytes": 37509,
      "hasAppShell": true,
      "httpStatus": 200,
      "path": "/system"
    }
  }
}
```
> These GETs prove the routes were built and served by `next start` — not `next dev`. They do **not** prove an authenticated session: `apps/web` gates the app shell in the browser from `localStorage`, so /app/dashboard serves the same shell to anyone. The authenticated half is proved with the demo token in the restart step.

### 6. `smoke:api` against the production-mode API — PASS

```
$ cmd /c pnpm --filter @careerforge/web smoke:api    # cwd=D:\workspace\epan
exit=0 in 1.858s
```
```text
…  GET /applications/board columns=7 total=1 archived=0
  ok   board column order     wishlist · applied · oa · interview · final · offer · rejected
  ok   PATCH /applications/reorder status=interview events=2 (每次变更都留痕)
  ok   GET /analytics/funnel  applications=1 interviews=1 cohort=1 basis=applications
  ok   GET /analytics/rates   interviewRate=1/1 sufficient=false (n<5)
  ok   GET /analytics/skill-correlation rows=0
  ok   GET /analytics/categories category=unknown applications=1
  ok   GET /analytics/timeline entries=1 months=12 basis=events
  ok   DELETE /applications/:id deleted, then GET → NOT_FOUND
  ok   GET /public (unpublished) 404 — 陌生人看到的是 404，不是半成品页
  ok   GET /public/candidate/:slug anonymous ok · skills=16 coverage=0.00 hidden=[contact,resume_file] · no PII
  ok   PATCH /public/settings skills hidden → 0 skills on the next anonymous read
  ok   GET /ai-runs           jd_analysis status=degraded latency=1ms tokens=0 prompt=jd_analysis@v1 steps=4
  ok   GET /ai-runs/:id       steps=[clean,extract,normalise,assess] calls=1
  ok   GET /ai-costs          runs=3 calls=3 tokens=0 budget=$1
  ok   GET /ai-costs/by-agent+by-feature agents=[job,recruiter] features=[JD 分析[jd_analysis],公开页生成[recruiter_publish]]
  ok   GET /cache/stats       kinds=[llm,embedding,tool] hits=1 misses=2 rate=0.3333
  ok   GET /prompts           10 prompts, 10 active, all versioned
  ok   GET unknown route      404 NOT_FOUND with requestId

25 checks passed against http://127.0.0.1:8341/api/v1
```
```text
$ node --experimental-strip-types scripts/smoke-live-api.mts
```
```json
{
  "checksPassed": 25,
  "exitCode": 0,
  "summaryLine": "25 checks passed against http://127.0.0.1:8341/api/v1"
}
```
> The smoke test is the frontend client's own contract test: it calls the live API through the same client and runtime guards the browser uses.

### 7. Restart on the same database: no migration, no re-seed — PASS

```json
{
  "alembicRevisionUnchanged": {
    "after": "0009",
    "before": "0009"
  },
  "authenticatedReadsAfterRestart": {
    "/documents?limit=100": {
      "bytes": 128,
      "httpStatus": 200,
      "items": 0
    },
    "/evidence-graph?depth=2": {
      "bytes": 611,
      "edges": 0,
      "httpStatus": 200,
      "nodes": 0
    },
    "/evidence?limit=200": {
      "bytes": 811,
      "httpStatus": 200,
      "items": 1
    },
    "/profile": {
      "bytes": 6314,
      "educations": 1,
      "experiences": 2,
      "httpStatus": 200,
      "projects": 3,
      "skills": 16,
      "slug": "alex"
    },
    "/system/version": {
      "bytes": 425,
      "httpStatus": 200
    }
  },
  "countsAfterRestart": {
    "achievements": 0,
    "agent_runs": 3,
    "ai_caches": 2,
    "alembic_version": 1,
    "application_events": 0,
    "applications": 0,
    "background_jobs": 0,
    "career_events": 1,
    "claim_evidence": 0,
    "document_chunks": 0,
    "documents": 0,
    "educations": 1,
    "evidence": 1,
    "evidence_links": 0,
    "experiences": 2,
    "job_matches": 0,
    "job_skills": 0,
    "jobs": 0,
    "llm_calls": 3,
    "profile_skills": 16,
    "profiles": 1,
    "projects": 3,
    "prompt_versions": 10,
    "public_profiles": 1,
    "resume_claims": 0,
    "resume_versions": 0,
    "skills": 126,
    "users": 1
  },
  "countsBeforeRestart": {
    "achievements": 0,
    "agent_runs": 3,
    "ai_caches": 2,
    "alembic_version": 1,
    "application_events": 0,
    "applications": 0,
    "background_jobs": 0,
    "career_events": 1,
    "claim_evidence": 0,
    "document_chunks": 0,
    "documents": 0,
    "educations": 1,
    "evidence": 1,
    "evidence_links": 0,
    "experiences": 2,
    "job_matches": 0,
    "job_skills": 0,
    "jobs": 0,
    "llm_calls": 3,
    "profile_skills": 16,
    "profiles": 1,
    "projects": 3,
    "prompt_versions": 10,
    "public_profiles": 1,
    "resume_claims": 0,
    "resume_versions": 0,
    "skills": 126,
    "users": 1
  },
  "demoLoginAfterRestart": {
    "hasAccessToken": true,
    "httpStatus": 200
  },
  "demoLoginBeforeRestart": {
    "hasAccessToken": true,
    "httpStatus": 200
  },
  "demoUserAfterRestart": {
    "createdAt": "2026-09-26 08:51:15.417206",
    "email": "demo@careerforge.ai",
    "found": true,
    "id": "6534fe47-4810-436f-b038-fdabbe87fb7a"
  },
  "demoUserBeforeRestart": {
    "createdAt": "2026-09-26 08:51:15.417206",
    "email": "demo@careerforge.ai",
    "found": true,
    "id": "6534fe47-4810-436f-b038-fdabbe87fb7a"
  },
  "evidenceRowSurvivedRestart": {
    "id": "972b9530-a988-4c01-83d0-b1ad1fc9a344",
    "present": true,
    "rows": 1
  },
  "evidenceWrittenBeforeRestart": {
    "httpStatus": 201,
    "id": "972b9530-a988-4c01-83d0-b1ad1fc9a344",
    "title": "Release proof \u00b7 restart durability"
  },
  "restartInstance": {
    "command": "D:\\workspace\\epan\\.venv\\Scripts\\python.exe -m uvicorn careerforge_api.main:app --host 127.0.0.1 --port 8341",
    "logFile": ".tmp\\release-proof\\api-restart.log",
    "pid": 37172,
    "ready": true,
    "readyDetail": "HTTP 200"
  },
  "stopFirstInstance": {
    "command": "D:\\workspace\\epan\\.venv\\Scripts\\python.exe -m uvicorn careerforge_api.main:app --host 127.0.0.1 --port 8341",
    "exitCode": 1,
    "name": "api",
    "pid": 16528,
    "wasAlive": true
  }
}
```
> No `alembic upgrade` and no `scripts/seed.py` ran between the two starts: the restarted process read the same tables, the same alembic revision and the same demo account row (identical id and created_at), it still served the seeded profile (3 projects, 16 declared skills), and the evidence row written through the API before the restart came back with the same id. The API's startup does call `ensure_demo_user` on every boot — it is idempotent, and that is the behaviour being proved, not a claim that startup skips the call.

## NOT RUN

| step | precise reason |
| --- | --- |
| `docker compose up` (the containerized path) | docker, podman and docker-compose are not installed on this machine (probed in step 1, not assumed). The native equivalent is what this machine can produce, and nothing in this artefact claims a compose run happened. |
| PostgreSQL migration path (`DATABASE_URL=postgresql+asyncpg://…`) | no PostgreSQL server or client is installed (no `psql` on PATH, nothing listening on 5432), so `alembic upgrade head` is proved on the SQLite path only. The migrations are dialect-aware, but that is not evidence. |
| Redis queue backend (`QUEUE_BACKEND=redis`) | no Redis server is installed. The deployment runs the in-process queue, and `/system/health` reports `queue=inprocess`; the Redis path is NOT RUN. |
| Durable vector index (pgvector / embeddings table) | not implemented in this build — `/system/health` reports `vector: degraded (in_memory_index)`. Readiness names it and stays `ready`, which is the documented behaviour, not a pass for a durable index. |
| Live cloud run: real LLM provider (DeepSeek / OpenAI) and a public deployment | no cloud account or API key is available to this machine, and this release is the zero-key demo. `LLM_PROVIDER=heuristic` is therefore the honest production-like setting, and the provider degradation is reported rather than hidden. |
| Browser-driven walkthrough of the built app | this proof asserts the built routes over HTTP; browser-level interaction (including `locator.click()` on graph nodes) is covered by `pnpm --filter @careerforge/web test:e2e`, which is run and reported separately in the phase report. |

## Machine-readable evidence

`reports/release-proof.json` carries the same steps with the full command lines, exit
codes, durations and observation payloads.
