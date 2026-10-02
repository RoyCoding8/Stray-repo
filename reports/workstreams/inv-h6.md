# inv-h6: bugfix pass 3 sweep of remaining open review findings

Tip at start: `8b7c0c4` on branch `wt/inv-h6-findings`, verified with
`git log --oneline -1` before any work. No code changed in this pass.
The only committed file is this note. All disposable databases below
are named `inv_h6_*` and were dropped after the runs quoted.

## Inventory

Every item is marked handled, already-fixed, not-a-defect, or open.
File references replace code for every non-open verdict.

### Semantic review (INV-R-S01..S10, tip `5ff0f1e`, rework: none)

- S01 contract rendering agrees with execution. Handled. B1 gate 11 of 11
  green on `inv_h6_b1`. Renderer `experiments/ad01/packet.py:172`,
  contract `experiments/ad01/method_exec.py:37`, parser
  `experiments/ad01/packet.py:221`.
- S02 malformed actions have visible effects. Handled. C malformed paths
  green inside the 9 of 9 C gate on `inv_h6_c` plus `inv_h6_c2`.
  Rejected path `experiments/ad01/trajectory.py:379`, invented-basis
  path `experiments/ad01/trajectory.py:269`.
- S03 retention with byte identity. Handled. C gate 9 of 9 green.
  Writer `experiments/ad01/trajectory.py:585`, digest check
  `experiments/ad01/trajectory.py:599`, frozen use
  `experiments/ad01/trajectory.py:649`.
- S04 rejection and kill resume durable. Handled. C gate 9 of 9 green,
  including resume with zero new gateway calls.
- S05 zero budget probes. Already-fixed. `src/settlement/loop.py:128`
  refuses `zero-budget-probe` without touching study lineage. B2 gate
  8 of 8 green on `inv_h6_b2`, B4 gate 4 of 4 green without a database.
- S06 replay boundaries hold. Handled. Covered by the C gate replay
  refusals, 9 of 9 green. Prefix check `experiments/doubles.py`.
- S07 no monkeypatched success gate. Not-a-defect. The B4 zero-allowance
  patch fails the test if construction runs, a guard rather than a
  success simulator. The dev-episode probe path is unpatched.
- S08 no direct proposal callback on this tip. Already-fixed. C success
  paths route through `learner.propose_from_model` via broker admission
  (`tests/test_inv_c_qualification.py:70`). The historical C3 recording
  learner stays a documented limitation, never acquisition evidence.
- S09 substantive acquired program. Handled with the same limitation.
  INV-C source `experiments/doubles.py:74` carries no imports and its
  own shrink. Historical C3 wrapper bytes stay fixtures.
- S10 fixture success not relabeled. Already-fixed at `5ff0f1e`.
  Doubles label simulated true and billed false, cost union reports
  tokens none, B3 canned seam asserts empty model operations.

### State review (INV-R-T01..T11, tip `5ff0f1e`, verdict: accept with findings)

- T01 lane A gate. Handled. Probe `reviews/probes/inv_a_baseline_gaps.py`
  exits 0 with 17 pass and 0 fail on this tip, rerun in this session.
- T02 INV-E-02 correction. Already-fixed at `5ff0f1e`. AD-06 row states
  72 of 72 checker clean with retained-byte execution 45 of 72.
- T03 C4 operation total split. Already-fixed by `2f7da96` (ancestor).
  `count_definition` in `reports/workstreams/inv-a-c4-ledger.json` names
  the accounting union, resume row Calls reads 5, column sums to 40.
- T04 C2 ledger. Handled. No code path in this scope disputes it.
- T05 single remaining envelope. Not-a-defect. `src/settlement/loop.py`
  binds one allocation per study root and reads remaining from durable
  `store.allocation_free`. B2, B4 and C gates green on this tip.
- T06 post-effect reads. Already-fixed by `1f27c99` (ancestor).
  `src/settlement/store.py:1039` selects
  `receipt_identity, outcome, content`, so `loop.read_measured_costs`
  observes settled receipt bytes. F2 gate 3 of 3 green on `inv_h6_f2`.
- T07 replay boundaries. Handled. Same evidence as S06.
- T08 raw evidence untouched. Handled. This pass touches no
  `evidence*/**` path. `git status` shows only this note.
- T09 no secrets. Handled. No secret added. This note carries only
  database names and DSN shapes with no credentials.
- T10 unselected-failure accounting. Handled. Dispositions match the
  committed bytes per the review, no owned path contradicts them.
- T11 lane D token floor. Already-fixed by `9f273ec` (ancestor).
  `reports/workstreams/inv-d.md:44` states 17383 and
  `reports/workstreams/inv-d.md:77` carries the floor at 17383.

### Merged lane notes

- inv-f1 seam refusal. Already-fixed by `0d6b905` plus the `a7da1cc`
  test migration (both ancestors). F1 gate 2 of 2 green in this session
  on `inv_h6_f1`. Refusing factories `experiments/coord02/experience.py`
  and `experiments/coord02/entry.py:438`, refusal mapping
  `experiments/coord02/controller.py:516`.
- inv-f2 finding 1 (zero budget, single envelope). Not-a-defect.
  B2 gate 8 of 8 green on this tip confirms it.
- inv-f2 finding 2 (post-effect reads). Already-fixed by `1f27c99`.
  Red was `assert 0 == 3` on billed charge units, green is 3 of 3.
- inv-f2 finding 3 (malformed visible effect). Not-a-defect. B2
  rejection-then-correction passes unchanged inside the 27-test B1/B2/B3
  run quoted below.
- inv-f2 out-of-scope r03 plus broker_dbos errors. Handled by inv-g1
  and inv-h5 (both ancestors, green evidence in their notes).
- inv-f3 INV-E-01. Already-fixed by `2f7da96`. Same evidence as T03.
- inv-f3 INV-E-03. Explicit limitation, no edit. The EC02 cap
  reconciliation bullet stays qualified to the ledger with unknown
  liabilities open. Not a defect in any owned file.
- inv-g1 r03 restore failures. Already-fixed by `758e415` (ancestor,
  test-only prerequisite pattern). inv-h5 reran the suite green.
- inv-g2 coord02 migrations. Already-fixed by `d168a25` (ancestor).
  All 114 owned coord02 tests pass on this tip, rerun in this session.
- inv-g3 IR-01(b) fresh diagnostic observation. Already-fixed by
  `1d47fb2` (ancestor). Constructor call
  `experiments/ad01/trajectory.py:368` appends the fresh observation.
  G3 regression test green in this session.
- inv-g3 IR-01(a) prompt content. Already-fixed. B1 gate 11 of 11 green.
- inv-g3 IR-03 allowance re-grant. Already-fixed by `d59c809`
  (ancestor). B4 gate 4 of 4 green.
- inv-g3 BDR-01 host execution. Already-fixed (ancestor).
  `test_bdr01_host_boundary.py` green inside the 76-test AD01 run below.
- inv-g3 BDR-03 protected-target admission. Already-fixed (ancestor).
  `test_bdr03_target_admission.py` green in the same run.
- inv-g3 BDR-02 child identity, noted as out of scope for that lane.
  Already-fixed by `aec2fdd` (ancestor): child model identities derive
  from durable plan plus node plus revision through
  `src/settlement/team.py:303`, called at
  `experiments/coord02/controller.py:437` and `:494`. The original
  single `coord02-child:<tag>:<task>` identity is gone from the tree.
- inv-h5 residual sweep. Handled. No code change was made there and none
  is needed here. One observation below goes to the coordinator because
  its file sits outside this scope.

Open findings in owned paths: none. Zero failing-before tests existed on
this tip, so no TDD red-to-green cycle ran. The one failure observed
during verification (`test_canned_episode_has_visible_refusal` against a
missing default `inv_f1_seam` database) failed for an unrelated reason,
a missing database rather than behavior, and passed once pointed at the
disposable `inv_h6_f1` database. Per the tdd workflow the reproduction
was corrected before any implementation edit, and no edit followed.

## Verification on this tip (all disposable `inv_h6_*` databases)

- B1 plus B3 plus B2: 27 passed on `inv_h6_b1`, `inv_h6_b3`, `inv_h6_b2`.
- B4 plus F2 plus F1 plus G3: 10 passed
  (`inv_h6_f2` and `inv_h6_f1`, B4 database-free).
- INV-C qualification: 9 passed on `inv_h6_c` plus `inv_h6_c2`.
- Owned coord02 suites (`test_coord02_learning`,
  `test_coord02_m2_qualification`, `test_coord02_m3_acquisition`,
  `test_coord02_m4_frozen`, `test_coord02_state`, `test_eacq_repair`,
  `test_ec02ad_verif`): 114 passed.
- AD01 boundary suites (`test_bdr01_host_boundary`,
  `test_bdr03_target_admission`, `test_ad01_traj`, `test_ad01_env`):
  76 passed.
- Broker plus store suites (`test_broker_prepare`,
  `test_broker_dispatch`, `test_adv_broker`, `test_settle_actual`,
  `test_acct_store_costs`): 15 passed, 39 skipped on the pre-existing
  `SETTLEMENT_TEST_DSN is not configured` gate, unchanged by this pass.
- Lane A probe: 17 pass, 0 fail, exit 0.

Verification boundary: doubles prove the integrated path, not live
inference or containment. No committed test uses a monkeypatched
controller or a direct proposal callback for a success claim.

## Rework for the coordinator (outside owned paths, files untouched)

- `tests/test_ag01_experiment.py:792`. The `finally` block in
  `test_duplicate_effect_decisions_charged` drops
  `f"agenda01_{trace['db']}"`, but `trace["db"]` already holds the full
  `agenda01_w08v0_r_t0` name from `runner.run_trajectory`, so the drop
  targets a doubled name and leaves one disposable database behind. The
  suite passes, so this is cleanup-only. Suggested fix: drop
  `trace["db"]` as returned instead of prefixing it again. This file is
  outside the inv-h6 owned scope, so the line is unchanged here.
- Historical C3 corpus stays a documented limitation (S08, S09). Never
  reuse it as acquisition evidence and never claim live benefit from
  doubles. No file change requested.
- INV-E-03 stays an explicit limitation. The EC02 cap reconciliation
  cites ledger-only gateway receipt totals with no receipt files under
  `evidence-live/` or `evidence-ad01/c4-live/`. Unreplayable numbers
  stay labeled, not filled. No file change requested.
