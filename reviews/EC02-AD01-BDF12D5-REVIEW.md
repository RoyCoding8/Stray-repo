# EC02/AD01 integration review at bdf12d5

Reviewed `bdf12d58c185c8b586b56c83b3d9857b85d2900f` against the complete assignment at `6fec14a`, on 2026-09-16 in an isolated worktree. No production code, old evidence, worker databases or other worktrees were modified. This is a completion review, not another whole-repository audit.

## Outcome

**Partial implementation accepted; C1 PASS, C3 QUALIFIED and “only two externally blocked remainders” are not supported.** The new child adapter and accepted-action routing are useful progress. But actual learning, public accounting, durable authority and continuity still have implementation gaps. A live allocation cannot supply missing code.

| Gate | Assessment |
|---|---|
| C1 | Partial. A child response now reaches submitted bytes, but operation identity, child inputs, actual accounting and required integrated paths are unfinished. |
| C2 | Live repairs remain unrun, with the allocation request recorded. Eligible profile-failure repair orchestration also remains unimplemented; this is not exclusively external. Preserve existing calls and the 96-versus-48 development discrepancy. |
| C3 | Reproducible authored trajectory/seed-use fixtures; not the assigned broker-backed model construction and autonomous trajectory qualification. |
| C4 | Unrun; separate authority is required. The current AD01 CLI also lacks a live learner/constructor path, so “implemented-but-unrun” is inaccurate. |
| C5 | Reports and evidence delivered, but completion assessment remains partial. No full integrated suite or worker receipt anchor was independently rerun here. |

## New blocking findings

### BDR-01 — P1: candidate programs execute in the trusted host

`experiments/ad01/trajectory.py`, `_run_member`, calls `exec(member["method_source"], namespace)` and then invokes the resulting function directly. There is no broker, execution profile, process boundary, capability verification, timeout or authoritative query settlement on this path. The program receives live oracle/reducer objects and can affect the process responsible for its measurement. This violates the explicit host/candidate separation in both AGENTS and AD01; it is not merely the deferred real-runsc qualification.

A trusted reviewer canary returning only its process ID ran in exactly the reviewer's process. No untrusted program or damaging operation was executed by the probe. The new outside-menu test manually constructs its repertoire member; it neither tests acquisition nor makes host execution an acceptable implementation of it.

**Required:** use the existing broker and representation execution profile for retained computation. Verify immutable acquired bytes and lineage before execution. Prove behavior-bearing substitution, bounded failure and fresh-process use through the actual campaign. Keep host reference checkers authoritative and inaccessible to candidate code.

### BDR-02 — P1: every child and rework uses the same inference identity

`entry.run_cell` constructs one `operation_id="coord02-child:<tag>:<task>"`; `run_child_factory` passes it unchanged for every node and invocation. The controller calls that factory for each missing child and again on rework. Different nodes carry different prompts under an identical immutable operation/request identity; `broker.ensure_operation` converts conflicting request payloads into `INVALID_INPUT`. Repeating a node with the old prompt instead reuses the prior operation, preventing fresh repair.

The independent boundary probe captured w1, w2 and w1-rework all using `one-cell`. This was an argument-level probe, not a local PostgreSQL run. Broker conflict semantics and controller callers were inspected. Existing new tests primarily exercise a single-owner plan, so their success does not cover decomposition/revision.

**Required:** derive operation identity from durable campaign/accepted-plan/child-attempt/revision state. Distinct accepted work gets distinct identity; resuming the same work preserves it. Demonstrate two real child calls and one permitted rework through the public entry, then restart without duplicate calls.

### BDR-03 — P1: accepted AD01 targets can cross the protected split

The new `_run_boundary` executes the proposal's target, but `admit_investigation` validates only basis references, not whether the proposed target/action is available to that arm and phase. A proposal citing an ordinary development observation and targeting `ad01-w0-within-sw-00` was accepted and executed during development in the independent probe.

This allows protected-use information into development before repertoire selection. It also leaves R's curriculum restriction unenforced at the dispatch boundary. A callback that changes the target is now causally effective, but admission must constrain that effect.

**Required:** validate the full action against the current world's visible set, phase, curriculum restriction and remaining authority before any diagnostic/construction effect. Distinguish development diagnostics from final protected measurement. Reject protected, other-world and otherwise inadmissible targets with zero dependent work.

## Continuing assignment gaps

These retain their prior EAR IDs; there is no need to rediscover them or create another layer of helpers.

- **EAR-01:** child inference now exists, but its prompt omits the public root contract, uses original snapshots on every invocation, forwards free-form obligation text, and receives only observation interface names from `controller.render_child_obligation`, not observed contents. Changing a diagnostic result can therefore leave child input unchanged. A's `selected_source_text` still reads the task snapshot rather than the selected retained coordination algorithm. A competent iterative S baseline and the declared A/F/L comparison are not closed by a marker assignment appearing in output files.
- **EAR-02/03:** `_cell_costs`, synthetic receipt fallback, per-receipt whole-cell cost copying and the public schedule/UUID path remain unchanged. `costs_for_operations` is a new helper with no caller in `entry.py`. The worker report explicitly says rewiring is not done, yet declares C1 complete. Public campaign/selection resume and grant enforcement remain required integration work.
- **EAR-04:** `experience.construct_lineages` still repairs only empty/unparseable source. `run_live_acquisition.py` still revalidates initial bytes under a repair label and uses authored development child factories. Both files are unchanged in this batch. Lack of grant explains absent live calls, not absent eligible-repair orchestration.
- **EAR-05:** `_run_boundary` now honors a callback's stop/target and supplies the real charter. It still supplies only one `unmeasured` seed observation, never accumulated diagnostic results. `dev_episode` still selects/runs an authored seed; no construction response becomes a checked retained program. The actual `cli.py` is unchanged and has no configured model/constructor route.
- **EAR-06:** decisions are still published after execution, claimed operation names are fabricated, persisted episodes lose executable contents/references, and per-action query limits do not enforce the trajectory's independent aggregate limits. These paths were not repaired by the new method loader or C3 driver.

## What the 6+72 result actually establishes

Independently ran the committed qualification driver in a fresh subprocess and compared its output with the repository: **all 19 JSON files matched structurally**. Independently checked all **72 use records: zero checker problems**. There are **15 retained repertoire entries, all `authored: true`, all seed methods, none carrying acquired program source**.

The driver preselects different I/R lists and a zero budget for one I item, then passes those plans to a recording callback. It runs `run_campaign` without a DSN, freezes a JSON repertoire and calls `run_use` directly in the same process. No broker-backed construction, DB continuity or fresh-process retained-use phase occurs in this 6+72 path. Starting the driver in a new process does not make its use phase separate from acquisition.

The use-only benefit calculation reproduces `no-benefit`. That describes these authored fixtures; it does not validate whole-trajectory resource accounting or a functioning live learner. The checker validates task outputs, membership and supplied numeric fields, not model acquisition, operation provenance or process isolation.

## Local verification and limits

- `python -m pytest tests/test_binit_action.py tests/test_bacq_method.py tests/test_ad01_env.py -q -p no:cacheprovider`: **32 passed in 7.42 seconds** on unchanged production source at `bdf12d5`.
- `python reviews/probes/ad01_bdf12d5_review.py`: all characterization assertions passed, including the fresh qualification replay. See [observations](probes/ad01-bdf12d5-observed.json).
- No live inference or database mutation was performed. The worker's 42/90/4 gate results and live-anchor receipt count remain worker-reported. Passing local tests demonstrates the tested slice, not all AD-01–08 obligations.

## Task list and next step

- [x] Fetch the exact tip and review the complete delta against the existing assignment.
- [x] Accept the real child-dispatch and callback-routing progress at their actual scope.
- [x] Reproduce C3 artifacts and inspect all retained members.
- [x] Probe host execution, child identities, protected-target admission and continuing integration gaps.
- [ ] Worker completes the existing behavioral assignment using the [integration handoff](../docs/HISTORY.md#worker-ec02-ad01-integration-finish).
- [ ] Run the authorized live remainder after the connected deterministic path is ready; then assess actual initiative, acquisition, benefit and transfer separately.

The design remains at stage 8. No additional architecture or experiment is commissioned here. The useful next step is one coordinator owning complete integration and semantic acceptance, including the work currently left between lanes.
