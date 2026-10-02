CREATE TABLE s09_policy_state (
  investigation_id TEXT NOT NULL,
  seq INT NOT NULL CHECK (seq >= 0),
  attempt_id TEXT NOT NULL,
  effect_id TEXT NOT NULL,
  policy_input JSONB NOT NULL DEFAULT '{}',
  policy_output JSONB NOT NULL DEFAULT '{}',
  state_transition JSONB NOT NULL DEFAULT '{}',
  accepted_action JSONB NOT NULL,
  effect_record JSONB,
  status TEXT NOT NULL DEFAULT 'accepted'
    CHECK (status IN ('accepted', 'incorporated')),
  provenance TEXT NOT NULL DEFAULT 's09-m1',
  driver_version TEXT NOT NULL DEFAULT 's09-m1',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (investigation_id, seq)
);

CREATE TABLE s09_assessment_exposure (
  batch_id TEXT NOT NULL,
  exposed_to TEXT NOT NULL,
  retired_at TIMESTAMPTZ,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (batch_id, exposed_to)
);
