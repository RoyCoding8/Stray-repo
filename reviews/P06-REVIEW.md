# P06 independent review

Reviewed `10455e67..fccb59f5` on isolated branch `codex/p06-sol-review`, then
independently checked the R1/R2 integration at `34653780` and R4 repair
`353fac29`, integrated in this review tree at
`e0c919a2`. The final verdict is **PASS for the claimed fixture engineering
scope**. R1, R2 and R4 are closed with observed proof. R3 remains minor, as does
the bounded verifier work before late refusal described below. P06 remains open
and P06-E remains live unqualified.

## Findings

### P06-R1. Offline replay can attribute an executed policy to different bytes

Priority P2. Closed at integrated source `34653780`.

`src/rsi/search.py:484` compares the reported policy with its copied
`pinned_evaluation`. `policy_effect_evidence` at line 515 checks operation and
receipt identity, but does not bind the observed invocation's `method_digest`
to that policy. It also lacks a prospectively recorded policy execution identity
against which to compare the observed execution.

The review probe begins with the existing accepted `rsi_search_fixture.bundle`.
It adds the correct observed method digest to the invocation and verifies one
supported result. It then changes only the reported and copied pinned policy's
genome, method name, and method digest. The actual invocation, operation,
receipt, output, request, and branch stay unchanged. `search.recompute` still
returns `supported=1, gaps=0`. The saved result can therefore credit a different
policy with an action it did not execute. The invariant is binding policy
assessment to the executable that produced the observed action.

Reproduce with
`tests/test_rsi_search_review.py::test_offline_replay_does_not_relabel_an_executed_policy`.
The final targeted run failed its expected `supported=0, gaps=1` assertion in
2.20 seconds. This is an authored offline evidence test, not a live execution
or an assertion that a digest authenticates external provenance.

Repair the policy-to-invocation identity boundary. Preserve the actual observed
method and runtime evidence and reject inconsistent attribution during
recomputation. Merely comparing two copies of the requested policy is insufficient.

### P06-R2. A persisted work choice can dispatch a different native runtime

Priority P2. Closed at integrated source `34653780`.

`src/rsi/agenda.py:640` reads the work flight's prepared start. Its checks cover
the visible input and decision, attempt, and operation IDs. The final call to
`investigate.step` at line 672 builds native execution from the current checker.
It does not compare that new invocation plan with the native runtime pinned in
the policy's selected frame.

The review probe first completes an actual native agenda and obtains a
`supported` result from `search.capture`. It then creates a second agenda and
interrupts execution immediately after the policy choice becomes a durable
work flight. No worker operation exists at this point. On resume, the probe
changes `LocalLauncher.staged_python` from the virtual-environment interpreter
to its trusted base interpreter. The worker executes with a different `cap1`
execution version from `flight.start.runtime.execution_version`.

The observed pinned identity was
`cap1-76387baeead2ceb8126f6f0734dad4879bb3fcaad9f67f4f5cea2a51e86db6b7`.
The dispatched identity was
`cap1-1a944064bf86e71fbbd76906006bd5d321f0368b0f745efe1a1da06df819815e`.
These identities depend on the disposable fixture paths. The repeatable fact
is their inequality after a persisted choice and before the first worker send.

Reproduce with
`tests/test_rsi_search_review.py::test_pending_work_rechecks_the_policy_pinned_native_runtime`.
The combined counterexample run finished with two failures, zero skips, and
zero errors in 59.63 seconds. Its native baseline passed and its captured branch
was supported before the intervention. Both disposable databases were dropped.

Recheck the selected native plan before a new worker dispatch. Preserve recovery
of an already recorded effect under its existing identity. A changed runtime
must not silently create a new execution for a policy-pinned work choice.

### P06-R3. Replay and agenda disagree on long stop reasons

Priority P3. Minor, open.

`src/rsi/search.py:340` accepts every nonempty string as a stop reason.
`src/rsi/agenda.py:1295` rejects reasons exceeding 1,024 UTF-8 bytes. Passing the
same completed invocation with a 1,025-byte reason to both parsers returns
`stop` in replay and a bounded-reason refusal in agenda. This is a direct parser
probe, not a claim about a live candidate. Consolidate the closed-action
validation so the same executable result has the same interpretation.

### P06-R4. Conflicted worker evidence can authorize capability retention

Priority P2. Reproduced at `34653780`; closed by `353fac29`, independently
verified at review integration `e0c919a2`.

The probe starts with a completed, supported native agenda baseline. On a fresh
agenda it interrupts the authored worker after the broker records its receipt
but before `capability-use` is archived. It admits a different receipt body
under the same receipt identity through `store.admit_receipt`. The worker remains
`observed` and settled, but its reconciliation state is `conflict` and the
receipt-conflict table contains one conflict. The intervention then changes the
current interpreter to a distinct copied path and verifies that its plan differs.

Recovery through the terminal checker view preserves the worker's original
operation and execution identity, with one spawn and no new worker send. It also
interprets the first receipt, archives a completed native capability result,
and launches one bounded verifier on those returned files. P01 correctly
retains the pending flight and emits no agenda acknowledgment. However, a new
public `capability.retain` call for that exact worker episode returns
`status=retained` while the worker is still conflicted. Retained capability
evidence therefore escapes the P01 acknowledgment fence.

`capability.invoke` at `src/rsi/capability.py:217` checks the terminal dispatch
state and ordinary receipt count before interpreting the result, without
checking conflict state. The authoritative retention boundary,
`_checked_use` at line 574, also checks worker settlement, identity and ordinary
receipt count but omits worker reconciliation and receipt-conflict evidence.
Its later `gate._known_test_result` check validates the verifier operation;
it does not reject the conflicted source worker.

Reproduce with
`tests/test_rsi_search_review.py::test_terminal_worker_receipt_recovery_preserves_identity_and_uncertainty[receipt-conflict]`.
The final targeted probe passed its original-identity, spawn-count,
verifier-only-send, pending-flight, no-acknowledgment and durable-conflict
assertions, then failed because retention returned `retained` rather than
`rejected`. The run had **one failure, zero passes, zero skips, and zero errors
in 59.27 seconds**. Both disposable databases were dropped.

Reject unresolved or conflicting source evidence at the capability evidence
admission boundary. Merely blocking the agenda acknowledgment does not prevent
another consumer from retaining the already published capability result.

## Integrated repair assessment

At `34653780`, replay compares the selected policy method digest with the
observed invocation before classifying the action as supported. The shared
fixture now supplies that observed identity. The relabeling probe retains
screening cost while expecting a gap for the altered policy.

Agenda recovery now recomputes the native plan and compares its complete
runtime with the durable work start. The portable intervention copies the
trusted current interpreter to a distinct path and asserts a different
`execution_version` before resuming. It does not depend on virtual-environment
symlink behavior and has no skip branch.

The additional R2 probes cover absent, prepared, and dispatching worker
operations. They expect a pending flight, unchanged worker operation, and no
launcher send after runtime drift. The dispatching case already sent the
original worker once and retains that one spawn.

The terminal probe crashes after the broker saves the worker receipt but
before `capability-use` is archived. It tests the `copy.copy` checker view with
a different current interpreter. Successful recovery must retain the recorded
worker operation and execution version, retain one worker spawn, and send only
the expected verifier. The caller's checker must still return the changed
interpreter. A conflicting admitted receipt must remain conflicted, with the
flight pending and no acknowledgment. A changed pending visible input must
raise `StaleRevision`, also preserving the flight and worker operation, with no
send. A receipt conflict permits one verifier send while preserving the pending
flight and no acknowledgment. That extra bounded verifier alone is not the
material finding; accepting its conflicted worker as retention evidence is R4.

The first integrated four-file run used `ad1069b1` and finished with **37 passed,
3 failed, zero skips, and zero errors in 497.02 seconds**. Its exact files were
`tests/test_rsi_search_review.py`, `tests/test_rsi_search.py`,
`tests/test_rsi_search_replay.py`, and `tests/test_rsi_search_agenda.py`.
All three failures were probe construction errors: an overly broad crash
injector interrupted the policy invocation before a work flight existed,
causing `KeyError: start`. The final probe restricts the crash to the authored
`maximum` worker. This failed run is separate from final verification.

A second probe-file run used `ad1069b2`: **six passed, one failed, zero skips,
and zero errors in 319.01 seconds**. Its receipt-conflict case failed an overly
strict zero-send expectation: the only new send was the expected verifier.
The final assertion distinguishes that attributable verifier from a new worker
dispatch and separately challenges authoritative retention. This run predates
the retention assertion and does not close R4.

The completed recovery-only probe-file run on `ad1069b3` had **seven passed,
zero skips, and zero errors in 316.89 seconds**. It independently closed R1 and
R2 and confirmed pending/no-acknowledgment behavior for receipt conflicts. It
was collected before the public retention assertion was added. The subsequent
single-case `ad1069b4` run, described in R4, is the final authoritative-evidence
counterexample at `34653780`. These counts are separate runs; the subsequent
repair and final closure run follow.

### R4 closure at the shared capability evidence boundary

Commit `353fac29` adds worker and verifier reconciliation checks inside
`capability._checked_use`. Both reject `conflict` and `unresolved` before
returning authoritative checked-use evidence. The repair uses the broker's
existing durable reconciliation state; it adds no parallel history owner or
recovery state. The original terminal public-retention counterexample now
passes: the worker and flight retain their recorded identities, the conflict
remains inspectable, no acknowledgment escapes, and fresh retention is rejected.

The maintained worker/verifier conflict regression starts from passing native
qualification, retention and selection. After admitting a real conflicting
receipt, fresh retention is rejected, fresh selection declines, and validation
of the previously selected capability raises `CapabilityError`. Historical
retention and selection decisions remain immutable records. Their stored
statuses describe the prior decision; current eligibility and use validation
recheck source evidence through `_checked_use`.

The independent closure run at `e0c919a2` passed **three tests, zero skips, and
zero errors in 78.05 seconds**. Its exact scope was:

```text
tests/test_rsi_search_review.py::test_terminal_worker_receipt_recovery_preserves_identity_and_uncertainty[receipt-conflict]
tests/test_rsi_capability_integration.py::test_conflicted_checked_use_cannot_retain_or_authorize_selection[worker]
tests/test_rsi_capability_integration.py::test_conflicted_checked_use_cannot_retain_or_authorize_selection[verifier]
```

Minor residual behavior: terminal recovery still publishes the completed native
result and launches one bounded, attributable verifier before P01 refuses the
conflicted source. This is extra work on unresolved evidence, not a duplicate
worker send or accepted assessment. The passing terminal probe verifies the
original worker operation and execution version, one worker spawn, only the
expected verifier send, a pending flight, no acknowledgment, a retained durable
conflict, and rejected capability retention. Moving this refusal earlier is a
minor efficiency improvement; no material fixture-scope finding remains open.

Ruff passed on both affected test files, and `git diff --check` passed. This is
targeted independent closure, not a repeated broad gate, whole-repository test
run, CI result, or live qualification.

## Verified scope

The original focused gate at `fccb59f5` passed **56 tests, zero skips, and zero
errors in 476.08 seconds**. Its exact files were:

```text
tests/test_rsi_search.py
tests/test_rsi_search_replay.py
tests/test_rsi_investigate_preparation.py
tests/test_rsi_capability_plan.py
tests/test_rsi_search_agenda.py
tests/test_rsi_search_campaign_export.py
tests/test_rsi_search_experiment.py
```

A separate neighboring gate passed **two tests, zero skips, and zero errors in
17.96 seconds**:

```text
tests/test_rsi_agenda.py::test_agenda_persists_choice_runs_p01_and_exports_exact_ack
tests/test_rsi_agenda.py::test_definitive_pre_dispatch_refusal_closes_pinned_flight
```

These runs are separate scopes. They are not a whole-repository suite or CI
verification. The initial review tests failed before the findings were
repaired. A later single-test rerun strengthened R1 by supplying the correct
observed method digest before its intervention. It failed in 2.20 seconds.
Ruff passed on the final review test file through `uvx ruff check`.

All database tests used the project interpreter
`D:/AI/Agent-Society-v2/.venv/Scripts/python.exe`, normal conftest loading, and
PostgreSQL at `127.0.0.1:55432`. Both administrator and test DSNs were
`dbname=postgres host=127.0.0.1 port=55432 user=postgres`, with
`SETTLEMENT_REQUIRE_TEST_DB=1`. `PYTHONPATH` contained this review tree's `src`,
`tests`, and root. Isolated tokens and short temporary roots were:

| Run | Token | Temporary root | Private log |
|---|---|---|---|
| Original focused gate | `ad1069a1` | `D:/AI/tools/p06/solad1069a1` | `D:/AI/tools/p06/sol-review-baseline.log` |
| Initial counterexamples | `ad1069a2` | `D:/AI/tools/p06/solad1069a2` | `D:/AI/tools/p06/sol-review-counterexamples.log` |
| Neighboring agenda checks | `ad1069a3` | `D:/AI/tools/p06/solad1069a3` | `D:/AI/tools/p06/sol-review-neighbor.log` |
| Integrated four-file probe calibration | `ad1069b1` | `D:/AI/tools/p06/solad1069b1` | `D:/AI/tools/p06/sol-review-closure.log` |
| Worker-only crash probe calibration | `ad1069b2` | `D:/AI/tools/p06/solad1069b2` | `D:/AI/tools/p06/sol-review-final-probes.log` |
| Recovery checks before retention assertion | `ad1069b3` | `D:/AI/tools/p06/solad1069b3` | `D:/AI/tools/p06/sol-review-final.log` |
| Authoritative retention counterexample | `ad1069b4` | `D:/AI/tools/p06/solad1069b4` | `D:/AI/tools/p06/sol-review-retention.log` |
| Independent R4 closure | `ad1069c1` | `D:/AI/tools/p06/solad1069c1` | `D:/AI/tools/p06/sol-review-r4-closure.log` |

Each database run reported that it dropped its two disposable databases.
No live database anchor was used.

## Contract assessment

The reviewed code and passing gate support the following fixture mechanics:

- P01 preparation supplies the same consumed visible input used by execution.
  Captured native branches compare that input and the recorded task, genome,
  execution, receipt, reservation, and artifact facts.
- Serialized policy input excludes private future evidence. Replay and P05 both
  execute policies through `capability.invoke`. R3 limits the claim that
  their complete policy assessments are equivalent.
- Supported results, missing coverage, deliberate stops, and execution refusals
  remain distinct. A requested second decision is a missing-child gap.
  Supported multi-step replay is not implemented or claimed.
- Screening costs include charged stops and refusals. Unknown costs remain
  explicit and cannot satisfy the candidate's bounded-cost eligibility check.
- Policy admission and work choice persist tagged flights. Existing crash
  recovery and final resource, memory, grant, and deadline fences pass their
  supplied checks. Integrated recovery now compares the native runtime pinned
  in the work choice before dispatch.
- Campaign export includes policy operations that have no P01 attempt, along
  with their supporting policy and frame artifacts.
- The apparatus uses a development-only P03 construction packet, checks the
  candidate's unchanged method identity, and freezes two construction operation
  IDs. Construction accounting preserves both IDs and unresolved effects.
- The P05 use deadline starts at first durable agenda creation and is reused
  when that agenda resumes. It is not derived from freeze creation.

The full source diff, relevant P01 and capability callers, component plan,
experiment documentation, ledger, and private decision trail were inspected.
The private trail was a secondary source, not proof of behavior. No private
trail contents or credentials were copied into Git. Direct comment review found
no material unsupported fixture or learning claim. No production comment or
code edits were authorized in this lane.

`LocalLauncher` remains uncontained. The plan and experiment README state this
limitation. Only authored trusted fixture candidates ran during this review.
No live model call, Jev call, or untrusted model-generated policy ran. The WSL
runtime direction remains future shared work. P06 stays open and P06-E remains
live unqualified. Passing fixtures do not demonstrate acquisition, transfer,
policy benefit, or improvement of the learner.

## Review tasks

- [x] Read instructions, memories, applicable skills, and current acceptance scope.
- [x] Inspect the full P06 source diff and relevant callers.
- [x] Run the original focused gate and neighboring agenda checks.
- [x] Probe policy attribution and work recovery from accepted baselines.
- [x] Record exact findings and verification boundaries.
- [x] Independently close R1 and R2 on integrated source.
- [x] Challenge terminal checker recovery and reproduce the R4 retention escape.
- [x] Independently verify R4 after the shared evidence admission repair.

Prove It Works required real native execution for R2. Test Behavior, Not
Implementation kept the probes tied to supported assessment and actual dispatch
identity. Laziness Protocol and Subtract Before You Add limit the repair advice
to the existing identity and action boundaries. They do not call for another
history owner or runtime platform in this review.
