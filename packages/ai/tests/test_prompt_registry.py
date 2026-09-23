"""Tests for the versioned prompt registry.

Prompts are treated as reviewable artefacts here (ADR-012), which means two
behaviours must be enforced rather than hoped for: a missing variable is an
error instead of a silently blank prompt, and reusing a version number for
different content is rejected instead of making traces ambiguous.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from careerforge_ai.errors import ConfigurationError
from careerforge_ai.prompting.registry import (
    PROMPT_NAMES,
    PromptRegistry,
    PromptTemplate,
    load_prompt_registry,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


class TestRepositoryPrompts:
    def test_all_canonical_prompts_load(self) -> None:
        registry = load_prompt_registry(REPO_ROOT / "prompts")
        assert registry.warnings == [], registry.warnings
        assert len(registry) >= len(PROMPT_NAMES)

    def test_each_canonical_prompt_is_present(self) -> None:
        registry = load_prompt_registry(REPO_ROOT / "prompts")
        names = set(registry.names())
        missing = [name for name in PROMPT_NAMES if name not in names]
        assert missing == []

    def test_every_prompt_declares_a_description(self) -> None:
        registry = load_prompt_registry(REPO_ROOT / "prompts")
        for name in registry.names():
            template = registry.latest(name)
            assert template.description, name

    def test_prompts_are_versioned_from_one(self) -> None:
        registry = load_prompt_registry(REPO_ROOT / "prompts")
        for name in registry.names():
            assert registry.latest(name).version >= 1

    def test_hallucination_guard_language_is_present(self) -> None:
        """The anti-fabrication instruction is a product requirement, not prose.

        If someone rewrites these prompts and drops the constraint, this test
        fails — which is the point.
        """
        registry = load_prompt_registry(REPO_ROOT / "prompts")
        validator = registry.latest("evidence_validator").body
        assert "unsupported" in validator.lower()
        assert "not evidence" in validator.lower() or "only source of truth" in validator.lower()

        optimizer = registry.latest("resume_optimizer").body
        assert "may not introduce a fact" in optimizer.lower()

        extractor = registry.latest("profile_extractor").body
        assert "empty" in extractor.lower()

    def test_describe_is_serialisable(self) -> None:
        registry = load_prompt_registry(REPO_ROOT / "prompts")
        rows = registry.describe()
        assert rows and all({"name", "version", "ref", "sha256"} <= set(row) for row in rows)


class TestRender:
    def test_renders_declared_variables(self) -> None:
        registry = PromptRegistry()
        registry.register(
            PromptTemplate(
                name="demo",
                version=1,
                body="Hello {{name}}, you have {{count}} items.\n---\nContext: {{context}}",
                description="demo",
                variables=("name", "count", "context"),
            )
        )
        rendered = registry.render("demo", name="Alex", count=3, context="none")
        assert "Hello Alex" in rendered.system
        assert "you have 3 items" in rendered.system
        assert rendered.user == "Context: none"

    def test_missing_variable_raises(self) -> None:
        registry = PromptRegistry()
        registry.register(
            PromptTemplate(
                name="strict",
                version=1,
                body="Need {{required_thing}}",
                variables=("required_thing",),
            )
        )
        with pytest.raises(ConfigurationError):
            registry.render("strict")

    def test_placeholders_are_detected_from_the_body(self) -> None:
        template = PromptTemplate(name="auto", version=1, body="{{a}} and {{b}}")
        assert set(template.declared_variables()) == {"a", "b"}

    def test_body_without_separator_is_all_system(self) -> None:
        registry = PromptRegistry()
        registry.register(PromptTemplate(name="sysonly", version=1, body="System only"))
        rendered = registry.render("sysonly")
        assert rendered.system == "System only"
        assert rendered.user == ""

    def test_messages_include_a_system_turn(self) -> None:
        registry = PromptRegistry()
        registry.register(PromptTemplate(name="m", version=1, body="sys\n---\nuser"))
        messages = registry.render("m").messages()
        assert messages[0].role.value == "system"
        assert messages[1].role.value == "user"


class TestVersioning:
    def test_latest_returns_highest_version(self) -> None:
        registry = PromptRegistry()
        registry.register(PromptTemplate(name="p", version=1, body="v1"))
        registry.register(PromptTemplate(name="p", version=3, body="v3"))
        registry.register(PromptTemplate(name="p", version=2, body="v2"))
        assert registry.latest("p").version == 3
        assert list(registry.versions("p")) == [1, 2, 3]

    def test_specific_version_can_be_requested(self) -> None:
        registry = PromptRegistry()
        registry.register(PromptTemplate(name="p", version=1, body="v1"))
        registry.register(PromptTemplate(name="p", version=2, body="v2"))
        assert registry.get("p", 1).body == "v1"

    def test_same_version_with_different_content_is_rejected(self) -> None:
        registry = PromptRegistry()
        registry.register(PromptTemplate(name="p", version=1, body="original", path="a.md"))
        with pytest.raises(ConfigurationError):
            registry.register(PromptTemplate(name="p", version=1, body="edited", path="b.md"))

    def test_same_version_with_identical_content_is_idempotent(self) -> None:
        registry = PromptRegistry()
        registry.register(PromptTemplate(name="p", version=1, body="same"))
        registry.register(PromptTemplate(name="p", version=1, body="same"))
        assert len(registry) == 1

    def test_unknown_prompt_raises(self) -> None:
        with pytest.raises(ConfigurationError):
            PromptRegistry().latest("nope")

    def test_content_hash_changes_with_content(self) -> None:
        first = PromptTemplate(name="p", version=1, body="a")
        second = PromptTemplate(name="p", version=2, body="b")
        assert first.content_sha256 != second.content_sha256

    def test_ref_format(self) -> None:
        assert PromptTemplate(name="jd_analysis", version=2, body="").ref == "jd_analysis@v2"


class TestLoading:
    def test_missing_directory_warns_but_does_not_raise(self, tmp_path: Path) -> None:
        registry = PromptRegistry()
        assert registry.load_directory(tmp_path / "absent") == 0
        assert registry.warnings

    def test_loads_markdown_with_front_matter(self, tmp_path: Path) -> None:
        (tmp_path / "sample.md").write_text(
            "---\nname: sample\nversion: 2\ndescription: a sample\nvariables: [a, b]\n---\n"
            "Body with {{a}} and {{b}}\n---\nUser half {{a}}\n",
            encoding="utf-8",
        )
        registry = PromptRegistry()
        assert registry.load_directory(tmp_path) == 1
        template = registry.latest("sample")
        assert template.version == 2
        assert template.name == "sample"
        assert set(template.declared_variables()) == {"a", "b"}
        rendered = registry.render("sample", a="1", b="2")
        assert "Body with 1" in rendered.system
        assert rendered.user == "User half 1"

    def test_invalid_version_defaults_with_a_warning(self, tmp_path: Path) -> None:
        (tmp_path / "odd.md").write_text(
            "---\nname: odd\nversion: notanumber\n---\nBody\n", encoding="utf-8"
        )
        registry = PromptRegistry()
        registry.load_directory(tmp_path)
        assert registry.latest("odd").version == 1
        assert registry.warnings

    def test_file_without_front_matter_uses_filename(self, tmp_path: Path) -> None:
        (tmp_path / "bare.md").write_text("Just a body\n", encoding="utf-8")
        registry = PromptRegistry()
        registry.load_directory(tmp_path)
        assert registry.latest("bare").version == 1
