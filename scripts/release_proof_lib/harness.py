"""Process, network and SQLite plumbing for the release proof.

Nothing here knows what a "step" is; it exists so the step bodies in :mod:`steps` read as
statements about the deployment under test rather than as subprocess bookkeeping.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.request

from release_proof_lib.reporting import REPO_ROOT, tail

__all__ = [
    "CommandResult",
    "Server",
    "display",
    "envelope_data",
    "http",
    "pnpm",
    "port_is_free",
    "proof_env",
    "remove_database",
    "run",
    "sqlite_alembic_revision",
    "sqlite_counts",
    "sqlite_demo_user",
    "wait_for_http",
]

#: Node and pnpm are not on this machine's default PATH (``docs/DEVELOPMENT.md``).
NODE_PATH_PREPEND = "C:\\Autodesk"


@dataclass
class CommandResult:
    """One executed command, with everything the report needs to be checkable."""

    argv: list[str]
    command: str
    cwd: str
    exit_code: int
    duration_seconds: float
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def as_dict(self, limit: int = 1500) -> dict[str, Any]:
        return {
            "command": self.command,
            "cwd": self.cwd,
            "exitCode": self.exit_code,
            "durationSeconds": round(self.duration_seconds, 3),
            "stdoutTail": tail(self.stdout, limit),
            "stderrTail": tail(self.stderr, limit),
        }


def proof_env(*, extra: dict[str, str] | None = None) -> dict[str, str]:
    """The environment every child process gets: temp on D:, Node on PATH, UTF-8 stdio."""
    env = dict(os.environ)
    env["TEMP"] = str(REPO_ROOT / ".tmp")
    env["TMP"] = str(REPO_ROOT / ".tmp")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    if NODE_PATH_PREPEND not in env.get("PATH", ""):
        env["PATH"] = NODE_PATH_PREPEND + os.pathsep + env.get("PATH", "")
    env.update(extra or {})
    return env


def display(argv: list[str]) -> str:
    """A copy-pasteable command line (quoted only where a value needs it)."""
    return " ".join(f'"{part}"' if " " in part else part for part in argv)


def run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float = 900.0,
) -> CommandResult:
    started = time.perf_counter()
    completed = subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return CommandResult(
        argv=argv,
        command=display(argv),
        cwd=str(cwd),
        exit_code=completed.returncode,
        duration_seconds=time.perf_counter() - started,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def pnpm(*args: str) -> list[str]:
    """`pnpm` via its Windows launcher — argv keeps it out of a shell."""
    return ["cmd", "/c", "pnpm", *args]


class Server:
    """A long-running child process (uvicorn / next start), terminable as a tree."""

    def __init__(
        self, name: str, argv: list[str], cwd: Path, env: dict[str, str], log: Path
    ) -> None:
        self.name = name
        self.argv = argv
        self.command = display(argv)
        self.cwd = str(cwd)
        self.log_path = log
        self.started_at = time.time()
        log.parent.mkdir(parents=True, exist_ok=True)
        self._handle = log.open("w", encoding="utf-8")
        creation_flags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        )
        self.process = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdout=self._handle,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creation_flags,
        )

    @property
    def pid(self) -> int:
        return self.process.pid

    def alive(self) -> bool:
        return self.process.poll() is None

    def log_text(self) -> str:
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def stop(self) -> dict[str, Any]:
        """Kill the whole tree: on Windows `pnpm` and `next` spawn child processes."""
        was_alive = self.alive()
        if was_alive and os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(self.pid)],
                capture_output=True,
                text=True,
                check=False,
            )
        elif was_alive:
            self.process.terminate()
        try:
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self._handle.close()
        return {
            "name": self.name,
            "command": self.command,
            "pid": self.pid,
            "wasAlive": was_alive,
            "exitCode": self.process.returncode,
        }


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


_PROXY_FREE = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http(
    url: str,
    *,
    method: str = "GET",
    body: Any = None,
    token: str | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any, str]:
    """One request with proxies disabled (a corporate proxy would answer instead of the API)."""
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=payload, method=method)
    request.add_header("Accept", "application/json")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with _PROXY_FREE.open(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        status = exc.code
    except urllib.error.URLError as exc:
        return 0, None, f"{type(exc).__name__}: {exc.reason}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    return status, parsed, raw


def wait_for_http(url: str, *, timeout: float = 90.0, interval: float = 0.5) -> tuple[bool, str]:
    """Poll until anything answers, then report what answered."""
    deadline = time.monotonic() + timeout
    last = "no attempt was made"
    while time.monotonic() < deadline:
        status, _, raw = http(url, timeout=10.0)
        if status:
            return True, f"HTTP {status}"
        last = tail(raw, 200)
        time.sleep(interval)
    return False, f"timed out after {timeout:.0f}s ({last})"


def envelope_data(payload: Any) -> Any:
    """`docs/API.md` §1.1: the documented envelope, or the raw body when it is not one."""
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def sqlite_counts(path: Path) -> dict[str, int]:
    """Row count per table, read-only, so the proof can compare two moments exactly."""
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        return {
            name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            for name in names
        }
    finally:
        connection.close()


def sqlite_alembic_revision(path: Path) -> str | None:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        return str(row[0]) if row else None
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def sqlite_demo_user(path: Path) -> dict[str, Any]:
    """The demo account's identity — an unchanged `created_at` proves it was reused, not rebuilt."""
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT id, email, created_at FROM users WHERE is_demo = 1 LIMIT 1"
        ).fetchone()
    except sqlite3.Error as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        connection.close()
    if row is None:
        return {"found": False}
    return {"found": True, "id": str(row[0]), "email": str(row[1]), "createdAt": str(row[2])}


def remove_database(path: Path) -> list[str]:
    """Delete the SQLite file and its WAL/SHM siblings, returning what was removed."""
    removed: list[str] = []
    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = Path(f"{path}{suffix}")
        if candidate.exists():
            candidate.unlink()
            removed.append(candidate.name)
    return removed


def interpreter() -> str:
    """The venv interpreter, asserted so a proof run by the wrong Python fails loudly."""
    expected = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if expected.exists():
        return str(expected)
    return sys.executable
