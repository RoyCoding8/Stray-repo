CREATE TABLE context_packets (
  id TEXT PRIMARY KEY,
  decision_kind TEXT NOT NULL CHECK (decision_kind IN ('diagnose', 'construct', 'resume')),
  purpose TEXT NOT NULL DEFAULT '',
  decision JSONB NOT NULL DEFAULT '{}',
  policy_version TEXT NOT NULL DEFAULT '',
  source_snapshot JSONB NOT NULL DEFAULT '{}',
  mandatory_content JSONB NOT NULL DEFAULT '{}',
  evidence_bundles JSONB NOT NULL DEFAULT '[]',
  gaps JSONB NOT NULL DEFAULT '[]',
  footprint JSONB NOT NULL DEFAULT '{}',
  omissions JSONB NOT NULL DEFAULT '[]',
  rendered TEXT NOT NULL DEFAULT '',
  rendered_digest TEXT NOT NULL DEFAULT '',
  outcome TEXT NOT NULL DEFAULT 'needs_information'
    CHECK (outcome IN ('ready', 'needs_information', 'stale')),
  token_estimate JSONB NOT NULL DEFAULT '{}',
  evidence_epoch BIGINT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX context_packets_kind_idx ON context_packets (decision_kind);
CREATE INDEX context_packets_outcome_idx ON context_packets (outcome);

CREATE TABLE packet_invocations (
  packet_id TEXT NOT NULL REFERENCES context_packets (id),
  operation_id TEXT NOT NULL,
  rendered_digest TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (packet_id, operation_id)
);
CREATE INDEX packet_invocations_operation_idx ON packet_invocations (operation_id);
