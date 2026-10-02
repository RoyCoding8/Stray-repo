CREATE TABLE agenda_options (
  option_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL DEFAULT '',
  question TEXT NOT NULL DEFAULT '',
  allocation_root TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0,
  disposition TEXT NOT NULL DEFAULT 'open'
    CHECK (disposition IN ('open', 'dormant', 'answered', 'retired')),
  disposition_version INTEGER NOT NULL DEFAULT 0,
  wake_condition JSONB,
  answer TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE agenda_option_revisions (
  option_id TEXT NOT NULL REFERENCES agenda_options (option_id),
  revision INTEGER NOT NULL,
  request_id TEXT NOT NULL UNIQUE,
  body JSONB NOT NULL,
  digest TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (option_id, revision)
);

CREATE TABLE agenda_disposition_events (
  id BIGSERIAL PRIMARY KEY,
  option_id TEXT NOT NULL REFERENCES agenda_options (option_id),
  version INTEGER NOT NULL,
  kind TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  policy_version TEXT NOT NULL DEFAULT '',
  input_digest TEXT NOT NULL DEFAULT '',
  decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (option_id, version, kind)
);

CREATE TABLE agenda_attempt_links (
  attempt_id TEXT PRIMARY KEY,
  trajectory TEXT NOT NULL DEFAULT '',
  option_id TEXT NOT NULL REFERENCES agenda_options (option_id),
  option_revision INTEGER NOT NULL,
  probe TEXT NOT NULL DEFAULT '',
  intended_decision TEXT NOT NULL DEFAULT '',
  replication_slot TEXT,
  effect_identity TEXT NOT NULL UNIQUE,
  operation_id TEXT NOT NULL DEFAULT '',
  reservation_id TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT 'admitted'
    CHECK (state IN ('admitted', 'settled')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX agenda_attempt_links_option_idx ON agenda_attempt_links (option_id);

CREATE TABLE agenda_outcomes (
  receipt_identity TEXT PRIMARY KEY,
  option_id TEXT NOT NULL REFERENCES agenda_options (option_id),
  attempt_id TEXT NOT NULL REFERENCES agenda_attempt_links (attempt_id),
  observation JSONB NOT NULL,
  epoch INTEGER NOT NULL,
  grounded BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX agenda_outcomes_option_idx ON agenda_outcomes (option_id);

CREATE TABLE agenda_decisions (
  id BIGSERIAL PRIMARY KEY,
  trajectory TEXT NOT NULL,
  tick INTEGER NOT NULL,
  policy_version TEXT NOT NULL,
  input_digest TEXT NOT NULL DEFAULT '',
  selection JSONB NOT NULL,
  reasons JSONB NOT NULL,
  decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (trajectory, tick, policy_version)
);

CREATE TABLE agenda_cursors (
  trajectory TEXT PRIMARY KEY,
  tick INTEGER NOT NULL DEFAULT 0,
  rotation INTEGER NOT NULL DEFAULT 0,
  epoch INTEGER NOT NULL DEFAULT 1,
  dep_versions JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE agenda_wake_log (
  option_id TEXT NOT NULL REFERENCES agenda_options (option_id),
  event_identity TEXT NOT NULL,
  matched BOOLEAN NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (option_id, event_identity)
);
