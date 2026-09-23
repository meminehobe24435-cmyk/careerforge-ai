"""Inventory of the schema: which tables exist, and which constraints they declare.

Split out of ``test_models.py`` when that file reached the 500-line guard. The split is by
responsibility rather than by size: this module asserts **what the schema declares** — the
exact table set per phase and the ``CHECK`` constraint names — while ``test_models.py``
asserts **what the database enforces**, by writing invalid values through the ORM and
requiring a refusal.

Keeping the inventory separate makes the phase boundary legible: a table that appears
without its phase being finished fails here, and the constants below are the only place
that has to be updated when a phase lands.
"""

from __future__ import annotations

from careerforge_api.db.base import Base

#: ``docs/DATABASE.md`` §2.1/§2.11 — identity, platform and observability.
PHASE_1_TABLES = {
    "users",
    "profiles",
    "public_profiles",
    "prompt_versions",
    "agent_runs",
    "llm_calls",
    "background_jobs",
    "ai_caches",
    "skills",
}

#: ``docs/DATABASE.md`` §2.3 — the tables that turn an upload into citable material.
PHASE_2_TABLES = {
    "documents",
    "document_chunks",
}

#: ``docs/DATABASE.md`` §2.2 — the structured career entities.
PHASE_2B_TABLES = {
    "educations",
    "experiences",
    "projects",
    "achievements",
    "profile_skills",
}

#: ``docs/DATABASE.md`` §2.9 — résumé versions, their claims and the claim→evidence links.
PHASE_6_TABLES = {
    "resume_versions",
    "resume_claims",
    "claim_evidence",
}

#: ``docs/DATABASE.md`` §2.5 — evidence and the edges over it.
PHASE_3_TABLES = {
    "evidence",
    "evidence_links",
}

#: ``docs/DATABASE.md`` §2.6 — postings, their skill requirements and computed matches.
PHASE_4_TABLES = {
    "jobs",
    "job_skills",
    "job_matches",
}

#: ``docs/DATABASE.md`` §2.7/§2.11 — the application tracker, its event log and the
#: career timeline.
PHASE_8_TABLES = {
    "applications",
    "application_events",
    "career_events",
}


def test_metadata_contains_exactly_the_migrated_tables() -> None:
    """Exact, not a superset assertion: a table added without its phase being finished
    should fail here rather than pass unnoticed."""
    assert (
        set(Base.metadata.tables)
        == PHASE_1_TABLES
        | PHASE_2_TABLES
        | PHASE_2B_TABLES
        | PHASE_3_TABLES
        | PHASE_6_TABLES
        | PHASE_4_TABLES
        | PHASE_8_TABLES
    )


def test_every_documented_table_has_its_check_constraints() -> None:
    """A representative constraint per table, by its documented name.

    The naming convention (``ck_<table>_<rule>``) is what makes this checkable at all: an
    anonymous constraint would be invisible to it, and the convention rejects those.
    """
    expected = {
        "users": {"ck_users_role_valid", "ck_users_storage_scope_valid"},
        "profiles": {"ck_profiles_profile_strength_range", "ck_profiles_years_experience_range"},
        "public_profiles": {"ck_public_profiles_view_count_non_negative"},
        "skills": {"ck_skills_category_valid"},
        "prompt_versions": {"ck_prompt_versions_version_positive"},
        "agent_runs": {"ck_agent_runs_status_valid", "ck_agent_runs_trigger_valid"},
        "llm_calls": {"ck_llm_calls_operation_valid", "ck_llm_calls_status_valid"},
        "background_jobs": {
            "ck_background_jobs_status_valid",
            "ck_background_jobs_progress_range",
        },
        "ai_caches": {"ck_ai_caches_kind_valid"},
        "documents": {"ck_documents_kind_valid", "ck_documents_parse_status_valid"},
        "document_chunks": {
            "ck_document_chunks_chunk_index_non_negative",
            "ck_document_chunks_char_range_valid",
        },
        "evidence": {
            # The formula constraint is the point of that table: a stored confidence its
            # own five factors do not produce must be impossible.
            "ck_evidence_confidence_formula",
            "ck_evidence_kind_valid",
            "ck_evidence_confidence_unit_range",
        },
        "evidence_links": {
            "ck_evidence_links_relation_valid",
            "ck_evidence_links_no_self_loops",
        },
        "jobs": {"ck_jobs_source_valid", "ck_jobs_salary_range_ordered"},
        "job_skills": {
            "ck_job_skills_requirement_valid",
            "ck_job_skills_weight_unit_range",
        },
        "job_matches": {
            "ck_job_matches_score_range",
            "ck_job_matches_dimension_scores_range",
        },
        "applications": {
            "ck_applications_status_valid",
            "ck_applications_match_score_snapshot_range",
            "ck_applications_position_non_negative",
        },
        "application_events": {
            # Both directions of a transition are constrained: a typo in ``to_status``
            # would otherwise become an eighth board column nobody can see.
            "ck_application_events_to_status_valid",
            "ck_application_events_from_status_valid",
        },
        "career_events": {"ck_career_events_kind_valid"},
    }
    for table, names in expected.items():
        found = {c.name for c in Base.metadata.tables[table].constraints if c.name}
        assert names <= found, f"{table} is missing {names - found}"


def test_every_table_carries_its_tenancy_key() -> None:
    """``docs/DATABASE.md`` §1.1: every business table is filtered by ``user_id``.

    Checked here rather than left to review, because a table that forgets the key cannot be
    made tenant-safe afterwards by the query layer alone.

    Two documented kinds of exception, named rather than waved through:

    * ``skills`` and ``prompt_versions`` are shared reference data — the skill dictionary and
      the prompt registry are the same for every account, so they have no owner at all;
    * ``agent_runs``, ``background_jobs`` and ``ai_caches`` may hold rows that belong to the
      system rather than to a candidate (a migration job, a shared cache entry), so their
      ``user_id`` is nullable on purpose. The column still exists, which is what the query
      layer needs.
    """
    #: Tables with no ``user_id`` at all, each for a stated reason:
    #: ``users`` *is* the account; ``skills`` and ``prompt_versions`` are shared reference
    #: data (the skill dictionary and the prompt registry are identical for every account).
    unowned = {"users", "skills", "prompt_versions"}
    #: Tables whose rows may belong to the system rather than to a candidate: a migration
    #: job, a shared cache entry, a provider call made outside any request. Documented as
    #: nullable in §2.11 — the column still exists, which is what the query layer needs.
    system_owned = {"agent_runs", "background_jobs", "ai_caches", "llm_calls"}

    for name, table in Base.metadata.tables.items():
        if name in unowned:
            assert "user_id" not in table.columns, f"{name} is not a tenanted table"
            continue
        assert "user_id" in table.columns, f"{name} has no user_id column"
        if name in system_owned:
            assert table.columns["user_id"].nullable is True, (
                f"{name}.user_id is a documented system-owned exception; if it became NOT "
                "NULL, update docs/DATABASE.md §2.11 rather than this list"
            )
            continue
        assert table.columns["user_id"].nullable is False, f"{name}.user_id must be NOT NULL"
