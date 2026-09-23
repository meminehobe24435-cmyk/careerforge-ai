"""Tests for the PHASE 1 API (``apps/api``).

Primary path: SQLite + in-process queue + heuristic provider, with no external
service and no API key — the configuration ``docs/ARCHITECTURE.md`` §1.3 calls the
zero-dependency path. Setting ``USE_SQLITE=false`` and a ``DATABASE_URL`` runs the
same suite against PostgreSQL (the CI matrix in ``.github/workflows/ci.yml``).
"""
