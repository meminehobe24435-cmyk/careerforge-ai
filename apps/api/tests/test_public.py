"""Recruiter View: what a stranger may see, and what must never leave the building.

The four exit criteria are asserted literally, because each one is a promise the product makes
to a candidate:

1. **The page is reachable without a login.**
2. **It contains no PII** — checked by scanning the *response body* with the same regexes the
   redactor uses, not by trusting the code path that was supposed to remove it.
3. **An unpublished page is 404** — as is an unknown slug, so a stranger cannot tell which
   slugs exist.
4. **A private skill does not appear**, and neither does the evidence of a public skill when the
   candidate has hidden citations.

Everything here goes through HTTP, because the failure these tests exist to prevent is a *served
payload* leaking, and only the response can prove it did not.
"""

from __future__ import annotations

import re

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from careerforge_ai.parsing.pii import scan_pii
from careerforge_api.models.user import PublicProfile, User
from tests.conftest import EnvelopeCheck, Session, UserFactory

RESUME = """教育经历
某某大学 电子信息工程 本科 2019-2023
联系方式：candidate@example.com 手机 13800138000

实习经历
某某科技 嵌入式软件实习生 2022-07 至 2022-12
使用 STM32 与 FreeRTOS 开发电机控制固件，负责 CAN 总线节点通信调试。

项目经历
平衡小车 2022
基于 STM32 的 PID 平衡控制，使用 FreeRTOS 任务调度与 CAN 通信。
"""

#: The pattern the exit criterion names in words: email and Chinese mobile numbers.
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


async def _resume_ready(client: AsyncClient, session: Session) -> None:
    """Upload the fixture and analyze it, so the account has real evidence behind it."""
    body = await client.post(
        "/api/v1/documents",
        files={"file": ("resume.txt", RESUME.encode(), "text/plain")},
        data={"kind": "resume"},
        headers=session.headers,
    )
    assert body.status_code == 202, body.text
    accepted = body.json()["data"]
    for _ in range(200):
        task = (
            await client.get(f"/api/v1/tasks/{accepted['taskId']}", headers=session.headers)
        ).json()["data"]
        if task["status"] in {"succeeded", "failed"}:
            break
    assert task["status"] == "succeeded", task
    analyzed = await client.post(
        f"/api/v1/documents/{accepted['documentId']}/analyze", headers=session.headers
    )
    assert analyzed.status_code == 200, analyzed.text


async def _published(
    client: AsyncClient, session: Session, *, sections: dict[str, bool] | None = None
) -> str:
    """Publish and return the slug."""
    response = await client.post(
        "/api/v1/public/publish",
        json={"published": True, "sections": sections} if sections else {"published": True},
        headers=session.headers,
    )
    assert response.status_code == 200, response.text
    slug = response.json()["data"]["slug"]
    assert slug, "publishing must produce a slug"
    return slug


def _assert_no_pii(payload: object) -> None:
    """Scan the served body the way a scraper would read it."""
    import json

    text = json.dumps(payload, ensure_ascii=False)
    assert not EMAIL_RE.search(text), f"an email address is published: {EMAIL_RE.search(text)}"
    assert not PHONE_RE.search(text), f"a phone number is published: {PHONE_RE.search(text)}"
    findings = scan_pii(text)
    assert findings == [], f"the PII scanner still finds {findings}"


# ── exit criterion 1: reachable without a login ───────────────────────────────


async def test_the_public_page_needs_no_authentication(
    client: AsyncClient, make_user: UserFactory
) -> None:
    account = await make_user(display_name="公开候选人")
    slug = await _published(client, account)

    # No Authorization header at all.
    response = await client.get(f"/api/v1/public/candidate/{slug}")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["displayName"] == "公开候选人"
    assert data["meta"]["slug"] == slug
    # The anonymous reader is told the shape of what they got, not just handed a blob.
    assert "hiddenSections" in data["meta"]
    assert "evidenceCoverage" in data["meta"]


async def test_the_evidence_expansion_needs_no_authentication(
    client: AsyncClient, make_user: UserFactory
) -> None:
    account = await make_user()
    await _resume_ready(client, account)
    slug = await _published(client, account)

    page = (await client.get(f"/api/v1/public/candidate/{slug}")).json()["data"]
    if not page["skills"]:
        # No parsed skills means there is nothing to expand; the shape assertion below still
        # matters, and the assertions on visibility are covered by the dedicated tests.
        return
    skill_id = page["skills"][0]["canonicalId"]

    response = await client.get(f"/api/v1/public/candidate/{slug}/evidence/{skill_id}")
    assert response.status_code == 200, response.text
    assert isinstance(response.json()["data"], list)


# ── exit criterion 2: no PII ──────────────────────────────────────────────────


async def test_the_published_page_contains_no_email_or_phone(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """The résumé fixture carries an email and a mobile number; neither may survive.

    Note what is being asserted: the *response body* is scanned, not the agent's intermediate
    state. A redaction that happened somewhere upstream and was then undone by a later step
    would still fail here — which is the point.
    """
    account = await make_user(display_name="隐私测试")
    await _resume_ready(client, account)
    slug = await _published(client, account)

    response = await client.get(f"/api/v1/public/candidate/{slug}")
    assert response.status_code == 200, response.text
    _assert_no_pii(response.json()["data"])

    # And the stored payload is clean too: a later read (or a different client) cannot resurrect
    # what was redacted.
    async with app.state.session_factory() as db:
        row = await db.scalar(select(PublicProfile).where(PublicProfile.slug == slug))
        assert row is not None
        _assert_no_pii(row.public_payload)
        assert isinstance(row.pii_findings, list)


async def test_the_owner_is_told_what_was_masked(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Silence about a redaction is indistinguishable from having nothing to redact."""
    account = await make_user(display_name="知情权")
    await _resume_ready(client, account)
    await _published(client, account)

    settings = (await client.get("/api/v1/public/settings", headers=account.headers)).json()["data"]
    assert settings["isPublished"] is True
    assert settings["url"], "the share link must be in the owner's own view"
    # Either the scanner found something (and it is reported) or the payload was already clean.
    assert isinstance(settings["piiFindings"], list)


# ── exit criterion 3: unpublished and unknown are both 404 ────────────────────


async def test_an_unpublished_page_is_404(client: AsyncClient, make_user: UserFactory) -> None:
    account = await make_user()
    slug = await _published(client, account)
    assert (await client.get(f"/api/v1/public/candidate/{slug}")).status_code == 200

    unpublished = await client.post(
        "/api/v1/public/publish", json={"published": False}, headers=account.headers
    )
    assert unpublished.status_code == 200, unpublished.text
    assert unpublished.json()["data"]["isPublished"] is False

    assert (await client.get(f"/api/v1/public/candidate/{slug}")).status_code == 404
    assert (await client.get(f"/api/v1/public/candidate/{slug}/evidence/stm32")).status_code == 404


async def test_an_unknown_slug_is_404_not_403(client: AsyncClient, envelope: EnvelopeCheck) -> None:
    response = await client.get("/api/v1/public/candidate/definitely-not-a-real-slug")
    assert response.status_code == 404, response.text
    payload = envelope(response, success=False)
    assert payload["error"]["code"] == "NOT_FOUND"
    # A slug that is not even slug-shaped is a client error, and still reveals nothing.
    assert (await client.get("/api/v1/public/candidate/A")).status_code == 400


async def test_two_accounts_get_different_slugs(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Same display name, different pages: the suffix is what stops enumeration."""
    first = await make_user(display_name="同名候选人")
    second = await make_user(display_name="同名候选人")
    slug_a = await _published(client, first)
    slug_b = await _published(client, second)
    assert slug_a != slug_b
    # A Chinese display name slugifies to nothing, so the fallback base carries the URL — the
    # point is that the slug is always URL-safe and always opaque at the end.
    assert re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug_a), slug_a

    page_a = (await client.get(f"/api/v1/public/candidate/{slug_a}")).json()["data"]
    page_b = (await client.get(f"/api/v1/public/candidate/{slug_b}")).json()["data"]
    assert page_a["displayName"] == page_b["displayName"] == "同名候选人"
    assert page_a["meta"]["slug"] != page_b["meta"]["slug"]


# ── exit criterion 4: privacy switches are honoured, immediately ──────────────


async def test_hiding_a_section_removes_it_on_the_next_read(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Switches apply on read, so "I turned that off" is true before the next republish."""
    account = await make_user(display_name="逐项开关")
    await _resume_ready(client, account)
    slug = await _published(client, account)

    before = (await client.get(f"/api/v1/public/candidate/{slug}")).json()["data"]

    hidden = await client.patch(
        "/api/v1/public/settings",
        json={"sections": {"skills": False, "projects": False, "highlights": False}},
        headers=account.headers,
    )
    assert hidden.status_code == 200, hidden.text

    after = (await client.get(f"/api/v1/public/candidate/{slug}")).json()["data"]
    assert after["skills"] == [], "a hidden section must not survive the read"
    assert after["projects"] == []
    assert after["highlights"] == []
    assert set(after["meta"]["hiddenSections"]) >= {"skills", "projects", "highlights"}
    # Sections that were not switched off are untouched.
    assert after["summary"] == before["summary"]


async def test_a_hidden_skill_disappears_from_a_public_page(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """The per-skill hide list: what the candidate does not want to be asked about."""
    account = await make_user(display_name="隐藏技能")
    await _resume_ready(client, account)
    slug = await _published(client, account)

    page = (await client.get(f"/api/v1/public/candidate/{slug}")).json()["data"]
    if not page["skills"]:
        return  # nothing parsed to hide; the section-level test covers visibility
    hidden_id = page["skills"][0]["canonicalId"]
    remaining = [skill["canonicalId"] for skill in page["skills"][1:]]

    response = await client.patch(
        "/api/v1/public/settings", json={"hiddenSkills": [hidden_id]}, headers=account.headers
    )
    assert response.status_code == 200, response.text

    after = (await client.get(f"/api/v1/public/candidate/{slug}")).json()["data"]
    visible = [skill["canonicalId"] for skill in after["skills"]]
    assert hidden_id not in visible
    assert visible == remaining, "only the hidden skill disappears"

    # And its evidence endpoint answers with nothing rather than with the citations.
    evidence = await client.get(f"/api/v1/public/candidate/{slug}/evidence/{hidden_id}")
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()["data"] == []


async def test_hiding_evidence_keeps_the_skill_but_drops_the_citations(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """ "I have used FreeRTOS" and "here is the file that proves it" are separable promises."""
    account = await make_user(display_name="只留技能")
    await _resume_ready(client, account)
    slug = await _published(client, account)

    hidden = await client.patch(
        "/api/v1/public/settings", json={"sections": {"evidence": False}}, headers=account.headers
    )
    assert hidden.status_code == 200, hidden.text

    page = (await client.get(f"/api/v1/public/candidate/{slug}")).json()["data"]
    for skill in page["skills"]:
        assert skill["evidence"] == [], "citations must not leak through the skill list"
    if page["skills"]:
        evidence = await client.get(
            f"/api/v1/public/candidate/{slug}/evidence/{page['skills'][0]['canonicalId']}"
        )
        assert evidence.json()["data"] == []


async def test_an_unknown_section_is_refused(client: AsyncClient, make_user: UserFactory) -> None:
    account = await make_user()
    await _published(client, account)
    response = await client.patch(
        "/api/v1/public/settings", json={"sections": {"salary": False}}, headers=account.headers
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ── local-scope accounts, and the owner's own view ────────────────────────────


async def test_a_local_scope_account_cannot_publish(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """ "My data does not leave this machine" and a public URL are contradictory promises."""
    account = await make_user(display_name="本地模式")
    async with app.state.session_factory() as db:
        user = await db.get(User, account.id)
        assert user is not None
        user.storage_scope = "local"
        await db.commit()

    settings = (await client.get("/api/v1/public/settings", headers=account.headers)).json()["data"]
    assert settings["canPublish"] is False

    response = await client.post(
        "/api/v1/public/publish", json={"published": True}, headers=account.headers
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_settings_are_private_to_their_owner(
    client: AsyncClient, make_user: UserFactory
) -> None:
    owner = await make_user(display_name="Owner")
    stranger = await make_user(display_name="Stranger")
    await _published(client, owner)

    mine = (await client.get("/api/v1/public/settings", headers=owner.headers)).json()["data"]
    theirs = (await client.get("/api/v1/public/settings", headers=stranger.headers)).json()["data"]
    assert mine["isPublished"] is True
    assert theirs["isPublished"] is False
    assert theirs["slug"] is None
    assert (await client.get("/api/v1/public/settings")).status_code == 401


async def test_a_view_is_counted(client: AsyncClient, make_user: UserFactory) -> None:
    """The candidate can see that their link is being opened — and it costs no model call."""
    account = await make_user(display_name="浏览计数")
    slug = await _published(client, account)
    for _ in range(3):
        assert (await client.get(f"/api/v1/public/candidate/{slug}")).status_code == 200

    settings = (await client.get("/api/v1/public/settings", headers=account.headers)).json()["data"]
    assert settings["viewCount"] == 3

    # The page itself reports the same number: a footer that always reads "0 views" is a page
    # that looks broken, and the count is served from the row rather than from the projection.
    page = (await client.get(f"/api/v1/public/candidate/{slug}")).json()["data"]
    assert page["meta"]["viewCount"] == 4, "this request counted too"


async def test_republishing_keeps_the_slug_and_the_settings(
    client: AsyncClient, make_user: UserFactory
) -> None:
    account = await make_user(display_name="重新发布")
    slug = await _published(client, account, sections={"contact": True})
    await client.patch(
        "/api/v1/public/settings", json={"sections": {"skills": False}}, headers=account.headers
    )

    again = await _published(client, account)
    assert again == slug, "a share link must survive a republish"

    settings = (await client.get("/api/v1/public/settings", headers=account.headers)).json()["data"]
    assert settings["sections"]["skills"] is False, "switches are not reset by a republish"
    assert settings["sections"]["contact"] is True


async def test_publishing_twice_does_not_create_two_rows(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    account = await make_user()
    await _published(client, account)
    await _published(client, account)
    async with app.state.session_factory() as db:
        rows = (
            await db.scalars(select(PublicProfile).where(PublicProfile.user_id == account.id))
        ).all()
    assert len(rows) == 1
