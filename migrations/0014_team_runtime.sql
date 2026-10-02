DO $$DECLARE r record; BEGIN
  FOR r IN SELECT conname FROM pg_constraint
    WHERE conrelid = 'context_packets'::regclass
    AND pg_get_constraintdef(oid) LIKE '%decision_kind%' LOOP
    EXECUTE 'ALTER TABLE context_packets DROP CONSTRAINT ' || quote_ident(r.conname);
  END LOOP;
END $$;
ALTER TABLE context_packets ADD CONSTRAINT context_packets_decision_kind_check
  CHECK (decision_kind IN ('diagnose', 'construct', 'resume', 'team'));

CREATE TABLE team_snapshots (
  digest TEXT PRIMARY KEY,
  snapshot JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE team_outputs (
  digest TEXT PRIMARY KEY,
  output JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE team_plans (
  plan_id TEXT PRIMARY KEY,
  investigation_id TEXT NOT NULL REFERENCES investigations (id),
  parent_obligation TEXT NOT NULL DEFAULT '',
  snapshot_digest TEXT NOT NULL REFERENCES team_snapshots (digest),
  shape TEXT NOT NULL CHECK (shape IN ('single', 'alternatives', 'decompose')),
  children JSONB NOT NULL DEFAULT '[]',
  interface_contract JSONB NOT NULL DEFAULT '{}',
  join_rules JSONB NOT NULL DEFAULT '{}',
  allocation_id TEXT NOT NULL REFERENCES allocations (id),
  checker_allocation_id TEXT NOT NULL DEFAULT '',
  composition JSONB NOT NULL DEFAULT '{}',
  budget JSONB NOT NULL DEFAULT '{}',
  revision INT NOT NULL DEFAULT 1 CHECK (revision > 0),
  revision_count INT NOT NULL DEFAULT 0 CHECK (revision_count >= 0 AND revision_count <= 1),
  policy_response JSONB NOT NULL DEFAULT '{}',
  frozen_candidate TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX team_plans_investigation_idx ON team_plans (investigation_id);

CREATE TABLE team_submissions (
  plan_id TEXT NOT NULL REFERENCES team_plans (plan_id),
  plan_revision INT NOT NULL CHECK (plan_revision > 0),
  node_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL DEFAULT '',
  input_digests JSONB NOT NULL DEFAULT '{}',
  ownership_generation INT NOT NULL CHECK (ownership_generation > 0),
  output_digest TEXT NOT NULL REFERENCES team_outputs (digest),
  receipt_refs JSONB NOT NULL DEFAULT '[]',
  accepted BOOLEAN NOT NULL DEFAULT TRUE,
  invalidated BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (plan_id, plan_revision, node_id)
);
CREATE INDEX team_submissions_plan_rev_idx ON team_submissions (plan_id, plan_revision);

CREATE TABLE team_joins (
  plan_id TEXT NOT NULL REFERENCES team_plans (plan_id),
  plan_revision INT NOT NULL CHECK (plan_revision > 0),
  candidate_digest TEXT NOT NULL DEFAULT '',
  passed BOOLEAN NOT NULL,
  failing_input JSONB NOT NULL DEFAULT '{}',
  observed_output JSONB NOT NULL DEFAULT '{}',
  join_receipt TEXT NOT NULL DEFAULT '',
  check_operation TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (plan_id, plan_revision)
);
