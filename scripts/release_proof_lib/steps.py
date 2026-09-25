"""The seven steps of the release proof.

Each step is a closure over the shared :class:`Context`, so the servers started in one step are
still addressable in the next. Every step declares what it *proves*, not just what it runs.

The two web-side steps (`built_frontend`, `contract_smoke`) live in :mod:`steps_web` and are
re-exported here, so the entry point keeps reading `steps.<name>` for every step while each file
stays inside the repository's 500-line limit.
"""

from __future__ import annotations

from collections.abc import Callable
import json
import shutil
from typing import Any

from release_proof_lib.harness import (
    Server,
    display,
    envelope_data,
    http,
    port_is_free,
    proof_env,
    remove_database,
    run,
    sqlite_alembic_revision,
    sqlite_counts,
    sqlite_demo_user,
    wait_for_http,
)
from release_proof_lib.reporting import (
    PROOF_DB,
    PROOF_JWT_SECRET,
    REPO_ROOT,
    WORK_DIR,
    Context,
    Step,
    requirement,
    tail,
)
from release_proof_lib.steps_web import built_frontend, contract_smoke

__all__ = [
    "built_frontend",
    "container_runtime",
    "contract_smoke",
    "fresh_database",
    "production_api",
    "restart_durability",
    "seed_idempotency",
    "server_command_note",
]

API_DIR = REPO_ROOT / "apps" / "api"
WEB_DIR = REPO_ROOT / "apps" / "web"


def container_runtime(step: Step) -> None:
    """Verify — do not assume — that there is no container runtime on this machine."""
    probes: dict[str, Any] = {}
    for tool in ("docker", "podman", "docker-compose"):
        found = shutil.which(tool)
        if found is None:
            probes[tool] = {"present": False, "probe": f"where {tool}", "result": "not found"}
            continue
        result = step.record(run([tool, "--version"], cwd=REPO_ROOT, env=proof_env(), timeout=30))
        probes[tool] = {
            "present": True,
            "path": found,
            "probe": result.command,
            "exitCode": result.exit_code,
            "stdoutTail": tail(result.stdout, 200),
        }
    step.observe("runtimeProbe", probes)
    step.observe("composeFilePresent", (REPO_ROOT / "docker-compose.yml").exists())
    step.observe("postgresClientInstalled", shutil.which("psql") is not None)
    step.observe("redisServerInstalled", shutil.which("redis-server") is not None)
    requirement(
        not probes["docker"]["present"] and not probes["podman"]["present"],
        "a container runtime is installed after all — this run must then be redone containerized",
    )
    step.note(
        "No container runtime: `docker compose up` cannot be executed here, so everything below is "
        "the native equivalent and no artefact claims otherwise."
    )


def _migration_env(environment: str = "test") -> dict[str, str]:
    return proof_env(
        extra={
            "USE_SQLITE": "true",
            "SQLITE_PATH": PROOF_DB.as_posix(),
            "ENVIRONMENT": environment,
        }
    )


def fresh_database(ctx: Context, python: str) -> Callable[[Step], None]:
    def body(step: Step) -> None:
        step.observe("databasePath", str(PROOF_DB.relative_to(REPO_ROOT)))
        step.observe("existedBefore", PROOF_DB.exists())
        step.observe("filesRemoved", remove_database(PROOF_DB))
        requirement(not PROOF_DB.exists(), "the database file still exists after deletion")

        env = _migration_env()
        base = [python, "-m", "alembic", "-c", "alembic.ini"]
        upgrade = step.record(run([*base, "upgrade", "head"], cwd=API_DIR, env=env))
        requirement(upgrade.ok, f"`alembic upgrade head` exited {upgrade.exit_code}")
        current = step.record(run([*base, "current"], cwd=API_DIR, env=env))
        heads = step.record(run([*base, "heads"], cwd=API_DIR, env=env))
        requirement(current.ok, f"`alembic current` exited {current.exit_code}")
        requirement(heads.ok, f"`alembic heads` exited {heads.exit_code}")

        revision = sqlite_alembic_revision(PROOF_DB)
        head = heads.stdout.strip().split(" ")[0] if heads.stdout.strip() else ""
        step.observe("revisionAfterUpgrade", revision)
        step.observe("alembicCurrent", current.stdout.strip())
        step.observe("alembicHeads", heads.stdout.strip())
        requirement(PROOF_DB.exists(), "the migration did not create the database file")
        step.observe("tablesCreated", len(sqlite_counts(PROOF_DB)))
        requirement(
            revision is not None and revision == head,
            f"alembic_version={revision!r} does not match head={head!r}",
        )
        step.note(
            "The database file was deleted at the start of this step (see `filesRemoved` and "
            "`existedBefore`), so the migration ran against nothing at all: this is 0 → head, not "
            "an upgrade of an existing schema."
        )

    return body


def seed_idempotency(ctx: Context, python: str) -> Callable[[Step], None]:
    def body(step: Step) -> None:
        env = _migration_env()
        after_migrations = sqlite_counts(PROOF_DB)
        first = step.record(run([python, "scripts/seed.py"], cwd=REPO_ROOT, env=env, timeout=300))
        requirement(first.ok, f"the first seed run exited {first.exit_code}")
        after_first = sqlite_counts(PROOF_DB)
        second = step.record(run([python, "scripts/seed.py"], cwd=REPO_ROOT, env=env, timeout=300))
        requirement(second.ok, f"the second seed run exited {second.exit_code}")
        after_second = sqlite_counts(PROOF_DB)

        step.observe("countsAfterMigrations", after_migrations)
        step.observe("countsAfterFirstSeed", after_first)
        step.observe("countsAfterSecondSeed", after_second)
        step.observe("exitCodes", {"first": first.exit_code, "second": second.exit_code})
        step.observe("demoUserAfterSeed", sqlite_demo_user(PROOF_DB))

        changed = {
            table: {"first": after_first.get(table), "second": after_second.get(table)}
            for table in after_first
            if after_second.get(table) != after_first[table]
        }
        added = {
            table: after_first.get(table, 0) - after_migrations.get(table, 0)
            for table in after_first
            if after_first.get(table, 0) != after_migrations.get(table, 0)
        }
        step.observe("rowsAddedByFirstSeed", added)
        step.observe("tablesChangedBySecondSeed", changed)
        requirement(
            not changed,
            f"the second seed run changed row counts: {json.dumps(changed, sort_keys=True)}",
        )
        requirement(
            bool(added), "the first seed run inserted nothing — the seed script did no work"
        )
        step.note(
            "Idempotency is proved by counting every table before and after the second run: "
            "identical counts and exit code 0 mean no duplicate account, skill or taxonomy row. "
            "`docs/DATABASE.md` §6 asks for exactly this."
        )

    return body


def api_env(ctx: Context) -> dict[str, str]:
    """Production-like settings on the zero-key provider — see the module docstring."""
    return proof_env(
        extra={
            "USE_SQLITE": "true",
            "SQLITE_PATH": PROOF_DB.as_posix(),
            "ENVIRONMENT": "production",
            "JWT_SECRET": PROOF_JWT_SECRET,
            "LLM_PROVIDER": "heuristic",
            "LLM_FALLBACK_PROVIDER": "heuristic",
            "QUEUE_BACKEND": "inprocess",
            "STORAGE_BACKEND": "local",
            "CORS_ORIGINS": f"{ctx.web_base},{ctx.web_base.replace('127.0.0.1', 'localhost')}",
            "TRUSTED_HOSTS": "*",
        }
    )


def _start_api(ctx: Context, python: str, log_name: str) -> tuple[Server, dict[str, Any]]:
    server = Server(
        name="api",
        argv=[
            python,
            "-m",
            "uvicorn",
            "careerforge_api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(ctx.api_port),
        ],
        cwd=API_DIR,
        env=api_env(ctx),
        log=WORK_DIR / log_name,
    )
    ready, detail = wait_for_http(f"{ctx.api_base}/system/health", timeout=120)
    return server, {
        "command": server.command,
        "pid": server.pid,
        "logFile": str(server.log_path.relative_to(REPO_ROOT)),
        "ready": ready,
        "readyDetail": detail,
    }


def _require_safe_version_payload(payload: Any, raw: str) -> None:
    """`/system/version` is public: no path, no DSN, no host, no credential may appear in it."""
    for key, value in (payload or {}).items():
        if not isinstance(value, str):
            continue
        requirement("\\" not in value, f"/system/version leaked a path in {key}: {value!r}")
        requirement("://" not in value, f"/system/version leaked a URL in {key}: {value!r}")
        requirement(not value.startswith("/"), f"/system/version leaked a path in {key}: {value!r}")
    lowered = raw.lower()
    for needle in ("sqlite", ".db", "postgres", "jwt", "secret"):
        requirement(needle not in lowered, f"/system/version body mentions {needle!r}")


def production_api(ctx: Context, python: str) -> Callable[[Step], None]:
    def body(step: Step) -> None:
        requirement(port_is_free(ctx.api_port), f"port {ctx.api_port} is in use before the step")
        server, info = _start_api(ctx, python, "api-production.log")
        ctx.api = server
        step.observe("api", info)
        requirement(info["ready"], f"the API never became reachable: {info['readyDetail']}")

        health_status, health, health_raw = http(f"{ctx.api_base}/system/health")
        health_data = envelope_data(health) or {}
        step.observe(
            "health",
            {
                "url": f"{ctx.api_base}/system/health",
                "httpStatus": health_status,
                "status": health_data.get("status"),
                "provider": (health_data.get("meta") or {}).get("provider"),
                "version": health_data.get("version"),
            },
        )
        requirement(health_status == 200, f"GET /system/health returned {health_status}")
        requirement(
            bool(health_data.get("services")),
            f"GET /system/health carried no services: {tail(health_raw, 300)}",
        )

        ready_status, ready, _ = http(f"{ctx.api_base}/system/ready")
        ready_data = envelope_data(ready) or {}
        step.observe(
            "ready",
            {
                "url": f"{ctx.api_base}/system/ready",
                "httpStatus": ready_status,
                "status": ready_data.get("status"),
                "ready": ready_data.get("ready"),
                "gate": ready_data.get("gate"),
                "degraded": ready_data.get("degraded"),
            },
        )
        requirement(ready_status == 200, f"GET /system/ready returned {ready_status}")
        requirement(ready_data.get("ready") is True, "the zero-key deployment is not ready")
        requirement(
            "llm_provider" in (ready_data.get("degraded") or []),
            "readiness did not name the degraded provider — degradation must not be hidden",
        )

        version_status, version, version_raw = http(f"{ctx.api_base}/system/version")
        version_data = envelope_data(version) or {}
        step.observe(
            "version",
            {
                "url": f"{ctx.api_base}/system/version",
                "httpStatus": version_status,
                "payload": version_data,
            },
        )
        requirement(version_status == 200, f"GET /system/version returned {version_status}")
        _require_safe_version_payload(version_data, version_raw)
        requirement(
            version_data.get("environment") == "production",
            f"/system/version reports environment={version_data.get('environment')!r}",
        )

        head = run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, env=proof_env(), timeout=30)
        step.observe(
            "gitHead",
            {"command": head.command, "exitCode": head.exit_code, "stdout": head.stdout.strip()},
        )
        if head.ok and head.stdout.strip():
            requirement(
                version_data.get("commit") == head.stdout.strip(),
                "/system/version reports a commit that is not this checkout's HEAD",
            )
        step.note(
            "`LLM_PROVIDER=heuristic` is the zero-key deployment: the public demo must run with no "
            "API key and no cloud account, so the deterministic provider is the honest choice. "
            "Readiness stays `ready` while naming `llm_provider` and `vector` as degraded — that is "
            "the distinction `/system/ready` exists to make."
        )

    return body


def restart_durability(ctx: Context, python: str) -> Callable[[Step], None]:
    def body(step: Step) -> None:
        requirement(ctx.api is not None, "the API was never started")

        # Write one row **through the API** before the restart. The seed's profile proves the
        # seed's work survived; this proves a row the running process wrote is still readable to
        # the next process, which is the durability claim the RC needs.
        login_status, login, login_raw = http(f"{ctx.api_base}/auth/demo", method="POST", body={})
        token = (envelope_data(login) or {}).get("accessToken") if login_status == 200 else None
        step.observe(
            "demoLoginBeforeRestart", {"httpStatus": login_status, "hasAccessToken": bool(token)}
        )
        requirement(
            login_status == 200 and bool(token),
            f"POST /auth/demo returned {login_status} before the restart: {tail(login_raw, 200)}",
        )
        write_status, write_payload, write_raw = http(
            f"{ctx.api_base}/evidence",
            method="POST",
            token=token,
            body={
                "title": "Release proof · restart durability",
                "snippet": (
                    "Manual evidence written through the API before the restart: STM32 FreeRTOS "
                    "motor-control firmware with CAN bus debugging."
                ),
                "locator": {"path": "release_proof.c", "line": 1},
            },
        )
        written = envelope_data(write_payload) or {}
        evidence_id = written.get("id") if isinstance(written, dict) else None
        step.observe(
            "evidenceWrittenBeforeRestart",
            {"httpStatus": write_status, "id": evidence_id, "title": written.get("title")},
        )
        requirement(
            write_status in {200, 201} and bool(evidence_id),
            f"POST /evidence returned {write_status}: {tail(write_raw, 300)}",
        )

        # Baseline taken *after* the write: the comparison below must be about the restart, not
        # about the row this step just added.
        before_counts = sqlite_counts(PROOF_DB)
        before_user = sqlite_demo_user(PROOF_DB)
        before_revision = sqlite_alembic_revision(PROOF_DB)
        step.observe("stopFirstInstance", ctx.api.stop())
        for _ in range(40):
            if port_is_free(ctx.api_port):
                break
            # The socket needs a moment to leave TIME_WAIT after the tree is killed.
            import time as _time

            _time.sleep(0.5)
        requirement(
            port_is_free(ctx.api_port), f"port {ctx.api_port} is still held after stopping the API"
        )

        server, info = _start_api(ctx, python, "api-restart.log")
        ctx.api = server
        step.observe("restartInstance", info)
        requirement(
            info["ready"], f"the restarted API never became reachable: {info['readyDetail']}"
        )

        after_counts = sqlite_counts(PROOF_DB)
        after_user = sqlite_demo_user(PROOF_DB)
        step.observe("countsBeforeRestart", before_counts)
        step.observe("countsAfterRestart", after_counts)
        step.observe("demoUserBeforeRestart", before_user)
        step.observe("demoUserAfterRestart", after_user)
        step.observe(
            "alembicRevisionUnchanged",
            {"before": before_revision, "after": sqlite_alembic_revision(PROOF_DB)},
        )
        requirement(
            before_counts == after_counts,
            "row counts changed across the restart — something re-seeded or re-migrated",
        )
        requirement(
            before_user.get("id") == after_user.get("id")
            and before_user.get("createdAt") == after_user.get("createdAt"),
            "the demo account was recreated by the restart rather than reused",
        )

        status, login, login_raw = http(f"{ctx.api_base}/auth/demo", method="POST", body={})
        token = (envelope_data(login) or {}).get("accessToken") if status == 200 else None
        step.observe("demoLoginAfterRestart", {"httpStatus": status, "hasAccessToken": bool(token)})
        requirement(
            status == 200 and bool(token),
            f"POST /auth/demo returned {status}: {tail(login_raw, 200)}",
        )
        ctx.token = token

        reads: dict[str, Any] = {}
        # `GET /documents` caps `limit` at 100 (`routers/documents.py`); asking for 200 is a 400.
        # `/profile` is the read that proves the demo account's *data* survived: the seed writes a
        # candidate with projects, experiences and declared skills, so a non-empty payload after the
        # restart is data, not just a live process. The evidence graph is recorded but deliberately
        # not gated — the seeded account holds no evidence rows, so an empty graph is the truth.
        for path in (
            "/profile",
            "/evidence-graph?depth=2",
            "/evidence?limit=200",
            "/documents?limit=100",
            "/system/version",
        ):
            read_status, read_payload, read_raw = http(f"{ctx.api_base}{path}", token=token)
            data = envelope_data(read_payload)
            entry: dict[str, Any] = {"httpStatus": read_status, "bytes": len(read_raw)}
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                entry["items"] = len(data["items"])
            if isinstance(data, dict) and isinstance(data.get("nodes"), list):
                entry["nodes"] = len(data["nodes"])
                entry["edges"] = len(data.get("edges") or [])
            if path == "/profile" and isinstance(data, dict):
                for field in ("projects", "experiences", "educations", "skills"):
                    value = data.get(field)
                    entry[field] = len(value) if isinstance(value, list) else None
                entry["slug"] = data.get("slug")
            reads[path] = entry
            requirement(read_status == 200, f"GET {path} returned {read_status} after the restart")
            requirement(
                len(read_raw) > 64, f"GET {path} returned a near-empty body after the restart"
            )
            if path == "/evidence?limit=200" and isinstance(data, dict):
                rows = data.get("items") or []
                step.observe(
                    "evidenceRowSurvivedRestart",
                    {
                        "id": evidence_id,
                        "present": any(row.get("id") == evidence_id for row in rows),
                        "rows": len(rows),
                    },
                )
                requirement(
                    any(row.get("id") == evidence_id for row in rows),
                    "the evidence row written through the API before the restart is not readable "
                    "after it, so the restart is not proved",
                )
        step.observe("authenticatedReadsAfterRestart", reads)
        seeded_projects = reads["/profile"].get("projects") or 0
        seeded_skills = reads["/profile"].get("skills") or 0
        requirement(
            seeded_projects >= 1 and seeded_skills >= 1,
            "the restarted API returned the demo profile without its seeded projects/skills, so the "
            "restart is not proved",
        )
        step.note(
            "No `alembic upgrade` and no `scripts/seed.py` ran between the two starts: the restarted "
            "process read the same tables, the same alembic revision and the same demo account row "
            "(identical id and created_at), it still served the seeded profile "
            f"({seeded_projects} projects, {seeded_skills} declared skills), and the evidence row "
            "written through the API before the restart came back with the same id. The API's startup does "
            "call `ensure_demo_user` on every boot — it is idempotent, and that is the behaviour "
            "being proved, not a claim that startup skips the call."
        )

    return body


def server_command_note(ctx: Context) -> str:
    """One line naming the two servers, for the report header."""
    parts = [server.command for server in (ctx.api, ctx.web) if server is not None]
    return " | ".join(parts) if parts else display([])
