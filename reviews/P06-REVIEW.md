# P06 independent review

Reviewed `10455e67..fccb59f5` on isolated branch `codex/p06-sol-review`.
The initial verdict is **changes required**. Two material fixture-scope findings
remain open. The existing focused gate passes, but it does not cover these
counterexamples.

## Findings

### P06-R1. Offline replay can attribute an executed policy to different bytes

Priority P2. Open.

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

Priority P2. Open.

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
verification. The added review tests intentionally fail until the findings are
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

Each database run reported that it dropped its two disposable databases.
No live database anchor was used.

## Contract assessment

The reviewed code and passing gate support the following fixture mechanics:

- P01 preparation supplies the same consumed visible input used by execution.
  Captured native branches compare that input and the recorded task, genome,
  execution, receipt, reservation, and artifact facts.
- Serialized policy input excludes private future evidence. Replay and P05 both
  execute policies through `capability.invoke`. R1 and R3 limit the claim that
  their complete policy assessments are equivalent.
- Supported results, missing coverage, deliberate stops, and execution refusals
  remain distinct. A requested second decision is a missing-child gap.
  Supported multi-step replay is not implemented or claimed.
- Screening costs include charged stops and refusals. Unknown costs remain
  explicit and cannot satisfy the candidate's bounded-cost eligibility check.
- Policy admission and work choice persist tagged flights. Existing crash
  recovery and final resource, memory, grant, and deadline fences pass their
  supplied checks. R2 exposes the missing native-runtime check on work resume.
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
- [ ] Independently check integrated repairs and rerun the necessary gates.

Prove It Works required real native execution for R2. Test Behavior, Not
Implementation kept the probes tied to supported assessment and actual dispatch
identity. Laziness Protocol and Subtract Before You Add limit the repair advice
to the existing identity and action boundaries. They do not call for another
history owner or runtime platform in this review.
