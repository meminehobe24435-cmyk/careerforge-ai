-- CareerForge AI - PostgreSQL extensions.
--
-- Executed by the postgres container on first initialisation: docker-compose mounts
-- infra/db/init as /docker-entrypoint-initdb.d, so this file runs before Alembic.
--
--   pgcrypto -> gen_random_uuid() for the uuid primary keys of docs/DATABASE.md
--   vector   -> pgvector 0.7, the embedding type and HNSW index (docs/DATABASE.md §2.5)
--
-- The SQLite fallback path needs neither: careerforge_api.db.compat supplies
-- client-side UUIDs and stores vectors as BLOBs.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
