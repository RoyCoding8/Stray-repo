# T5 S3 executable learning + trials + experiment — task report

- Base: `16ce0ad` (branch `codex/task-s3-learning` start, per assignment).
- Code commit: `f9143ea` — migration, 4 new modules, `run.py` hook, experiments, tests.
- This report: follow-up commit on the same branch (tip = this commit).
- Worktree: `/home/ubuntu/AI/Agent-Society-v2-s3-learning` only. No other checkout touched.

## Modified paths (owned only + one granted edit)

- `migrations/0003_s3_learning.sql` (new, exactly one migration; only S3 tables)
- `src/settlement/capabilities.py` (new: IF-4, LEARN-1/7/9, router, quarantine registry)
- `src/settlement/trials.py` (new: LEARN-2/3/4/5/6, IF-7 opportunities)
- `src/settlement/evaluation.py` (new: IF-6, LEARN-2 evaluator isolation)
- `src/settlement/experiment.py` (new: §11 A/B/C harness)
- `src/settlement/run.py` (granted narrow edit only: `check_eligibility`
  appends a quarantine reason via lazy `capabilities.pinned_quarantines`
  import; missing-table guard keeps pre-0003 databases working)
- `experiments/` (new: `fault_tasks.py`, `offbyone_fixer.py`, `run_tests.py`,
  `doubles.py`, `run_live_abc.py`)
- `tests/test_s3_helpers.py`, `tests/test_s3_capabilities.py`,
  `tests/test_s3_trials.py`, `tests/test_s3_evaluation.py`,
  `tests/test_s3_experiment.py` (new)

Shared contracts untouched. No contract change requests.

## Outcomes

- `uv run pytest`: **18/18 S3 tests pass** against real PostgreSQL
  (`SETTLEMENT_TEST_DSN=postgresql://ubuntu@/settlement_t3learning?host=/var/run/postgresql`);
  full suite **161 passed**, plus `test_broker_dbos.py` 3/3 under its own
  expected DSN. The 2 DBOS errors under the `t3learning` DSN are a
  pre-existing hardcoded-DSN assumption (`settlement_t1broker` partition),
  unrelated to S3.
- LEARN-1: `publish_candidate` binds reference version, change, hypothesis,
  scope, dependencies, protocol id, budget; generated code is executed as an
  ARTIFACT digest through broker `sandbox-exec` (typed-JSON success receipt
  required) and never imported (`sys.modules` asserted clean).
- LEARN-2: protocols freeze with separated development / visible-regression /
  protected-eval groups; a trigger refuses in-place amendment (amendment
  creates a new version, old trials keep meaning); hidden answers are
  `hidden`-label claims invisible to candidate scope, served to evaluator
  scope, and withheld from candidate retrieval views.
- LEARN-3/4: results bind actual invocations (unknown refs refused) with
  model/env conditions; every assignment needs an outcome before verdict;
  timeout/invalid/unavailable/infra are first-class; expenditure ledger
  (construction/retrieval/evaluation/coordination/selection/failed_trials/use)
  adds up per protocol with a declared amortization horizon.
- LEARN-5: finite-panel verdicts only (observed-gain / regression /
  inconclusive); simulated panel-C shows observed-gain 3-1, transfer arms
  report inconclusive as-is.
- LEARN-6: `inferential_claim` always raises `UnverifiedProcedure` and records
  the gate as unverified. No statistics invented.
- LEARN-7: scoped releases bind exact versions, evidence (epoch-checked),
  scope, disposition, fallback, policy, invalidation; incumbents outside scope
  are preserved; regression refuses limited/default; evaluator pin mismatch
  (always-pass swap) refuses release; router keeps Y on the incumbent while X
  advances, with mixed correct/abstain/wrong-version scoring.
- LEARN-9: consolidation proposes reuse/retirement with costs and affected
  dependencies; history rows are never rewritten.
- §15: always-pass swap refused; hidden answers withheld from retrieval;
  budget refusal + quarantine + cancel-while-dispatched with late receipt all
  covered; X-gain/Y-regression release + router misrouting covered.
- §11: full simulated A/B/C over 8 fault tasks (3 dev / 3 panel / 2 transfer):
  fresh attempt per task, arm C invokes the retained fixer through the broker
  (operation + receipt asserted, 3 invokes + 2 recorded abstentions outside
  applicability), matched sandbox/token caps, construction+retrieval counted
  in B/C totals, every cell labeled `simulated=True`.

## Limitations / explicitly unverified

- All arm results are simulated (`ScriptedDouble` with fixed per-arm
  competence). No live inference was performed; nothing here claims it.
- LEARN-6 inferential machinery is unverified by design (refusal only).
- runsc/gVisor untested here; arms run on the `local-process` profile.
- Live A/B/C is blocked on endpoint + grant. Exact command:

  `uv run python experiments/run_live_abc.py --dsn $SETTLEMENT_DSN --allocation live-abc --artifacts-root $ARTIFACT_ROOT`

  Required inputs: `SETTLEMENT_GATEWAY_URL` (endpoint URL),
  `SETTLEMENT_GATEWAY_KEY` (key), `SETTLEMENT_GRANT_UNITS` (monetary grant
  cap). The harness accepts any `GatewayAdapter` unchanged with
  `simulated=False`.

## API for T6 quarantine control and UI (all take `(dsn, ...)`)

- Release: `capabilities.scoped_release(dsn, cmd, release_id, protocol_id,
  versions, scope, disposition, fallback, policy_version, invalidation,
  evidence_refs, evaluator_version)`; `releases_for_scope(dsn, family)`;
  `propose_consolidation(dsn, cmd, proposal_id, subject_versions, action,
  costs, affected, rationale)`.
- Quarantine: `capabilities.quarantine(dsn, cmd, version_id, reason)`;
  `quarantine_status(dsn, version_id)`; `pin_capability(dsn, attempt_id,
  version_id)`; `pinned_quarantines(dsn, attempt_id)`; enforced for pinned
  attempts in `run.check_eligibility(dsn, attempt_id, comp)`;
  `route` abstains on quarantined selections.
- Router: `save_router_policy(dsn, cmd, version, mapping, evidence_refs)`;
  `route(dsn, policy_version, family)` → select/abstain;
  `evaluate_router(dsn, policy_version, cases)` → correct/wrong/abstain counts.
- Evaluator: `evaluation.register_evaluator(dsn, cmd, evaluator_id, version,
  access_policy, code_digest)`; `propose_hidden_answer(dsn, cmd, task_id,
  answer)`; `hidden_answer(dsn, task_id, scope)` (candidate scope raises
  `Unauthorized`); `submit_candidate` (never a receipt);
  `submit_evaluator_receipt(dsn, cmd, receipt_id, assignment_id, evaluator_id,
  evaluator_version, invocation_ref, result)` (pin + invocation enforced).
- Trials: `trials.freeze_protocol / amend_protocol / assign /
  blinded_assignment / resolve_blind / record_result / record_expenditure /
  development_expenditure / verdict / inferential_claim (refuses) /
  register_opportunity / allocate_opportunity`.
- Experiment: `experiment.run_abcs(dsn, launcher, artifacts_root,
  allocation_id, investigation_id, tasks, dev_ids, panel_ids, transfer_ids,
  lessons, double, grader_path, ...)`; `experiment.live_blocker()`.
