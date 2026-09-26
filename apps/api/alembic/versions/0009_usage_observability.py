"""PHASE 13: usage status, cached tokens, a failure code — and counters that may be ``NULL``.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-26

Five changes to the two observability tables, all of them one idea: **"we were not told" and
"zero" are different facts, and the cost page is a claim about money.**

``agent_runs`` and ``llm_calls``
-------------------------------
* ``prompt_tokens``/``completion_tokens``/``total_tokens``/``cost_usd``/``cost_cny`` become
  **nullable**, and ``NULL`` means *the provider did not report usage*. Before this migration the
  columns were ``NOT NULL`` and the structured call path — the only path any agent uses — wrote
  ``0`` for every call, so a paid deployment's cost page read ``$0.00`` for work it had genuinely
  paid for (``docs/QUALITY.md`` §7.1). ``SUM`` skips ``NULL``, which is exactly the behaviour a
  partial total needs.
* ``usage_status`` records *which kind of fact* the numbers beside it are:
  ``reported`` / ``estimated`` / ``cached`` / ``unavailable``, plus ``legacy`` for rows that
  already existed. The backfill is ``legacy`` rather than ``reported`` on purpose: those rows hold
  ``0`` written by a version that had no status to record, so calling them ``reported`` would claim
  a measurement nobody took.
* ``cached_tokens`` records the vendor-side prompt-cache hit count where the vendor reports one
  (OpenAI's ``prompt_tokens_details.cached_tokens``, DeepSeek's ``prompt_cache_hit_tokens``).
  ``NULL`` means "not reported" — Ollama and the heuristic provider never report it, and a ``0``
  there would read as "nothing was cached".

``agent_runs`` only
-------------------
* ``error_code`` is the machine-readable classification (``PROVIDER_UNAVAILABLE``, ``TIMEOUT``, …)
  of the sanitized ``error`` text. PHASE 12's finding was that a failed request left *no row at
  all*; now that it does, the row has to say what failed, and free text alone is not something an
  operator can filter on.

The tables are rebuilt by ``batch_alter_table`` because SQLite cannot ALTER a column's nullability or
add a CHECK in place — but the strategy is ``recreate="auto"``, **not** ``"always"``. ``auto`` asks the
dialect and still rebuilds on SQLite, where a rebuild is the only option; ``always`` forced the same
rebuild on PostgreSQL, where it is neither needed nor possible: dropping ``agent_runs`` trips over the
foreign key ``llm_calls.run_id`` references and the migration dies with
``DependentObjectsStillExistError: cannot drop constraint pk_agent_runs on table agent_runs because
other objects depend on it``.

That failure is worth recording rather than just fixing. The PostgreSQL migration path had **never been
executed** — no PostgreSQL server on the development machine — and the release proof said so in its
``NOT RUN`` table. The first run of the ``api-postgres`` CI job (2026-09-26) is what turned "the
migrations are dialect-aware, but that is not evidence" into evidence of a real bug.

``docs/DATABASE.md`` §6 requires a working ``downgrade()``: it restores the original shape and deletes
the rows the original ``NOT NULL`` columns cannot hold — stated here rather than losing them silently.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from careerforge_api.db.compat import NumericType

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_USAGE_STATUSES = "'reported', 'estimated', 'cached', 'unavailable', 'legacy'"

_COUNT_TYPES: dict[str, sa.types.TypeEngine[object]] = {
    "prompt_tokens": sa.Integer(),
    "completion_tokens": sa.Integer(),
    "total_tokens": sa.Integer(),
    "cost_usd": NumericType(10, 6),
    "cost_cny": NumericType(10, 6),
}


def upgrade() -> None:
    # `auto`: rebuild where the dialect cannot ALTER in place (SQLite), alter in place where it can
    # (PostgreSQL). See the module docstring for the CI failure that `always` produced.
    with op.batch_alter_table("agent_runs", recreate="auto") as batch:
        for column, column_type in _COUNT_TYPES.items():
            batch.alter_column(column, existing_type=column_type, nullable=True)
        batch.add_column(sa.Column("cached_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("usage_status", sa.Text(), nullable=True))
        batch.add_column(sa.Column("error_code", sa.Text(), nullable=True))
        batch.create_check_constraint(
            "usage_status_valid",
            f"usage_status IS NULL OR usage_status IN ({_USAGE_STATUSES})",
        )

    with op.batch_alter_table("llm_calls", recreate="auto") as batch:
        for column, column_type in _COUNT_TYPES.items():
            batch.alter_column(column, existing_type=column_type, nullable=True)
        batch.add_column(sa.Column("cached_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("usage_status", sa.Text(), nullable=True))
        batch.create_check_constraint(
            "usage_status_valid",
            f"usage_status IS NULL OR usage_status IN ({_USAGE_STATUSES})",
        )

    # Existing rows predate the status column. ``legacy`` says exactly that: the zeros in them came
    # from a writer that could not distinguish "reported zero" from "never reported".
    op.execute("UPDATE agent_runs SET usage_status = 'legacy' WHERE usage_status IS NULL")
    op.execute("UPDATE llm_calls SET usage_status = 'legacy' WHERE usage_status IS NULL")


def downgrade() -> None:
    # The original columns were NOT NULL, so rows that honestly hold ``NULL`` cannot survive the
    # downgrade. Deleting them is the alternative to writing zeros back, and a zero written by a
    # downgrade is precisely the lie this migration exists to remove.
    op.execute(
        "DELETE FROM llm_calls WHERE prompt_tokens IS NULL OR completion_tokens IS NULL "
        "OR total_tokens IS NULL OR cost_usd IS NULL OR cost_cny IS NULL"
    )
    op.execute(
        "DELETE FROM agent_runs WHERE prompt_tokens IS NULL OR completion_tokens IS NULL "
        "OR total_tokens IS NULL OR cost_usd IS NULL OR cost_cny IS NULL"
    )
    for table in ("agent_runs", "llm_calls"):
        with op.batch_alter_table(table, recreate="auto") as batch:
            batch.drop_constraint("usage_status_valid", type_="check")
            batch.drop_column("usage_status")
            batch.drop_column("cached_tokens")
            if table == "agent_runs":
                batch.drop_column("error_code")
            for column, column_type in _COUNT_TYPES.items():
                batch.alter_column(column, existing_type=column_type, nullable=False)
