"""The two web-side steps of the release proof: the built app and the contract smoke test.

Split out of :mod:`steps` to keep every file inside the repository's 500-line limit
(``scripts/check_file_length.py``); the steps themselves are unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
import re
import shutil
from typing import Any

from release_proof_lib.harness import (
    Server,
    http,
    pnpm,
    port_is_free,
    proof_env,
    run,
    wait_for_http,
)
from release_proof_lib.reporting import REPO_ROOT, WORK_DIR, Context, Step, requirement

WEB_DIR = REPO_ROOT / "apps" / "web"
SMOKE_CHECK_PATTERN = re.compile(r"(\d+)\s+checks passed", re.IGNORECASE)


def built_frontend(ctx: Context) -> Callable[[Step], None]:
    def body(step: Step) -> None:
        requirement(port_is_free(ctx.web_port), f"port {ctx.web_port} is in use before the step")
        env = proof_env(extra={"NEXT_PUBLIC_API_BASE_URL": ctx.api_base})
        dist_dir = WEB_DIR / ".next"
        # Build from nothing, like the database step: a stale `.next` can serve an artefact that no
        # longer matches the source, and a half-written one fails the build for the wrong reason.
        step.observe("distExistedBefore", dist_dir.exists())
        shutil.rmtree(dist_dir, ignore_errors=True)
        requirement(not dist_dir.exists(), "the previous build output could not be removed")

        build = step.record(
            run(pnpm("--filter", "@careerforge/web", "build"), cwd=REPO_ROOT, env=env, timeout=1200)
        )
        requirement(build.ok, f"`next build` exited {build.exit_code}")
        build_id = dist_dir / "BUILD_ID"
        step.observe(
            "buildOutput",
            {
                "distDir": "apps/web/.next",
                "buildId": build_id.read_text(encoding="utf-8").strip()
                if build_id.exists()
                else None,
                "requiredServerFiles": (dist_dir / "required-server-files.json").exists(),
            },
        )
        requirement(build_id.exists(), "the build produced no BUILD_ID — no production output")

        server = Server(
            name="web",
            argv=pnpm("--filter", "@careerforge/web", "start", "--port", str(ctx.web_port)),
            cwd=REPO_ROOT,
            env=env,
            log=WORK_DIR / "web-start.log",
        )
        ctx.web = server
        ready, detail = wait_for_http(f"{ctx.web_base}/login", timeout=120)
        step.observe(
            "nextStart",
            {
                "command": server.command,
                "pid": server.pid,
                "logFile": str(server.log_path.relative_to(REPO_ROOT)),
                "ready": ready,
                "readyDetail": detail,
            },
        )
        requirement(ready, f"`next start` never served a page: {detail}")

        pages = {
            "landing": "/",
            "login": "/login",
            "system": "/system",
            "authenticated-dashboard": "/app/dashboard",
        }
        observed: dict[str, Any] = {}
        for name, path in pages.items():
            status, _, raw = http(f"{ctx.web_base}{path}", timeout=30)
            observed[name] = {
                "path": path,
                "httpStatus": status,
                "bytes": len(raw),
                "hasAppShell": "__next" in raw or "self.__next_f" in raw,
            }
            requirement(status == 200, f"GET {path} returned {status}")
            requirement(len(raw) > 500, f"GET {path} returned an implausibly small body")
        step.observe("pages", observed)
        step.note(
            "These GETs prove the routes were built and served by `next start` — not `next dev`. "
            "They do **not** prove an authenticated session: `apps/web` gates the app shell in the "
            "browser from `localStorage`, so /app/dashboard serves the same shell to anyone. The "
            "authenticated half is proved with the demo token in the restart step."
        )

    return body


def contract_smoke(ctx: Context) -> Callable[[Step], None]:
    def body(step: Step) -> None:
        env = proof_env(extra={"API_BASE_URL": ctx.api_base})
        result = step.record(
            run(
                pnpm("--filter", "@careerforge/web", "smoke:api"),
                cwd=REPO_ROOT,
                env=env,
                timeout=900,
            )
        )
        combined = f"{result.stdout}\n{result.stderr}"
        match = SMOKE_CHECK_PATTERN.search(combined)
        count = int(match.group(1)) if match else None
        step.observe("exitCode", result.exit_code)
        step.observe("checksPassed", count)
        step.observe(
            "summaryLine",
            next(
                (line for line in reversed(combined.splitlines()) if "checks passed" in line),
                None,
            ),
        )
        requirement(result.ok, f"`smoke:api` exited {result.exit_code}")
        requirement(count is not None and count > 0, "`smoke:api` reported no checks")
        step.note(
            "The smoke test is the frontend client's own contract test: it calls the live API "
            "through the same client and runtime guards the browser uses."
        )

    return body
