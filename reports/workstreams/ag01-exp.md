# AG01-EXP workstream report (AG01-10, AG01-11)

Base: `769aeef14004ad6123f6f5a142df7ce666c6bfb3`.
Tip: `f6279911ef181df2ec3f133a97cbadb8e307e9b6` (package + tests).
Branch: `codex/ag01-exp`. Worktree: `/tmp/asv2-ag01-exp` (sole writer).
Lane DBs: `agenda01_exp` (scratch base only); trajectory DBs `agenda01_w*`
created/dropped per run, none retained. No other branch touched, no merge.

## Owned paths

- `experiments/agenda01/__init__.py`, `worlds.py`, `grader.py`,
  `observations.py`, `manifest.py`, `runner.py`, `checker.py`
- `tests/test_ag01_experiment.py`
- this report. No other source file touched.

## What was built

32 scored worlds (8 families x 4 variants, variant 3 carries each family's
mandated adverse case) plus 2 tiny diagnostic dev worlds (`scored: false`).
Public fixture fields only: measurement specs, probe costs from {2,4,8},
noise rates, prerequisites, delays, replication plans, hypothesized decision
consequences, exogenous event schedules, option seeds, 8 end-use task specs.

`grader.py` holds the only copy of latent prop facts (seed `AG01-GRADER-v1`),
`grade`/`solve`/wrong-answer controls, and the equal end-use solver
(majority vote over scored observations at the horizon dep version plus
labeled simulated product claims; 1 eval unit per task). Importing it after
any marked policy-observation module raises; `grade`/`latent_bit` refuse
policy-path callers by stack inspection.

`manifest.py` builds the frozen manifest (source revision, file digests,
world params, public/privileged field lists, proposal rule, tick order, two
opposite tie orders, AG01-R/1 + AG01-Q/1, AG01-OBS/1, grading rule, budgets
24 ticks / 64 exploration / 8 eval / 16 recovery, analysis rule) and writes
`manifest.json` + `manifest.sha256`. Every trace embeds the manifest hash.
`manifest.json`/`manifest.sha256` are deliberately NOT committed: freezing is
the coordinator gate after review.

`runner.py` runs the durable path only for scored work: per-trajectory
isolated DB `agenda01_w<WW>v<V>_<r|q>_t<0|1>` (migrated, independently seeded
authority: root 88 = explore 64 + eval 8 + recovery 16), deterministic tick
order (due events+receipts, wake/eligibility, one paid decision + possible
admission), 1 unit per decision incl. idle, full 2/4/8 probe exposure reserved
before launch via `prepare_operation`/`settle_reservation` with op identities
`ag01:<traj>:dec|probe:<tick>`, horizon end at 24 ticks or unfundable
decision, evidence cut at horizon (drain reported, never scored), drain
reconciliation under the recovery cap with retained/unresolved liability.
The pure runner shares the tick logic for debugging and the agreement test
only. Policies arrive as callables over the public packet; `resolve_policy`
binds the frozen `settlement.agenda_policy.decide_R/decide_Q` signatures once
the POLICY lane merges and raises a coordinator-verified message until then.

`checker.py` rebuilds pair/family totals, cost unions (op identities unioned,
shared ancestors once), liabilities and waiting/idle from traces +
operation/reservation rows + re-run grader output; rejects altered, missing
and duplicate records with reasons and nonzero exit; reports the resource
vector, no universal score.

## Checks and results

`SETTLEMENT_TEST_DSN="postgresql://ubuntu@/agenda01_exp?host=/var/run/postgresql"`
(host-param form), real PostgreSQL 16.15, `uv sync` + `uv sync --extra test`
(lock untouched):
`python -m pytest tests/test_ag01_experiment.py -q` → **16 passed** (57 s).
Collection of the full suite intact (606 tests, no breakage outside the lane).

Fail-as-designed (negative capability is the point):
- wrong-answer control: inverted answers score 0/8 on all 32 worlds.
- Q-losing fixture `w23` (premature stopping loses a real finding): durable
  R 4/8 vs Q 3/8; Q dormants the re-sample after one misleading readout while
  R's second/third samples restore the majority. A selective policy CAN lose
  here; fixtures were not tuned so Q wins.
- checker rejects amount-flipped, field-deleted and duplicate-op traces with
  reasons and nonzero exit (`main([])` returns 2).

Mechanical adverse probes (refusals hold on real PG):
- cross-arm discovery replay refused (foreign op id unknown in the other
  trajectory DB) and ledgers disjoint.
- privileged access: grader-after-observations import raises in a fresh
  process; reverse order loads; stack-marked `latent_bit` caller refused.
- branch cap-reset refused (`INSUFFICIENT_RESOURCES`; reseed refused);
  backend overdraft raises `InsufficientResources` on both backends.
- duplicate/out-of-order wakeups and receipts yield a single effect; repeat
  admission on one effect identity refused; settle idempotent, consumed once.
- stale select-then-admit refused (`StaleRevision`).
- positive controls: R and Q each solve 8/8 on `w28` and `w29` (durable).
- agreement: pure debug runner and durable path agree exactly (actions,
  observations, op ids/amounts, ledger, grade) on both dev worlds x both
  reference arms.
- fixture validation independent of policy code; observation release
  deterministic; manifest build deterministic with opposite tie orders.

## Public/privileged separation evidence

- Runtime walk of all 34 world dicts: no `informative`/`good_action`/
  `expected_score_gain`/`latent`/`answer`/`truth`/`expected`/`privileged` keys.
- AST check: `observations.py` imports nothing grader-related.
- Policy packets assert exact public key allowlists; anyone importing the
  grader from that path raises (tested both directions + stack refusal).
- Reference R/Q in the test file are labeled apparatus doubles implementing
  the frozen Q1/Q2/Q3 routes over public fields only; they are not scored
  policies and never import the grader.

## Limitations

- STATE+POLICY lanes were unmerged (all worktrees at base; no new origin
  refs), so the committed backend sequences select-then-admit as separate
  transactions in a single-threaded harness instead of one atomic transact;
  scored runs must use the lane backend, and merge-conformance (including the
  single-dict-arg `decide_R/decide_Q` adapter assumption) is
  coordinator-verified. `resolve_policy` raises until then.
- Authored deterministic panel: authors know the simulator; draws are fixed
  hashes, not a held-out benchmark. Descriptive merit reading only.
- Pure runner is memory-only and debug-labeled; agreement-tested, never scored.
- Crash-resume across processes (AG01-09 seam proof) belongs to STATE lane;
  this lane persists decisions/cursors/dispositions/observations/pending/ops
  per trajectory DB but does not prove resume.
- No live inference, gateway, containment or GPU anywhere in this lane.

## Contract change requests

None. Two integration expectations for the coordinator: (1) lane
`select_and_admit` must be the single atomic transact of AG01-D02 (this
harness sequences the same checks and will switch to it); (2) lane
`decide_R`/`decide_Q` receive the public packet dict defined in
`observations.build_policy_input` (adapter in `resolve_policy`).
