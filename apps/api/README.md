# CareerForge AI · API (`careerforge-api`)

FastAPI service that wraps the finished AI core (`packages/ai`) in the HTTP
contract frozen by [`docs/API.md`](../../docs/API.md): one response envelope, one
error-code table, session auth, rate limits and task polling.

PHASE 1 scope: the envelope, the middleware chain, the error model, `bcrypt` +
JWT auth, `/auth/*`, `/system/health`, `/system/info`, `/tasks/*`, the PHASE 1
tables ([`docs/DATABASE.md`](../../docs/DATABASE.md) §2) and the Alembic baseline.
Later phases add the domain endpoints (profile, documents, GitHub, evidence
graph, jobs, resume, interview, applications, analytics).

## Zero-dependency run (no PostgreSQL, no Redis, no Docker, no API key)

```powershell
# from the repository root
.\.venv\Scripts\python.exe -m pip install -e ".\packages\ai[dev]"
.\.venv\Scripts\python.exe -m pip install -e ".\apps\api[dev]"

$env:USE_SQLITE = "true"
cd apps\api
..\..\.venv\Scripts\python.exe -m alembic upgrade head
..\..\.venv\Scripts\python.exe -m uvicorn careerforge_api.main:app --port 8123
```

`USE_SQLITE=true` selects SQLite (`aiosqlite`), the in-process queue and the
heuristic provider through `careerforge_ai.config.Settings` — the API reuses that
resolution and never re-implements it.

```bash
curl -s -X POST http://127.0.0.1:8123/api/v1/auth/demo
curl -s http://127.0.0.1:8123/api/v1/system/health
curl -s http://127.0.0.1:8123/api/v1/system/info
```

## Tests

```powershell
cd apps\api
..\..\.venv\Scripts\python.exe -m pytest -q
```

The suite runs against SQLite by default and needs no external service. If
`USE_SQLITE=false` and `DATABASE_URL` point at PostgreSQL (the CI matrix in
`.github/workflows/ci.yml`), the same suite runs against that database instead:
table creation and migrations are idempotent and every test uses unique rows.

## Layout

| Path | Responsibility |
|---|---|
| `src/careerforge_api/main.py` | `create_app()` factory, lifespan, middleware wiring |
| `src/careerforge_api/core/` | settings extension, security (bcrypt/JWT), error model, JSON logging |
| `src/careerforge_api/middleware/` | request id → logging → CORS → rate limit → error handling → envelope |
| `src/careerforge_api/db/` | engine/session, naming conventions, SQLite⇄PostgreSQL type compatibility |
| `src/careerforge_api/models/` | PHASE 1 ORM tables with the documented `CHECK` constraints |
| `src/careerforge_api/schemas/` | Pydantic request/response models (envelope, pagination, auth, system, tasks) |
| `src/careerforge_api/repositories/` | user-scoped data access (every query filters `user_id`) |
| `src/careerforge_api/services/` | auth, demo seed, skill taxonomy sync, system probes |
| `src/careerforge_api/routers/` | `/auth`, `/system`, `/tasks` |
| `src/careerforge_api/workers/` | queue port (`InProcessQueue`, `RedisQueue` stub) and the worker entrypoint |
| `alembic/` | async-aware migration environment and the `0001_initial` baseline |
