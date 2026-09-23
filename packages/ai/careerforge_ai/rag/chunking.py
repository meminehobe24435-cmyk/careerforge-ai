"""Heading-aware recursive chunking.

Chunking decides what retrieval can ever find, so the boundaries matter more than
the algorithm. Two rules here are deliberate:

* **Headings are preserved as a path**, not discarded. A fragment from
  ``## Requirements`` inside a job description means something different from the
  same words under ``## Benefits``, and the path travels with the chunk so a
  filtered search can use it.
* **Overlap carries context across a boundary.** A claim split across two chunks
  would otherwise be unfindable by either.

Token counts come from the shared estimator, so chunk sizing and cost accounting
agree with each other.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from careerforge_ai.parsing.tokenize import estimate_tokens

__all__ = ["Chunk", "ChunkingConfig", "chunk_text", "SourceKind"]

SourceKind = Literal[
    "resume",
    "project_doc",
    "readme",
    "code",
    "commit",
    "job_description",
    "interview_note",
    "notes",
]

_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*$")
_CHINESE_HEADING_RE = re.compile(r"^(?P<title>[^\n]{1,20})(?:：|:)$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])\s*|\n+")


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    """Sizing rules, per source kind.

    Defaults target the embedding models this project uses. Code and commits get
    smaller chunks because a 512-token window over source code spans several
    unrelated functions, which makes a retrieved hit hard to justify.
    """

    target_tokens: int = 512
    overlap_tokens: int = 64
    min_tokens: int = 24

    @classmethod
    def for_kind(cls, kind: SourceKind) -> ChunkingConfig:
        if kind == "code":
            return cls(target_tokens=256, overlap_tokens=32, min_tokens=16)
        if kind == "commit":
            return cls(target_tokens=128, overlap_tokens=0, min_tokens=8)
        if kind == "resume":
            return cls(target_tokens=256, overlap_tokens=48, min_tokens=16)
        return cls()


@dataclass(frozen=True, slots=True)
class Chunk:
    index: int
    content: str
    heading_path: str = ""
    char_start: int = 0
    char_end: int = 0
    token_count: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.content.strip()


@dataclass(slots=True)
class _Block:
    text: str
    heading: str
    char_start: int


def _split_blocks(text: str) -> list[_Block]:
    """Split into paragraph-level blocks, tracking the heading path of each."""
    blocks: list[_Block] = []
    heading_stack: list[tuple[int, str]] = []
    buffer: list[str] = []
    buffer_start = 0
    offset = 0

    def flush() -> None:
        nonlocal buffer, buffer_start
        joined = "\n".join(buffer).strip()
        if joined:
            path = " > ".join(title for _, title in heading_stack)
            blocks.append(_Block(text=joined, heading=path, char_start=buffer_start))
        buffer = []

    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        heading_match = _HEADING_RE.match(stripped)
        chinese_match = (
            _CHINESE_HEADING_RE.match(stripped)
            if not heading_match and len(stripped) <= 22
            else None
        )

        if heading_match or chinese_match:
            flush()
            title = (heading_match or chinese_match).group("title").strip()  # type: ignore[union-attr]
            if heading_match:
                level = len(heading_match.group("hashes"))
            else:
                level = 2
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            offset += len(line)
            continue

        if not stripped:
            flush()
            offset += len(line)
            continue

        if not buffer:
            buffer_start = offset
        buffer.append(stripped)
        offset += len(line)

    flush()
    return blocks


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]


def _tail_overlap(pieces: list[tuple[str, int]], overlap_tokens: int) -> list[tuple[str, int]]:
    """Take trailing pieces worth roughly ``overlap_tokens``."""
    if overlap_tokens <= 0:
        return []
    taken: list[tuple[str, int]] = []
    total = 0
    for piece in reversed(pieces):
        taken.insert(0, piece)
        total += estimate_tokens(piece[0])
        if total >= overlap_tokens:
            break
    return taken


def chunk_text(
    text: str,
    *,
    kind: SourceKind = "notes",
    config: ChunkingConfig | None = None,
) -> list[Chunk]:
    """Split ``text`` into overlapping, heading-aware chunks.

    Blocks larger than the target are split on sentence boundaries and packed; a
    single sentence longer than the target is emitted as its own chunk rather than
    being cut mid-word, because a truncated sentence makes a retrieved hit
    impossible to verify by eye.
    """
    settings = config or ChunkingConfig.for_kind(kind)
    blocks = _split_blocks(text)
    if not blocks:
        return []

    chunks: list[Chunk] = []
    pieces: list[tuple[str, int]] = []
    current_tokens = 0
    current_heading = ""
    current_start = blocks[0].char_start
    current_end = blocks[0].char_start
    index = 0

    def emit() -> None:
        nonlocal pieces, current_tokens, index, current_start, current_end
        if not pieces:
            return
        content = "\n".join(piece for piece, _ in pieces).strip()
        tokens = estimate_tokens(content)
        if tokens >= settings.min_tokens or not chunks:
            chunks.append(
                Chunk(
                    index=index,
                    content=content,
                    heading_path=current_heading,
                    char_start=current_start,
                    char_end=current_end,
                    token_count=tokens,
                )
            )
            index += 1
        pieces = []

    for block in blocks:
        block_tokens = estimate_tokens(block.text)
        heading = block.heading

        if block_tokens > settings.target_tokens:
            emit()
            current_heading = heading
            current_start = block.char_start
            current_end = block.char_start + len(block.text)
            current_tokens = 0
            carry: list[tuple[str, int]] = []
            for sentence in _split_sentences(block.text):
                sentence_tokens = estimate_tokens(sentence)
                if current_tokens + sentence_tokens > settings.target_tokens and pieces:
                    emit()
                    pieces = list(carry)
                    current_tokens = sum(estimate_tokens(piece) for piece, _ in pieces)
                pieces.append((sentence, block.char_start))
                current_tokens += sentence_tokens
                carry = _tail_overlap(pieces, settings.overlap_tokens)
            emit()
            current_tokens = 0
            continue

        if current_tokens + block_tokens > settings.target_tokens and pieces:
            emit()
            current_heading = heading
            pieces = _tail_overlap(
                [(piece, start) for piece, start in pieces], settings.overlap_tokens
            )
            current_tokens = sum(estimate_tokens(piece) for piece, _ in pieces)

        if not pieces:
            current_heading = heading
            current_start = block.char_start
        pieces.append((block.text, block.char_start))
        current_tokens += block_tokens
        current_end = block.char_start + len(block.text)

    emit()
    return chunks
