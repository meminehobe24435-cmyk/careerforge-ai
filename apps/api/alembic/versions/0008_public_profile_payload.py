"""PHASE 10: the stored public projection and its PII findings.

Revision ID: 0008
Revises: 0007
Create Date: 2026-02-13

Two columns added to ``public_profiles`` (``docs/DATABASE.md`` §2.1), both for the same
reason: a public page must be cheap to serve and honest about what was removed.

* ``public_payload`` keeps the projection exactly as published, so a recruiter refreshing the
  page does not trigger a model call per view. The private parts are filtered on the way out,
  which is what makes "I turned that off" true immediately rather than at the next republish.
* ``pii_findings`` records what the scanner found when the page was generated, so the owner can
  be shown what was masked instead of being reassured by silence.

Both are NOT NULL with server defaults, so the migration is safe on a table that already has
rows (an unpublished profile has no payload, which is exactly what ``{}`` says).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from careerforge_api.db.compat import JSONType

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "public_profiles",
        sa.Column("public_payload", JSONType(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "public_profiles",
        sa.Column("pii_findings", JSONType(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("public_profiles", "pii_findings")
    op.drop_column("public_profiles", "public_payload")
