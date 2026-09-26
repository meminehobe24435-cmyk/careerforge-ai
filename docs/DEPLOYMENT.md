# Deployment

Two paths: **Docker Compose** for a complete run on one machine (the one this project was developed
against, in principle), and **managed services** for a public URL. Read §0 first — it states what has
and has not been executed, because a deployment guide that implies a run it never had is worse than no
guide.

## 0. What has actually been run

| path                                                                                                                                        | state                                                                                                                                                                                                                                                                                                                                                   |
| ------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Native run on Windows: fresh DB → `alembic upgrade head` → seed twice → production-mode `uvicorn` → `next start` → contract smoke → restart | **executed, 7/7** — `reports/release-proof.md`                                                                                                                                                                                                                                                                                                          |
| Browser suite against that stack (desktop + mobile)                                                                                         | **executed, 45 passed**                                                                                                                                                                                                                                                                                                                                 |
| `docker compose build` / `docker compose up`                                                                                                | **never executed.** The development machine has no `docker`, `podman` or `docker-compose` (probed in release-proof step 1 and recorded in its `NOT RUN` table). The Dockerfiles and the compose file are written and reviewed; they are not witnessed.                                                                                                  |
| `docker build` in CI                                                                                                                        | **never executed** — the job is `images` in `.github/workflows/ci.yml`, added in this phase. Its first run is what will witness the image path.                                                                                                                                                                                                         |
| PostgreSQL / pgvector                                                                                                                       | The CI job `api-postgres` runs the full API suite against `pgvector/pgvector:pg16` **on GitHub's runners**. It has never run on the development machine, which has no PostgreSQL.                                                                                                                                                                       |
| Redis queue                                                                                                                                 | **never executed.** No Redis on the development machine. With `QUEUE_BACKEND=redis` configured but no implementation in the process, the app falls back to the in-process queue and `GET /system/health` reports the downgrade; the unsupported **storage** backend is the one refused outright (`assert_runtime_configuration`, `STORAGE_BACKEND=s3`). |
| A public deployment                                                                                                                         | **not done.** No cloud account or credentials were available. `DEPLOYMENT BLOCKED` — see `reports/release-readiness.md` §4.                                                                                                                                                                                                                             |

Anything below marked **[unwitnessed]** has not been executed by this project's own tooling. That is a
statement about this machine, not about the code.

## 1. Compose path (single machine) **[unwitnessed]**

```bash
cp .env.example .env          # then set JWT_SECRET (32+ chars) and, optionally, an API key
docker compose build
docker compose up -d
docker compose ps             # wait for api: healthy, web: up, migrate: exited(0)
```

What the file brings up, and why in that order:

| service    | image                    | notes                                                                                                                                            |
| ---------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `postgres` | `pgvector/pgvector:pg16` | `pg_isready` healthcheck; data in a named volume                                                                                                 |
| `redis`    | `redis:7-alpine`         | `redis-cli ping` healthcheck; backs the queue and the shared rate limiter                                                                        |
| `migrate`  | API image                | one-shot `alembic upgrade head`; every other service waits on `service_completed_successfully`, so nothing starts against an unmigrated database |
| `api`      | API image                | `uvicorn`; the compose healthcheck hits `/api/v1/system/health`                                                                                  |
| `worker`   | API image                | `python -m careerforge_api.workers.main` — parses uploads off the queue                                                                          |
| `web`      | web image                | `next start`; `NEXT_PUBLIC_API_BASE_URL` is a **build arg**, not a runtime variable                                                              |

Ports are `${API_PORT:-8000}` and `${WEB_PORT:-3000}`, so both are overridable without editing the
file. The web image is built with the API URL inlined; changing that URL requires a rebuild, which is
the documented consequence of a Next.js public variable and is why it is a build arg rather than a
secret.

Verify:

```bash
curl -sf localhost:8000/api/v1/system/health | head -c 300   # {"success":true,"data":{"status":"ok",...}}
curl -sf localhost:8000/api/v1/system/ready  | head -c 300   # {"ready":true,"degraded":[...]}
open http://localhost:3000                                    # landing → /login → demo account
```

`/system/ready` reporting `ready: true` with `degraded: ["llm_provider","vector"]` is the **expected**
zero-key state: no API key means the heuristic provider, and no pgvector index means the in-process
retrieval index. Readiness deliberately does not fail for either; `/system` shows both on screen.

## 2. Managed services (public URL) **[unwitnessed]**

| piece       | service                   | configuration                                                                                                                             |
| ----------- | ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Web         | Vercel                    | root `apps/web`, build `pnpm --filter @careerforge/web build`; set `NEXT_PUBLIC_API_BASE_URL` to the API's public URL **before** building |
| API         | Render or Railway         | `infra/docker/Dockerfile.api`; start `uvicorn careerforge_api.main:app --host 0.0.0.0 --port $PORT`; pre-deploy `alembic upgrade head`    |
| Worker      | same host, second process | `python -m careerforge_api.workers.main`                                                                                                  |
| Database    | Neon or Supabase          | PostgreSQL 16 **with pgvector**; `DATABASE_URL=postgresql+asyncpg://…`                                                                    |
| Cache/queue | Upstash Redis             | `QUEUE_BACKEND=redis`, `REDIS_URL=rediss://…`                                                                                             |

Environment variables, grouped by what happens if they are wrong:

| variable                              | production value                               | if it is wrong                                                                                                                                                                                                           |
| ------------------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `ENVIRONMENT`                         | `production`                                   | `development` keeps debug behaviour and relaxes secret checks                                                                                                                                                            |
| `JWT_SECRET`                          | 32+ random characters (`openssl rand -hex 32`) | the API **refuses to start** in production if the secret is still the `.env.example` placeholder; a secret shorter than 32 characters is logged as a warning rather than refused, which is why the length is stated here |
| `DATABASE_URL`                        | `postgresql+asyncpg://…`                       | falls back to SQLite and the deployment loses durability                                                                                                                                                                 |
| `CORS_ORIGINS`                        | the exact web origin                           | the browser blocks every API call before the response is read; preflights fail with no server-side error                                                                                                                 |
| `TRUSTED_HOSTS`                       | the API's own hostname(s)                      | `*` disables the host check                                                                                                                                                                                              |
| `LLM_PROVIDER` + `<provider>_API_KEY` | `deepseek` (or `openai`)                       | with no key the chain ends at the heuristic provider, which is a working product — every response is marked `degraded` rather than pretending                                                                            |
| `QUEUE_BACKEND` / `REDIS_URL`         | `redis`                                        | falls back to the in-process queue, reported on `/system/health`                                                                                                                                                         |
| `RATE_LIMIT_*`                        | defaults from `docs/API.md` §1.7               | the AI budget counts only requests that can spend model tokens (`POST`/`PUT`/`PATCH`); reads are charged to `read`                                                                                                       |

Migrations are the deployment's job, not the application's: the app never runs `alembic` at boot on
PostgreSQL (the compose `migrate` service and the platform's pre-deploy hook do), while the SQLite
path calls `create_all` because it has no migration step by design.

## 3. After deploying: prove it, do not assume it

```bash
curl -sf https://<api-host>/api/v1/system/health
curl -sf https://<api-host>/api/v1/system/ready
curl -sf https://<api-host>/api/v1/system/version     # build identity: commit, build time, provider

# the strongest single check: the browser suite against the deployed URL
cd apps/web
E2E_BASE_URL=https://<web-host> E2E_API_URL=https://<api-host>/api/v1 pnpm test:e2e
```

Then re-run `python scripts/release_proof.py` with the deployed URLs and replace §2 of
`reports/release-readiness.md` with that output. Until then, **the release remains a candidate**:
`v1.0.0-rc.1` is tagged and `v1.0.0` should be tagged only once the image path and the live URL are
witnessed, because those are the two claims this repository currently refuses to make.

## 4. Rollback

- **Web**: Vercel keeps every deployment; promote the previous one. No migration involved.
- **API**: redeploy the previous image. Migrations in this project are additive (new tables and
  nullable columns), so the previous release runs against the newer schema; a destructive migration
  would need its own plan and there is none yet.
- **Data**: `POST /documents`, evidence rows and applications are user data; a rollback never deletes
  them. The one irreversible step is dropping a column, and no migration in `0001`–`0009` does.

## 5. Operational notes

- **Health vs readiness**: `/system/health` is liveness (the process answers, the database responds);
  `/system/ready` is readiness and reports `degraded` components without failing. A load balancer
  should use `/system/health` for restarts and `/system/ready` for traffic.
- **Uploads** are spooled to `storage_local_path` between the request and the worker. On a platform
  with an ephemeral filesystem that directory must be a mounted volume, or the worker will not find
  the file — the `s3` backend arrives in a later phase and is refused loudly today rather than
  silently ignored.
- **The rate limiter is in-process.** With more than one API replica, each replica enforces its own
  budget, so the effective limit multiplies; `/system/health` says `queue=inprocess` and the same
  section of `docs/API.md` states the limitation. A shared limiter belongs with the Redis queue.
- **Costs**: with a real provider, `/app/costs` reports real token counts and CNY/USD cost per run;
  runs whose usage the vendor did not report are marked `unavailable` and their counts are `null`, so
  the totals are a documented floor rather than a fabricated exact figure.
