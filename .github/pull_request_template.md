## What changed

<!-- One or two sentences. Link the issue if there is one: Closes #123 -->

## Why

<!-- The reasoning. If this changes a design decision, add or amend an ADR in docs/DECISIONS.md -->

## Type of change

- [ ] `feat` — new capability
- [ ] `fix` — bug fix
- [ ] `refactor` — no behaviour change
- [ ] `perf` — performance
- [ ] `docs` — documentation only
- [ ] `test` — tests only
- [ ] `ci` / `chore` — tooling

## How it was verified

<!-- Real commands and their real results. Paste output, do not summarise it away. -->

```bash
# e.g.
pytest -q
pnpm typecheck && pnpm lint
pnpm test
```

## Checklist

- [ ] Runs from a clean checkout (both Docker and zero-Docker paths if applicable)
- [ ] Type checking passes: `pnpm typecheck`, `mypy`
- [ ] Lint and format pass: `eslint`, `prettier`, `ruff`
- [ ] Tests added or updated for the new behaviour
- [ ] No file exceeds 500 lines
- [ ] No hardcoded colour values (design tokens only)
- [ ] `packages/ai` still has **no** FastAPI / SQLAlchemy imports
- [ ] Numbers produced by LLMs are still zero — scoring stays deterministic
- [ ] Docs updated (README and/or `docs/*.md`)
- [ ] No secrets, `.env`, or large binaries committed
- [ ] New/changed metrics traceable to real artifacts (no estimates)

## Screenshots

<!-- For UI changes, include before/after at 1440px. Note if 1024/768/375 were checked. -->
