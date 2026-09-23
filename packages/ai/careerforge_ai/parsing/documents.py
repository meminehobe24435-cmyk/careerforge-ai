"""Document ingestion: bytes on disk → text the rest of the pipeline can use.

Everything downstream — evidence extraction, retrieval, claim validation — is only as
good as this step. So the module's real job is not "extract text" but **extract text and
say what it could not read**:

* a scanned PDF yields no text, and the caller is told that rather than handed an empty
  string that looks like an empty résumé;
* a text file in GB18030 (still the default on many Chinese Windows machines) is decoded
  correctly instead of becoming mojibake, and the encoding used is reported;
* a missing optional parser is a typed error naming the extra to install, not an
  ``ImportError`` surfacing as a 500.

The optional dependencies stay optional (ADR-022): ``pypdf`` and ``python-docx`` are
imported inside the functions that need them, so the core is still installable and
testable with no extras at all.
"""

from __future__ import annotations

from codecs import BOM_UTF8
from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
from importlib import import_module
from io import BytesIO
from typing import Any

from careerforge_ai.errors import (
    DocumentParseError,
    DocumentTooLargeError,
    UnsupportedDocumentError,
)

__all__ = [
    "MAX_DOCUMENT_BYTES",
    "DocumentFormat",
    "ParsedDocument",
    "detect_format",
    "parse_document",
    "sha256_of",
]

#: 20 MiB. A résumé or project doc is orders of magnitude below this; the limit exists to
#: stop an accidental 2 GB upload from being read into memory.
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024

#: Decoding order for text-like input that arrives without a declared charset. UTF-8
#: first because it is correct; GB18030 second because it is what a Chinese résumé saved
#: on Windows actually is; the rest catch the long tail. ``latin-1`` last never fails, so
#: the ladder always terminates — with a warning, since a wrong guess is silent damage.
_TEXT_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "utf-8", "gb18030", "big5", "latin-1")

#: Legacy binary Word documents start with the OLE2 compound-file magic. They share the
#: ``.doc`` extension with nothing useful, and python-docx rejects them obscurely.
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0"


class DocumentFormat(StrEnum):
    """The formats this build reads directly."""

    PDF = "pdf"
    DOCX = "docx"
    MARKDOWN = "markdown"
    TEXT = "text"

    @property
    def is_text_native(self) -> bool:
        """Whether the format is text already, so no parser dependency is involved."""
        return self in (DocumentFormat.MARKDOWN, DocumentFormat.TEXT)


#: Extensions → format. Deliberately explicit rather than ``mimetypes.guess_type``,
#: whose answer depends on the host's registry.
_EXTENSION_FORMATS: dict[str, DocumentFormat] = {
    ".pdf": DocumentFormat.PDF,
    ".docx": DocumentFormat.DOCX,
    ".doc": DocumentFormat.DOCX,  # told apart from .docx by content, see _read_docx
    ".md": DocumentFormat.MARKDOWN,
    ".markdown": DocumentFormat.MARKDOWN,
    ".mdx": DocumentFormat.MARKDOWN,
    ".txt": DocumentFormat.TEXT,
    ".text": DocumentFormat.TEXT,
}

_MIME_FORMATS: dict[str, DocumentFormat] = {
    "application/pdf": DocumentFormat.PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        DocumentFormat.DOCX
    ),
    "text/markdown": DocumentFormat.MARKDOWN,
    "text/x-markdown": DocumentFormat.MARKDOWN,
    "text/plain": DocumentFormat.TEXT,
}


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """The result of reading one uploaded file.

    ``warnings`` is not decoration: it is how the pipeline learns that a document was
    read *partially* (a scanned page, an old binary ``.doc``, a decoded-with-fallback
    charset) so it can tell the user instead of quietly scoring incomplete material.
    """

    text: str
    format: DocumentFormat
    #: Populated for PDFs; ``None`` when the format has no page concept.
    page_count: int | None = None
    #: The charset actually used for text-native formats.
    encoding: str | None = None
    size_bytes: int = 0
    sha256: str = ""
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """No usable text — which the caller must treat as a failure, not an empty doc."""
        return not self.text.strip()

    @property
    def char_count(self) -> int:
        return len(self.text)


@dataclass(frozen=True, slots=True)
class _ReadResult:
    """What a format reader produces, before normalisation.

    A small carrier rather than a widening tuple or a module-level variable: the charset
    a text file was decoded with has to travel back to the caller, and both alternatives
    lose either readability or thread safety.
    """

    text: str
    page_count: int | None = None
    encoding: str | None = None
    warnings: tuple[str, ...] = ()


def sha256_of(data: bytes) -> str:
    """Content hash used for de-duplication and as a cache key."""
    return hashlib.sha256(data).hexdigest()


def detect_format(filename: str, mime: str | None = None) -> DocumentFormat | None:
    """Best-effort format detection, extension first and MIME as the fallback.

    Extension wins because users rename files far less often than browsers and operating
    systems mislabel them: a ``.md`` upload sent as ``text/plain`` is far more common than
    a Markdown file that is genuinely plain text.
    """
    lowered = filename.strip().lower()
    dot = lowered.rfind(".")
    if dot != -1:
        by_extension = _EXTENSION_FORMATS.get(lowered[dot:])
        if by_extension is not None:
            return by_extension
    if mime:
        by_mime = _MIME_FORMATS.get(mime.split(";")[0].strip().lower())
        if by_mime is not None:
            return by_mime
    return None


def parse_document(
    data: bytes,
    *,
    filename: str,
    mime: str | None = None,
) -> ParsedDocument:
    """Read ``data`` into text, raising a typed error when that cannot be done honestly.

    Args:
        data: the raw file bytes.
        filename: used for format detection and for messages a user will read.
        mime: optional declared content type, consulted only if the name is unknown.

    Raises:
        DocumentTooLargeError: the payload exceeds :data:`MAX_DOCUMENT_BYTES`.
        UnsupportedDocumentError: the type is not one this build reads.
        DocumentParseError: the file claims a supported type but cannot be read.
    """
    if len(data) > MAX_DOCUMENT_BYTES:
        raise DocumentTooLargeError(
            f"{filename} is {len(data) / 1_048_576:.1f} MiB, above the "
            f"{MAX_DOCUMENT_BYTES // 1_048_576} MiB ingestion limit",
            details={"filename": filename, "size_bytes": len(data)},
        )
    if not data:
        raise DocumentParseError(f"{filename} is empty", details={"filename": filename})

    fmt = detect_format(filename, mime)
    if fmt is None:
        raise UnsupportedDocumentError(
            f"unsupported file type: {filename}. This build reads PDF, DOCX, Markdown and "
            "plain text.",
            details={"filename": filename, "mime": mime},
        )

    if fmt is DocumentFormat.PDF:
        read = _read_pdf(data, filename)
    elif fmt is DocumentFormat.DOCX:
        read = _read_docx(data, filename)
    else:
        read = _read_text(data, fmt)

    return ParsedDocument(
        text=_normalise(read.text),
        format=fmt,
        page_count=read.page_count,
        encoding=read.encoding,
        size_bytes=len(data),
        sha256=sha256_of(data),
        warnings=read.warnings,
    )


def _read_pdf(data: bytes, filename: str) -> _ReadResult:
    pypdf = _require("pypdf", "parsing")
    try:
        reader = pypdf.PdfReader(BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise DocumentParseError(
                f"{filename} is password-protected; remove the password and upload it again",
                details={"filename": filename},
            )
        pages = [page.extract_text() or "" for page in reader.pages]
    except DocumentParseError:
        raise
    except Exception as exc:  # pypdf raises a wide range of its own error types
        raise DocumentParseError(
            f"could not read {filename} as a PDF: {exc}",
            details={"filename": filename},
        ) from exc

    warnings: list[str] = []
    blank = sum(1 for page in pages if not page.strip())
    if pages and blank == len(pages):
        # The most common real-world case: a résumé exported as images.
        warnings.append("PDF 中没有可提取的文本，可能是扫描件或图片型 PDF；需要 OCR 才能继续分析。")
    elif blank:
        warnings.append(f"PDF 有 {blank}/{len(pages)} 页没有可提取文本，可能是扫描页。")
    return _ReadResult(text="\n\n".join(pages), page_count=len(pages), warnings=tuple(warnings))


def _read_docx(data: bytes, filename: str) -> _ReadResult:
    if data[:4] == _OLE2_MAGIC:
        raise DocumentParseError(
            f"{filename} is the legacy binary .doc format. Save it as .docx or PDF and "
            "upload it again.",
            details={"filename": filename},
        )

    docx = _require("docx", "parsing")
    try:
        document = docx.Document(BytesIO(data))
    except Exception as exc:
        raise DocumentParseError(
            f"could not read {filename} as a DOCX file: {exc}",
            details={"filename": filename},
        ) from exc

    blocks = [paragraph.text.strip() for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                blocks.append(" | ".join(cells))

    warnings: list[str] = []
    if not any(blocks):
        warnings.append("DOCX 中没有可提取的文本，可能是图片或文本框内容。")
    body = "\n".join(block for block in blocks if block)
    return _ReadResult(text=body, warnings=tuple(warnings))


def _read_text(data: bytes, fmt: DocumentFormat) -> _ReadResult:
    warnings: list[str] = []
    for encoding in _TEXT_ENCODINGS:
        try:
            text = data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        # ``utf-8-sig`` decodes plain UTF-8 too, but reporting it would claim a byte-order
        # mark the file does not have. The charset is reported as it actually is.
        reported = (
            "utf-8" if encoding == "utf-8-sig" and not data.startswith(BOM_UTF8) else encoding
        )
        if reported not in ("utf-8", "utf-8-sig"):
            warnings.append(
                f"文件按 {reported} 解码（不是 UTF-8）；如果内容出现乱码，"
                "请另存为 UTF-8 后重新上传。"
            )
        if fmt is DocumentFormat.MARKDOWN:
            text = _strip_markdown_front_matter(text)
        return _ReadResult(text=text, encoding=reported, warnings=tuple(warnings))

    # Unreachable in practice: latin-1 decodes any byte sequence. Kept so the function
    # cannot fall off the end if the ladder is ever reordered.
    raise DocumentParseError("could not decode the file with any known encoding")


def _strip_markdown_front_matter(text: str) -> str:
    """Drop a leading YAML/TOML front-matter block.

    A résumé exported from a notes app often starts with ``---`` metadata. It is not
    résumé content, and leaving it in pollutes the first chunk — which is exactly the
    chunk a retrieval hit for "自我评价" would return.
    """
    stripped = text.lstrip("\ufeff")
    if not stripped.startswith("---"):
        return text
    end = stripped.find("\n---", 3)
    if end == -1:
        return text
    return stripped[end + 4 :].lstrip("\n")


def _normalise(text: str) -> str:
    """Collapse the whitespace differences that come from the file, not from the author.

    Windows line endings, non-breaking spaces and runs of blank lines are artefacts of
    the writer. Removing them here means the character offsets recorded on chunks refer
    to text a user would recognise.
    """
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = cleaned.replace("\u00a0", " ").replace("\u3000", " ")
    lines = [line.rstrip() for line in cleaned.split("\n")]
    out: list[str] = []
    blank_run = 0
    for line in lines:
        if line:
            blank_run = 0
            out.append(line)
            continue
        blank_run += 1
        if blank_run <= 1:
            out.append("")
    return "\n".join(out).strip()


def _require(module: str, extra: str) -> Any:
    """Import an optional dependency, or explain how to install it.

    Returns ``Any`` on purpose: the alternative is annotating every pypdf and python-docx
    object this module touches, which would put those libraries on the critical path of a
    core that must not depend on them.
    """
    try:
        return import_module(module)
    except ImportError as exc:
        raise DocumentParseError(
            f"reading this file type needs the optional '{module}' package: "
            f'install it with pip install -e "packages/ai[{extra}]"',
            details={"module": module, "extra": extra},
        ) from exc
