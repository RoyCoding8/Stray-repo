# INV-B1: contracts and domain interfaces

Lane B1, worktree `.worktrees/inv-b1`, branch `wt/inv-b1-contracts`, base `32e2ea2`.
Required reading: `inv-brief-design` (ranked reqs 1-3), `inv-brief-assessment`
(IR-01, IR-02), `docs/design/INVESTIGATION-01.md` (loop, usable packets,
renderer/parser/executor agreement).

## Public-path trace (lane B step 1)

Broker core (`src/settlement/broker.py`, read-only for this lane):
`ensure_operation` (admission: `validate_effect` + `store.prepare_operation`),
`dispatch_operation` (routes `model-inference`/`sandbox-exec` to launchers or
gateway), `dispatch_pending`, `attempt_workflow`, `read_operation`.

Callers of `broker.dispatch_operation`: `capabilities.py`, `experiment.py`,
`development.py`, `representation.py`, `team.py`, `scripts/scheduler.py`
(`dispatch_pending` loop), `scripts/agenda01.py` (operator CLI).

Model-visible contracts and sole owners:

| Contract | Sole owner | Consumers (read-only) |
|---|---|---|
| Broker effect shapes (`model-inference`, `sandbox-exec`, ...) | `broker.validate_effect` | every dispatcher |
| Settlement packet kinds + output contracts (`diagnose`, `construct`, `resume`, `team`) | `settlement/context.py` (`_REQUIRED`, `_OUTPUT_CONTRACTS`, `build_packet`) | `development.diagnose`/`construct` via `_packet_for` |
| File-to-file candidate ABI (`METHOD_ABI`, `--selftest`, JSON envelope) | `settlement/development.py` | `experiment._invoke_method`, `_grade` |
| AD01 construction entry rules (arity, no imports, no dunder, no IO/reflection) | `experiments/ad01/method_exec.py` (`verify_member`) | `experiments/ad01/construct.py` (`_prompt`, `_evaluate`) |
| AD01 candidate shape + preservation objective + oracle meaning | `experiments/representation/checkers.py` + `software.py`/`graphs.py` | `method_exec` driver, `trajectory._check`/`dev_episode` |
| Learner packet shape + proposal validation | `experiments/ad01/learner.py` (`learner_request`, `validate_proposal`, `model_propose`) | `trajectory._run_boundary`, `cli.py`, C3 driver |
| Campaign orchestration over the above | `experiments/ad01/trajectory.py` | `run_c3_qualification.py`, `cli.py`, ale* tests |

Duplicated orchestration noted for lane B2 (per toolchain brief): `broker.heartbeat`/
`broker.recover`, `agenda.repair_scan` + `collect_wakeups`, `scripts/scheduler.run_once`
have no single owner. Not touched here.

## IR-01 root cause

`construct._prompt` hand-writes a paraphrase of the entry rules ("the word import
anywhere ... fails validation") instead of rendering the contract `verify_member`
enforces, and carries no candidate shape, no reducer signatures, no oracle verdict
vocabulary, no preservation objective. A prompt-compliant novel program cannot be
valid: the candidate shape is unknowable from the prompt. Separately, the propose
path consumes two packet shapes for one decision: `trajectory._run_boundary` builds
an ad-hoc `seen` dict while `learner.model_propose` renders `learner_request`; the
two already diverge (charter/curriculum/`required_response` vs `boundary`), so a fix
to one leaves the other stale.

Fix: `experiments/ad01/packet.py` owns one typed `decision_packet` builder used by
both `learner.learner_request` and `trajectory._run_boundary`, and one typed
`construction_packet` (task content, public operations, candidate shape,
preservation objective, oracle meaning, verbatim diagnostics, budgets, entry rules
rendered from `method_exec` constants) rendered by `render_construction_prompt` and
parsed by `parse_construction_response`. `construct._prompt`/`_parse_entry` become
thin delegates. Renderer, parser, executor agree by construction; transport examples
for both domains are mechanically tested.

## IR-02 root cause

`experiments/ad01/run_c3_qualification.py::_recording_learner` returns proposals
through the raw `propose=` callback, so C3 records decisions with zero
`model-inference` learner operations: no admission, no receipts, no measured costs,
and `remaining["model_calls"]` never decreases. Same file runs unequal I/R lists (I
visits software-only `[sw1, sw0, sw2]`, R visits mixed `dev[:3]`) and serves authored
canned entries from a single script stream.

Fix: the committed C3 driver goes through `learner.propose_from_model` with a
demultiplexing recording gateway (learner scripts vs construction scripts routed by
operation id; doubles stay at the provider seam, which the design permits). I and R
visit the same task set in different selection orders (I chooses, R follows the
frozen curriculum); zero-budget rejection coverage is kept as one scripted probe.
The raw `propose=` callable remains as the versioned-policy seam owned by the loop
(B2 will own admission around it); what is deleted is the committed driver bypass,
not the seam. Rationale recorded here per assignment: the seam must live in
`trajectory.run_campaign` because ale*/ad01 tests and `cli.py` (seed path,
`propose=None`) consume it, and the loop will consume it as the replaceable
next-decision policy over the same packet/action contract.

## Preserved historical reproduction entry points (no silent renames)

`trajectory.run_campaign`, `trajectory.resume_campaign`, `trajectory.dev_episode`,
`trajectory.run_use`, `trajectory.run_diagnostic`, `trajectory.propose_investigation`,
`trajectory.admit_investigation`, `trajectory.ensure_campaign`,
`trajectory.freeze_repertoire`, `trajectory.load_repertoire`,
`trajectory.cost_union`, `trajectory.campaign_id`,
`construct.construct_method`, `construct.ConstructionFailed`,
`learner.model_propose`, `learner.propose_from_model`, `learner.learner_request`,
`learner.validate_proposal`, `learner.RecordingGatewayAdapter`,
`method_exec.verify_member`, `method_exec.run_member_out_of_process`,
`method_exec.MethodExecutionError`, `cli.py run|resume|use`,
`run_c3_qualification.run_trajectories` (+ new `run_trajectory` helper),
`context.build_packet`, `context.bind_packet_invocation`,
`context.revalidate_packet`, `development.collect_experience`,
`development.diagnose`, `development.construct`.

Changed contracts (reported to coordinator): `learner_request` gains
`packet_version` and `boundary` keys (existing asserted keys unchanged);
`trajectory` `seen` packet gains the `learner_request` keys (`charter`,
`visible_opportunities`, `curriculum_item`, `required_response`,
`packet_version`) plus `boundary`; `construct._prompt` output text changes
(same signature) to render the executable contract; C3 I/R task lists change
to the same set (order differs by arm); `method_exec` subprocess driver adapts
to validated 2-param entries (previously only 3-param calls worked, a
validator/executor trap); `store.transact` journals domain refusals as
refused results rather than raising (observed, not changed).
C3 campaign grants sized for the bypass era (`agenda_authorized` ~1000) no
longer cover admitted learner calls (~2.6k exposure each at current prompt
sizes); the study then honestly falls back to no-candidate per boundary
instead of erroring. Reruns must authorize the admitted path.

## Gate

`tests/test_inv_b1_contracts.py` (new; real Postgres `inv_b1_contracts`,
recording doubles at the gateway seam only): rendering agrees with
execution/validation for software and graph; malformed actions have visible
effects; one C3-style trajectory through the driver shows learner + construction
operations admitted with receipts; I/R lists equal as sets.

## Progress

- [x] Trace public path + owners (above).
- [x] Red repros: IR-01 prompt/contract divergence, IR-02 learner bypass.
- [x] `packet.py` + wire `construct.py`/`learner.py`/`trajectory.py` to it.
- [x] C3 driver through broker admission + equal I/R sets.
- [x] Gate tests green; affected suite green (275 passed, 0 failed).
- [ ] Commit + push branch (next).
- [ ] Drop `inv_b1_contracts` DB on completion.

## Gate output

`tests/test_inv_b1_contracts.py`: 11 passed in ~13s on disposable
`inv_b1_contracts`. Affected set (every test file importing ad01 or the
settlement context/development packets): 275 passed in ~383s, same DB,
`EC02_AD01C_DSN` overridden to the lane database. No existing test changed.
