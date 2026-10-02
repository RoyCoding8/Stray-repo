CREATE TABLE control (
  id INT PRIMARY KEY CHECK (id = 1),
  admission_epoch BIGINT NOT NULL DEFAULT 0 CHECK (admission_epoch >= 0),
  authority_version INT NOT NULL DEFAULT 1 CHECK (authority_version > 0),
  evidence_epoch BIGINT NOT NULL DEFAULT 0 CHECK (evidence_epoch >= 0),
  release_epoch BIGINT NOT NULL DEFAULT 0 CHECK (release_epoch >= 0),
  event_epoch BIGINT NOT NULL DEFAULT 0 CHECK (event_epoch >= 0)
);
INSERT INTO control (id) VALUES (1);

CREATE TABLE grants (
  version INT PRIMARY KEY CHECK (version > 0),
  charter_text TEXT NOT NULL,
  authority_grant JSONB NOT NULL DEFAULT '{}',
  envelopes JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE command_journal (
  request_id TEXT PRIMARY KEY,
  payload_digest TEXT NOT NULL,
  result_code TEXT NOT NULL,
  result_detail TEXT NOT NULL DEFAULT '',
  result_data JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE domain_events (
  epoch BIGINT NOT NULL CHECK (epoch > 0),
  ordinal INT NOT NULL CHECK (ordinal >= 0),
  kind TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}',
  PRIMARY KEY (epoch, ordinal)
);

CREATE TABLE outbox (
  workflow_identity TEXT PRIMARY KEY,
  intent_kind TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}',
  delivered BOOLEAN NOT NULL DEFAULT FALSE,
  created_epoch BIGINT NOT NULL DEFAULT 0,
  created_ordinal INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  delivered_at TIMESTAMPTZ
);
CREATE INDEX outbox_undelivered_idx ON outbox (created_at) WHERE delivered = FALSE;

CREATE TABLE investigations (
  id TEXT PRIMARY KEY,
  revision INT NOT NULL DEFAULT 1 CHECK (revision > 0),
  objective TEXT NOT NULL,
  scope JSONB NOT NULL DEFAULT '{}',
  obligations JSONB NOT NULL DEFAULT '{}',
  sponsor TEXT NOT NULL DEFAULT '',
  origin TEXT NOT NULL DEFAULT '',
  disposition TEXT NOT NULL DEFAULT 'accepted'
    CHECK (disposition IN ('proposed', 'accepted', 'fulfilled', 'amended', 'withdrawn', 'suspended')),
  fulfilled_revision INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (fulfilled_revision IS NULL OR fulfilled_revision > 0)
);

CREATE TABLE investigation_revisions (
  investigation_id TEXT NOT NULL REFERENCES investigations (id),
  revision INT NOT NULL CHECK (revision > 0),
  objective TEXT NOT NULL,
  obligations JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (investigation_id, revision)
);

CREATE TABLE allocations (
  id TEXT PRIMARY KEY,
  parent_id TEXT REFERENCES allocations (id),
  domain TEXT NOT NULL,
  epoch INT NOT NULL DEFAULT 0,
  authorized BIGINT NOT NULL CHECK (authorized >= 0),
  amount_scale INT NOT NULL DEFAULT 1 CHECK (amount_scale > 0),
  consumed BIGINT NOT NULL DEFAULT 0 CHECK (consumed >= 0),
  reserved BIGINT NOT NULL DEFAULT 0 CHECK (reserved >= 0),
  occupancy INT NOT NULL DEFAULT 0 CHECK (occupancy >= 0),
  max_occupancy INT NOT NULL DEFAULT 8 CHECK (max_occupancy >= 0),
  owner_scope TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (consumed + reserved <= authorized)
);
CREATE INDEX allocations_parent_idx ON allocations (parent_id);

CREATE TABLE reservations (
  id TEXT PRIMARY KEY,
  allocation_id TEXT NOT NULL REFERENCES allocations (id),
  operation_id TEXT NOT NULL DEFAULT '',
  amount BIGINT NOT NULL CHECK (amount > 0),
  state TEXT NOT NULL DEFAULT 'reserved'
    CHECK (state IN ('reserved', 'settled', 'uncertain', 'released')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX reservations_allocation_idx ON reservations (allocation_id);

CREATE TABLE attempts (
  id TEXT PRIMARY KEY,
  investigation_id TEXT NOT NULL REFERENCES investigations (id),
  investigation_revision INT NOT NULL,
  allocation_id TEXT REFERENCES allocations (id),
  ownership_generation INT NOT NULL CHECK (ownership_generation > 0),
  composition TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  env TEXT NOT NULL DEFAULT '',
  lifecycle TEXT NOT NULL DEFAULT 'running'
    CHECK (lifecycle IN ('prepared', 'running', 'suspended', 'completed', 'failed', 'cancelled')),
  deadline TIMESTAMPTZ,
  continuation_ref TEXT NOT NULL DEFAULT '',
  owner TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (investigation_id, investigation_revision)
    REFERENCES investigation_revisions (investigation_id, revision)
);
CREATE INDEX attempts_investigation_idx ON attempts (investigation_id);

CREATE TABLE attempt_observations (
  id BIGSERIAL PRIMARY KEY,
  attempt_id TEXT NOT NULL REFERENCES attempts (id),
  content JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE operations (
  id TEXT PRIMARY KEY,
  attempt_id TEXT REFERENCES attempts (id),
  allocation_id TEXT REFERENCES allocations (id),
  reservation_id TEXT REFERENCES reservations (id),
  payload_digest TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}',
  dispatch_state TEXT NOT NULL DEFAULT 'prepared'
    CHECK (dispatch_state IN ('prepared', 'dispatching', 'sent', 'observed', 'unresolved', 'reconciled', 'cancelled')),
  launcher_id TEXT NOT NULL DEFAULT '',
  provider_id TEXT NOT NULL DEFAULT '',
  receipt_provenance TEXT NOT NULL DEFAULT '',
  reconcile_state TEXT NOT NULL DEFAULT 'none'
    CHECK (reconcile_state IN ('none', 'conflict', 'unresolved', 'reconciled')),
  cancel_state TEXT NOT NULL DEFAULT 'none'
    CHECK (cancel_state IN ('none', 'requested', 'worker_stopped', 'confirmed')),
  execution_version TEXT NOT NULL DEFAULT '',
  settled BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX operations_dispatch_idx ON operations (dispatch_state);

CREATE TABLE receipts (
  receipt_identity TEXT PRIMARY KEY,
  operation_id TEXT NOT NULL REFERENCES operations (id),
  content_digest TEXT NOT NULL,
  content JSONB NOT NULL DEFAULT '{}',
  outcome TEXT NOT NULL CHECK (outcome IN ('success', 'failure', 'unknown')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX receipts_operation_idx ON receipts (operation_id);

CREATE TABLE receipt_conflicts (
  id BIGSERIAL PRIMARY KEY,
  receipt_identity TEXT NOT NULL,
  operation_id TEXT NOT NULL REFERENCES operations (id),
  content_digest TEXT NOT NULL,
  content JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
