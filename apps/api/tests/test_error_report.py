"""The error sanitiser: what must never reach the ``agent_runs`` row.

A failed run is now recorded (PHASE 13), which means the failure's text is now a **row** — one copied
out of an arbitrary exception, sitting in a table an operator browses, exports and screenshots. The
exceptions on this path carry request bodies: ``httpx`` quotes the payload it failed on, and
``SchemaValidationError`` carries the model's raw output. A résumé is 2 000–20 000 characters of a
real person's data and an API key is a live credential.

So the sanitising happens **before** storage, and these tests drive it with a payload that genuinely
contains all three: a fake key in the vendor's shape, a bearer token, and a whole résumé. The
assertion is the blunt one — the stored text must not contain any of them — because anything softer
(did it redact *enough*?) is the kind of judgement that fails in production.

The tests also pin the other direction, which is easy to lose while chasing the first one: a
legitimate error sentence has to survive intact. The first version of this sanitiser replaced
"no provider in the chain could serve the request …" with ``[omitted:136 chars]``, which is a
diagnostic tool that deletes the diagnostic.
"""

from __future__ import annotations

import pytest

from careerforge_api.services.error_report import (
    MAX_ERROR_LENGTH,
    sanitize_error_text,
    summarise_document,
)
from tests.leak_fixtures import (
    DOCUMENT_TEXT,
    FAKE_API_KEY,
    FAKE_BEARER,
    LEAKY_ERROR,
    RESUME_EMAIL,
    RESUME_PHONE,
)

#: Everything the stored text must not contain.
FORBIDDEN: tuple[tuple[str, str], ...] = (
    ("the API key", FAKE_API_KEY),
    ("the bearer value", FAKE_BEARER.split()[1]),
    ("the résumé's phone number", RESUME_PHONE),
    ("the résumé's email address", RESUME_EMAIL),
    ("the résumé's body", "两轮自平衡机器人控制链路"),
    ("any part of the document, verbatim", DOCUMENT_TEXT[:60]),
)


class TestWhatMustDisappear:
    def test_a_leaky_message_loses_its_secrets_and_its_document(self) -> None:
        stored = sanitize_error_text(LEAKY_ERROR)
        assert stored, "the message was discarded entirely, which loses the diagnosis too"
        for label, needle in FORBIDDEN:
            assert needle not in stored, f"{label} survived sanitising: {stored!r}"
        # It still says *something*: a redaction that leaves a bare empty string is not a record.
        assert "[redacted:" in stored or "[omitted:" in stored

    def test_the_secret_shapes_are_named_rather_than_blanked(self) -> None:
        """An operator can act on "a bearer token was involved" and cannot act on "***".

        Checked on a message short enough to survive the document pass: when the whole message *is*
        a document, it collapses to a length marker (asserted above) and the individual marker names
        go with it — the identity of the secret is worth less than removing the document.
        """
        stored = (
            sanitize_error_text(
                f"upstream rejected the request: Authorization: {FAKE_BEARER} api_key={FAKE_API_KEY}"
            )
            or ""
        )
        assert stored.startswith("upstream rejected the request:"), stored
        # The header names what the *shape* was, the key rule names what the *credential* was. Which
        # of the two markers survives depends on their order, and both are honest; what matters is
        # that the value is gone, which the parametrised cases above assert individually.
        assert "redacted:" in stored, stored
        assert "api key" in stored or "openai key" in stored, stored
        assert FAKE_BEARER.split()[1] not in stored
        assert FAKE_API_KEY not in stored

    @pytest.mark.parametrize(
        ("label", "text", "needle"),
        [
            ("openai key", "failed with key sk-proj-abcdefghijklmnopqrstuvwxyz", "sk-proj-abcd"),
            ("github token", "auth ghp_abcdefghijklmnopqrstuvwxyz01 rejected", "ghp_abcdefgh"),
            ("aws key", "access key AKIAIOSFODNN7EXAMPLE denied", "AKIAIOSFODNN7EXAMPLE"),
            ("jwt", "token eyJhbGciOiJIUzI1NiJ9.cGF5bG9hZA.c2ln intended", "eyJhbGciOiJIUzI1NiJ9"),
            (
                "authorization header",
                "Authorization: Bearer abcdefghijklmnop refused",
                "abcdefghijklmnop",
            ),
            ("api_key assignment", "request api_key=topsecretvalue123 failed", "topsecretvalue123"),
            ("password", "password=hunter2hunter2 rejected", "hunter2hunter2"),
            (
                "email",
                "owner zhangwei.private@example.com not found",
                "zhangwei.private@example.com",
            ),
            ("phone", "contact 13800001111 unreachable", "13800001111"),
        ],
    )
    def test_each_shape_is_removed(self, label: str, text: str, needle: str) -> None:
        stored = sanitize_error_text(text) or ""
        assert needle not in stored, f"{label}: {stored!r}"

    def test_a_long_document_is_summarised_to_its_length(self) -> None:
        stored = sanitize_error_text(f"validation failed on body: {DOCUMENT_TEXT}") or ""
        for label, needle in FORBIDDEN:
            assert needle not in stored, label
        assert "[omitted:" in stored, stored
        # The length is kept on purpose: "a 400-character document leaked into the error" is
        # exactly the diagnostic an operator needs, and it costs no privacy.
        assert "chars]" in stored

    def test_summarise_document_is_available_for_known_documents(self) -> None:
        assert summarise_document(DOCUMENT_TEXT) == f"[omitted:{len(DOCUMENT_TEXT)} chars]"


class TestWhatMustSurvive:
    """A sanitiser that eats the diagnosis is a sanitiser that hides incidents."""

    @pytest.mark.parametrize(
        "message",
        [
            "no provider in the chain could serve the request",
            "[PROVIDER_UNAVAILABLE] no provider in the chain could serve the request",
            "upstream returned HTTP 429 after 3 attempts; retry-after=30",
            "upstream did not answer within the read timeout",
            'model output did not satisfy the declared schema: {"role": "engineer"}',
            "vector backend is unreachable",
        ],
    )
    def test_an_ordinary_error_message_is_left_alone(self, message: str) -> None:
        assert sanitize_error_text(message) == message

    def test_a_long_but_legitimate_message_is_not_collapsed(self) -> None:
        """136 characters, one sentence, no document — it must still be readable.

        This is the case that made the first version of the rule wrong.
        """
        message = (
            "[PROVIDER_UNAVAILABLE] no provider in the chain could serve the request "
            "{'chain': ['scripted', 'heuristic'], 'errors': ['scripted:ProviderTimeout']}"
        )
        assert len(message) > 120
        assert sanitize_error_text(message) == message

    def test_a_stack_trace_keeps_its_lines(self) -> None:
        """Four lines stay four lines. Indentation is normalised, structure is not.

        The first version collapsed every whitespace run, which folded the traceback into one line —
        the same mistake as deleting the message, one layer down.
        """
        trace = (
            "Traceback (most recent call last):\n"
            '  File "provider.py", line 42, in chat\n'
            "    return await self._call(payload)\n"
            "ValueError: unexpected keyword argument"
        )
        stored = sanitize_error_text(trace) or ""
        assert stored.count("\n") == 3
        for fragment in (
            "Traceback (most recent call last):",
            'File "provider.py", line 42, in chat',
            "await self._call(payload)",
            "ValueError: unexpected keyword argument",
        ):
            assert fragment in stored, stored


class TestTheBounds:
    def test_the_result_is_bounded(self) -> None:
        # A document long enough to be summarised, then clipped: both bounds hold.
        stored = sanitize_error_text(DOCUMENT_TEXT * 20) or ""
        assert len(stored) <= MAX_ERROR_LENGTH

    def test_a_single_long_token_is_clipped(self) -> None:
        # 150 characters: past the run-summarising threshold, under the storage bound.
        stored = sanitize_error_text("z" * 250 + " failed") or ""
        assert stored == "[omitted:250 chars] failed"
        assert len(stored) <= MAX_ERROR_LENGTH

    def test_a_message_over_the_bound_is_clipped(self) -> None:
        stored = sanitize_error_text("boom " * 200) or ""
        assert len(stored) <= MAX_ERROR_LENGTH
        assert stored.endswith("…")

    def test_none_and_empty_stay_none(self) -> None:
        assert sanitize_error_text(None) is None
        assert sanitize_error_text("") is None
        assert sanitize_error_text("   ") is None
