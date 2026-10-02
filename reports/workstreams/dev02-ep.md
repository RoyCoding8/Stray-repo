# Workstream M-EP — episode seams D02-001..D02-004, CTX-08, CTX-10

Owner branch `codex/dev02-episode` produced no output: the specialist
terminated after the reading phase with an empty tree (no venv, no DB, no
edits). The coordinator reclaimed the lane and implemented the slice
directly on `codex/implementation-development-02` (commit `8648d8e`;
lane branch left at `b7d7c85`). No parallel-edit conflict was possible.

## Dispositions (all four confirmed, none rebutted)

- D02-001: `development.collect_experience` runs the permitted dev batch
  before diagnosis (DEV inference + grade through the real broker/launcher
  paths, costs settled to the episode dev protocol). Each task records an
  authenticated observation, a candidate-scope experience claim carrying the
  actual broken code/cases/model text/outcome, and a live observation-premise
  warrant. `diagnose`/`construct` build a real `context.build_packet`
  (ready-gated; non-ready refuses before any inference spend), embed the
  rendered packet + packet id in the model prompt, bind the invocation, and
  return packet id + digest. The trigger-refs-only `_allowed_experience`
  shape is deleted. Response shape (`code`/`no_candidate`) and the
  entry/selftest invocation contract are explicit prompt fields.
- D02-002: entry `synthesize` resolves the bound version id + artifact
  digest only; reject/no-candidate returns None, fixer version is `""`.
  The existing harness C-arm abstention (`no-applicable-method`) is the
  declared incumbent/control behavior; rejections and costs are retained in
  checks/selection. No fallback version stem.
- D02-003: `panel_policy_for` builds the finite-panel policy;
  `admit(..., panel_policy=...)` freezes it as `{episode}-panel` before any
  development feedback. `freeze_comparison` verifies submitted groups
  against the frozen policy (divergence refused) and amends to
  `{panel}-eval`; `bind` amends to `{eval}-bound` with the candidate
  version. `run_abcs(..., panel_protocol=...)` amends per-arm protocols
  superseding the eval protocol and refuses group drift. Amendment
  (`trials.amend_protocol`) preserves the exposure lineage throughout.
- D02-004/CTX-08: `experiment.run_subsequent_use` + `experiments/run_use.py`.
  After disposition the entry spawns the use script in a fresh process:
  ordinary selection (bound version when eligible, else incumbent),
  invocation, grading of the new task, cost settlement to a frozen use
  protocol, `development.subsequent_use` domain event, prior-exposure and
  pending-operation snapshot in the use record. Report phases derive from
  these receipts.
- CTX-10: `experiments/dev02_challenge.py` freezes six scenarios;
  `tests/test_dev02_episode.py` executes missing-content refusal,
  counterexample preservation, retraction failover to a live route,
  oversize staging, resume-with-unresolved-operation visibility, and
  reject-to-incumbent use.

## No-double-run seam

`collect_experience` transcripts feed `run_abcs(..., dev_transcripts=...)`;
`_run_development` reuses them (ops/outcomes identical, no new inference,
`reused` lists the ids) while lesson authoring and synthesis still run.
Lesson/synthesis costs settle to the harness dev protocol; collection costs
to the episode dev protocol. Same-DSN reruns keep working (new episode ids).

## Packet-layer corrections (coordinator integration, M-CTX reviewed)

- `_OUTPUT_CONTRACTS["construct"]` response shape corrected to the real
  `code`/`no_candidate` contract the code enforces.
- Optional entry-declared `candidate_contract` (invocation/applicability/
  effect/resource) resolves the pre-candidate contract slots, labeled
  `entry-declared-pre-candidate`; pinned versions still take precedence,
  otherwise the slots stay needs-information. Without this the construct
  packet could never be ready (no candidate exists yet).
- `templates/overview.html` renders the packet region (autoescaped env).

## Probes

The four characterization probes are retired to
`reviews/probes/historical_test_development_01_readiness.py` with per-probe
correspondence; three no longer drive the entry (stale harnesses), the
release unit property is preserved as
`test_release_orchestrator_never_invokes`.

## Checks

`tests/test_dev02_episode.py` (13 tests) + migrated
`tests/test_dev01_episode.py`/`test_dev01_ops.py` expectations, all on real
PostgreSQL + LocalLauncher with inference-only doubles. Full suite gate at
integration. No live gateway in this environment: deterministic slice only.

## Limits

Live finite-panel comparison (held-out groups, real model conditioning)
unverified; live run of `run_use.py --gateway live` refused here (no
endpoint/key/grant). `collect_experience` partial rows persist if a later
task refuses on budget (refusal aborts, mark recorded).
