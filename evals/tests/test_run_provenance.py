"""The provenance fields an evaluation report carries must be able to say "clean".

`reports/eval-report.json` records the commit it was generated from and whether the tree was dirty,
and a reader uses those two to decide whether the numbers belong to a commit or to somebody's
half-finished edit. Until PHASE 14 the dirty flag was **always true**: `_git` returned the sentinel
`"unknown"` for *any* empty output, and the caller read it with `bool(...)`, so `git status` answering
"nothing is modified" produced the truthy string `"unknown"`. Measured on a verified-clean tree, which
is how it was found while generating the release candidate's artefacts.

These tests pin the three cases, because collapsing any two of them is what produced the bug. The
subprocess double records how it was called rather than ignoring its arguments — which is both the
honest way to write a double (the parameters are used) and a stronger test: the command line and the
`cwd` are part of what `_git` guarantees.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from evals import run


class _RecordedRun:
    """A stand-in for `subprocess.run` that answers a canned result and remembers its call."""

    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        self.calls.append((args, kwargs))
        return SimpleNamespace(returncode=self.returncode, stdout=self.stdout)

    @property
    def command(self) -> list[str]:
        return list(self.calls[0][0][0])

    @property
    def options(self) -> dict[str, Any]:
        return self.calls[0][1]


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(stdout: str, returncode: int = 0) -> _RecordedRun:
        double = _RecordedRun(stdout=stdout, returncode=returncode)
        monkeypatch.setattr(run.subprocess, "run", double)
        return double

    return install


def test_an_empty_porcelain_output_means_clean(stub: Any) -> None:
    """The case that was broken: git answered, and the answer was "nothing modified"."""
    double = stub("")

    assert run._git("status", "--porcelain") == ""
    assert run._tree_is_dirty(run._git("status", "--porcelain")) is False

    # Why the double records instead of ignoring: these two are the rest of the contract, and a
    # double that swallowed its arguments could not check either of them.
    assert double.command == ["git", "status", "--porcelain"]
    assert double.options["cwd"] == run.REPO_ROOT, (
        "git must run in the repository, not the caller's cwd"
    )
    assert double.options["check"] is False, (
        "a non-zero exit must come back as a value, not a raise"
    )


def test_porcelain_output_means_dirty(stub: Any) -> None:
    stub(" M reports/eval-report.json\n")

    assert run._tree_is_dirty(run._git("status", "--porcelain")) is True


def test_git_being_unavailable_is_reported_as_dirty_not_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Conservative direction: not proved clean is not the same as proved dirty, and not clean either.

    The report has one boolean for this, so it takes the safe side, and `git_commit` says `unknown`
    next to it so the two fields are read together.
    """

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise OSError(f"git is not installed (called with {args!r} {kwargs!r})")

    monkeypatch.setattr(run.subprocess, "run", boom)

    assert run._git("status", "--porcelain") is None
    assert run._tree_is_dirty(None) is True
    assert run._git_or("rev-parse", "--short", "HEAD") == "unknown"


def test_the_commit_field_still_reports_the_commit(stub: Any) -> None:
    stub("7bbce49\n")

    assert run._git_or("rev-parse", "--short", "HEAD") == "7bbce49"
