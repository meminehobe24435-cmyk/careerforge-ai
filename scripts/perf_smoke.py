"""Local API latency smoke test: P50 and P95 for the endpoints a page waits on.

What this is *not*: a benchmark. It runs against a development server on a laptop, with SQLite, on
a shared CI runner's worth of noise, and the numbers describe that machine and nothing else. What it
*is*: a regression tripwire. A change that turns a 12 ms dashboard read into 400 ms — a missing
index, an N+1 query, a payload built per row — shows up here immediately and shows up nowhere else,
because correctness tests do not measure time.

Four endpoints are chosen because they are **locally deterministic**: they read the database and
compute, and they call no model. Model latency is deliberately excluded: an LLM's response time is
not a property of this code, and gating on it would produce a number that fluctuates with someone
else's queue depth.

Usage (needs a running API)::

    python scripts/perf_smoke.py --base-url http://127.0.0.1:8317/api/v1 --repeats 20
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = REPO_ROOT / "reports" / "api-performance.json"

#: (label, path, needs auth). Model-calling endpoints are absent on purpose.
ENDPOINTS: tuple[tuple[str, str, bool], ...] = (
    ("GET /system/health", "/system/health", False),
    ("GET /dashboard", "/dashboard", True),
    ("GET /ai-runs?limit=50", "/ai-runs?limit=50", True),
    ("GET /ai-costs?range=7d", "/ai-costs?range=7d", True),
    ("GET /applications/board", "/applications/board", True),
)


def _percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile: with 20 samples, P95 is the 19th, not an interpolation."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * len(ordered)) - 1))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8317/api/v1")
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=3, help="discarded requests per endpoint")
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    import httpx

    client = httpx.Client(base_url=args.base_url, timeout=30.0)
    health = client.get("/system/health")
    if health.status_code != 200:
        print(f"the API at {args.base_url} is not answering ({health.status_code})")
        return 1
    token = client.post("/auth/demo").json()["data"]["accessToken"]
    headers = {"Authorization": f"Bearer {token}"}

    results: list[dict[str, Any]] = []
    for label, path, needs_auth in ENDPOINTS:
        request_headers = headers if needs_auth else {}
        for _ in range(args.warmup):
            client.get(path, headers=request_headers)
        samples: list[float] = []
        status = 0
        for _ in range(args.repeats):
            started = time.perf_counter()
            response = client.get(path, headers=request_headers)
            samples.append((time.perf_counter() - started) * 1000)
            status = response.status_code
        if status != 200:
            # A failing endpoint measured for latency would publish a fast number for a broken route.
            print(f"{label} answered {status}; refusing to report a latency for it")
            return 1
        results.append(
            {
                "endpoint": label,
                "samples": len(samples),
                "status": status,
                "p50_ms": round(statistics.median(samples), 2),
                "p95_ms": round(_percentile(samples, 0.95), 2),
                "min_ms": round(min(samples), 2),
                "max_ms": round(max(samples), 2),
            }
        )

    payload = {
        "schema_version": "1.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": args.base_url,
        "repeats": args.repeats,
        "warmup": args.warmup,
        "caveat": (
            "Local development server (SQLite, single process, laptop hardware). These are "
            "tripwires for a local regression, not a benchmark of the product: no concurrency, no "
            "network, one machine. Model-calling endpoints are excluded because an LLM's latency "
            "is not a property of this code."
        ),
        "endpoints": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    print(f"{'endpoint':28s} {'p50':>8s} {'p95':>8s} {'min':>8s} {'max':>8s}")
    for row in results:
        print(
            f"{row['endpoint']:28s} {row['p50_ms']:>7.2f}ms {row['p95_ms']:>7.2f}ms "
            f"{row['min_ms']:>7.2f}ms {row['max_ms']:>7.2f}ms"
        )
    print(f"→ {args.out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
