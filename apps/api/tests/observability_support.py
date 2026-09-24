"""Shared helper for the observability suites.

Split out when ``test_observability.py`` crossed the 500-line guard. Two files now read the same
listing endpoint — the run/cost suite and the cache/prompt suite — and a copied query builder
would let them drift into disagreeing about the endpoint's contract.

Not named ``test_*`` so pytest does not collect it, the same convention as
``application_support.py`` and ``interview_data.py``.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import Session


async def fetch_runs(client: AsyncClient, session: Session, **params: str) -> dict:
    """Read ``/ai-runs`` and assert the request itself worked, so a 500 cannot read as a pass."""
    query = "&".join(f"{key}={value}" for key, value in params.items())
    response = await client.get(f"/api/v1/ai-runs?{query}", headers=session.headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]
