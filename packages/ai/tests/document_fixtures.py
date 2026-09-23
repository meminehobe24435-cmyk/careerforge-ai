"""Byte-level builders for real PDF and DOCX files, using only the standard library.

These exist so the ingestion tests exercise the actual formats rather than a mock. A
mock would have proven that the code calls pypdf; it would not have proven that pypdf can
read what a user uploads.

The PDF builder writes the five objects a text-bearing PDF needs and computes the xref
offsets properly, because a fixture with a broken xref tests pypdf's recovery path
instead of its normal one. The DOCX builder writes the OPC package (content types,
relationships, document part) that python-docx expects.
"""

from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

__all__ = ["build_docx", "build_pdf"]

_DOCX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

_DOCX_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_XML_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}


def _escape(text: str) -> str:
    return "".join(_XML_ESCAPES.get(char, char) for char in text)


def build_docx(paragraphs: list[str], *, table: list[list[str]] | None = None) -> bytes:
    """Build a minimal but valid ``.docx`` holding ``paragraphs`` and an optional table."""
    body: list[str] = []
    for paragraph in paragraphs:
        body.append(f"<w:p><w:r><w:t xml:space='preserve'>{_escape(paragraph)}</w:t></w:r></w:p>")
    if table:
        rows = []
        for row in table:
            cells = "".join(
                f"<w:tc><w:p><w:r><w:t>{_escape(cell)}</w:t></w:r></w:p></w:tc>" for cell in row
            )
            rows.append(f"<w:tr>{cells}</w:tr>")
        body.append(f"<w:tbl>{''.join(rows)}</w:tbl>")

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body)}</w:body></w:document>"
    )

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _DOCX_CONTENT_TYPES)
        archive.writestr("_rels/.rels", _DOCX_RELS)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def build_pdf(pages: list[list[str]]) -> bytes:
    """Build a minimal text PDF, one page per element of ``pages``.

    A page list is used rather than a count so a fixture can mix a text page with a blank
    one — the partly-scanned document the ingestion code has to describe accurately.
    Concatenating two PDFs instead would test pypdf's xref recovery, not a real document.
    """
    objects: list[bytes] = []

    def add(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    def add_stream(content: bytes) -> int:
        header = f"<< /Length {len(content)} >>".encode("ascii")
        return add(header + b"\nstream\n" + content + b"\nendstream")

    # Reserve object numbers: 1 catalog, 2 pages, 3 font, then content + page per sheet.
    add(b"<< /Type /Catalog /Pages 2 0 R >>")
    add(b"")  # pages node, filled in below
    add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")

    escape = {"\\": r"\\", "(": r"\(", ")": r"\)"}
    content_ids = []
    for lines in pages:
        for line in lines:
            # A base-14 Helvetica font with WinAnsi encoding cannot represent Chinese, and
            # encoding with ``replace`` would silently write "???" — a fixture that
            # mangles its own text can hide a real extraction bug. Non-ASCII coverage
            # belongs to the DOCX and plain-text paths, which are UTF-8 throughout.
            if not line.isascii():
                raise ValueError(
                    f"build_pdf only supports ASCII text (got {line!r}); use build_docx for "
                    "non-ASCII fixtures"
                )
        text_ops = "".join(
            f"BT /F1 12 Tf 72 {720 - index * 20} Td ({_pdf_escape(line, escape)}) Tj ET\n"
            for index, line in enumerate(lines)
        )
        content_ids.append(add_stream(text_ops.encode("latin-1")))

    page_ids = [
        add(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode("ascii")
        )
        for content_id in content_ids
    ]
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    count = len(page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode("ascii")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, payload in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("ascii") + payload + b"\nendobj\n"

    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode(
        "ascii"
    )
    return bytes(out)


def _pdf_escape(text: str, table: dict[str, str]) -> str:
    return "".join(table.get(char, char) for char in text)
