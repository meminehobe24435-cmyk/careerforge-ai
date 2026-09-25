"""Sanitising a failure before it is written to ``agent_runs``.

Why this module exists
----------------------
An error message is the one field in the observability tables that is copied out of an arbitrary
exception, and the exceptions on this path carry request bodies. ``httpx`` includes the URL and
sometimes the body in a transport error; ``SchemaValidationError`` carries the model's raw output
(the "raw" detail the validator feeds back for repair); a provider SDK happily echoes the payload
it failed to parse. A resume or a job description is 2 000–20 000 characters of a real person's
data, and a leaked API key is a live credential. So the text is sanitised **before** it is stored,
not masked in the UI afterwards: the row itself must be safe to read, export and screenshot.

What "sanitised" means here, and what it does not
------------------------------------------------
Three rules, all of them structural rather than clever:

1. **Secrets are removed by shape.** Anything that looks like a bearer token, an API key
   (``sk-…``, ``sk-ant-…``, ``ghp_…``, ``AKIA…``), a ``Authorization:``/``api_key=`` assignment, a
   JWT, or a long high-entropy hex/base64 run is replaced by ``[redacted:…]`` naming the shape it
   matched. Shape matching is deliberately over-inclusive: a false redaction costs a reader one
   clue, a missed one costs the candidate their key.
2. **Long free text is summarised, not copied.** A stretch of 120+ characters that is also *wordy*
   (15+ whitespace-separated parts) becomes ``[omitted: N chars]``. That is what keeps a résumé out
   of the table: its length is still visible, which is diagnostically useful, while its content is
   not. The wordiness test matters in the other direction too — a legitimate 136-character error
   ("no provider in the chain could serve the request", with the chain and the errors listed after
   it) has to survive, and the first version of this module replaced it with a bare length marker.
3. **The result is bounded.** Whole messages are clipped to :data:`MAX_ERROR_LENGTH` with a
   marker, so a pathological error cannot turn one row into a megabyte.

It does **not** try to identify individuals, and it does not touch ``error_code`` or the
classification: those are derived from the exception's type, which is safe by construction and is
what an operator acts on.
"""

from __future__ import annotations

import re

__all__ = [
    "MAX_ERROR_LENGTH",
    "REDACTED",
    "sanitize_error_text",
    "summarise_document",
]

REDACTED = "[redacted]"

#: Longest stored error message. Long enough for a useful sentence plus a stack frame, short enough
#: that no row can hold a document.
MAX_ERROR_LENGTH = 400

#: A run of non-space characters this long or longer is treated as embedded document text rather
#: than as prose. Real words in an error message are far shorter; a base64 blob, a JSON dump or a
#: paragraph of a résumé is far longer.
_MIN_DOCUMENT_RUN = 120

#: How many characters make a stretch of text a *document* rather than a message. The value differs
#: by script because the signal does: 120 latin characters is a long sentence ("no provider in the
#: chain could serve the request {'chain': …}" is 148 and must survive), while 120 CJK characters is
#: already several paragraphs of a résumé. Latin text needs length *and* sentence structure (see
#: :data:`_SENTENCE_END_RE`) before it is treated as prose, because error messages quote dicts.
_MIN_DOCUMENT_CJK = 90
_MIN_DOCUMENT_LATIN = 300

#: A line of latin text needs this many words before it counts as prose rather than a quoted payload.
_MIN_DOCUMENT_WORDS = 40

#: Sentence-ending punctuation, including the full-width forms a Chinese document uses.
_SENTENCE_END_RE = re.compile(r"[.!?。！？；;]\s|\n")

#: How many CJK characters make a run document-like. Below this, Chinese text is a message:
#: "岗位描述解析失败，请检查文本内容" is 16 characters and must survive.
_CJK_DOCUMENT_CHARS = 40

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")

#: Prefixes that introduce echoed request material. Kept narrow on purpose: ``text=``, ``body=`` and
#: ``input=`` are what an SDK prints when it reports the payload it could not send.
_ECHOED_MATERIAL_PREFIXES = ("body=", "body:", "payload=", "input=", "text=", "content=")

#: Redaction markers that mean the text held something a person's **material** would hold — an
#: address, a phone number. A marker for a key or a bearer token is a leak of *credentials* and says
#: nothing about the surrounding text being a document.
_PII_MARKERS = ("[redacted:email]", "[redacted:phone number]")

#: Shapes that must never reach the database. Ordered so that the specific prefixes are tried
#: before the generic "long token" rule, which would otherwise swallow them into one bucket.
#:
#: Single-line only (no ``\n`` in the value pattern): a header is one line, and a pattern that can
#: cross lines swallows the payload printed underneath it — which is how an early version of the
#: bearer rule deleted everything after the header *except* the token itself.
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Order inside this tuple is load-bearing. The scheme-specific rules run first so the marker can
    # name what was there ("bearer token"), and the generic ``Authorization:`` value rule is guarded
    # by a lookahead over the *rest of the line*: without that guard it matches the word "Bearer"
    # itself, eats it, and leaves the actual token — which is exactly what an early version of this
    # module did.
    ("bearer token", re.compile(r"(?i)\bbearer[^\S\n]+\S+")),
    ("basic auth", re.compile(r"(?i)\bbasic[^\S\n]+[A-Za-z0-9+/=]{8,}")),
    (
        "authorization header",
        re.compile(r"(?i)\b(?:authorization|proxy-authorization)\b[^\S\n]*[:=][^\S\n]*\S+"),
    ),
    (
        "api key",
        re.compile(
            r"(?i)\b(?:api[_-]?key|apikey|secret|token|password|passwd|pwd)\b[^\S\n]*[:=][^\S\n]*"
            r"[\"']?[^\s\n\"']+"
        ),
    ),
    ("openai key", re.compile(r"\bsk-[A-Za-z0-9_-]{8,}")),
    ("anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{8,}")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{8,}")),
    ("aws access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{12,}")),
    ("google key", re.compile(r"\bAIza[0-9A-Za-z_-]{10,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{4,}")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("phone number", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

#: A long unbroken run of token-ish characters: base64, hex digests, minified JSON.
_LONG_TOKEN_RE = re.compile(rf"[A-Za-z0-9+/=_\-]{{{_MIN_DOCUMENT_RUN},}}")


def _redact(text: str) -> str:
    for label, pattern in _SECRET_PATTERNS:
        text = pattern.sub(f"[redacted:{label}]", text)
    return text


def _summarise_runs(text: str) -> str:
    """Replace long unbroken run(s) with a length marker."""
    text = _LONG_TOKEN_RE.sub(lambda match: f"[omitted:{len(match.group(0))} chars]", text)
    return _summarise_document_span(text)


def _looks_like_document(chunk: str) -> bool:
    """Whether a line of a failure message is copied prose rather than a diagnostic.

    Two signals, because the two scripts fail differently, and both were measured against the
    counterexamples in ``tests/test_error_report.py``:

    * **Chinese** — 40+ CJK characters in a 90+ character span. A Chinese error message is short
      (``岗位描述解析失败，请检查文本内容`` is 16 characters); a Chinese résumé is paragraphs. No
      length-only threshold separates those from a long ASCII diagnostic either, because a long
      ASCII diagnostic has *no* CJK at all.
    * **Latin** — 300+ characters, 40+ words **and** sentence punctuation. Length and wordiness
      alone are not enough: ``no provider in the chain could serve the request {'chain': […]}`` is
      148 characters of a quoted dict, it is an error message, and the first version of this rule
      deleted it. Prose has sentences; a repr of a payload does not.

    Neither signal tries to identify a person or a topic. It answers one question — "was a document
    pasted into this exception?" — and errs toward yes, because the cost of being wrong is a
    redaction marker where a clue used to be, and the cost of the other error is a candidate's
    résumé sitting in a table an operator browses.
    """
    if len(_CJK_RE.findall(chunk)) >= _CJK_DOCUMENT_CHARS and len(chunk) >= _MIN_DOCUMENT_CJK:
        return True
    # Text that held a person's own material — an address, a phone number — is a document even when
    # the rest of the sentence looks like a diagnostic. This also covers the case the length rules
    # cannot: a résumé whose Chinese body has just been redacted down to markers.
    lowered = chunk.lower()
    if any(marker in lowered for marker in _PII_MARKERS):
        return True
    # An SDK printing the payload it failed to send.
    if (
        any(prefix in lowered for prefix in _ECHOED_MATERIAL_PREFIXES)
        and len(chunk) >= _MIN_DOCUMENT_CJK
    ):
        return True
    return (
        len(chunk) >= _MIN_DOCUMENT_LATIN
        and len(chunk.split()) >= _MIN_DOCUMENT_WORDS
        and bool(_SENTENCE_END_RE.search(chunk))
    )


def _summarise_document_span(text: str) -> str:
    """Collapse the lines of ``text`` that are copied prose, keeping the ones that are diagnostics."""
    parts: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        newline = text.find("\n", index)
        chunk = text[index:] if newline == -1 else text[index:newline]
        parts.append(f"[omitted:{len(chunk)} chars]" if _looks_like_document(chunk) else chunk)
        if newline == -1:
            break
        parts.append("\n")
        index = newline + 1
    # Neighbouring markers separated by one space are one document, not several: fold them.
    return re.sub(
        r"(?:\[omitted:\d+ chars\][ ]){2,}\[omitted:\d+ chars\]",
        lambda match: _fold_omissions(match.group(0)),
        "".join(parts),
    )


def _fold_omissions(span: str) -> str:
    total = sum(int(value) for value in re.findall(r"\[omitted:(\d+) chars\]", span))
    return f"[omitted:{total} chars]"


def summarise_document(text: str, *, limit: int = _MIN_DOCUMENT_RUN) -> str:
    """Replace ``text`` with a bare length marker — for material known to be a document."""
    return f"[omitted:{len(text)} chars]"


def sanitize_error_text(text: str | None, *, limit: int = MAX_ERROR_LENGTH) -> str | None:
    """A failure message safe to store. ``None`` in, ``None`` out.

    The order matters: secrets are removed first, because redacting a shape is a local operation
    that does not care how the text is chunked, while the run-summarising pass works on lengths and
    would otherwise fold a key into one "omitted" span and lose the fact that a key was there at
    all.
    """
    if text is None:
        return None
    cleaned = _redact(str(text))
    cleaned = _summarise_runs(cleaned)
    # Collapse the whitespace a removed run leaves behind, so the stored text still reads — but
    # never the newlines: a stack trace's structure is its content, and folding four lines into one
    # turns a diagnostic into a paragraph.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{2,}", "\n", cleaned).strip()
    if not cleaned:
        return None
    if len(cleaned) > limit:
        cleaned = cleaned[: limit - 1].rstrip() + "…"
    return cleaned
