CREATE TABLE capability_versions (
  id TEXT PRIMARY KEY,
  family TEXT NOT NULL DEFAULT '',
  invocation JSONB NOT NULL DEFAULT '{}',
  effect JSONB NOT NULL DEFAULT '{}',
  resource JSONB NOT NULL DEFAULT '{}',
  artifact_digest TEXT NOT NULL DEFAULT '',
  applicability JSONB NOT NULL DEFAULT '{}',
  evidence_refs JSONB NOT NULL DEFAULT '[]',
  reference_version TEXT NOT NULL DEFAULT '',
  change_desc TEXT NOT NULL DEFAULT '',
  hypothesis TEXT NOT NULL DEFAULT '',
  scope JSONB NOT NULL DEFAULT '{}',
  dependencies JSONB NOT NULL DEFAULT '[]',
  protocol_id TEXT NOT NULL DEFAULT '',
  budget JSONB NOT NULL DEFAULT '{}',
  verification_op TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE development_opportunities (
  id TEXT PRIMARY KEY,
  question TEXT NOT NULL DEFAULT '',
  hypothesis TEXT NOT NULL DEFAULT '',
  basis TEXT NOT NULL DEFAULT '',
  desired_observation TEXT NOT NULL DEFAULT '',
  cap JSONB NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'proposed'
    CHECK (status IN ('proposed', 'allocated', 'completed', 'withdrawn')),
  investigation_id TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX capability_versions_family_idx ON capability_versions (family);

CREATE TABLE capability_releases (
  id TEXT PRIMARY KEY,
  protocol_id TEXT NOT NULL DEFAULT '',
  versions JSONB NOT NULL DEFAULT '[]',
  scope JSONB NOT NULL DEFAULT '{}',
  disposition TEXT NOT NULL CHECK (disposition IN
    ('candidate', 'experimental', 'limited', 'default', 'quarantined', 'retired')),
  fallback TEXT NOT NULL DEFAULT '',
  policy_version TEXT NOT NULL DEFAULT '',
  invalidation JSONB NOT NULL DEFAULT '{}',
  evidence_refs JSONB NOT NULL DEFAULT '[]',
  evaluator_version TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE quarantine_registry (
  version_id TEXT PRIMARY KEY,
  reason TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE attempt_capability_pins (
  attempt_id TEXT NOT NULL REFERENCES attempts (id),
  version_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (attempt_id, version_id)
);

CREATE TABLE consolidation_proposals (
  id TEXT PRIMARY KEY,
  subject_versions JSONB NOT NULL DEFAULT '[]',
  action TEXT NOT NULL CHECK (action IN ('reuse', 'retire')),
  costs JSONB NOT NULL DEFAULT '{}',
  affected JSONB NOT NULL DEFAULT '[]',
  rationale TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE trial_protocols (
  id TEXT PRIMARY KEY,
  candidate_version TEXT NOT NULL DEFAULT '',
  reference_version TEXT NOT NULL DEFAULT '',
  evaluator_version TEXT NOT NULL DEFAULT '',
  task_groups JSONB NOT NULL DEFAULT '[]',
  budgets JSONB NOT NULL DEFAULT '{}',
  metrics JSONB NOT NULL DEFAULT '[]',
  stopping JSONB NOT NULL DEFAULT '{}',
  exclusions JSONB NOT NULL DEFAULT '[]',
  uncertainty JSONB NOT NULL DEFAULT '{}',
  frozen BOOLEAN NOT NULL DEFAULT TRUE,
  supersedes TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION refuse_frozen_protocol_update() RETURNS trigger AS $$
BEGIN
  IF OLD.frozen THEN
    RAISE EXCEPTION 'trial protocol % is frozen; amend by creating a new version', OLD.id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trial_protocols_frozen_guard
  BEFORE UPDATE ON trial_protocols
  FOR EACH ROW EXECUTE FUNCTION refuse_frozen_protocol_update();

CREATE TABLE trial_assignments (
  id TEXT PRIMARY KEY,
  protocol_id TEXT NOT NULL REFERENCES trial_protocols (id),
  task_id TEXT NOT NULL,
  task_group TEXT NOT NULL DEFAULT '',
  arm TEXT NOT NULL CHECK (arm IN ('candidate', 'reference')),
  blind_key TEXT NOT NULL UNIQUE,
  instance JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (protocol_id, task_id, arm)
);
CREATE INDEX trial_assignments_protocol_idx ON trial_assignments (protocol_id);

CREATE TABLE candidate_submissions (
  id BIGSERIAL PRIMARY KEY,
  assignment_id TEXT NOT NULL REFERENCES trial_assignments (id),
  content JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE evaluator_packages (
  id TEXT PRIMARY KEY,
  version TEXT NOT NULL,
  access_policy JSONB NOT NULL DEFAULT '{}',
  code_digest TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE evaluator_receipts (
  id TEXT PRIMARY KEY,
  assignment_id TEXT NOT NULL REFERENCES trial_assignments (id),
  evaluator_id TEXT NOT NULL REFERENCES evaluator_packages (id),
  evaluator_version TEXT NOT NULL,
  invocation_ref TEXT NOT NULL DEFAULT '',
  result JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (assignment_id)
);

CREATE TABLE trial_results (
  assignment_id TEXT PRIMARY KEY REFERENCES trial_assignments (id),
  outcome TEXT NOT NULL CHECK (outcome IN
    ('success', 'failure', 'timeout', 'invalid', 'unavailable', 'infra')),
  invocation_ref TEXT NOT NULL DEFAULT '',
  conditions JSONB NOT NULL DEFAULT '{}',
  cost JSONB NOT NULL DEFAULT '{}',
  detail JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE expenditure_ledger (
  id BIGSERIAL PRIMARY KEY,
  protocol_id TEXT NOT NULL REFERENCES trial_protocols (id),
  category TEXT NOT NULL CHECK (category IN
    ('construction', 'retrieval', 'evaluation', 'coordination', 'selection',
     'failed_trials', 'use')),
  amount BIGINT NOT NULL CHECK (amount >= 0),
  note TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX expenditure_ledger_protocol_idx ON expenditure_ledger (protocol_id);

CREATE TABLE inferential_gates (
  protocol_id TEXT PRIMARY KEY REFERENCES trial_protocols (id),
  requested_procedure TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'unverified',
  reason TEXT NOT NULL DEFAULT ''
);

CREATE TABLE router_policies (
  version TEXT PRIMARY KEY,
  mapping JSONB NOT NULL DEFAULT '{}',
  evidence_refs JSONB NOT NULL DEFAULT '[]',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
