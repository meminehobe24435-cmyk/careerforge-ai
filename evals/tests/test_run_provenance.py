"""The provenance fields an evaluation report carries must be able to say "clean".

`reports/eval-report.json` records the commit it was generated from and whether the tree was dirty,
and a reader uses those two to decide whether the numbers belong to a commit or to somebody's
half-finished edit. Until PHASE 14 the dirty flag was **always true**: `_git` returned the sentinel
`"unknown"` for *any* empty output, and the caller read it with `bool(...)`, so `git status` answering
"nothing is modified" produced the truthy string `"unknown"`. Measured on a verified-clean tree, which
is how it was found while generating the release candidate's artefacts.

These tests pin the three cases, because collapsing any two of them is what produced the bug.
"""

from __future__ import annotations

from types import SimpleNamespace

from evals import run


def test_an_empty_porcelain_output_means_clean(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The case that was broken: git answered, and the answer was "nothing modified"."""
    monkeypatch.setattr(
        run.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=""),
    )

    assert run._git("status", "--porcelain") == ""
    assert run._tree_is_dirty(run._git("status", "--porcelain")) is False


def test_porcelain_output_means_dirty(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        run.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=" M reports/eval-report.json\n"
        ),
    )

    assert run._tree_is_dirty(run._git("status", "--porcelain")) is True


def test_git_being_unavailable_is_reported_as_dirty_not_clean(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Conservative direction: not proved clean is not the same as proved dirty, and not clean either.

    The report has one boolean for this, so it takes the safe side, and `git_commit` says `unknown`
    next to it so the two fields are read together.
    """

    def boom(*args: object, **kwargs: object) -> object:
        raise OSError("git is not installed")

    monkeypatch.setattr(run.subprocess, "run", boom)

    assert run._git("status", "--porcelain") is None
    assert run._tree_is_dirty(None) is True
    assert run._git_or("rev-parse", "--short", "HEAD") == "unknown"


def test_the_commit_field_still_reports_the_commit(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        run.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="7bbce49\n"),
    )

    assert run._git_or("rev-parse", "--short", "HEAD") == "7bbce49"
