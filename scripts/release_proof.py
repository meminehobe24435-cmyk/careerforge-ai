#!/usr/bin/env python
"""Release proof — the fresh-install path, executed natively on this machine.

**There is no container in this proof, and the artefact says so.** Docker and Podman are not
installed here (probed in step 1, never assumed), so `docker compose up` cannot be run and nothing
produced by this script may imply that it was. What it does instead is the honest native equivalent
of the compose path:

1. delete a dedicated SQLite file, then `alembic upgrade head` from nothing (0 → head);
2. run the seed script twice and prove idempotency by counting every table both times;
3. start `uvicorn` with production-like settings on the **zero-key** provider
   (`LLM_PROVIDER=heuristic`) and read `health` / `ready` / `version`;
4. build the Next.js app and serve the built output with `next start`;
5. run the frontend's contract smoke test against that API;
6. restart the API against the same database and prove the demo account's data is still readable
   with no re-seed and no second migration.

Why `heuristic` in "production": it is the zero-key deployment this release ships. A public demo
must run with no API key and no cloud account, and the deterministic provider is what serves it.
Claiming a cloud provider would need a secret this machine does not have, and skipping the AI path
entirely would not be a proof of *this* deployment.

Usage (from the repository root, with the venv interpreter)::

    .venv\\Scripts\\python.exe scripts\\release_proof.py

Artefacts: `reports/release-proof.json` (machine-readable) and `reports/release-proof.md`.
Every step records the exact command, its exit code, its duration and the observed result; a step
that cannot be run is recorded as `NOT RUN` with the reason rather than omitted.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from release_proof_lib import harness, reporting, steps
from release_proof_lib.reporting import (
    WORK_DIR,
    Context,
    Step,
    step,
    write_reports,
)

__all__ = ["main"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Native release proof for PHASE 14.")
    parser.add_argument("--api-port", type=int, default=8341)
    parser.add_argument("--web-port", type=int, default=3341)
    parser.add_argument(
        "--keep-servers",
        action="store_true",
        help="leave the API and web processes running (debugging only)",
    )
    args = parser.parse_args()

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    python = harness.interpreter()
    env = harness.proof_env()
    env["PROOF_PYTHON"] = python

    ctx = Context(
        api_port=args.api_port,
        web_port=args.web_port,
        api_base=f"http://127.0.0.1:{args.api_port}/api/v1",
        web_base=f"http://127.0.0.1:{args.web_port}",
    )

    recorded: list[Step] = []
    step(recorded, "container-runtime", "Container runtime probe (expect: absent)")(
        steps.container_runtime
    )
    step(recorded, "fresh-database", "Fresh database: delete the SQLite file, migrate 0 → head")(
        steps.fresh_database(ctx, python)
    )
    step(recorded, "seed-idempotency", "Seed twice: identical row counts, no duplicates, exit 0")(
        steps.seed_idempotency(ctx, python)
    )
    step(recorded, "production-api", "Production-mode API on the zero-key provider")(
        steps.production_api(ctx, python)
    )
    step(recorded, "built-frontend", "Built frontend served by `next start` (not `next dev`)")(
        steps.built_frontend(ctx)
    )
    step(recorded, "contract-smoke", "`smoke:api` against the production-mode API")(
        steps.contract_smoke(ctx)
    )
    step(recorded, "restart-durability", "Restart on the same database: no migration, no re-seed")(
        steps.restart_durability(ctx, python)
    )

    teardown: list[dict[str, object]] = []
    if not args.keep_servers:
        for server in (ctx.web, ctx.api):
            if server is None:
                continue
            if server.alive():
                teardown.append(server.stop())
            else:
                teardown.append({"name": server.name, "command": server.command, "wasAlive": False})

    document = reporting.build_document(recorded, ctx, reporting.NOT_RUN, env)
    document["teardown"] = teardown
    document["serverCommands"] = steps.server_command_note(ctx)
    write_reports(document)

    summary = document["summary"]
    print(
        f"release proof: {summary['status'].upper()} — {summary['passed']} passed, "
        f"{summary['failed']} failed, {summary['notRun']} NOT RUN"
    )
    print(f"  {reporting.REPORT_JSON.relative_to(reporting.REPO_ROOT)}")
    print(f"  {reporting.REPORT_MD.relative_to(reporting.REPO_ROOT)}")
    for item in recorded:
        if item.status != "PASS":
            print(f"  ! {item.id}: {item.status} — {item.reason}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
