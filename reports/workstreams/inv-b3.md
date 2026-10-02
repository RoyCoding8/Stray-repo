# INV-B3: coord02 onto the shared contract

Lane B3, worktree `.worktrees/inv-b3`, branch `wt/inv-b3-coord02`, base `5f75ef6`.
Required reading: `experiments/ad01/packet.py` (shared envelope, read-only),
`tests/test_inv_b1_contracts.py` (gate pattern mirrored),
`reports/workstreams/inv-b1.md` (preserved entry points, contract changes),
`docs/design/INVESTIGATION-01.md` (two-domain calibration, usable packets,
renderer/parser/executor agreement).

## Public-path trace

Coord02 model calls and their admission, all verified ensure-then-dispatch
pairs in the committed drivers:

| Model call | Driver | Admission + receipt |
|---|---|---|
| A-arm decision | `entry._interpret_with_model` | `broker.ensure_operation` MODEL_INFERENCE, dispatch, `gw:<op>` success receipt, settled-text reuse |
| Child work | `entry.dispatch_admitted_child` via `run_child_factory` | same MODEL_INFERENCE pair, `<child-op>:model` identity derived from the admitted plan |
| Policy construction | `experience.ConstructionLedger._serialized` | same MODEL_INFERENCE pair, four-call ceiling, lineage guard, pg_advisory_lock serialization |
| Policy steps / probes | `policy_exec.invoke_policy_step` / `run_probe_call` | SANDBOX_EXEC pair with step/probe receipt identities |

Sole owners consumed read-only by the packet module: wire shape and limits
(`coord02/schemas.py`: `ACTIONS`, `ALLOWED`, `MAX_*`, `build_request`,
`validate_response`), execution transport (`policy_exec.py` filenames and
receipt kinds), task content and witness meaning (`oracle.py`:
`worker_files`, `TASK_FAMILY`, `EVALUATOR_ID/VERSION`, `evaluate_tree`
semantics), the shared construction envelope (`ad01/packet.py`:
`parse_construction_response`, read-only).

## Root causes

Forked construction envelope. `experience.keep_response` hand-rolled
`json.loads` with no fence handling, so a fenced reply carrying a valid
entry was refused (`unparsable-response`) while the shared
`parse_construction_response` accepts it. Renderer, parser and executor
disagreed by paraphrase. Reproduced red before the fix: fenced valid
entry unusable under `keep_response`, clean under the shared parse.

Duplicated packet builders. `controller.construction_call_spec` hardcoded
the action list, state limit and probe wording that `schemas.py` owns;
`controller.render_task_input` / `render_child_obligation` lived beside
their only caller; `experience` carried its own `_wire_schema`,
`_transport_specimen`, `_episode_contents`, `_as_episode_list`,
`_snapshot_digest_of` copies; `entry.dispatch_admitted_child` hand-built
the child prompt and hand-parsed the files shape the team submission path
enforces. A fix to one left the others stale, the B1 IR-01 shape exactly.

Unattested canned construction. `experience.dev_constructor` and
`entry.solved_child_factory` return solved tree bytes through a pure
function with zero broker operations. Reproduced red on real Postgres:
S-policy plus `dev_constructor` reaches `success` with five operations,
zero `model-inference`, five sandbox receipts. No committed driver uses
either factory (`run_cell`/`run_panel`/`main` use `run_child_factory`;
`acquire`/`run_live_acquisition` take explicit admitted factories); both
remain as named historical test seams only, which is why the existing
suite that depends on them is untouched.

## Fix

New `experiments/coord02/packet.py` owns one typed shape per decision.
`construction_packet` builds the construction request from `schemas.py`
constants with family-specific content limited to `candidate_shape`
(owned tree files per task) and `witness_rule` (protected-case
preservation meaning, no protected bytes, no counts). The response
envelope parses through the shared `parse_construction_response`, mapped
to the existing `keep_response` reason vocabulary byte-for-byte.
`render_construction_prompt`, `render_task_input`,
`render_child_obligation`, `render_child_prompt`,
`parse_child_response` and `construction_call_spec` live there;
`experience` and `controller` and `entry` keep their names as thin
delegates with identical output. Net diff deletes 207 lines.

## Preserved historical reproduction entry points (no silent renames)

`entry.run_cell`, `entry.run_panel`, `entry.main`, `entry.arm_decision`,
`entry.dispatch_admitted_child`, `entry.run_child_factory`,
`entry.solved_child_factory`, `entry.plan_children`,
`entry.arm_policy_entry`, `controller.run_episode`,
`controller.resume_episode`, `controller.run_s_fallback`,
`controller.render_task_input`, `controller.render_child_obligation`,
`controller.construction_call_spec`, `controller.seed_episode`,
`controller.build_experience_packet`, `experience.acquire`,
`experience.acquire_episodes`, `experience.construct_lineages`,
`experience.validate_on_development`, `experience.select_candidate`,
`experience.experience_packet`, `experience.construction_request`,
`experience.render_construction_prompt`, `experience.keep_response`,
`experience.parse_candidate`, `experience.stage_gate`,
`experience.dev_constructor`, `experience.ConstructionLedger`,
`policy_exec.invoke_policy_step`, `policy_exec.run_probe_call`,
`solved_child_factory` and `dev_constructor` retained as test seams,
not drivers.

Changed contracts (reported to coordinator): `construction_request`
output gains `candidate_shapes` and `witness_rules` keys (per task id);
`render_construction_prompt` gains CANDIDATE SHAPES and WITNESS RULES
sections; fenced construction responses are now usable (previously
`unparsable-response`); all other keys, key order, reason strings and
rendered bytes are unchanged. No existing test changed.

Proposal for coordinator follow-up (not taken unilaterally): reject
unattested constructor artifacts at the seam, so canned factories cannot
reach submission outside labeled mechanism tests. The gate pins the
current status both ways: the real path is fully admitted, the canned
seam provably carries no admission.

## Gate

`tests/test_inv_b3_coord02_contracts.py` (new; real Postgres
`inv_b3_contracts`, recording doubles at the gateway seam only):
rendering agrees with enforcement for sep and dia with wire schema
identical and only shapes differing; validator matrix against prompt
vocabulary; bare-plus-fenced parse agreement; ledger round trip through
`stage_gate` select for both families with receipts; malformed
construction visibly refused with repair lineage; every gateway call in
a real arm-A cell matched to a `model-inference` operation row plus
`gw:` success receipt with marker bytes restaged; malformed child
output visibly `submit-refused` with admission rows intact; canned seam
success with zero admitted model calls.

## Progress

- [x] Trace model path + owners (above).
- [x] Red repros: canned success with zero admission, fenced-entry refusal.
- [x] `packet.py` + wire `experience`/`controller`/`entry` to it.
- [x] Gate tests green; affected suite green (285 passed, 0 failed).
- [ ] Commit + push branch (next).
- [ ] Drop `inv_b3_contracts` and `inv_b3_repro` DBs on completion.

## Gate output

`tests/test_inv_b3_coord02_contracts.py`: 8 passed in ~17s on disposable
`inv_b3_contracts`. Affected set (every test file importing coord02):
285 passed, 0 failed, plus 16 skipped (live-grant-gated), same lane
databases. One transient order-dependent failure in
`test_coord02_learning.py` during a combined run passed alone and on
rerun; no code path touched by this lane explains it. No existing test
changed.
