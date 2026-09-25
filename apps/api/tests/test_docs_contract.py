"""``docs/API.md`` must describe the API that is actually mounted.

**Why this exists** (PHASE 14). PHASE 13 found the interview section documenting ``/interview/*``
with ``{success,data}`` envelopes and camelCase fields (``interviewId``, ``difficultyChange``,
``jobId``) while what is mounted is ``/ai/interview/*``, snake_case, with the parsed ``JDAnalysis``
as the body — "the docs describe a different API" is a release blocker, because a client written
from the document cannot talk to the server at all. It also found ``/evidence/validate`` documented
as being served by ``/ai/validate/claim``, which was never true and could never have worked.

**Scope.** The *public product* families: auth, jobs, evidence (the validator included), ``ai/*``,
applications, analytics, dashboard, observability and public. Those are the endpoints an external
client is given, and the ones whose drift is a product defect rather than internal churn. The
sections that own them are listed in :data:`TESTED_SECTIONS`.

**What is asserted, in both directions.** Each documented path must be mounted with the documented
methods (:data:`DOCUMENTED`), *and* it must actually appear as a table row in ``docs/API.md`` — so a
document edit that drops a row fails here too. And no endpoint inside a tested section may be
documented as mounted while being absent from the route table: a row counts as "documented as
mounted" unless its description says ``未实现``, which is the marker this document already uses.

The route table is read from the generated OpenAPI document, which is the same view ``pnpm gen:api``
consumes — not a hand-written list. Only membership and method sets are read; the document itself is
never snapshotted.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest

from careerforge_api.main import create_app

#: ``docs/API.md``'s convention for "documented, deliberately not built".
NOT_IMPLEMENTED = "未实现"

DOC_PATH = Path(__file__).resolve().parents[3] / "docs" / "API.md"

#: The sections whose endpoints this test polices, by their ``### 2.x`` heading prefix.
TESTED_SECTIONS: tuple[str, ...] = (
    "2.1",
    "2.5",
    "2.6",
    "2.8",
    "2.9",
    "2.10",
    "2.11",
    "2.12",
    "2.13",
)

#: Documented path (as written in ``docs/API.md``, without the ``/api/v1`` prefix) → the methods
#: the document gives it. Derived from the code, checked against the document, and read back from
#: the route table: three statements that have to agree.
DOCUMENTED: dict[str, tuple[str, ...]] = {
    # §2.1 认证与账户（`/me/*` 四个端点未实现，因此不在此表内 —— 见文档中的 未实现 标记）
    "/auth/register": ("POST",),
    "/auth/login": ("POST",),
    "/auth/demo": ("POST",),
    "/auth/refresh": ("POST",),
    "/auth/logout": ("POST",),
    "/auth/me": ("GET",),
    # §2.5 证据与图谱
    "/evidence-graph": ("GET",),
    "/evidence": ("GET", "POST"),
    "/evidence/{id}": ("GET", "DELETE"),
    "/evidence/{id}/trace": ("GET",),
    "/evidence/validate": ("POST",),
    "/evidence/validate/batch": ("POST",),
    "/documents/{id}/analyze": ("POST",),
    # §2.6 岗位与匹配
    "/jobs/analyze": ("POST",),
    "/jobs": ("GET",),
    "/jobs/{id}": ("GET", "DELETE"),
    "/jobs/{id}/skill-tree": ("GET",),
    "/jobs/{id}/match": ("GET", "POST"),
    "/jobs/{id}/applications": ("POST",),
    # §2.8 AI 端点（含面试）
    "/ai/analyze/jd": ("POST",),
    "/ai/match": ("POST",),
    "/ai/capabilities": ("GET",),
    "/ai/interview/start": ("POST",),
    "/ai/interview/{session_id}/answer": ("POST",),
    "/ai/interview/{session_id}/finish": ("POST",),
    "/ai/interview/{session_id}": ("GET", "DELETE"),
    # §2.9 投递看板
    "/applications": ("GET", "POST"),
    "/applications/board": ("GET",),
    "/applications/reorder": ("PATCH",),
    "/applications/{id}": ("GET", "PATCH", "DELETE"),
    "/applications/{id}/events": ("GET",),
    # §2.10 简历与断言（validator 行；`/resume/*` 不在本次覆盖范围）
    "/resume/optimize": ("POST",),
    "/resume/versions": ("GET",),
    "/resume/versions/{id}": ("GET", "DELETE"),
    # §2.11 分析
    "/dashboard": ("GET",),
    "/analytics/funnel": ("GET",),
    "/analytics/rates": ("GET",),
    "/analytics/skill-correlation": ("GET",),
    "/analytics/categories": ("GET",),
    "/analytics/timeline": ("GET",),
    # §2.12 可观测性
    "/ai-runs": ("GET",),
    "/ai-runs/{id}": ("GET",),
    "/ai-costs": ("GET",),
    "/ai-costs/by-agent": ("GET",),
    "/ai-costs/by-feature": ("GET",),
    "/cache/stats": ("GET",),
    "/prompts": ("GET",),
    # §2.13 公开候选人页
    "/public/candidate/{slug}": ("GET",),
    "/public/candidate/{slug}/evidence/{skillId}": ("GET",),
    "/public/publish": ("POST",),
    "/public/settings": ("GET", "PATCH"),
}

#: Routes mounted under the tested families that deliberately have no documented counterpart here.
#: Empty, and asserted to stay empty: an endpoint in a public family that the document does not
#: mention is an endpoint no client can discover.
UNDOCUMENTED_ALLOWED: frozenset[str] = frozenset()

#: The path prefixes the reverse check walks. ``/api/v1/ai/`` covers the interview family, which is
#: where the PHASE 13 drift was; ``/api/v1/documents/{...}/analyze`` is documented inside §2.5 and so
#: is checked through :data:`DOCUMENTED` rather than by prefix.
FAMILY_PREFIXES: tuple[str, ...] = (
    "/api/v1/auth",
    "/api/v1/jobs",
    "/api/v1/evidence",
    "/api/v1/ai/",
    "/api/v1/applications",
    "/api/v1/analytics",
    "/api/v1/dashboard",
    "/api/v1/ai-runs",
    "/api/v1/ai-costs",
    "/api/v1/cache",
    "/api/v1/prompts",
    "/api/v1/public",
)

#: A markdown table row: ``| METHOD | `path` | description |``.
ROW = re.compile(r"^\|\s*(GET|POST|PUT|PATCH|DELETE)\s*\|\s*(.+?)\s*\|(.*)\|\s*$", re.MULTILINE)
_BACKTICKED = re.compile(r"`([^`]+)`")
_PLACEHOLDER = re.compile(r"\{[^}]+\}")


def _normalise(path: str) -> str:
    """Compare paths by shape, not by placeholder spelling.

    The document writes ``/evidence/{id}`` and the router writes ``{evidence_id}``; the document
    writes ``{skillId}`` and the router ``{skill_id}``. Those are the same path — a test that
    failed on the spelling would be enforcing a naming convention the contract does not have.
    """
    return _PLACEHOLDER.sub("{}", path)


def _documented_rows() -> dict[str, set[str]]:
    """Every table row in ``docs/API.md``, as ``{path shape: {methods}}``, dropping 未实现 rows."""
    rows: dict[str, set[str]] = {}
    for method, raw_paths, description in ROW.findall(DOC_PATH.read_text(encoding="utf-8")):
        for raw in _BACKTICKED.findall(raw_paths):
            if not raw.startswith("/") or raw.startswith("//"):
                # ``/me/export``-style paths are covered; a bare ``{id}`` continuation (as in the
                # old ``· /reject`` row) is not a path and is skipped.
                continue
            if NOT_IMPLEMENTED in description:
                continue
            rows.setdefault(_normalise(raw), set()).add(method)
    return rows


def _section_rows(prefix: str) -> list[tuple[str, str, str]]:
    """The ``(method, path, description)`` rows of one ``### 2.x`` section."""
    text = DOC_PATH.read_text(encoding="utf-8")
    heading = re.search(rf"^### {re.escape(prefix)}[^\n]*$", text, re.MULTILINE)
    assert heading is not None, f"docs/API.md has no section {prefix}"
    rest = text[heading.end() :]
    next_heading = re.search(r"^###? ", rest, re.MULTILINE)
    body = rest[: next_heading.start()] if next_heading else rest
    found: list[tuple[str, str, str]] = []
    for method, raw_paths, description in ROW.findall(body):
        for raw in _BACKTICKED.findall(raw_paths):
            if raw.startswith("/"):
                found.append((method, raw, description))
    return found


def _route_table() -> dict[str, set[str]]:
    """The mounted routes, keyed by path shape, from the generated OpenAPI document."""
    spec = create_app().openapi()
    return {
        _normalise(path): {method.upper() for method in operations}
        for path, operations in spec["paths"].items()
    }


@pytest.fixture(scope="module")
def routes() -> dict[str, set[str]]:
    return _route_table()


@pytest.fixture(scope="module")
def documented_rows() -> dict[str, set[str]]:
    return _documented_rows()


def _mounted(path: str) -> str:
    return f"/api/v1{path}"


def test_every_documented_endpoint_is_mounted_with_the_documented_method(
    routes: dict[str, set[str]],
) -> None:
    """The forward direction: what the document promises must exist, with those methods."""
    missing: list[str] = []
    wrong_method: list[str] = []
    for path, methods in DOCUMENTED.items():
        mounted = routes.get(_normalise(_mounted(path)))
        if mounted is None:
            missing.append(path)
            continue
        for method in methods:
            if method not in mounted:
                wrong_method.append(f"{method} {path} (mounted: {sorted(mounted)})")
    assert not missing, f"documented in docs/API.md but not mounted: {missing}"
    assert not wrong_method, f"documented with a method the router does not serve: {wrong_method}"


def test_every_mounted_route_in_a_tested_family_is_documented(
    routes: dict[str, set[str]],
) -> None:
    """The reverse direction: no public endpoint exists that the document forgets.

    Without this, :data:`DOCUMENTED` could quietly shrink to whatever someone remembered to list,
    and the forward check alone would still pass.
    """
    undocumented = [
        path
        for path in sorted(routes)
        if path.startswith(FAMILY_PREFIXES) and path not in UNDOCUMENTED_ALLOWED
    ]
    known = {_normalise(_mounted(path)) for path in DOCUMENTED}
    assert not (set(undocumented) - known), (
        "mounted in a public family but absent from the documented set: "
        f"{sorted(set(undocumented) - known)}"
    )


def test_every_documented_path_has_a_table_row_in_the_document(
    documented_rows: dict[str, set[str]],
) -> None:
    """The document is the source of truth here, so the row itself is asserted to exist.

    A path that is in :data:`DOCUMENTED` but absent from ``docs/API.md`` would mean this test had
    silently become a list of one person's memory.
    """
    for path in DOCUMENTED:
        rows = documented_rows.get(_normalise(path))
        assert rows, f"{path} is in DOCUMENTED but has no table row in docs/API.md"


def test_no_tested_section_documents_a_path_that_is_not_mounted(
    routes: dict[str, set[str]],
) -> None:
    """A row inside a tested section counts as "mounted" unless it says ``未实现``.

    This is the check that would have caught ``/interview/*``. It reads the document rather than a
    list, so a newly invented endpoint cannot slip in by being written down.
    """
    offenders: list[str] = []
    for prefix in TESTED_SECTIONS:
        for method, path, description in _section_rows(prefix):
            if NOT_IMPLEMENTED in description:
                continue
            mounted = routes.get(_normalise(_mounted(path)))
            if mounted is None or method not in mounted:
                offenders.append(f"§{prefix}: {method} {path}")
    assert not offenders, (
        "documented as mounted in a tested section, but not in the route table "
        f"(mark them 未实现 if they are planned): {offenders}"
    )


def test_the_removed_stateless_claim_endpoint_is_gone(routes: dict[str, set[str]]) -> None:
    """``POST /ai/validate/claim`` must not come back (PHASE 14).

    It ran the gate with ``app.state.retriever`` — set by nothing in this repository — and with no
    material, so it retrieved nothing, cited nothing and answered ``unsupported`` with
    ``confidence: 0.0`` even for a sentence the candidate's own evidence supports. Two entry points
    over one gate is one too many when the second cannot tell the truth; if it is ever reinstated it
    must delegate to ``ResumeService.validate`` and this test must change on purpose.
    """
    assert "/api/v1/ai/validate/claim" not in routes
    assert "/api/v1/evidence/validate" in routes
