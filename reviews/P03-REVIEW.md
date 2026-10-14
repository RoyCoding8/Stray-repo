# Independent P03 review

**Final verdict: clear at the reviewed scope.** Independently revalidated actual
main source `0800a14c8461634c5b3e02d8e8142911baccbc61`. The unchanged retained
nine-cell baseline passed. All six altered-data controls were rejected, and both
usage controls passed. No material findings remain open within this review.
No live comparison, whole-repository, CI, or deployment result is inferred.

The original application review covered
`9844d876e8192dd955b3db2606e6f38328cda0e0` against `dafb7624`. Intermediate repair
`a72ccfac9f935658527bf9499deeda845ff384d3` fixed the original counterexamples but
retained two R2 omissions. Both are repaired in the final source. Application
source remained read-only throughout this independent review.

## Review tasks

- [x] Read the component contract, master plan, ledger, assignment, and source diff.
- [x] Trace packet identity through P01 admission, pending resume, and episode rendering.
- [x] Run the real PostgreSQL and fixture-child consumer acceptance tests.
- [x] Test new-packet withdrawal and adaptive feedback with independent source observations.
- [x] Retain an independent nine-cell fixture baseline and challenge its offline recomputation.
- [x] Record the findings on the reviewed implementation source.
- [x] Verify repairs against the actual merged application revision.

## Historical findings on the original source

The original verdict requested changes before the live comparison. Two
independently reproduced P2 findings concerned the offline evidence boundary,
rather than packet construction.

1. **Bind cell source hashes to the prospective manifest.**
   `experiments/context03/recompute.py:283` reads each cell's source hashes and
   checks agreement across cells. It never compares these hashes or the driver
   hash with the prospective manifest. Against the unchanged passing nine-cell
   baseline, replace only `manifest.source_sha256['src/rsi/context.py']` with
   64 zeroes. Recomputation accepts the mismatch. The live coordinator's runtime
   source check is useful, but does not make the independent offline archive
   check verify the prospective freeze. Compare the exported source and driver
   hashes against that manifest. Do not require equal Git revision labels when
   the freeze itself is committed after the manifest is prepared.

2. **Check grading consistency before calculating task quality.**
   `experiments/context03/recompute.py:341` takes the grading boolean directly
   from `state.last_observation`. Against the unchanged passing baseline, change
   only the first complete cell's `state.last_observation.passed` from `true` to
   `false`. Keep its attempt observation, decision, packet, invocation, operations,
   and receipts unchanged. Recomputation accepts the contradiction and changes
   `verified_quality_rate` from `1.0` to `0.8333333333333334`. Check the state's
   final observation against the exported observation and its decision and
   verifier association before using it to grade the cell.

These findings do not claim cryptographic authenticity of exported responses.
They identify concrete internal consistency checks required to bind the result
to its declared frozen campaign and recorded outcome.

## Merged repair revalidation

Final revalidation read repair `a4fa9277`, confirmed main revision `0800a14c`,
and loaded the application from main through `PYTHONPATH`. The retained-baseline
audit passed with exit code 0 in 3.40 seconds. It rejected a mismatched prospective
source pin, a changed state grade, an erased state observation, a Boolean grade
without a verifier reference, an actually disconnected rendered instruction,
and a changed packet. Unknown worker usage stayed unknown. Unrelated receipt
costs did not change worker token totals. The valid source-removed cells remained
accepted as refusals, with no observation or dispatch. No workers or database
effects were rerun. The final log is
`D:/AI/tools/p03/sol-review/offline-0800a14c.log`.

The following records the intermediate repair and its remaining omissions.

Read repair `cd8cd5e9` and independently loaded the actual main source at
`a72ccfac`. Reused the preserved nine-cell baseline without workers or database
effects. The unchanged baseline passed, both original findings were rejected,
instruction and packet mutations were rejected, unknown usage stayed unknown,
and unrelated receipt costs did not change worker token totals. The original
six controls passed with exit code 0.

Two requested narrow checks show that R2 is incomplete on this revision.

- Delete only the structured-complete cell's `state.last_observation`, leaving
  its completed `attempt_observations` unchanged. Recomputation accepts it,
  reports the cell's grade as `null`, and changes the connected passing baseline
  flag to `false`. The early return in `_verify_last_observation` must not discard
  a retained completed outcome when the state copy is absent.
- Delete `verdict` from both the state observation and matching attempt
  observation, retaining `passed: true` and all exported operations and receipts.
  Recomputation accepts the Boolean grade and still reports quality `1.0`.
  A Boolean grade requires its explicit verifier-operation association. An
  unknown, ungraded result may legitimately lack that association.

Both cases concern missing outcome-consistency checks within R2. They do not
require proving response authenticity. The expanded audit returns exit code 2
on `a72ccfac`. Its log is
`D:/AI/tools/p03/sol-review/offline-a72ccfac-omissions.log`.

## Independently verified behavior

The seven consumer acceptance tests passed, with no skips, in 125.97 seconds.
Their passing baseline consumed the selected support and opposition in a stored
decision, broker instruction, and actual fixture-child input. The disconnected
case failed the pristine task while retaining its admitted packet. The tests
also checked swapped packets, stripped packets, changed selected bytes,
information needs without dispatch, fresh-process resume, and the complete
canonical UTF-8 continuation limit.

Two reviewer-authored tests and the inherited legacy restart test passed,
with no skips, in 107.80 seconds. A selected lesson withdrawn after P03 admission
blocked dispatch, preserved the exact pending operation, and produced no child
call. Separately created source observations `maximum alpha` and `maximum beta`
changed the second adaptive inspection under the same two-action allocation.
The alpha branch retained the literal follow-up excerpt `alpha bears the zero
default`; the beta branch did not. Both packets validated against their actual
P02 originals.

The legacy adapter has a different, inherited contract. A pre-P03 pending decision
reuses its exact saved memory snapshot after withdrawal, provided its original
bytes remain valid. The original `dafb7624` consumer and its existing restart test
already behaved this way. New P03 packets check current claim eligibility.
This compatibility behavior is not a newly selected withdrawn claim.

The retained independent nine-cell fixture comparison completed all nine cells.
Six workers dispatched, all six passed their pristine task, and all three
source-removal cells refused before dispatch. The connected structured-complete
baseline passed. Recomputation totaled 5,160 tokens reported by fixtures and zero
unknown worker-usage operations. Replacing one worker's receipt token data with
`null`, consistently in the invocation and accounting exports, retained unknown
usage and made the total `null`. The two altered-data controls above were accepted
on the reviewed source; they are failed sensitivity checks, not passing gates.
Removing the packet from the actual rendered instruction while recomputing that
instruction's byte count and hash was rejected. Removing observations from the
packet was also rejected. These controls show that the original checker has
sensitivity at the packet and invocation boundaries, but not at the two findings.
Setting every exported receipt's `actual_cost` to 3,000, including verifier
receipts, left the fixture worker token total at 5,160 and produced no aggregate
actual-cost field. CPU and model cost figures were not added to worker tokens.

## Scope and evidence limits

The reviewer read the packet builder and validator, P01 consumer, episode
renderer, comparison driver, offline recomputation, relevant P02 resolution,
and the private live coordinator. The private coordinator was read-only.
Its SHA-256 was
`85f5a6be50808e41c9f61b329966d7d606e3f68271fa3e58b70d1a528ad39fb5`.

The coordinator creates one fresh database per cell, executes the fixed nine-cell
order, and aborts on existing databases or errors. The driver permits six live
worker invocations across the complete and misleading cells. Each has one
decision, a 180-second worker timeout, a finite token allowance, the free router
alias, and zero request or stream retries. Source-removed cells require the
missing opposition source and refuse before dispatch. The stated bound counts
worker invocations, not provider HTTP turns or an invoice ceiling. No live,
gateway, Jev, paid-model, or untrusted candidate execution ran in this review.

The policies and lessons are authored. Fixture behavior qualifies mechanics.
It does not establish live utility, a policy advantage, capability acquisition,
transfer, or learning. Inspection counts concern logical bounded operations over
P02-resolved strings. They do not account for all physical reads or cumulative
work across interrupted uncached builds. The review does not qualify hostile
filesystem or network containment, the whole repository, CI, or deployment.

## Reproduction

Run in the review checkout with the existing repository interpreter.
The test isolation harness creates and drops only its own databases.

```powershell
$env:PYTHONPATH='D:/AI/Agent-Society-v2/.worktrees/p03-review/src;D:/AI/Agent-Society-v2/.worktrees/p03-review/tests;D:/AI/Agent-Society-v2/.worktrees/p03-review'
$env:SETTLEMENT_TEST_DSN='dbname=postgres host=127.0.0.1 port=55432 user=postgres'
$env:S09ISO_ADMIN_DSN=$env:SETTLEMENT_TEST_DSN
$env:SETTLEMENT_REQUIRE_TEST_DB='1'
$env:PATH='D:/AI/tools/pgsql/bin;'+$env:PATH
$env:S09ISO_TOKEN='e374a56b'
& D:/AI/Agent-Society-v2/.venv/Scripts/python.exe -m pytest tests/test_rsi_context_integration.py -q --basetemp=D:/AI/tools/p03/sol-tmp
$env:S09ISO_TOKEN='fe4a57dc'
& D:/AI/Agent-Society-v2/.venv/Scripts/python.exe -m pytest tests/test_p03_review.py tests/test_rsi_memory_integration.py::test_p02_c_and_e_pending_replay_keeps_withdrawn_lesson_snapshot_after_restart -q --basetemp=D:/AI/tools/p03/sol-own-tmp
& D:/AI/Agent-Society-v2/.venv/Scripts/python.exe -u reviews/p03_offline_probe.py fixture --root D:/AI/tools/p03/sol-review/fixture
& D:/AI/Agent-Society-v2/.venv/Scripts/python.exe -u reviews/p03_offline_probe.py audit --root D:/AI/tools/p03/sol-review/fixture
```

For the merged-source audit, set `PYTHONPATH` to
`D:/AI/Agent-Society-v2/src;D:/AI/Agent-Society-v2/tests;D:/AI/Agent-Society-v2`
and invoke the script from the review checkout. This imports the actual main
application while keeping the reviewer artifacts in the isolated worktree.

Private logs are `D:/AI/tools/p03/sol-review/consumer-gate.log`,
`own-probes.log`, and `fixture-gate.log`. The retained fixture archive contains
each cell's freeze, exported decision, packet, broker instruction, actual child
input, operations, and receipts. An `audit` rerun uses these exports without
creating databases or running workers. The negative-control script returns exit
code 2 if altered data is accepted. Python compilation and `git diff --check`
passed for the reviewer artifacts. Ruff was unavailable in the repository
interpreter, so no Ruff pass is claimed.
