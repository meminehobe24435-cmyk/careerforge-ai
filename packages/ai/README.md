# careerforge-ai (Python core)

The domain intelligence of [CareerForge AI](../../README.md): agent orchestration,
the evidence graph, hybrid retrieval, deterministic scoring and prompt management.

## Why it is a separate package

This package **never imports a web framework or an ORM** (ADR-022). It receives
plain Pydantic objects and reaches the outside world through ports
(:mod:`careerforge_ai.ports`). Two things follow from that:

1. Every agent can be unit-tested in milliseconds, with no database and no network.
2. The evaluation runner (`evals/run.py`) executes the real production code paths
   in memory, so benchmark numbers describe the shipped system rather than a
   simplified copy of it.

## Install

```bash
pip install -e "packages/ai[dev]"        # core + test tooling
pip install -e "packages/ai[parsing]"    # adds PDF/DOCX/HTML parsers
```

## Layout

| Module | Contents |
|---|---|
| `orchestrator/` | `Step`, `Workflow`, `RunContext`, `WorkflowExecutor` |
| `agents/` | the nine domain agents (populated per phase) |
| `providers/` | `LLMProvider` port + DeepSeek / OpenAI / Ollama / **heuristic** |
| `rag/` | chunking, hybrid retrieval, RRF fusion |
| `graph/` | evidence graph construction and traversal |
| `scoring/` | **all numeric output** — confidence, match, gaps, profile strength |
| `parsing/` | skill taxonomy and deterministic text parsing |
| `prompting/` | versioned prompt registry |
| `observability/` | token accounting, price table, run tracking |
| `schemas/` | every structured-output contract |

## Design rules

- **Scores are deterministic.** No language model produces a number that ends up
  in a match score, a confidence value or a gap priority.
- **No string parsing of model output.** Responses are validated against a
  Pydantic schema; a violation triggers one repair attempt, then a degrade.
- **The heuristic provider is always available.** The product must work with no
  API key, and anything it serves is flagged `degraded` rather than passed off as
  a model result.

See [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) and
[`docs/DECISIONS.md`](../../docs/DECISIONS.md).
