# Contributing to CareerForge AI

Thanks for your interest. This project is primarily a portfolio-grade engineering artifact, but it is built to open-source standards and contributions are welcome.

## Before you start

1. Read [`docs/PRD.md`](docs/PRD.md) — it defines what this product is and, more importantly, **what it deliberately is not**.
2. Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/DECISIONS.md`](docs/DECISIONS.md) — most "why don't you just…" questions are answered there.
3. Check [`docs/ROADMAP.md`](docs/ROADMAP.md) for the current phase.

## Development setup

Two supported paths. Pick whichever matches your machine.

**With Docker**

```bash
cp .env.example .env
docker compose up --build
```

**Without Docker (no PostgreSQL, no Redis, no API key required)**

```bash
# backend
py -3.12 -m venv .venv && .venv\Scripts\activate     # Windows
python -m venv .venv && source .venv/bin/activate     # macOS / Linux
pip install -e "packages/ai[dev]" -e "apps/api[dev]"
uvicorn careerforge_api.main:app --reload             # :8000

# frontend
pnpm install
pnpm --filter web dev                                 # :3000
```

## Engineering standards

These are enforced in CI, not suggestions.

| Rule                                                       | Enforcement                                               |
| ---------------------------------------------------------- | --------------------------------------------------------- |
| TypeScript `strict` — no `any` without a documented reason | `tsc --noEmit`                                            |
| Python: full type hints, `mypy` clean                      | `mypy packages/ai apps/api`                               |
| Lint + format                                              | `eslint`, `prettier`, `ruff check`, `ruff format --check` |
| **No file over 500 lines**                                 | review + a repo script                                    |
| **No hardcoded color values** in components                | lint rule (use design tokens)                             |
| Structured LLM output only — never string parsing          | Pydantic schemas in `packages/ai/careerforge_ai/schemas`  |
| Numbers must be deterministic — LLMs never produce scores  | `scoring/` module owns all numeric output                 |
| Tests required for new behaviour                           | `pytest` / `vitest`                                       |
| Pre-commit hooks installed                                 | `pre-commit install`                                      |

### Layering rule (important)

`packages/ai` **must not** import FastAPI or SQLAlchemy. It receives plain data objects and talks to the outside world through ports (`LLMProvider`, `VectorStore`, `EvidenceRepo`). This keeps the AI core independently testable and evaluable. PRs that break this will be asked to change.

### Data honesty rule

Any number that appears in a README, doc, comment, or resume artifact must come from a real build, test, or eval artifact (`reports/eval-report.json`, CI output). **Fabricated metrics are the one thing this project cannot tolerate** — the entire product thesis is that unverifiable claims are worthless.

## Commit convention

[Conventional Commits](https://www.conventionalcommits.org/):

```
feat:     new capability
fix:      bug fix
docs:     documentation only
refactor: no behaviour change
test:     tests only
chore:    tooling, deps
perf:     performance
ci:       CI/CD
```

Scope is encouraged: `feat(evidence): add corroboration scoring`.

## Pull request checklist

- [ ] The project builds and runs from a clean checkout
- [ ] `pnpm typecheck && pnpm lint && pytest && pnpm test` all pass
- [ ] New behaviour has tests
- [ ] Docs updated (`README.md` and/or the relevant `docs/*.md`)
- [ ] No secrets, no `.env`, no large binaries committed
- [ ] Numbers in docs are traceable to real artifacts
- [ ] If the PR changes a design decision, an ADR was added or amended in `docs/DECISIONS.md`

## Reporting bugs

Use the issue templates. A useful bug report includes: what you ran, what you expected, what happened, and the `requestId` from the API response (it links straight to the agent run trace in the AI Runs page).

## Security issues

Do **not** open a public issue for vulnerabilities. See the security section of [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and contact the maintainer privately.

## License

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE).
