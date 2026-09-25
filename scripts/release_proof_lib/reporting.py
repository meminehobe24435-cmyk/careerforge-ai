"""Step recording and the two report writers (JSON + Markdown).

The report is the deliverable, so the data model here is deliberately flat: one :class:`Step` per
claim, carrying the commands that were run, their exit codes and the observed result. A step that
fails does not stop the run — the remaining steps still produce evidence, and the summary says which
one failed and why.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
WORK_DIR = REPO_ROOT / ".tmp" / "release-proof"
REPORT_JSON = REPO_ROOT / "reports" / "release-proof.json"
REPORT_MD = REPO_ROOT / "reports" / "release-proof.md"
PROOF_DB = REPO_ROOT / "data" / "release_proof.db"

#: A production JWT secret must be long and must not be the documented development default.
PROOF_JWT_SECRET = "release-proof-secret-0123456789abcdef0123456789abcdef"


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def tail(text: str, limit: int = 1500) -> str:
    """The last ``limit`` characters — enough to see the failure, not the whole log."""
    stripped = text.strip()
    return stripped if len(stripped) <= limit else "…" + stripped[-limit:]


class Fail(Exception):
    """A step assertion failed — the step is recorded as FAIL with this message."""


def requirement(condition: bool, message: str) -> None:
    if not condition:
        raise Fail(message)


@dataclass
class Step:
    """One claim, its commands and its observed result."""

    id: str
    title: str
    status: str = "NOT RUN"
    reason: str | None = None
    started_at: str = field(default_factory=utc_now)
    finished_at: str | None = None
    duration_seconds: float = 0.0
    commands: list[Any] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def observe(self, key: str, value: Any) -> Any:
        self.observations[key] = value
        return value

    def note(self, text: str) -> None:
        self.notes.append(text)

    def record(self, result: Any) -> Any:
        self.commands.append(result)
        return result

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "reason": self.reason,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "durationSeconds": round(self.duration_seconds, 3),
            "commands": [command.as_dict() for command in self.commands],
            "observations": self.observations,
            "notes": self.notes,
        }


@dataclass
class Context:
    """Ports and live servers shared across the steps."""

    api_port: int
    web_port: int
    api_base: str
    web_base: str
    api: Any = None
    web: Any = None
    token: str | None = None


def step(
    recorder: list[Step], step_id: str, title: str
) -> Callable[[Callable[[Step], None]], None]:
    """Wrap a step body so a failure is recorded instead of ending the run."""

    def decorate(body: Callable[[Step], None]) -> None:
        current = Step(id=step_id, title=title)
        recorder.append(current)
        started = datetime.now(UTC)
        try:
            body(current)
        except Fail as exc:
            current.status = "FAIL"
            current.reason = str(exc)
        except Exception as exc:  # a proof records failures; it does not crash on them
            current.status = "FAIL"
            current.reason = f"{type(exc).__name__}: {exc}"
        else:
            current.status = "PASS"
        finally:
            current.duration_seconds = (datetime.now(UTC) - started).total_seconds()
            current.finished_at = utc_now()

    return decorate


#: Steps this proof deliberately does not run, each with a reason a reader can check.
NOT_RUN: list[dict[str, str]] = [
    {
        "title": "`docker compose up` (the containerized path)",
        "reason": (
            "docker, podman and docker-compose are not installed on this machine (probed in step 1, "
            "not assumed). The native equivalent is what this machine can produce, and nothing in "
            "this artefact claims a compose run happened."
        ),
    },
    {
        "title": "PostgreSQL migration path (`DATABASE_URL=postgresql+asyncpg://…`)",
        "reason": (
            "no PostgreSQL server or client is installed (no `psql` on PATH, nothing listening on "
            "5432), so `alembic upgrade head` is proved on the SQLite path only. The migrations are "
            "dialect-aware, but that is not evidence."
        ),
    },
    {
        "title": "Redis queue backend (`QUEUE_BACKEND=redis`)",
        "reason": (
            "no Redis server is installed. The deployment runs the in-process queue, and "
            "`/system/health` reports `queue=inprocess`; the Redis path is NOT RUN."
        ),
    },
    {
        "title": "Durable vector index (pgvector / embeddings table)",
        "reason": (
            "not implemented in this build — `/system/health` reports `vector: degraded "
            "(in_memory_index)`. Readiness names it and stays `ready`, which is the documented "
            "behaviour, not a pass for a durable index."
        ),
    },
    {
        "title": "Live cloud run: real LLM provider (DeepSeek / OpenAI) and a public deployment",
        "reason": (
            "no cloud account or API key is available to this machine, and this release is the "
            "zero-key demo. `LLM_PROVIDER=heuristic` is therefore the honest production-like "
            "setting, and the provider degradation is reported rather than hidden."
        ),
    },
    {
        "title": "Browser-driven walkthrough of the built app",
        "reason": (
            "this proof asserts the built routes over HTTP; browser-level interaction (including "
            "`locator.click()` on graph nodes) is covered by `pnpm --filter @careerforge/web "
            "test:e2e`, which is run and reported separately in the phase report."
        ),
    },
]


def _step_summary(item: dict[str, Any]) -> str:
    observations = item.get("observations", {})
    if "countsAfterSecondSeed" in observations:
        changed = observations.get("tablesChangedBySecondSeed") or {}
        added = observations.get("rowsAddedByFirstSeed") or {}
        return (
            f"seed added {sum(added.values())} rows across {len(added)} tables; "
            f"second run changed {len(changed)} tables"
        )
    if "checksPassed" in observations:
        return f"{observations['checksPassed']} smoke checks passed"
    if "pages" in observations:
        return ", ".join(
            f"{name}={page['httpStatus']}" for name, page in observations["pages"].items()
        )
    if "revisionAfterUpgrade" in observations:
        return (
            f"revision={observations['revisionAfterUpgrade']}, "
            f"tables={observations.get('tablesCreated')}"
        )
    if "ready" in observations:
        return f"health/ready/version answered; degraded={observations['ready'].get('degraded')}"
    if "countsAfterRestart" in observations:
        return "row counts and demo identity unchanged; authenticated reads OK"
    if "runtimeProbe" in observations:
        return "no container runtime present"
    return "see the JSON artefact"


def _version_of(argv: list[str], env: dict[str, str]) -> str:
    try:
        result = subprocess.run(
            argv,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    lines = (result.stdout or result.stderr).strip().splitlines()
    return lines[-1].strip() if lines else "unavailable"


def build_document(
    steps: list[Step],
    ctx: Context,
    not_run: list[dict[str, str]],
    env: dict[str, str],
) -> dict[str, Any]:
    passed = sum(1 for item in steps if item.status == "PASS")
    failed = sum(1 for item in steps if item.status == "FAIL")
    not_run_steps = sum(1 for item in steps if item.status == "NOT RUN")
    probe = next(
        (
            item.observations.get("runtimeProbe", {})
            for item in steps
            if item.id == "container-runtime"
        ),
        {},
    )
    return {
        "schemaVersion": 1,
        "phase": "PHASE 14",
        "generatedAt": utc_now(),
        "containerized": False,
        "containerizedReason": (
            "No container runtime on this machine: `docker`, `podman` and `docker-compose` are all "
            "absent (probed and recorded in the `container-runtime` step), so `docker compose up` "
            "could not be executed. Every step below was run natively."
        ),
        "containerRuntimeProbe": probe,
        "environment": {
            "os": f"{platform.system()} {platform.release()} ({platform.version()})",
            "python": sys.version.split()[0],
            "pythonInterpreter": env.get("PROOF_PYTHON", sys.executable),
            "node": _version_of(["node", "--version"], env),
            "pnpm": _version_of(["cmd", "/c", "pnpm", "--version"], env),
            "database": "SQLite (aiosqlite) — no PostgreSQL server is installed",
            "queue": "inprocess — no Redis server is installed",
            "llmProvider": "heuristic (the zero-key deployment)",
            "apiBase": ctx.api_base,
            "webBase": ctx.web_base,
            "proofDatabase": str(PROOF_DB.relative_to(REPO_ROOT)),
        },
        "summary": {
            "status": "fail" if failed else "pass",
            "total": len(steps),
            "passed": passed,
            "failed": failed,
            "notRun": not_run_steps,
            "durationSeconds": round(sum(item.duration_seconds for item in steps), 3),
        },
        "steps": [item.as_dict() for item in steps],
        "notRun": not_run,
    }


def render_markdown(document: dict[str, Any]) -> str:
    summary = document["summary"]
    lines = [
        "# Release proof — native fresh-install path",
        "",
        f"- generated: `{document['generatedAt']}`",
        f"- overall: **{summary['status'].upper()}** — {summary['passed']} passed, "
        f"{summary['failed']} failed, {summary['notRun']} not run",
        f"- containerized: **{str(document['containerized']).lower()}** — "
        f"{document['containerizedReason']}",
        "",
        "## What this proves, and what it is not",
        "",
        "This machine has no Docker, Podman, PostgreSQL or Redis (probed in step 1, not assumed), so",
        "**`docker compose up` was not run and no artefact here claims it was.** The steps below are",
        "the native equivalent: empty file → `alembic upgrade head` → seed twice → a production-mode",
        "`uvicorn` on the zero-key provider → the built Next.js app served by `next start` → the",
        "contract smoke test → a restart against the same database.",
        "",
        "## Environment",
        "",
        "| fact | value |",
        "| --- | --- |",
    ]
    lines += [f"| {key} | {value} |" for key, value in document["environment"].items()]
    lines += ["", "## Steps", "", "| # | step | status | result |", "| --- | --- | --- | --- |"]
    for index, item in enumerate(document["steps"], start=1):
        detail = item.get("reason") or _step_summary(item)
        lines.append(f"| {index} | {item['title']} | {item['status']} | {detail} |")

    for index, item in enumerate(document["steps"], start=1):
        lines += ["", f"### {index}. {item['title']} — {item['status']}", ""]
        if item.get("reason"):
            lines += [f"**Reason:** {item['reason']}", ""]
        for command in item["commands"]:
            lines += [
                "```",
                f"$ {command['command']}    # cwd={command['cwd']}",
                f"exit={command['exitCode']} in {command['durationSeconds']}s",
                "```",
            ]
            if command["stdoutTail"]:
                lines += ["```text", command["stdoutTail"], "```"]
            if command["stderrTail"]:
                lines += ["```text", command["stderrTail"], "```"]
        if item["observations"]:
            lines += ["```json", json.dumps(item["observations"], indent=2, sort_keys=True), "```"]
        lines += [f"> {note}" for note in item["notes"]]

    if document["notRun"]:
        lines += ["", "## NOT RUN", "", "| step | precise reason |", "| --- | --- |"]
        lines += [f"| {entry['title']} | {entry['reason']} |" for entry in document["notRun"]]

    lines += [
        "",
        "## Machine-readable evidence",
        "",
        "`reports/release-proof.json` carries the same steps with the full command lines, exit",
        "codes, durations and observation payloads.",
        "",
    ]
    return "\n".join(lines)


def write_reports(document: dict[str, Any]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(document, indent=2), encoding="utf-8")
    REPORT_MD.write_text(render_markdown(document), encoding="utf-8")
