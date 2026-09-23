"""Prompt registry: prompts as versioned, reviewable artefacts (ADR-012).

Prompts live in ``prompts/*.md`` with a small YAML-ish front-matter block::

    ---
    name: jd_analysis
    version: 2
    description: Parse a job description into a structured analysis.
    variables: [jd_text, locale]
    ---
    System instructions go here...

    ## Input
    {{jd_text}}

Why not keep them in Python strings? Because a prompt is the part of an AI
system that changes most often, and code is a bad place to review prose. Here
prompts can be diffed, versioned, rolled back, and attributed: every LLM call
records the ``name@version`` that produced it, so a quality regression can be
traced to the exact prompt change that caused it.

The front-matter parser is intentionally minimal (flat ``key: value`` pairs and
inline lists). Adding a YAML dependency to parse eight lines of metadata would
be a poor trade.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re

from careerforge_ai.errors import ConfigurationError
from careerforge_ai.providers.base import ChatMessage, ChatRole

__all__ = [
    "PROMPT_NAMES",
    "PromptRegistry",
    "PromptTemplate",
    "RenderedPrompt",
    "load_prompt_registry",
]

#: Canonical prompt names. Kept explicit so a typo at a call site fails loudly
#: instead of silently rendering an empty prompt.
PROMPT_NAMES: tuple[str, ...] = (
    "profile_extractor",
    "github_analyst",
    "jd_analysis",
    "match_explainer",
    "resume_optimizer",
    "evidence_validator",
    "interviewer",
    "interview_evaluator",
    "skill_gap",
    "recruiter_summary",
)

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
_FRONT_MATTER_RE = re.compile(r"^---\s*\n(?P<body>.*?)\n---\s*\n", re.DOTALL)


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """One version of one prompt."""

    name: str
    version: int
    body: str
    description: str = ""
    variables: tuple[str, ...] = ()
    path: str = ""
    tags: tuple[str, ...] = ()

    @property
    def ref(self) -> str:
        return f"{self.name}@v{self.version}"

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()

    def declared_variables(self) -> tuple[str, ...]:
        """Front-matter variables unioned with placeholders found in the body."""
        found = {match.group("name") for match in _PLACEHOLDER_RE.finditer(self.body)}
        return tuple(sorted(found | set(self.variables)))

    def render(self, **values: object) -> str:
        """Substitute ``{{placeholders}}``.

        A missing variable is an error, not an empty string: silent blanks in a
        prompt produce confidently wrong output that is very hard to trace.
        """
        missing = [name for name in self.declared_variables() if name not in values]
        if missing:
            raise ConfigurationError(
                f"prompt {self.ref} is missing variables: {', '.join(missing)}",
                details={"prompt": self.ref, "missing": missing},
            )

        def substitute(match: re.Match[str]) -> str:
            return str(values[match.group("name")])

        return _PLACEHOLDER_RE.sub(substitute, self.body)


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    """A rendered prompt ready to send to a provider."""

    template: PromptTemplate
    system: str
    user: str

    @property
    def ref(self) -> str:
        return self.template.ref

    def messages(self) -> list[ChatMessage]:
        messages = [ChatMessage(role=ChatRole.SYSTEM, content=self.system)]
        if self.user.strip():
            messages.append(ChatMessage(role=ChatRole.USER, content=self.user))
        return messages


def _parse_scalar(raw: str) -> object:
    value = raw.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("\"'") for item in inner.split(",") if item.strip()]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.isdigit():
        return int(value)
    return value.strip("\"'")


def _parse_front_matter(text: str) -> tuple[dict[str, object], str]:
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict[str, object] = {}
    for line in match.group("body").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, _, raw_value = stripped.partition(":")
        meta[key.strip()] = _parse_scalar(raw_value)
    return meta, text[match.end() :]


def _split_system_user(body: str) -> tuple[str, str]:
    """Split a prompt body into system and user halves.

    The convention is a line containing only ``---`` separating the two; without
    it the whole body is treated as the system prompt.
    """
    parts = re.split(r"\n\s*---\s*\n", body, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return body.strip(), ""


@dataclass
class PromptRegistry:
    """In-memory index of prompt templates, keyed by ``name`` and version."""

    templates: dict[tuple[str, int], PromptTemplate] = field(default_factory=dict)
    source_dir: Path | None = None
    warnings: list[str] = field(default_factory=list)

    # ── population ───────────────────────────────────────────────────────────

    def register(self, template: PromptTemplate) -> PromptTemplate:
        key = (template.name, template.version)
        existing = self.templates.get(key)
        if existing is not None and existing.content_sha256 != template.content_sha256:
            # Same version, different content: the version number was not bumped.
            # Registering both would make traces ambiguous, so this is an error.
            raise ConfigurationError(
                f"prompt {template.ref} is already registered with different content",
                details={"path": template.path, "previous_path": existing.path},
            )
        self.templates[key] = template
        return template

    def load_directory(self, directory: Path | str) -> int:
        """Load every ``*.md`` file in ``directory``. Returns the count loaded."""
        root = Path(directory)
        self.source_dir = root
        if not root.exists():
            self.warnings.append(f"prompt directory does not exist: {root}")
            return 0
        count = 0
        for path in sorted(root.glob("*.md")):
            count += 1 if self._load_file(path) else 0
        return count

    def _load_file(self, path: Path) -> bool:
        text = path.read_text(encoding="utf-8")
        meta, body = _parse_front_matter(text)
        name = str(meta.get("name") or path.stem)
        version = _coerce_version(meta.get("version", 1), path.name, self.warnings)
        variables = meta.get("variables") or []
        tags = meta.get("tags") or []
        self.register(
            PromptTemplate(
                name=name,
                version=version,
                body=body,
                description=str(meta.get("description") or ""),
                variables=tuple(str(item) for item in variables)
                if isinstance(variables, list)
                else (),
                path=str(path),
                tags=tuple(str(item) for item in tags) if isinstance(tags, list) else (),
            )
        )
        return True

    # ── lookup ───────────────────────────────────────────────────────────────

    def latest(self, name: str, /) -> PromptTemplate:
        versions = [version for (candidate, version) in self.templates if candidate == name]
        if not versions:
            raise ConfigurationError(
                f"prompt '{name}' is not registered",
                details={"available": sorted({candidate for candidate, _ in self.templates})},
            )
        return self.templates[(name, max(versions))]

    def get(self, name: str, /, version: int | None = None) -> PromptTemplate:
        if version is None:
            return self.latest(name)
        template = self.templates.get((name, version))
        if template is None:
            raise ConfigurationError(f"prompt {name}@v{version} is not registered")
        return template

    def render(
        self, name: str, /, *, version: int | None = None, **values: object
    ) -> RenderedPrompt:
        """Render a prompt.

        ``name`` is positional-only on purpose: prompts legitimately contain a
        variable called ``name`` (the candidate's name), and a keyword-capable
        parameter would make those prompts impossible to render.
        """
        template = self.get(name, version)
        rendered = template.render(**values)
        system, user = _split_system_user(rendered)
        return RenderedPrompt(template=template, system=system, user=user)

    def names(self) -> Sequence[str]:
        return sorted({name for name, _ in self.templates})

    def versions(self, name: str) -> Iterable[int]:
        return sorted(version for (candidate, version) in self.templates if candidate == name)

    def __len__(self) -> int:
        return len(self.templates)

    def describe(self) -> list[dict[str, object]]:
        """Serialisable listing for ``GET /prompts``."""
        rows: list[dict[str, object]] = []
        for (name, version), template in sorted(self.templates.items()):
            rows.append(
                {
                    "name": name,
                    "version": version,
                    "ref": template.ref,
                    "sha256": template.content_sha256,
                    "description": template.description,
                    "variables": list(template.declared_variables()),
                    "path": template.path,
                }
            )
        return rows


def load_prompt_registry(directory: Path | str | None = None) -> PromptRegistry:
    """Load the registry from disk, defaulting to ``<repo>/prompts``."""
    registry = PromptRegistry()
    if directory is None:
        from careerforge_ai.config import get_settings

        directory = get_settings().resolved_prompts_dir
    registry.load_directory(directory)

    missing = [name for name in PROMPT_NAMES if name not in set(registry.names())]
    if missing:
        registry.warnings.append(f"missing canonical prompts: {', '.join(missing)}")
    return registry


def find_prompt_values(template: PromptTemplate, values: Mapping[str, object]) -> dict[str, object]:
    """Filter ``values`` down to what the template declares (helper for call sites)."""
    declared = set(template.declared_variables())
    return {key: value for key, value in values.items() if key in declared}


def _coerce_version(raw: object, filename: str, warnings: list[str]) -> int:
    """Read a prompt's front-matter version, warning instead of failing.

    Front matter is hand-written, so a missing or unusable version must not stop the
    registry from loading: it falls back to 1 and records why. The value type is
    narrowed rather than coerced blindly — ``bool`` is excluded explicitly because
    ``int(True)`` is 1, and a version of ``true`` is a typo, not a version.
    """
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        warnings.append(f"{filename}: invalid version {raw!r}, defaulting to 1")
        return 1
    try:
        return int(raw)
    except ValueError:
        warnings.append(f"{filename}: invalid version {raw!r}, defaulting to 1")
        return 1
