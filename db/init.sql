CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- One legal source: a judgment, an act, a rule set.
CREATE TABLE IF NOT EXISTS sources (
  id            TEXT PRIMARY KEY,               -- from manifest, e.g. "kesavananda-1973"
  title         TEXT NOT NULL,
  doc_type      TEXT NOT NULL,                  -- judgment | statute | rules | circular
  court         TEXT,
  year          INT,
  language      TEXT NOT NULL DEFAULT 'en',
  citations     TEXT[] NOT NULL DEFAULT '{}',   -- display form, e.g. {"(2017) 10 SCC 1"}
  citation_keys TEXT[] NOT NULL DEFAULT '{}',   -- normalised, e.g. {"SCC|2017|10|1"}
  aliases       TEXT[] NOT NULL DEFAULT '{}',   -- lower-cased names
  file_path     TEXT NOT NULL,
  sha256        TEXT NOT NULL,                  -- re-ingest only if the file changed
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sources_citation_keys_idx ON sources USING GIN (citation_keys);

-- A passage of a source: usually one numbered paragraph or one section.
CREATE TABLE IF NOT EXISTS chunks (
  id         BIGSERIAL PRIMARY KEY,
  source_id  TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  ord        INT  NOT NULL,
  page_start INT,
  page_end   INT,
  para       TEXT,                              -- "45" for a judgment para, "138" for a section
  text       TEXT NOT NULL,                     -- verbatim; never rewritten
  tsv        TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
  embedding  VECTOR(1024) NOT NULL              -- must equal EMBEDDING_DIM
);
CREATE INDEX IF NOT EXISTS chunks_source_idx    ON chunks (source_id, ord);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx       ON chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);

-- One run of the checker on one draft.
CREATE TABLE IF NOT EXISTS checks (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title       TEXT,
  input_text  TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'running',  -- running | done | failed
  summary     JSONB,
  error       TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);

-- One checkable claim inside a draft.
CREATE TABLE IF NOT EXISTS claims (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  check_id        UUID NOT NULL REFERENCES checks(id) ON DELETE CASCADE,
  ord             INT  NOT NULL,
  char_start      INT  NOT NULL,
  char_end        INT  NOT NULL,
  text            TEXT NOT NULL,
  claim_type      TEXT NOT NULL,                -- holding | statutory | quote | fact
  citation_raw    TEXT,
  citation_key    TEXT,
  citation_status TEXT,                         -- found | not_found | ambiguous | none
  case_name       TEXT,
  source_id       TEXT REFERENCES sources(id) ON DELETE SET NULL,
  quote_text      TEXT,
  quote_score     REAL,
  quote_match     TEXT,
  quote_diff      JSONB,                        -- word-level diff ops
  quote_critical  BOOLEAN,                      -- a critical word (shall/may/not/number) differs
  support_probs   JSONB,
  evidence_chunk  BIGINT REFERENCES chunks(id) ON DELETE SET NULL,
  verdict         TEXT NOT NULL,                -- verified | weak | insufficient | misquote | contradicted | fabricated | not_legal
  colour          TEXT NOT NULL,                -- green | amber | red | grey
  confidence      REAL,
  reason          TEXT NOT NULL,
  fix             JSONB
);
CREATE INDEX IF NOT EXISTS claims_check_idx ON claims (check_id, ord);

-- Results of each evaluation run, for the dashboard.
CREATE TABLE IF NOT EXISTS eval_runs (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  dataset    TEXT NOT NULL,
  mode       TEXT NOT NULL,                     -- pipeline | baseline
  config     JSONB NOT NULL,
  metrics    JSONB NOT NULL
);
