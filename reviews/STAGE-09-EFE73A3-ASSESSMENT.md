# Stage 9 delivery assessment

Reviewed 2026-09-21 at `efe73a3fe047a62ae9ad21bd10da527ccf754020`.

**Disposition: useful mechanisms delivered; consolidation not complete.** Keep the accepted stage 8 closeout closed. Finish the existing stage 9 contract through the public path, then run the newly authorized free-model study. No architecture restart or unrelated hardening campaign is needed.

The intended advance is executable learning-policy revision: experience changes the program deciding what to investigate, construct and use; independent outcomes determine whether to retain that revision. Acquiring another task solver is useful, but does not demonstrate that advance.

## Material findings

### S9R-01 — The prospective pilot does not exercise the selected policy treatment

`scripts/s09_pilot.py::_construct_arm` calls `construct_method` with a recording gateway, producing a task method. `_run_episode` calls `trajectory.run_campaign` without a STEP consumer or gateway. Assessment episodes therefore follow the seed investigation path; the later repertoire/use differences do not establish P0/P1/P2 learning-policy treatment. `run_study(mode=live)` checks a grant environment variable but still constructs the recording gateways and scripted sources. It does not select a configured live provider.

The M5 workstream explicitly describes this as a skeleton whose STEP and promotion connections belong to other lanes. Lane ownership does not discharge the coordinator's integration obligation. The offline verifier's pass validates the exported fixture against that verifier, not the missing experimental treatment or live adapter.

Complete N5 with acquired STEP source bytes, the same current driver, frozen distinct arms, proper development/assessment separation and real configured inference. Preserve the current doubled bundle as historical apparatus evidence. Missing candidates remain unavailable arms, without substitution.

### S9R-02 — STEP continuity and action execution are incomplete

`agenda_policy.py::StepPolicyConsumer.decide` starts each boundary with empty private state and reconstructs `remaining` from the original packet inside the step loop. A reviewer probe observed three model preparations from a one-call allowance, then empty state at the next boundary after the previous STEP returned `counter=4`. The recorded event order was three model preparations followed by policy-transition persistence. This is a controller probe with the child, broker, receipt read and persistence doubled; it is not evidence of actual spending or a database crash test.

There are also unconnected action semantics. `_step_proposal` translates `use_method` into `development`, attaching a method ID which `_run_boundary` does not consume; that path instead performs development/construction. `propose_revision` records metadata and returns a stop action; the current driver stops without executing a revision lifecycle. The manual full-cycle test does not close these public action paths.

Make each accepted STEP action execute its declared effect, preserve policy state and result feedback across boundaries, and persist attributable pending identity before effects. Enforce cumulative step/model limits, including failure and retry, from durable state. Prove restart with real PostgreSQL and real child execution. In particular, using an existing method must not silently construct a new one, and proposing a revision must reach construction/assessment or a durable, named refusal.

### S9R-03 — Atomic binding is not independent qualification

`selection.py::bind_revision` accepts caller-supplied versions, scope and disposition, with optional empty protocol/evaluator values. It writes releases with empty evidence references and does not require a passing assessment bound to those bytes. The version compare-and-swap prevents stale replacement but does not authorize promotion.

`tests/test_s09m34_cycle.py::test_full_deterministic_cycle_with_provider_double_only` manually opens a proposal, constructs a method, freezes, assesses, invents its version ID and calls binding. The test caller performs the lifecycle; the runtime does not establish that binding consumes the actual passing result.

Connect assessment to promotion in the trusted shared path. Refuse absent, failed, stale, differently scoped or differently sourced evidence. Keep authored baseline installation explicit. Operational feedback must remain distinct from sealed assessment, and protected outcomes must not become construction inputs. An honest failed assessment must leave the incumbent active.

### S9R-04 — Public subsequent use is not explicitly scoped to its binding

`selection.py::active_binding_for` without a release ID scans eligible releases globally and picks the newest matching family. The public use command does not expose/thread an explicit release selection. An unrelated eligible release can therefore influence which binding a use resolves. A test passing `release_id` directly to `select_member` does not establish public CLI behavior.

Carry the investigation's exact binding identity through the public entry, persistence and fresh-process use. Prove two studies/releases of the same family cannot select one another's methods. The resumed use must resolve the same immutable selected bytes or record a precise refusal.

## Checks observed by this reviewer

- Fetched and reviewed the exact worker tip, including its original assignment, implementation contract, source and reported limitations.
- `python scripts/s09_verify.py evidence_s09pilot/doubled-r1`: exit 0, 8 claimed operations, 3 construction/model calls, 24 use records, 128 acquisition witnesses, 0 use witnesses, worst-case 100. This is fixture-verifier evidence only.
- `python reviews/probes/stage09_step_continuity.py`: exit 0 with the observations under S9R-02. Source and output are committed. This is a diagnostic, not a passing acceptance test.
- `python -m pytest tests/test_s09m34_visibility.py -q -p no:cacheprovider -k 'not stale_bind'`: **3 passed, 1 deselected**. These passing visibility checks are useful and do not prove the integrated study.
- No local PostgreSQL/full-suite rerun, live study inference or containment qualification was performed in this review. The worker's full-suite numbers remain its reported evidence, including its failures/errors; they are not a clean suite verified here.

## Jev second opinion

Used the installed Jev skill with the actual functions, requirements, observed diagnostic and counter-evidence. Request and raw response are in `reviews/evidence/stage09-efe73a3/`. Jev classified policy pilot, live route, assessment binding and continuity as incomplete, with choice probabilities 0.61, 0.73, 0.87 and 0.73. It classified the remaining work as material rather than optional polish at 0.96. Some confidence values were modest; these are judgments on supplied evidence, not independent execution or calibrated correctness probabilities.

The source trace and probe support the findings independently. Jev neither authorizes spending nor changes an observed test result. The completion assignment requires similarly concrete Jev checks with preserved disagreements.

## Completion and authority

Use [WORKER-STAGE-09-COMPLETION.md](../WORKER-STAGE-09-COMPLETION.md) for the whole next assignment, including its explicit free-model live grant. Resolve these integrated requirements together and report what was implemented, what ran live, whether behavior changed, and whether it helped. An executed, valid negative result can close the study; an unconnected live path cannot.

The original assignment forbids changing or deleting other owners' databases. It does not forbid creating isolated databases owned by this assignment. Repair test configuration and create/remap owned test databases rather than presenting missing setup as an inherent external blocker. Preserve any genuine environment limitations and exact run counts.
