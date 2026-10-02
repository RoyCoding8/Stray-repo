CREATE TABLE development_episodes (
  id TEXT PRIMARY KEY,
  investigation_id TEXT NOT NULL REFERENCES investigations (id),
  allocation_id TEXT NOT NULL DEFAULT '',
  trigger_refs JSONB NOT NULL DEFAULT '[]',
  bottleneck TEXT NOT NULL DEFAULT '',
  predicted_effect TEXT NOT NULL DEFAULT '',
  reference_version TEXT NOT NULL DEFAULT '',
  access_policy JSONB NOT NULL DEFAULT '{}',
  max_explanations INT NOT NULL DEFAULT 2 CHECK (max_explanations >= 0 AND max_explanations <= 2),
  max_probes INT NOT NULL DEFAULT 1 CHECK (max_probes >= 0 AND max_probes <= 1),
  max_candidates INT NOT NULL DEFAULT 2 CHECK (max_candidates >= 0 AND max_candidates <= 2),
  state TEXT NOT NULL DEFAULT 'observed'
    CHECK (state IN ('observed', 'proposed', 'admitted', 'diagnosed',
                     'constructed', 'checked', 'selected', 'bound')),
  explanations JSONB NOT NULL DEFAULT '[]',
  intervention JSONB NOT NULL DEFAULT '{}',
  probes_used INT NOT NULL DEFAULT 0 CHECK (probes_used >= 0 AND probes_used <= 1),
  probe_ops JSONB NOT NULL DEFAULT '[]',
  candidates JSONB NOT NULL DEFAULT '[]',
  development_protocol_id TEXT NOT NULL DEFAULT '',
  comparison_policy JSONB NOT NULL DEFAULT '{}',
  comparison_exposed BOOLEAN NOT NULL DEFAULT FALSE,
  checks JSONB NOT NULL DEFAULT '[]',
  selection JSONB NOT NULL DEFAULT '{}',
  bindings JSONB NOT NULL DEFAULT '{}',
  disposition TEXT NOT NULL DEFAULT 'open'
    CHECK (disposition IN ('open', 'no-candidate', 'invalid-output',
                           'budget-exhausted', 'ready', 'bound')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX development_episodes_investigation_idx ON development_episodes (investigation_id);
