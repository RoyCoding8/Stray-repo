# L2 — Make the probe a durable operation

Lane A7. Branch `wt/a7-probe`, forked from `450a988`. Takes the item lane A1
recorded as "not completed": `scripts/invl02_live.py:probe` was still a bare
send.

## How the probe became durable

The probe handed a hand-built `ModelRequest` to `LiveGuard.infer`, which
called a bare `HttpGatewayAdapter` directly. `invl02-probe-<read_ms>` was
minted and admitted nowhere, so the send had no operation row, no
reservation, no receipt and no exposure, and the guard's ceiling was seeded
with `already_spent=0` because there was no store to ask.

It now goes through `_DurableBrokerOutput`, the same object every other live
path in this file sends through and the same shape lane A1 gave the
preflight. That object calls `broker.ensure_operation` and
`broker.dispatch_operation`, so the store holds the identity and the
allocation and the broker writes the receipt and settles the reservation.

`probe` takes `dsn` and `allocation_id` and requires them together, and the
`probe` verb gained `--dsn` and `--allocation-id`. The ceiling is now
`_already_spent(dsn, allocation_id) + 1` rather than a literal `1`, and the
guard is handed that same read as its `spend_reader`, so it re-asks the store
on every check instead of trusting the seed.

The guard stays the outer object. It keeps the route check, the cost block
and the evidence ledger, which are per-attempt observations of one send.
What it no longer owns is the send's admission. A send now ends in a
receipt, so `_DurableBrokerOutput` rebuilds the `ModelResponse` or the
`GatewayError` the guard already knows how to read.

Two properties follow from that placement rather than from bookkeeping.
A second dispatch of one operation id finds a settled operation and returns
the settled text without reaching the gateway, so identity is what stops the
second send. And the position the ceiling enforces is
`COUNT(*) FROM operations` under the allocation, which is a fact that
survives a crash, a resume or another process.

`probe` also gained a `gateway` seam, defaulting to `None` with `None`
building the real `HttpGatewayAdapter` from settings. That is the same
explicit-injection shape `run_output_live` already has, and it is what lets
the requirements be tested offline against a stub. A caller that omits the
argument cannot end up anywhere but the provider.

`probe` now also writes its own output directory, which the bare send never
did. The path is derived from `out`, so a caller naming a fresh directory
gets it rather than an `IsADirectoryError`.

## The updated no-dsn assertion, and why it is not a weakening

`tests/test_c14_live_already_spent_source.py` had two assertions pinned to
the defect. Both were updated, and neither was deleted.

`test_the_probe_verb_offers_no_dsn_flag` read `assert "--dsn" not in block`.
That asserted the absence of a flag, which any probe that had simply not
been made durable satisfied. It passed on the bare send. The new
`test_the_probe_verb_refuses_a_caller_with_no_dsn` asserts the opposite
shape and is strictly stronger: the verb now offers `--dsn` and
`--allocation-id`, forwards both, and `probe` raises `PROBE_STORE_REFUSAL`
when either is missing. The companion
`test_the_probe_path_reads_its_count_from_the_store` replaces
`test_the_probe_path_has_no_store_to_read` (which asserted `"dsn" not in
params`) with the affirmative `dsn` and `allocation_id` in the signature.

`test_probe_refuses_rather_than_seeding_a_ceiling_it_cannot_ground` read
`assert "_already_spent(" not in block`. Its claim was that a count nobody
writes must not decide whether a probe may send, and it was true while the
send was bare. It is now the same claim pointed the other way, under the
name `test_the_probe_ceiling_is_the_stores_count_and_not_a_seed`: the
ceiling is built from a store read, and the guard is handed that read.
Deleting it would have dropped a real assertion, so it was rewritten rather
than removed.

The behavioural replacement, the refusal a caller with no dsn actually
meets, lives in `tests/test_inv_a7_probe_durable.py` and is asserted against
a real database rather than against the source text.

## The four requirement tests

`tests/test_inv_a7_probe_durable.py`, all against a real PostgreSQL store
through the `migrated_db` fixture. Asserted as presence, not as
absence-of-error.

| Requirement | Test |
|---|---|
| A probe with a dsn produces an operation row, a reservation with exposure, and a decided receipt | `test_a_probe_with_a_store_is_an_operation_with_a_receipt_and_exposure` |
| A probe without a dsn is refused, writes no row, issues no send | `test_a_probe_with_no_store_is_refused_and_sends_nothing` |
| A second probe on one operation id sends exactly once | `test_a_second_probe_on_one_operation_id_sends_once` |
| Half the pair is refused too | `test_a_half_given_pair_is_refused_before_the_wire` |

The refusal literal is `driver.PROBE_STORE_REFUSAL`:

```
a probe is durable or it is not: dsn and allocation_id are required together, because a send with no store is a model call that leaves no operation row, no receipt and no exposure
```

The no-store test asserts that string exactly, so the refusal cannot be
satisfied by any unrelated `ValueError`. It then asserts `operations`,
`reservations` and `receipts` are all empty and the allocation's
`consumed`/`reserved` are both zero.

The send-once test reads its count from the adapter the broker actually
called, so it fails on a second wire contact rather than on a bookkeeping
difference.

The adapter is `_RoutedAdapter`, an offline stub returning the frozen route.
`FakeGatewayAdapter` answers with no route fields, which the shipped guard
refuses before any of these claims could be observed. No network, no
credential, no live route. `INVL02_LIVE_GRANT` and `INVL02_LIVE_MODEL` are
set to fixture strings in a `monkeypatch` so the refusals under test are the
probe's own and not those two gates.

### TDD

The four tests failed first against the unmodified base driver, with
`TypeError: probe() got an unexpected keyword argument 'dsn'`, which is the
defect stated as an interface. The red run also caught two real bugs in my
first implementation: a `path.mkdir` that created a directory at the
output file's own path, and a half-given-pair refusal that sat behind
`_require_grant`.

## The three raw sends

All three are outside this lane's owned paths. None was migrated. Each is
recorded here with the state measured on `450a988`.

| Site | State | Disposition |
|---|---|---|
| `src/settlement/boot.py:163` | RAW liveness probe at boot. `adapter.infer(ModelRequest(... operation_id="boot-inference-probe"))` with no operation, no receipt, no exposure. | Not owned. Migrating it is a change to `settlement.boot`'s status contract: it returns a `_status` tuple, so a durable send would need a store in `boot`'s signature and a decision about whether a boot check may demand a database. Belongs to whoever owns `src/settlement`. |
| `experiments/ad01/run_c3_qualification.py:95` | Not a live send. `_C3Gateway.infer` is a demux over `RecordingGatewayAdapter` doubles. The docstring at line 68 is explicit that every call still travels through broker ensure and dispatch with settled receipts; only the provider answers are recorded. | Already broker-owned. No defect. |
| `scripts/s09_pilot.py:229` | RAW delegating wrapper. `StudyGatewayGuard.infer` calls `self.delegate.infer` directly after its own integer `dispatch_count` check, so a send here has no operation row. Its `already_spent` is read at line 1101 from `S09_STUDY_CALLS_ALREADY_SPENT`, the dead name, defaulting to `"2"`. | Not owned. This is the same hole C14 named and the same second-admission path `tests/test_s09_a8_production_adoption.py::test_the_recorder_is_still_a_second_admission_path` describes. It is also the file whose line drift is the one failing test in the gate. |
| `experiments/run_dev_episode.py:119` | A scripted double. | Left, as instructed. |

`scripts/invl02_live.py` also keeps `_already_spent`, `_output_already_spent`
and `_output_evidence_spent` as three reads of the same currency. The probe
now uses the first. The other two remain one fact read three ways and are
still worth one owner; that is A1's note, unchanged by this lane.

## Gate

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'mkdir -p /home/ubuntu/claims; export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/a7.jsonl; cd /mnt/d/AI/Agent-Society-v2/.worktrees/a7-probe && PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/a7-probe/src timeout 1200 /home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_inv_a7_probe_durable.py tests/test_c14_live_already_spent_source.py tests/test_inv_a_preflight_durable.py -q -p no:cacheprovider'
```

`1 failed, 18 passed in 40.92s`

**The one failure is pre-existing and is not this lane's.**
`tests/test_c14_live_already_spent_source.py::test_the_dead_name_is_no_longer_a_reader_anywhere`
asserts the surviving reader of the dead name is at
`scripts/s09_pilot.py:1109`. On this base it is at `scripts/s09_pilot.py:1101`.
`git diff --name-only 450a988 -- scripts/s09_pilot.py` is empty, so the
reader moved under the test from a lane outside this one and this lane's diff
touches neither file. A1 recorded the same failure with the same two line
numbers. Verified by stashing this lane's two files and running the base C14
file: `2 failed, 10 passed`, one of which is this same line-drift failure.

The C14 module docstring was updated in the same file, because it stated
that the probe has no store, which is no longer true and which its own
assertions now contradict. No file under `reports/evidence/` was edited,
overwritten or moved.

## Regression runs

The driver is imported by 24 test files. Its consumers were run on this
branch and on the stashed base over the same file list.

```
tests/test_child_limits_platform.py tests/test_evidence_integrity.py
tests/test_invl02_causality.py tests/test_json_repair.py
tests/test_live_integration.py tests/test_m4_clean_baseline.py
tests/test_m4_live_ceiling.py tests/test_preflight_zero_overwrite.py
tests/test_r123_gates.py tests/test_route_refusal_fidelity.py
tests/test_s09_c11_reported_spend.py tests/test_s09_n203_dispatch_ceiling.py
tests/test_s09_r6_small_defects.py tests/test_s09_r7_output_problems.py
tests/test_s09_verdict.py
```

Branch: `14 failed, 230 passed, 3 skipped in 280.45s`
Base: `14 failed, 230 passed, 3 skipped in 443.85s`

Same count and the same test ids on both sides, so **no test regressed on
this branch**. The 14 are `MethodExecutionError: refused: execution needs
explicit authority and identity` from `experiments/ad01/method_exec.py:1413`
and its dependents, and they are outside this lane's paths.

`tests/test_output_evidence.py`, `tests/test_r4_live_blockers.py` and
`tests/test_resume_exposure_fidelity.py` were not run. A1 measured six base
failures in the first of them and the coordinator's policy caps this lane at
one scoped run, so the durable-gateway consumers are left unmeasured here and
A1's numbers stand unverified by this lane.

Not measured, and left that way on purpose: the full suite. Four other lanes
were running concurrently in the same WSL instance.

## Changes outside this lane's owned paths

None. The three files changed are `scripts/invl02_live.py` (the `probe`
region and its `_guard` docstring, both mine),
`tests/test_c14_live_already_spent_source.py` and the new
`tests/test_inv_a7_probe_durable.py`.
`experiments/ad01/live_construct.py` needed no change: `_DurableBrokerOutput`
in `scripts/invl02_live.py` is the adapter the probe needed, and A1's
`_DurablePreflightGateway` was the pattern to copy rather than a second
durable wrapper to add.
