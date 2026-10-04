# CI run 37228382802: shards 2, 3 and heavy

The second triage lane. Shard py3.13-1 was triaged by an earlier lane
(e86cea5, a17d881); this covers what it did not.

throughput checkpoint: 2 fixes committed, 4 escalated, coverage gap measured.

## Method, and why the number validates it

The baseline was re-derived from run 37172638343's own artifacts, not from
any summary document. `FAILED <id> - <msg>` and `ERROR <id> - <msg>` lines
were read from every file in every artifact directory of both runs, and the
id sets compared.

Baseline distinct ids: **259** (245 FAILED + 8 ERROR from shard 3 + 6 ERROR
from heavy). This matches the count the shard-1 lane validated, which is what
makes the comparison trustworthy rather than merely plausible.

Full untruncated failure strings were compared, not ids. Of the 259 ids
present in both runs, **0** had a changed failure string. Every shared id is
byte-identical. So no shared failure was re-dressed.

Shard membership held exactly: **0** ids changed shard between the two runs.
No in-baseline failure is a re-sharded test in new clothes.

Run 37228382802 distinct ids: **277** (263 FAILED + 14 ERROR).

| | count |
|---|---|
| IN_BASELINE (byte-identical, same shard) | 259 |
| Not in baseline at all | 18 |
| In both, failure string changed | 0 |
| Moved shard | 0 |

The 18 are 12 already repaired at HEAD by shard-1 triage and 6 that are open.
Every one of the 18 is absent from the baseline entirely, which is expected:
the baseline was taken before this batch, so anything this batch broke is new
by construction. The claim that matters is the reverse direction, and it holds
cleanly: nothing in the 259 moved.

## Per shard

| shard | distinct ids | IN_BASELINE | new | notes |
|---|---|---|---|---|
| py3.13-1 | 31 | 23 | 8 | triaged by the earlier lane, all 8 now fixed |
| py3.13-2 | 60 | 52 | 8 | 4 fixed, 4 open |
| py3.13-3 | 113 | 111 | 2 | both open, both 0bc02d3 |
| heavy-archived | 73 | 73 | 0 | fully baseline |
| py3.13-4 | 0 | 0 | 0 | CANCELLED, UNMEASURED |
| py3.12 / py3.13 / py3.14 | 0 | 0 | 0 | CANCELLED, UNMEASURED |

heavy-archived contributed 67 FAILED and 6 ERROR, all 73 byte-identical to the
baseline. Nothing in it is this batch's.

## UNMEASURED. Not a pass.

Four of seven shards were cancelled at the 100-minute timeout and produced no
`failures.txt` and no `FAILED`/`ERROR` lines. They are recorded as unmeasured,
never as green.

| shard | tests executed | progress reached | F observed |
|---|---|---|---|
| py3.12 | 3240 | 76% | 198 |
| py3.13 | 3240 | 76% | 198 |
| py3.14 | 3240 | 76% | 198 |
| py3.13-4 | 144 | 18% | 2 |

Those 3240-progress-char shards are three interpreter runs of the same
`--splits` set and their progress is identical, which is consistent with one
split plan replayed per version rather than three independent measurements.

The baseline run cancelled the same four shards at the same points, so the
unmeasured region is the same region in both. That is why the 259 reproduces:
it is derived entirely from the three shards that did complete. The cost is
that roughly a quarter of coverage has no verdict in either run, and no
comparison here can say anything about it. The F count in those shards grew
180 to 198 between runs, which is suggestive of this batch's effect, but with
no test identity attached to those 18 additional F characters there is
nothing to attribute them to. Recording that as evidence of anything would be
reading a number as a cause.

Shard 4 reached 18% and had already produced 2 F. Those two are unmeasured for
the same reason: cancelled before pytest wrote the summary.

## The 18, classified

Fixed at HEAD by the shard-1 lane (12):

- test_bdr01_host_boundary (2), test_evidence_integrity (6),
  test_inv_c7_two_domain (4). e86cea5 and a17d881.

Open, fixed here (2):

- **tests/test_mission_entry.py::test_mission_fields_is_exactly_what_is_written**
  `TypeError: record_mission() missing 1 required positional argument: 'dsn'`.
  Introduced by 2fcc217. The test asserts that `record_mission` refuses a
  field name outside `MISSION_FIELDS`, but it called the function as
  `record_mission(store=None, investigation_id=...)`. The first parameter has
  been named `dsn` since 8e06980, so `store=` never bound and the call died at
  the signature. The refusal this test exists to prove was never reached.
  Fixed by passing the fixture dsn positionally, so the call reaches
  `_validate` and refuses on the field name. Confirmed by running
  `mission._validate` directly: it raises `MissionRefused: unknown mission
  field: retained_use`. The sibling case in test_mission_join_repair.py:36 was
  migrated correctly by the same commit and still passes; this one was missed.

- **tests/test_inv_r1_authored_control.py::test_an_authored_control_member_executes_under_the_child_contract**
  `KeyError: 'fault'`. 7ac77bb/0604164 stopped copying the fault into the
  candidate in `software_atoms.build`. The test asserted the copy as intended
  behaviour. The commit message names this line as expected red, so it was
  known and left. Fixed by asserting the property the seam exists for: the
  answer is absent from the candidate. Verified against the real frozen task
  that the candidate keys are exactly `family`, `ops`, `task_id`, so
  `"fault" not in candidate` and `"seed" not in candidate` hold. The
  behavioural assertions in the same test were not touched; `len(ops)` is still
  asserted at 8.

Open, escalated, not fixed here (4):

- **tests/test_r123_gates.py::test_r1_driver_routes_through_frontier**
- **tests/test_r123_gates.py::test_r1_live_improver_via_doubles**
- **tests/test_invl02_causality.py::test_p2_frontier_construction_prompt_contains_permitted_history**
- **tests/test_invl02_causality.py::test_route_metadata_must_match_before_e0_retention**

These are the 0bc02d3 group. All four raise the same refusal from the same
line, confirmed from the run's own tracebacks:
`scripts/invl02_live.py:1973` → `live_construct.py:1368` →
`improve_channel.py:2248`.

The fix is a design decision and is specified below rather than chosen here.

## 0bc02d3 settled, with a confirmed code path

The refusal is reachable and the path is confirmed from the run's tracebacks,
not inferred. `_run_frontier_investigation` calls
`_live.run_live_improve_round(store, task, active, 1)` at
`scripts/invl02_live.py:1973` with no `authority`. `run_live_improve_round`
forwards `authority=authority` (default `None`) to
`drive_improve_round`, which raises when `authority is None` and
`store.identity is not None`. The store is an `ensure_live_store` store opened
with `dsn=` and `investigation_id=`, so it names an owner. The refusal is
reached.

Why this batch could not simply supply the authority, and why that is the
decision to make:

1. `drive_improve_round`'s docstring and 0bc02d3 both record that the
   operation id this round mints carried neither arm nor investigation, so
   every arm binding the deterministic `make_control("low")` minted an
   identical id for the same step, and under one shared allocation the second
   arm read the first arm's settled receipt instead of executing. **That
   blocker is now gone**: 8e63b0e and 0d23ee2 name the investigation and the
   arm in the round's operation id, and it reads
   `invl02-improve-<investigation>-<arm>-<digest>-r<n>-s<k>` at
   improve_channel.py:2311. The precondition the lane recorded as missing has
   been met by a later commit in this same batch. This is the fact that makes
   the escalation resolvable now rather than before.

2. The driver holds `allocation_id` but not the `{dsn, allocation_id}` pair
   the round needs. `authorize_campaign` returns `study_root`,
   `allocation_id`, `authorized` and `store_fingerprint`, and no dsn, so
   forwarding is a one-line change at the two call sites but a change of what
   the driver claims to hold.

3. The round's executions would then settle against the E0 study allocation
   whose ceiling sheet is `{"model_calls": ..., "construction_calls": 4}`.
   `sandbox_calls` is not on it. `_check_study_ceilings` skips a ceiling whose
   counter is not spent by the operation, and `sandbox-exec` does spend
   `sandbox_calls`, so a round would be bounded only by `operations`, not by
   the sandbox bound `_disposable_authority` gave it. Whether to widen the
   study's cap sheet, or to accept that a live round is bounded by the
   allocation's own total, changes what the E0 grant authorizes. That is a
   research-budget question, not a code question.

4. `_run_frontier_investigation` is called from four sites: run_e0 (twice,
   control and live), run_e12 (twice, per arm and control). The control arm
   passes `guard=None` and still drives two rounds at lines 1973 and 1997. So
   the change lands on four call sites in the production driver, not one.

## The exact spec, for whoever decides

Decision required: should the production live path authorize the improve
round against the study allocation it already holds, and what bounds that
round?

Preconditions, all confirmed:
- The operation-identity blocker named by 0bc02d3 is cleared by 8e63b0e and
  0d23ee2. Operation ids now name the investigation and the arm.
- The driver holds a real `allocation_id` per arm.
- The store is owned, which is the condition that triggers the refusal.

Open choices, in the order they must be answered:
1. Thread `{dsn, allocation_id}` into `_run_frontier_investigation` and forward
   it to both `run_live_improve_round` calls, at all four call sites. Or keep
   the refusal and change the tests to assert it.
2. Bound the round. The disposable ledger bounded each execution in
   `sandbox_calls: 1000` against a database that dies with the round. A shared
   allocation is bounded by whatever its study's `ceilings` row declares, and
   E0's declares `model_calls` and `construction_calls` only. Either add
   `sandbox_calls` to the study's cap sheet or accept the allocation's
   `operations` ceiling as the only bound on a live round.
3. The control arm (`guard=None`) also drives two rounds per call. If only the
   live arm is authorized, the control arm keeps a disposable ledger on an
   owned store and must be exempted deliberately rather than by accident.

Option 1 is the smaller change and it is what the code is shaped for: the
refusal is the seam reporting a caller omission, and the omission is now
fillable. Option 2's second half is a change to what an E0 grant authorizes,
which is why it is escalated rather than implemented.

## What was not classified

Nothing in shards 2, 3 or heavy is unclassified. All 246 distinct ids across
those three shards carry a verdict: 236 IN_BASELINE byte-identical, 2 fixed
here, 6 fixed by the earlier lane, 2 escalated above.

The unclassified region is the four cancelled shards, which have no test
identity at all rather than an ambiguous one.

## Tests run

None. No pytest, no WSL. Classifications are from failure text plus the code
path read at HEAD. Every "confirmed" label above is a code path or a direct
call I ran; the `test_mission_entry` and `test_inv_r1_authored_control`
verdicts were confirmed by executing `_validate` and `software_atoms.build`
against the real frozen task. The claim that the four 0bc02d3 failures share
one path is confirmed from the run's own traceback frames, not inferred.