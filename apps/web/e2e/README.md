# End-to-end suite

The browser suite drives the real product against a real API: no mocks, no fixtures written into the
database by hand, no route interception. Everything it asserts is what the running stack returned.

```
e2e/
  helpers/      the API client, the session installer, the worker fixtures, the axe assertion
  *.spec.ts     the flows, one file per surface
```

## Running it

`playwright.config.ts` deliberately has **no `webServer` block**: the stack is two processes and the
order matters (the web bundle inlines the API base URL at build time, and the API has to know the
origin the browser will use). Start them yourself, in this order.

```powershell
# ── 1. the API on :8318 ───────────────────────────────────────────────────────────────────────────
$env:USE_SQLITE='true'; $env:SQLITE_PATH='D:/workspace/epan/data/e2e.db'
$env:ENVIRONMENT='development'
$env:JWT_SECRET='local-verification-secret-000000000000'
$env:LLM_PROVIDER='heuristic'
$env:CORS_ORIGINS='http://localhost:3318,http://127.0.0.1:3318'
$env:RATE_LIMIT_AI_PER_MIN='600'; $env:RATE_LIMIT_READ_PER_MIN='10000'
$env:RATE_LIMIT_WRITE_PER_MIN='10000'; $env:RATE_LIMIT_UPLOAD_PER_HOUR='500'
& D:\workspace\epan\.venv\Scripts\python.exe -m uvicorn careerforge_api.main:app --host 127.0.0.1 --port 8318

# ── 2. the web app on :3318, built against that API ───────────────────────────────────────────────
$env:NEXT_PUBLIC_API_BASE_URL='http://127.0.0.1:8318/api/v1'
pnpm --filter @careerforge/web build
pnpm --filter @careerforge/web start --port 3318

# ── 3. the suite ──────────────────────────────────────────────────────────────────────────────────
pnpm --filter @careerforge/web test:e2e            # desktop + mobile
pnpm --filter @careerforge/web test:e2e:mobile     # the mobile project alone
```

Browsers are never downloaded: `channel: 'chrome'` uses the installed Google Chrome, so
`playwright install` is not part of this project's setup and must not become part of it.

## Why the suite declares its own rate-limit budgets

The numbers in step 1 are not the product's defaults, and that is on purpose rather than a
convenience.

The suite is **one user driving ~45 flows in about ninety seconds** — a load no human produces. The
shipped AI budget is 20 requests per minute per user (`docs/API.md` §1.7). On a full run the bucket
ran dry near the end and the last two specs failed with a `429` that surfaces in the app as a failed
job analysis: _"Rate limit exceeded for ai requests"_. A red build that reads like a product bug is
worse than no build, so the stack the suite runs against declares its budgets explicitly.

This is the same decision `apps/api/tests/conftest.py` already makes for the unit suite
(`rate_limit_ai_per_min = 10_000`). What it is **not** is a weaker guarantee: the shipped defaults
are asserted in `apps/api/tests/test_rate_limit.py`, and the limiter itself is tested there too.

Two measured facts behind the numbers, both from the PHASE 14 run recorded in `docs/ROADMAP.md`:

- in the sixty seconds ending at the first `429` the suite made **33 requests to AI-marked paths**
  against a bucket that holds **20** — 23 of them `POST`s that spend model tokens, and 10 `GET`s that
  do not (`GET /jobs/{id}/match` × 5 and `GET /ai/interview/{id}` × 5);
- those ten reads were charged to the AI budget until PHASE 14 corrected the classification, so a
  single page visit billed two of the twenty. The fix removes 30% of the burn; it does not remove the
  need for this budget, because 23 spending calls per minute is still above 20.

## What the specs are allowed to assume

- **Setup is idempotent**: re-uploading the same résumé returns the existing document, re-importing
  the same text updates the same rows, re-analysing the same posting updates the same job, publishing
  keeps the slug. Each spec creates what it needs and does not depend on run order.
- **The evidence base is built once per worker** (`helpers/fixtures.ts`). `POST /profile/import` and
  `POST /documents/{id}/analyze` draw on the hourly upload bucket, and one setup per worker is also
  what a real user does: they import their material once, then use the product.
- **Nothing waits on a fixed delay.** Every wait is either Playwright's auto-waiting on a real
  element or `expect.poll` against the API's own state. `page.waitForTimeout` is not used.
- **A route that is not shipped is asserted as not shipped**, not skipped silently: the specs check
  that an unshipped destination is rendered as a non-clickable item rather than as a dead link.

## Gates, not reports

Two specs exist to fail a build rather than to inform a human:

- `a11y.spec.ts` — axe, on five pages × two viewports. `critical` and `serious` fail; `moderate` and
  `minor` are printed and attached as annotations, because a gate that also fires on a heading-order
  nit gets switched off and then guards nothing.
- `overflow.spec.ts` — no horizontal overflow at 375 / 768 / 1440.

Both run in CI as named steps (`.github/workflows/ci.yml`), so "accessibility failed" is its own red
or green line in the job.
