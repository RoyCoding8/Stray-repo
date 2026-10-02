CREATE TABLE artifact_versions (
  digest TEXT PRIMARY KEY,
  size BIGINT NOT NULL CHECK (size >= 0),
  manifest JSONB NOT NULL DEFAULT '{}',
  format TEXT NOT NULL DEFAULT '',
  version TEXT NOT NULL DEFAULT '',
  dependencies JSONB NOT NULL DEFAULT '[]',
  availability TEXT NOT NULL DEFAULT 'staged'
    CHECK (availability IN ('staged', 'available', 'retired', 'invalid')),
  protection_count INT NOT NULL DEFAULT 0 CHECK (protection_count >= 0),
  retention_state TEXT NOT NULL DEFAULT 'active'
    CHECK (retention_state IN ('active', 'retired', 'purged')),
  access_label TEXT NOT NULL DEFAULT 'public'
    CHECK (access_label IN ('public', 'candidate', 'hidden', 'evaluator')),
  scope TEXT NOT NULL DEFAULT '',
  path TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX artifact_versions_scope_idx ON artifact_versions (scope);
CREATE INDEX artifact_versions_access_idx ON artifact_versions (access_label);

CREATE TABLE artifact_refs (
  id BIGSERIAL PRIMARY KEY,
  digest TEXT NOT NULL REFERENCES artifact_versions (digest),
  holder_kind TEXT NOT NULL
    CHECK (holder_kind IN ('evidence', 'release', 'attempt', 'checkpoint', 'continuation')),
  holder_id TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (digest, holder_kind, holder_id)
);
CREATE INDEX artifact_refs_digest_idx ON artifact_refs (digest);

CREATE TABLE retention_budgets (
  scope TEXT PRIMARY KEY,
  kind TEXT NOT NULL DEFAULT 'working_set' CHECK (kind IN ('working_set', 'archive')),
  quota_bytes BIGINT NOT NULL CHECK (quota_bytes >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE observations (
  receipt_id TEXT PRIMARY KEY,
  attempt_id TEXT REFERENCES attempts (id),
  source_identity TEXT NOT NULL DEFAULT '',
  conditions JSONB NOT NULL DEFAULT '{}',
  content JSONB NOT NULL DEFAULT '{}',
  authenticated BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX observations_attempt_idx ON observations (attempt_id);

CREATE TABLE claims (
  id TEXT PRIMARY KEY,
  proposition JSONB NOT NULL DEFAULT '{}',
  scope JSONB NOT NULL DEFAULT '{}',
  assumptions JSONB NOT NULL DEFAULT '[]',
  access_label TEXT NOT NULL DEFAULT 'public'
    CHECK (access_label IN ('public', 'candidate', 'hidden', 'evaluator')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE derivations (
  id TEXT PRIMARY KEY,
  claim_id TEXT NOT NULL REFERENCES claims (id),
  procedure TEXT NOT NULL,
  proc_version TEXT NOT NULL DEFAULT '',
  scope JSONB NOT NULL DEFAULT '{}',
  assumptions JSONB NOT NULL DEFAULT '[]',
  result JSONB NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'valid' CHECK (status IN ('valid', 'invalid')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX derivations_claim_idx ON derivations (claim_id);

CREATE TABLE derivation_premises (
  derivation_id TEXT NOT NULL REFERENCES derivations (id) ON DELETE CASCADE,
  group_id INT NOT NULL CHECK (group_id >= 0),
  premise_ref TEXT NOT NULL,
  premise_kind TEXT NOT NULL DEFAULT 'claim'
    CHECK (premise_kind IN ('claim', 'observation', 'artifact')),
  PRIMARY KEY (derivation_id, group_id, premise_ref)
);

CREATE TABLE oppositions (
  id TEXT PRIMARY KEY,
  claim_id TEXT NOT NULL REFERENCES claims (id),
  kind TEXT NOT NULL CHECK (kind IN ('opposition', 'defeat')),
  body JSONB NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'withdrawn')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX oppositions_claim_idx ON oppositions (claim_id);

CREATE TABLE retractions (
  id BIGSERIAL PRIMARY KEY,
  target_ref TEXT NOT NULL UNIQUE,
  reason TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE evidence_relations (
  id BIGSERIAL PRIMARY KEY,
  src_ref TEXT NOT NULL,
  dst_ref TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN
    ('required-support', 'opposition', 'background', 'attribution', 'equivalence')),
  detail JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (src_ref, dst_ref, kind)
);

CREATE TABLE support_cache (
  claim_id TEXT PRIMARY KEY REFERENCES claims (id),
  supported BOOLEAN NOT NULL,
  version INT NOT NULL DEFAULT 1 CHECK (version > 0),
  epoch BIGINT NOT NULL DEFAULT 0 CHECK (epoch >= 0),
  detail JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE context_views (
  id TEXT PRIMARY KEY,
  decision JSONB NOT NULL DEFAULT '{}',
  sources JSONB NOT NULL DEFAULT '[]',
  transforms JSONB NOT NULL DEFAULT '[]',
  governing_refs JSONB NOT NULL DEFAULT '[]',
  limitations JSONB NOT NULL DEFAULT '[]',
  staged BOOLEAN NOT NULL DEFAULT FALSE,
  version INT NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE continuation_docs (
  id TEXT PRIMARY KEY,
  investigation_id TEXT NOT NULL REFERENCES investigations (id),
  composition_version TEXT NOT NULL DEFAULT '',
  position JSONB NOT NULL DEFAULT '{}',
  completed_refs JSONB NOT NULL DEFAULT '[]',
  unresolved_ops JSONB NOT NULL DEFAULT '[]',
  obligations JSONB NOT NULL DEFAULT '{}',
  next_decision JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX continuation_docs_investigation_idx ON continuation_docs (investigation_id);
