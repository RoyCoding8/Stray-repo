# Review 03 — S0–S3 repair acceptance

**Disposition: changes required. S0–S3 acceptance remains open.**

Reviewed source: `72cfa11774b393dbe63a20622b00ef48e0b7966c`.
Fix-cycle base: `d7b46aa1c6f85e273103689134f7d0f36c65aad1`.
Comparison: `git diff d7b46aa...72cfa11` (39 files, 4,212 insertions, 572 deletions).
Scope: R02-001–012 repairs and their production callers, tests, and evidence.
The worker reports 418 passing tests; this review does not independently reproduce that full run.

Worker assessment: independently confirm, narrow, or rebut each finding against the
production path and cited requirement before choosing a remedy. The proposed changes
are recommendations, not an infallible implementation prescription. A probe using
doubles establishes only the behavior described in its evidence boundary. Record
counterevidence and invalid probe assumptions alongside fixes; the next review will
consider both. The continuation prompt reflects this assessment-first workflow.

The implementation improves ordinary admission checks, refusal of scope broadening,
gateway deadline return behavior, conservative unpriced usage, and immutable
assignment metadata. Several remaining defects are failures of integration or
authority at execution time. Adding another metadata check or testing a helper in
isolation will not close those requirements.

## Specification findings

### R03-001 [P1] A newer generation still cannot fence an already released sender

Requirements: EFF-5, REC-3/4, R02-001/004. REC-3 requires: “Discover or fence old
launchers before resuming effects; an old dispatcher may outlive the lost connection.”

Locations: `src/settlement/launcher_runsc.py:346-380`,
`src/settlement/broker.py:410-432`, `src/settlement/gateway_http.py:181-200`,
`src/settlement/store.py:1113-1137`.

The launcher's generation file is checked at line 361, followed by more writes and
an unconditional `run_gvisor`. A newer dispatcher can update the file to generation
2 during that interval and receive `superseded-claim`; the generation-1 sender still
launches. The committed probe reproduces precisely this interleaving. The new broker
check correctly catches a change *before* `_revalidate`, but that is a different case.

Restore only modifies the target database. It does not revoke the old database's
sender authority or install a launch-host/provider fence. The HTTP adapter receives
`dispatch_generation` but neither checks it nor transmits an enforced authority
contract. A generation passed as data does not establish cross-database exclusion.

Required: define the point where the effect executor accepts ownership and implement
a fence or explicit old-executor quiescence at that boundary. Restore must refuse
resumption until that evidence exists. Test old and restored databases with an old
sender paused at the final pre-send boundary. Preserve late receipts separately;
their attribution cannot undo a stale effect.

Probe: `test_new_generation_cannot_stop_sender_past_file_check` (scripted interleaving
through the real launcher method; container execution doubled).

### R03-002 [P1] Watchdog failure and timeout can leave an untracked running container

Requirements: EFF-6/7/9, R02-006. EFF-7 requires: “Killing the broker must not remove
the worker's stop mechanism.”

Locations: `src/settlement/exec_profile.py:325-337,441-491`,
`src/settlement/launcher_runsc.py:279-281,381-388`,
`src/settlement/broker.py:145-147`.

`docker run` starts before watchdog creation. If watchdog creation fails, execution
continues and can return success with `supervised=False`; broker death in the gap
also leaves no independent supervisor. On timeout, failed `docker stop` leads to
killing the Docker CLI, not verified container termination. The function then reaps
the watchdog. The launcher writes a failure result, removes container/supervision
tracking, and `is_live` returns false merely because the result exists.

The second probe holds the modeled container running throughout this exact path and
observes tracking removal. Existing shim tests verify a different case where the
supervisor successfully stops the process representing the container.

Required: establish supervision before releasing execution, fail closed if it is
unavailable, and retain tracking/exposure until termination is established. Account
for startup, stop, inspection, and kill grace in the declared bound. The current
fixed five-second exposure allowance does not cover multiple 15/30-second control
timeouts. Real qualification must also test writable output/scratch limits; a
storage flag and a bind mount are not evidence that all output paths are bounded.

Probes: `test_execution_proceeds_when_supervisor_cannot_start`,
`test_timeout_loses_tracking_without_proving_container_stopped` (real orchestration,
process/runtime boundary doubled; no real-container claim).

### R03-003 [P1] The contained experiment never stages its executable inputs

Requirements: EFF-3, ART-1, S3, R02-006/007/010.

Locations: `src/settlement/experiment.py:115-130,195-219`,
`src/settlement/launcher_runsc.py:138-161`,
`src/settlement/capabilities.py:publish_candidate`.

The CLI now selects runsc by default, but grading still passes the host Python
executable and absolute host grader/candidate/cases paths. Method invocation does
the same for its script and input/output paths. `stage_input` has no production
caller in `src/`, `scripts/`, or `experiments/`; `_mounts` therefore returns an empty
list for these operations. The controlled data-plane helper does not make the live
experiment runnable. A real container does not share the controller's temporary
directory or virtual environment.

Required: route capability verification, grading, and method invocation through the
same admitted staging/export interface; use image-local executable paths and verify
exported artifacts. Keep protected evaluator inputs inaccessible to candidate code,
including when files are mounted read-only and unlinking them cannot succeed. An
uncontained local run is not closure of this requirement.

Probe: `test_contained_grading_prepares_only_unmounted_host_paths` (real preparation
and mount selection with admission captured; no container needed to show the absent
mounts).

### R03-004 [P1] Binding metadata does not prove which candidate/evaluator actually ran

Requirements: EFF-4, LEARN-2/7, R02-008. LEARN-2 requires that “a candidate cannot
write its own successful receipt.”

Locations: `src/settlement/evaluation.py:131-157,169-220,233-288`,
`src/settlement/capabilities.py:314-391`,
`src/settlement/experiment.py:120-129,468-470`.

Any prepared sandbox operation can be bound to candidate/evaluator metadata. The
validators do not prove that its executable, candidate bytes, or task inputs match
those records. A process that simply emits `{"status":"ok","data":{}}` is enough:
`_check_claimed_outcome` explicitly accepts success with **no evaluator tallies**.
The release validator uses that same check. The experiment registers an evaluator
with no code digest and copies grader bytes without binding them to execution.

The probe executes that unrelated process and passes both real binding validators,
even with an evaluator package naming a different code digest. Database lookup
state is supplied explicitly; the database transaction and full release are not
claimed reproduced. Existing tests reject *unbound* or *wrong-ID* operations, which
does not test falsely binding an unrelated prepared operation.

Required: bind verified executable/evaluator, candidate, task/input digests and the
issued operation before execution; verify them at launch and receipt admission.
Require an authenticated evaluator result conforming to the frozen protocol. Bare
process success cannot certify a test outcome. Include pre-bound unrelated commands,
same-version changed grader bytes, changed candidate files, and changed task files
in real broker/database release-path regressions.

Probe: `test_unrelated_successful_process_can_back_evaluation_binding`.

### R03-005 [P1] C's executable result has no causal role in the A/B/C result

Requirements: LEARN-3, practical specification §11, R02-010.
§11 says: “Between-task retention is the experimental difference” and “All arms may
construct tools inside an individual task.”

Locations: `src/settlement/experiment.py:157-192,419-421,523-553`.

The synthesized method is a fixed source-hash-to-saved-answer table. It returns an
unseen source unchanged while reporting success. More seriously, the arm loop
discards `_invoke_method`'s return value and places the **method source text** in
the model prompt. Only the model's subsequent answer is graded. Thus the executable
invocation itself is overhead; C's successful outcome may come entirely from
textual examples encoded in that source. No invocation result reaches the solver,
and there is no common within-task tool loop for A/B/C. This is not a test of the
specified executable carrier against a strong document-memory baseline.

Required: provide the same bounded within-task tools to all arms, expose actual
retained invocation results to C, and measure the intended retention difference.
Candidate synthesis must be able to propose a procedure beyond the fixed exact
lookup encoding. An exact lookup can remain a labeled baseline. Include a no-op
method ablation and independent inputs; positive learning is not required, but an
honest experiment that could detect or refute the carrier's benefit is required.

Probe: `test_synthesized_method_returns_unseen_broken_input_unchanged` executes the
generated program in a real subprocess. Discarded-result/tool-loop findings are
source traces, not an empirical claim about model performance.

### R03-006 [P1] The experiment does not bind the final method version through release and reuse

Requirements: LEARN-1/7, S3, R02-009/010. LEARN-1 says “publication is not release.”

Locations: `src/settlement/experiment.py:335-354,467-501,523-537,601-602`.

Protocols pin `fixer-v1` before development. `_freeze_method` can choose
`fixer-v1-<digest>` when another artifact already occupies that ID, including another
family's artifact. Protocols still name the original version while the experiment
invokes the new one. Its conditions also retain the original `method_version`.
The arm loop reads and pins candidate versions directly; the experiment computes
verdicts but never performs a scoped release or router-backed post-release reuse.

Calling an unreleased candidate inside a trial is legitimate. It does not fulfill
S3's limited-release-and-actual-reuse gate. A later attempt to promote a suffixed
version would encounter the exact-version validator, which correctly refuses the
mismatch rather than fixing the experiment.

Required: freeze selection/access rules before evaluation, then bind each trial to
the actual immutable candidate after construction and before scoring. Define how a
multi-family set is represented. For eligible finite-panel evidence, exercise a
visibly limited release and fresh-worker router use with fallback/quarantine checks.
Synthetic evidence must remain non-promotable; an inconclusive experiment must not
be forced into release. Test existing-version conflicts and multiple families.

Evidence: independent source/spec pass, verified by the primary reviewer; no live
release run independently executed.

### R03-007 [P1] Workflow backup consistency is inferred from an unchanged list of pending IDs

Requirements: REC-1/2/3, R02-004. REC-1 requires stopping old executors from further
checkpoint mutation and a consistent recovery set.

Locations: `scripts/checkpoint.py:198-237,271-309`,
`scripts/restore.py:145-152,194-208`, `src/settlement/store.py:1049-1109`.

For a real DBOS database, `_workflow_barrier` and `_workflow_verify` only compare IDs
whose status is ENQUEUED/PENDING. They neither quiesce the executor nor compare its
checkpointed step results. A workflow may advance steps while retaining its ID and
PENDING status; a new workflow may finish between observations. Both pass the check.
The domain and workflow dumps can therefore capture different execution boundaries.
Restore copies the workflow dump but does not establish its correspondence to the
domain manifest or rebind persisted workflow arguments away from the source DSN.

Pause ownership also needs repair: checkpoint unconditionally replaces an existing
restore pause with a checkpoint pause and unconditionally calls `resume_dispatch` in
`finally`. Taking a checkpoint of a paused restored runtime must not itself authorize
new dispatch. `checkpoint_verify` additionally omits `dispatch_paused` from its SELECT,
so its newly added pause comparison always reads the default value.

Required: a coordinated, quiesced backup protocol with recorded workflow progress,
pause ownership/preservation, clean-runtime restoration, and source-executor fencing.
Test a still-PENDING workflow committing a step during backup, a pre-existing restore
pause, and restored workflow arguments/resources. A nonempty DBOS dump is insufficient.

Probe: `test_dbos_checkpoint_ignores_changed_step_results` exposes the exact query
coverage with a scripted database. The active DBOS interleaving remains a required
worker integration test.

### R03-008 [P1] Waiting workflows have no production wakeup path

Requirements: RUN-2, AGENDA-4, R02-005. AGENDA-4 requires completed operations to wake
the relevant workflow and a periodic scan to repair missed wakeups.

Locations: `src/settlement/broker.py:740-762,974-987`,
`tests/test_r02_authority.py:339-374`.

The workflow now consumes a delayed success **if called again**. When still waiting,
it returns a normal `waiting` result. Heartbeat only restores in-memory resources
and dispatches/reconciles operations; it never starts/resumes the waiting workflow.
There is no production caller of `attempt_workflow` or `start_workflow` under
`src/`, `scripts/`, or `experiments/`. The new “clean process resume” test clears a
dictionary in the same process and explicitly starts a new workflow afterward.

Required: implement the event/outbox/repair path that durably wakes an eligible
continuation, with idempotent wake identities and correct lifecycle handling. Prove
it through a separate process restart and a delayed receipt, without the test
manually restarting `attempt_workflow` on behalf of production.

Probe: `test_heartbeat_restores_resources_but_never_wakes_waiting_workflow` plus
production-call-site inspection. The probe doubles DBOS and database state.

### R03-009 [P2] Positive retry budgets never exhaust after a single failed invocation

Requirements: RUN-1/2, EFF-5/9, R02-005.

Locations: `src/settlement/broker.py:860-875,927-929,988-997`,
`src/settlement/run.py:483-486`.

`wf_ensure_dispatch` exhausts retries only when the number of failure receipts is
greater than `retry_max`. With `retry_max=1` and one failed, observed operation,
that condition remains false forever. The same operation ID is redispatched, the
broker properly avoids re-executing it, and the node is never completed. The workflow
eventually returns `rounds-exhausted`. The new test covers only `retry_max=0`.

Required: define durable retry-attempt accounting and eligible retry behavior. Keep
uncertain-effect retries forbidden without the EFF-5 guarantee. Proven terminal
failure must lead to a bounded retry or an explicit terminal/observation decision,
not repeated reads of the same immutable failed operation.

Probe: `test_positive_retry_budget_repeats_completed_failure_until_round_cap`
(real workflow/interpreter with persistence and dispatch responses doubled).

### R03-010 [P2] Database operations still outlive the declared absolute command deadline

Requirements: transition deadline contract, R02-012.

Location: `src/settlement/store.py:97-167`.

The remaining budget is passed as a fractional `connect_timeout` to psycopg.
Installed psycopg 3.3.5 converts it to integer seconds; a subsecond value becomes
zero and selects its default timeout, not the requested deadline. A local TCP server
accepting a connection but withholding the PostgreSQL handshake holds a 200 ms
command for at least 800 ms before the probe server closes it. The call raises
`OperationalError` instead of returning the bounded command result.

After connection, statement/lock timeouts receive the original remaining budget
once, so successive statements each get that allowance. The refusal transaction
after rollback does not reinstall those LOCAL timeouts. The worker test's 200 ms
command with `elapsed < 5.0` does not establish a 200 ms total bound.

Required: enforce one actual deadline across connection, statements, transaction
completion, retries, and refusal recording; preserve uncertain commit outcomes.
Test handshake stalls, sequential near-budget statements, refusal-journal contention,
and slow commit. Do not merely round the connect timeout and relabel it absolute.

Probe: `test_tcp_connection_wait_outlives_command_deadline` uses a real loopback
socket and real psycopg connection code; no PostgreSQL server is involved. Driver
timeout semantics were inspected in the installed dependency source.

### R03-011 [P1] Claim-backed fulfillment skips protected artifact bytes

Requirements: IF-3, ART-3, R02-003. ART-3 requires: “Missing or corrupted protected
bytes invalidate availability and dependent use.”

Locations: `src/settlement/store.py:618-650,693`,
`src/settlement/evidence.py:157-171,243-250`.

The new claim-witness path calls `evidence.check_use` without an artifact root.
Artifact premises then pass solely because their database availability flag is
`available`. Missing/corrupt bytes can remain undetected when that claim is used to
fulfill an investigation. Requiring a witness ID and the current epoch does not
establish the witness's present availability.

Required: connect fulfillment to the admitted artifact store and reverify required
bytes under the evidence-use contract. Include missing/corrupted protected bytes
through the public fulfillment transaction, preserving valid alternative support.

Probe: `test_claim_fulfillment_omits_artifact_byte_verification` follows the production
witness call and real artifact-premise predicate with scripted claim/SQL state. A
full real-database fulfillment remains to be reproduced by the worker.

### R03-012 [P1] Over-reservation billing discards the actual receipt

Requirements: EFF-4/8/9, R02-011. EFF-4 requires a durable receipt; EFF-8 says older
liability is not erased by a lower authorized budget.

Locations: `src/settlement/store.py:137-149,227-228,841-852`,
`src/settlement/broker.py:504-511`.

When a real bill exceeds the estimate, `_settle_amount` raises after the receipt
insert. `transact` rolls back the receipt and records only the command digest and
refusal detail. `_finish_send` ignores the refusal and marks the dispatch outbox
delivered. The actual response and its billing evidence are no longer in receipts,
and only the smaller reservation remains held. A journaled refusal is not durable
observation or full liability accounting. Estimates are explicitly allowed, so this
is not limited to a provider violating a hard cap.

Required: preserve the authenticated receipt regardless of settlement feasibility;
record the excess liability and an explicit reconciliation/blocking state without
making allocation invariants lie. Do not acknowledge durable delivery when receipt
admission failed. Test above-estimate billing and subsequent restart/operator view
through a real database, as well as the already-fixed unknown-cost branch.

Probe: `test_overcharge_rolls_back_receipt_and_broker_acknowledges_delivery` executes
the production transaction, settlement and broker completion branches against a
scripted rollback-capable connection. It proves the control flow, not PostgreSQL
durability.

## Standards findings

### R03-S01 [P2] The committed final handoff still identifies the previous fix cycle

Rule: `COLLABORATION.md` requires the coordinator's plan, current implementation
status, exact tested-source verification, decisions and current review request.

`reviews/REQUEST.md:1-9` still requests the REVIEW-01 repair review against the older
code/report tips. `reports/VERIFICATION.md:3` and `reports/IMPLEMENTATION-STATUS.md`
still describe the 348-test cycle. `reports/PLAN.md` lacks the completed R02
integration record. `reports/workstreams/r02-evalbind.md:3-6` leaves its code commit
as TBD. The reported final 418-test run is not recorded in these committed reports.
The external `/tmp/adv_billing.py` and `/tmp/adv_binding.py` scripts are not available
in the shared repository.

Update the central handoff, preserving historical results as historical. Name the
tested source revision, exact commands, dependency/runtime versions, counts and
remaining limitations. Preserve useful adversarial checks as committed tests or
bounded reproducible evidence. Do not copy credentials or machine-private paths.

The independent standards pass also noted duplicated state-reading queries in
`evaluation.py:298-493` as a maintainability judgement. It is not a separate required
refactor: preserve transaction correctness and prioritize the concrete findings.
No additional clear introduced code-style violations were found.

**Counts:** specification/correctness: 12 findings (10 P1, 2 P2); standards: one P2.
Standards acceptance is blocked by stale reproducibility records. Specification
acceptance is blocked by execution and evaluation authority failures.

## Disposition of the previous findings

“Addressed” below is scoped to the named behavior and evidence; it does not mean a
full subsystem or live acceptance gate has passed.

| Previous ID | Disposition at 72cfa11 |
|---|---|
| R02-001 | Ordinary pre-check generation mismatch passes independently; final-send and restore fencing remain open (R03-001). |
| R02-002 | Withdrawal/revision checks now appear in shared admission; worker's real-DB tests inspected, not rerun here. No additional defect established for this specific fix. |
| R02-003 | Witness shape, exact epoch and quarantine checks added; claim-byte availability remains open (R03-011). |
| R02-004 | Domain pause, second verification and workflow dump restore added; coherent workflow barrier and safe pause ownership remain open (R03-007/001). |
| R02-005 | Outcome consumption wired into workflow; actual wakeup and positive retry handling remain open (R03-008/009). |
| R02-006 | Output pumps, supervisor and staging helper added; fail-closed supervision and actual staging integration remain open (R03-002/003). |
| R02-007 | Relative repository lookup probe now refused; this does not prove an OS boundary between candidate and evaluator. Contained experiment unavailable (R03-003); evaluator authority open (R03-004). |
| R02-008 | Immutable pre-launch metadata/rebinding checks added; executed bytes and verdict provenance remain open (R03-004). |
| R02-009 | Scope implication direction independently passes drop/change tests. Actual experiment-version/release integration remains open (R03-006). |
| R02-010 | Exact retained version selected for invocation, model texts now graded consistently; executable result discarded, fixed lookup synthesis and incomplete release path remain (R03-005/006). |
| R02-011 | Unknown usage is no longer free, canonical-scale refusal independently passes, child allocation cap added; overage receipt/liability handling remains open (R03-012). No paid validation. |
| R02-012 | Gateway header deadline return independently passes; store end-to-end deadline still fails (R03-010). |

## Independently performed verification

Environment: Windows, Python 3.12.13, psycopg 3.3.5, dependencies from the existing
review virtual environment. Imports were explicitly directed at this worktree's
`src`; `SETTLEMENT_TEST_DSN` was unset. No implementation files were edited.

PowerShell setup used for equivalent direct reproduction from this worktree:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
$env:SETTLEMENT_TEST_DSN = $null
$reviewPython = '../Agent-Society-v2-review-02/.venv/Scripts/python.exe'
& $reviewPython -m pytest -q reviews/probes/test_review_02.py tests/test_r01_grader.py tests/test_run_compose.py tests/test_s0_gateway.py
& $reviewPython -m pytest -q reviews/probes/test_review_03.py
```

The same pytest arguments ran via a subprocess with these environment settings.
For another host, create the locked test environment with `uv sync --extra test` and
use `uv run pytest` with these paths; never point destructive test fixtures at a
non-disposable database.

| Check | Observed result | Boundary |
|---|---|---|
| Six migrated R02 probes + grader/composition/gateway files above | 33 passed, 11 skipped; 17.67 s | Skips: nine grader DB cases, two composition DB cases. Includes real HTTP and grader subprocess checks; no live provider. |
| Nine selected new repair tests listed below | 9 passed; 3.44 s | Source-generation check, scope predicates, HTTP decode and header/cancel behavior. |
| `reviews/probes/test_review_03.py` | 12 passed; 3.95 s | **Passing means the counterexample reproduced. These are not acceptance tests.** Per-test real/doubled boundaries described above. |

The nine selected nodes were:

```text
tests/test_r02_authority.py::test_stale_generation_sender_never_sends
tests/test_r02_evalbind.py::test_release_scope_drop_refused
tests/test_r02_evalbind.py::test_release_scope_change_refused
tests/test_r02_exec.py::test_unknown_billing_decode_keeps_zero_unbilled
tests/test_r02_exec.py::test_explicit_priced_charge_decode_marks_billed
tests/test_r02_exec.py::test_noncanonical_charge_scale_is_protocol_error
tests/test_r02_exec.py::test_malformed_charge_decode_is_protocol_error
tests/test_r02_exec.py::test_header_wait_is_bounded_by_absolute_deadline
tests/test_r02_exec.py::test_cancelled_inference_stays_distinct_from_timeout
```

All runs reported the existing `Unknown config option: asyncio_mode` warning. During
probe development, the unrelated-process probe initially hit Windows' unsupported
`preexec_fn`. Its final version omits only POSIX child setup on Windows, then executes
the real child and protocol validators. It makes no isolation claim. Earlier partial
probe runs are not additional evidence counts.

Two bounded read-only independent passes covered standards and experiment/evaluation
requirements. The primary reviewer validated actionable findings and built the probes.
No full PostgreSQL suite, real DBOS restart, real gVisor containment, live inference,
paid billing, PostgreSQL 18 qualification, or empirical learning comparison was run
here. Worker workstream results were inspected; the reported 418 total remains
worker-reported.

## Probe-retirement assessment

- Stale generation: the maintained replacement covers the original pre-check
  mismatch. It does not cover R03-001's final-send interleaving.
- Fulfillment: copied unwitnessed obligations are rejected in source and worker
  tests. Claim-backed missing bytes need R03-011's public-path regression.
- Delayed outcome: the named `test_adv_broker.py` tests in the triage report do not
  establish workflow wakeup. The newer authority test explicitly starts the
  workflow in-process; R03-008 remains uncovered.
- Checkpoint: the migrated probe still constructs a manifest/dump mismatch while
  mocking verification to pass. It tests call order only. The added domain mutation
  refusal test does not establish a coordinated active DBOS snapshot.

Retirement is acceptable only with a behavior-level replacement and traceable
coverage. Do not invert or remove these probes merely because implementation details
changed; establish the forbidden behavior is prevented through the real entry point.

## Next action and architectural interpretation

Use [WORKER-REVIEW-03-PROMPT.md](../docs/HISTORY.md#worker-review-03-prompt) in the existing worker conversation.
Assess the findings, repair confirmed S0–S3 defects, and publish a reproducible handoff. Hold
S4–S7. Live environment gates can be qualified once the repaired path is runnable;
missing credentials/runtime access remain explicit blockers, not inferred passes.

This review does not reject composable retained competence as an architecture. It
rejects treating the present plumbing and simulated outcomes as evidence for that
hypothesis. First establish truthful execution/evaluation and a fair experiment.
An inconclusive or negative learning result is an acceptable experimental result;
it should guide the next architecture decision rather than be engineered away.
