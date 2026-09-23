"""Tests for document ingestion.

The fixtures are real PDF and DOCX files built byte-by-byte in
:mod:`tests.document_fixtures`, so these tests exercise what a user actually uploads.
The assertions concentrate on the failure modes, because a parser that returns the wrong
text confidently is worse than one that refuses:

* a Chinese résumé saved as GB18030 on Windows must not become mojibake;
* a scanned PDF must be reported as scanned, not as an empty document;
* an unsupported file must be refused with a reason, not silently read as text;
* a missing optional parser must name the extra to install.
"""

from __future__ import annotations

import pytest
from tests.document_fixtures import build_docx, build_pdf

from careerforge_ai.errors import (
    DocumentParseError,
    DocumentTooLargeError,
    UnsupportedDocumentError,
)
from careerforge_ai.parsing import documents
from careerforge_ai.parsing.documents import (
    DocumentFormat,
    detect_format,
    parse_document,
    sha256_of,
)

RESUME_ZH = """教育经历
某某大学 电子信息工程 本科 2019-2023

实习经历
某某科技 嵌入式软件实习生 使用 STM32 与 FreeRTOS 开发电机控制固件
"""


class TestFormatDetection:
    def test_reads_the_extension_first(self) -> None:
        assert detect_format("resume.PDF") is DocumentFormat.PDF
        assert detect_format("notes.md") is DocumentFormat.MARKDOWN
        assert detect_format("jd.txt") is DocumentFormat.TEXT
        assert detect_format("cv.docx") is DocumentFormat.DOCX

    def test_falls_back_to_the_declared_mime_type(self) -> None:
        # Browsers routinely send `text/plain` for a Markdown upload; the MIME type is
        # what makes an extension-less name usable at all.
        assert detect_format("download", "text/markdown") is DocumentFormat.MARKDOWN
        assert detect_format("download", "application/pdf") is DocumentFormat.PDF

    def test_ignores_a_charset_parameter(self) -> None:
        assert detect_format("x", "text/plain; charset=utf-8") is DocumentFormat.TEXT

    def test_unknown_type_has_no_format(self) -> None:
        assert detect_format("scan.png") is None
        assert detect_format("archive.zip", "application/zip") is None

    def test_text_native_formats_need_no_parser(self) -> None:
        assert DocumentFormat.TEXT.is_text_native
        assert DocumentFormat.MARKDOWN.is_text_native
        assert not DocumentFormat.PDF.is_text_native
        assert not DocumentFormat.DOCX.is_text_native


class TestPlainText:
    def test_reads_utf8(self) -> None:
        parsed = parse_document(RESUME_ZH.encode("utf-8"), filename="resume.txt")
        assert "嵌入式软件实习生" in parsed.text
        assert parsed.encoding == "utf-8"
        assert parsed.format is DocumentFormat.TEXT

    def test_reads_gb18030_without_mojibake(self) -> None:
        """A résumé saved by a Chinese Windows editor is usually GB18030, not UTF-8.

        Decoding it as UTF-8 would either fail or produce replacement characters, and
        every skill extracted from it afterwards would be wrong.
        """
        parsed = parse_document(RESUME_ZH.encode("gb18030"), filename="resume.txt")
        assert "嵌入式软件实习生" in parsed.text
        assert parsed.encoding == "gb18030"
        assert any("gb18030" in warning for warning in parsed.warnings), (
            "a non-UTF-8 guess must be reported, since a wrong guess is silent damage"
        )

    def test_strips_a_utf8_bom(self) -> None:
        parsed = parse_document("\ufeff标题\n正文".encode(), filename="notes.txt")
        assert parsed.text.startswith("标题")

    def test_normalises_line_endings_and_wide_spaces(self) -> None:
        raw = "第一行\r\n\r\n\r\n\r\n第二行\u3000结尾\u00a0x"
        parsed = parse_document(raw.encode(), filename="notes.txt")
        assert "\r" not in parsed.text
        assert "\u3000" not in parsed.text
        assert "\u00a0" not in parsed.text
        # Runs of blank lines collapse to one: extra blank lines are the writer's, not
        # the author's, and they shift every character offset downstream.
        assert "\n\n\n" not in parsed.text

    def test_whitespace_only_file_reads_as_empty(self) -> None:
        parsed = parse_document(b"   \n\n\t  ", filename="notes.txt")
        assert parsed.is_empty
        assert parsed.char_count == 0  # normalisation trims it to nothing
        # The upload itself was fine, so this is not a parse error — the caller decides
        # what an empty document means.
        assert parsed.size_bytes == 8

    def test_reports_size_and_content_hash(self) -> None:
        data = RESUME_ZH.encode()
        parsed = parse_document(data, filename="resume.txt")
        assert parsed.size_bytes == len(data)
        assert parsed.sha256 == sha256_of(data)
        assert len(parsed.sha256) == 64


class TestMarkdown:
    def test_keeps_the_body(self) -> None:
        parsed = parse_document("# 简介\n\n嵌入式工程师。".encode(), filename="cv.md")
        assert parsed.format is DocumentFormat.MARKDOWN
        assert "# 简介" in parsed.text

    def test_drops_yaml_front_matter(self) -> None:
        """Front matter is metadata, and it would otherwise pollute the first chunk."""
        raw = "---\ntitle: 简历\ntags: [embedded]\n---\n# 简介\n\n嵌入式工程师。"
        parsed = parse_document(raw.encode(), filename="cv.md")
        assert "title:" not in parsed.text
        assert parsed.text.startswith("# 简介")

    def test_front_matter_without_a_closing_marker_is_left_alone(self) -> None:
        # A résumé may legitimately start with a horizontal rule; mangling it would lose
        # real content, so an unterminated block is not treated as front matter.
        raw = "---\n真正的第一行"
        parsed = parse_document(raw.encode(), filename="cv.md")
        assert "真正的第一行" in parsed.text


class TestPdf:
    def test_extracts_text_and_counts_pages(self) -> None:
        pdf = build_pdf([["Alex Chen - Embedded Engineer", "STM32 / FreeRTOS / PID"]])
        parsed = parse_document(pdf, filename="resume.pdf")
        assert parsed.format is DocumentFormat.PDF
        assert "Alex Chen" in parsed.text
        assert "FreeRTOS" in parsed.text
        assert parsed.page_count == 1
        assert parsed.warnings == ()

    def test_counts_every_page(self) -> None:
        parsed = parse_document(
            build_pdf([["page one"], ["page two"], ["page three"]]), filename="long.pdf"
        )
        assert parsed.page_count == 3
        assert "page one" in parsed.text
        assert "page three" in parsed.text

    def test_the_pdf_fixture_refuses_non_ascii_rather_than_mangling_it(self) -> None:
        """A base-14 font cannot render Chinese, and silently writing "???" would let a
        broken extraction assertion pass. ASCII-only PDF fixtures, and an explicit error
        if one is written by mistake."""
        with pytest.raises(ValueError, match="ASCII"):
            build_pdf([["中文"]])

    def test_a_docx_carries_chinese_through_the_whole_path(self) -> None:
        docx = build_docx(["某某科技 嵌入式软件实习生", "使用 STM32 开发电机控制固件"])
        parsed = parse_document(docx, filename="resume.docx")
        assert "嵌入式软件实习生" in parsed.text
        assert "电机控制固件" in parsed.text

    def test_a_scanned_pdf_is_reported_not_silently_empty(self) -> None:
        """The most common real-world failure: a résumé exported as images.

        Returning an empty string would look to the pipeline like a blank résumé, and the
        user would be told their profile is empty rather than that their file needs OCR.
        """
        parsed = parse_document(build_pdf([[]]), filename="scan.pdf")
        assert parsed.is_empty
        assert parsed.warnings
        assert any("OCR" in warning for warning in parsed.warnings)

    def test_a_partly_scanned_pdf_says_how_many_pages(self) -> None:
        """A text page followed by a scanned one: readable, but incompletely.

        The warning is what lets the profile say "we read 1 of your 2 pages" instead of
        silently scoring half a résumé as if it were all of it.
        """
        pdf = build_pdf([["Alex Chen", "STM32"], []])
        parsed = parse_document(pdf, filename="mixed.pdf")
        assert parsed.page_count == 2
        assert not parsed.is_empty
        assert any("1/2" in warning for warning in parsed.warnings)

    def test_corrupt_pdf_raises_a_typed_error(self) -> None:
        with pytest.raises(DocumentParseError) as caught:
            parse_document(b"%PDF-1.4\ngarbage that is not a pdf", filename="broken.pdf")
        assert caught.value.code == "DOCUMENT_PARSE_FAILED"


class TestDocx:
    def test_reads_paragraphs(self) -> None:
        docx = build_docx(["Alex Chen", "嵌入式软件工程师", "STM32 / FreeRTOS"])
        parsed = parse_document(docx, filename="resume.docx")
        assert parsed.format is DocumentFormat.DOCX
        assert "嵌入式软件工程师" in parsed.text
        assert parsed.page_count is None  # DOCX has no page concept before rendering
        assert parsed.warnings == ()

    def test_reads_table_cells(self) -> None:
        """Skills are very often in a table, and a parser that only reads paragraphs
        silently drops the section that matters most."""
        docx = build_docx(["技能"], table=[["技能", "年限"], ["C", "3"]])
        parsed = parse_document(docx, filename="resume.docx")
        assert "技能 | 年限" in parsed.text
        assert "C | 3" in parsed.text

    def test_legacy_binary_doc_is_refused_with_guidance(self) -> None:
        ole2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64
        with pytest.raises(DocumentParseError) as caught:
            parse_document(ole2, filename="old.doc")
        assert ".docx" in str(caught.value)

    def test_empty_docx_reports_that_it_holds_no_text(self) -> None:
        parsed = parse_document(build_docx([]), filename="blank.docx")
        assert parsed.is_empty
        assert parsed.warnings


class TestRefusals:
    def test_unsupported_type_is_refused(self) -> None:
        with pytest.raises(UnsupportedDocumentError) as caught:
            parse_document(b"\x89PNG\r\n\x1a\n", filename="photo.png")
        assert caught.value.code == "UNSUPPORTED_DOCUMENT_TYPE"
        assert "photo.png" in str(caught.value)

    def test_empty_upload_is_a_parse_error(self) -> None:
        with pytest.raises(DocumentParseError):
            parse_document(b"", filename="empty.txt")

    def test_oversized_upload_is_refused_not_truncated(self, monkeypatch) -> None:
        """Truncating would build a plausible profile from partial material."""
        monkeypatch.setattr(documents, "MAX_DOCUMENT_BYTES", 32)
        with pytest.raises(DocumentTooLargeError) as caught:
            parse_document(b"x" * 64, filename="huge.txt")
        assert caught.value.code == "DOCUMENT_TOO_LARGE"
        assert "huge.txt" in str(caught.value)

    def test_a_missing_optional_parser_names_the_extra_to_install(self) -> None:
        with pytest.raises(DocumentParseError) as caught:
            documents._require("definitely_not_installed_package", "parsing")
        message = str(caught.value)
        assert "definitely_not_installed_package" in message
        assert "packages/ai[parsing]" in message


class TestDeterminism:
    def test_the_same_bytes_parse_identically(self) -> None:
        pdf = build_pdf(["Alex Chen", "STM32"])
        first = parse_document(pdf, filename="resume.pdf")
        second = parse_document(pdf, filename="resume.pdf")
        assert first == second

    def test_a_different_filename_does_not_change_the_text(self) -> None:
        # The name is metadata; if it leaked into the text, two uploads of the same
        # résumé would produce two different evidence graphs.
        data = RESUME_ZH.encode()
        assert (
            parse_document(data, filename="a.txt").text
            == parse_document(data, filename="b.txt").text
        )
