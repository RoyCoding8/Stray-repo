# Stage 09 structural failures

A structural failure is red because of how the fixture or module was built, not
because a product defect exists. It is worse than a guaranteed-green test,
because its red is a standing false alarm. Every engineer who learns to ignore
that file then misses a real failure in it.

The proof standard here is construction, not reproduction. "It fails" is already
known. A test belongs in the structural class only if the fixture cannot produce
the shape the assertion needs, whatever the product does. If a product change
makes it green, it is a real defect and it is listed in the second section
instead.

**The split: 8 rows structural, 5 rows real defects that look structural.** The
census's own two largest groups (G5a at 6 rows, G8 at 8 rows) split across that
line, and the census put both on the wrong side of it for the ones that matter.
Details in [Cross-check](#cross-check-of-the-catalogue).

## Confirmed structural

### S1. The five operator-UI rows are one fixture defect, not a UI defect

The census classified these **environmental**, on the grounds that the HTML
names "settlement operator", a different UI's content. That is factually wrong.
`api.py:29` sets `HERE = Path(__file__).resolve().parent.parent.parent`, which
resolves to the repo root, and `api.py:435` loads `HERE / "templates"`. That is
`/home/ubuntu/AI/Agent-Society-v2/templates/`, the ten real templates. There is
no second UI. `src/settlement/templates/` does not exist.

The real cause is in the `client` fixture, which is byte-identical in both
files and passes an incomplete call.

`tests/test_ui_views.py:20-22` and `tests/test_ui_commands.py:20-22`:

```python
store.acquire_work(dsn, _cmd({"attempt_id": "w1", "investigation_id": "i1",
                              "allocation_id": "a1"}))
store.prepare_operation(dsn, _cmd({"operation_id": "op1", "attempt_id": "w1",
                                   "operation": {"effect": "note"}}))
```

`acquire_work` binds `w1` to allocation `a1`, so the attempt carries an
`allocation_id`. `store.py:372-376` then refuses any `prepare_operation` that
does not pass it back:

```python
if allocation_id is None:
    raise ConflictPayload(f"attempt {attempt_id} requires its bound allocation")
```

The fixture never inspects the result, so `op1` is never created. Measured, on a
disposable database, replaying the fixture verbatim:

```
prepare_operation: ResultCode.INVALID_INPUT | detail: attempt w1 requires its bound allocation
operation_data(op1) is None: True
broker.read_operation(op1): None
GET / -> 200 | 'w1': True | 'op1': False
GET /operations/op1 -> 404
GET /investigations/i1 -> 200 | 'w1': True | 'op1': False
```

That is the whole failure. The tests assert that `op1` appears in the overview
and the investigation view and has a detail page. The fixture never made `op1`.

The one-line change, adding `"allocation_id": "a1"` to the `prepare_operation`
payload and changing nothing else:

```
prepare_operation WITH allocation_id: ResultCode.APPLIED
GET / -> 200 | w1: True | op1: True
  obligations: 1 -> True | capacity -> True | models unavailable -> True
GET /operations/op1 -> 200
GET /investigations/i1 -> 200 | w1: True | op1: True
  escaped script -> True | raw script absent -> True
GET /evidence -> 200 | &lt;script&gt; -> True
```

Every assertion in both files passes, including the escaping and the
no-mutation checks. The product was never involved.

Rows this clears, all five from the same cause:

| Row | File | Test |
|---|---|---|
| 85 | `tests/test_ui_views.py:38` | `test_overview_renders_from_durable_records_with_gateway_down` |
| 86 | `tests/test_ui_views.py:47` | `test_investigation_view_escapes_generated_content` |
| 87 | `tests/test_ui_views.py:72` | `test_gets_never_mutate_domain_state` |
| 100 | `tests/test_ui_commands.py:42` | `test_pause_resume_cancel_cycle_with_external_unknown` |
| 101 | `tests/test_ui_commands.py:52` | `test_cancel_forwards_to_gateway` |

Row 87 is the clearest instance of the class the coordinator described. The
failure message is `assert 404 == 200` on `GET /operations/op1`. That reads
like a missing route. The route exists at `api.py:475`. It 404s because
`operation_data` returns `None` for an operation the fixture never created, and
`api.py:479` turns that into a 404. Every route 404s identically for an
operation that does not exist, so the message cannot distinguish "the operator
UI lost this page" from "this test never built the thing it is looking at".

The census's own note for rows 100 and 101, that they share a cause with the UI
views rows, is right. Its reason for the cause is wrong.

I own the report, not the fix. Both files are in another lane's territory by
being live test files, so I have not edited them.

### S2. G5a, six rows, is a missing `advance_dispatch` and nothing else

`src/settlement/store.py:1780-1781`:

```python
raise SettlementError(f"operation {op['id']} was not dispatched")
```

The census read this as "a real design question: should the store refuse a
receipt for a prepared operation?", and ranked the six rows fourth because
answering it could invalidate the fix. The question is real, but it is not what
is making these tests red, and it does not need answering to make them green.

The store rule is correct and the tests are the thing that predates it. What
they share is a setup that calls `prepare_operation` and then files a receipt,
never dispatching in between. Measured across the three files:

| File | `prepare_operation` | `advance_dispatch` |
|---|---|---|
| `tests/test_settle_actual.py` | 4 | **0** |
| `tests/test_eng_close1.py` | 1 | **0** |
| `tests/test_inva_recovery.py` | 1 | 4 |
| `tests/test_state_operations.py` (passing) | several | 6 |

`test_state_operations.py` is the control. It dispatches, and it passes.

Reproduced on a disposable database with the census's exact call:

```
receipt on PREPARED op -> ResultCode.INVALID_INPUT | detail: operation op1 was not dispatched
ownership_generation: 1
advance_dispatch -> ResultCode.APPLIED operation op1 dispatching
receipt on DISPATCHED op -> ResultCode.APPLIED | settled: False
```

Two calls, the second of which is the one the tests omit, and the same
assertion passes. That is the definition of a fixture defect, and it is the same
shape as S1: a setup that stops one step short of the state the assertion reads.

`test_inva_recovery.py` is the odd one out. It does dispatch, but it prepares
two operations and dispatches only `inva-r-op1` (`tests/test_inva_recovery.py:36`).
The failing leg is the replay against `op2`. Same cause, one operation further
on.

**Why the census's "read the exception" instruction would not have found it.**
The census notes that `transact` puts the message in `result.detail` and the
tests never read it, so all nine G5 rows read identically. True, and the useful
conclusion is the opposite of the one drawn. Reading `result.detail` in a probe
is what names the cause in one line, and the probe is twenty seconds on a
disposable database. The census treated the swallowed message as the reason
grouping by exception was hard. It is the reason the cause was cheap to find.

## Real defects that look structural

Listed so nobody re-derives them as structural.

### R1. G8, the pilot `unavailable` rows, is a product budget, not a fixture

The census called this "a pre-existing product defect, one cause behind several
assertions" and said "the origin the log does not show". It is one cause and it
is short. Measured by instrumenting `run_study` on a disposable database:

```
--- P1: status=unavailable disposition=unavailable calls=0
    reason='policy constructor unavailable: construction call not admitted:
            study s09-m5-pilot-o1 ceiling construction_calls=4 reached at 4'
--- P2: status=unavailable disposition=unavailable calls=0
    reason='policy constructor unavailable: construction call not admitted:
            study s09-m5-pilot-o1 ceiling construction_calls=4 reached at 4'
```

The budget is gone before either arm is constructed. Every construction
operation in the study:

```
ad01-ad01-w0-I-50-o1-b0-ad01-w0-dev-sw-00-construct-l1-init
ad01-ad01-w0-I-51-o1-b0-ad01-w0-dev-sw-01-construct-l1-init
ad01-ad01-w0-I-52-o1-b0-ad01-w0-dev-gr-00-construct-l1-init
ad01-ad01-w0-I-53-o1-b0-ad01-w0-dev-gr-01-construct-l1-init
```

All four are the development phase. `DEV_SPECS` (`scripts/s09_pilot.py:260`) has
four entries and `run_study` runs all four before it reaches `_construct_arm`
at `scripts/s09_pilot.py:1132`. `CONSTRUCTION_CALLS = 4`
(`scripts/s09_pilot.py:45`) is consumed by the dev phase, and the two arms that
the six assertions are about get none.

This is not structural, because a product change fixes it. Raising the one
constant and changing nothing else:

```
BEFORE: CONSTRUCTION_CALLS = 4
  P1: status=available calls=1 reason=''
  P2: status=available calls=1 reason=''
  report.complete: True
```

A product change makes it green, so it is a real defect. The design question,
which is the one worth asking, is whether a study-level construction ceiling
should be spent by a phase that is not the one the ceiling names. A per-phase
budget, or counting only the operations under the construction arms, would both
do it. That is a decision, not a repair.

Rows: 48-52 (`test_s09o_pilot.py`, 6 rows in the file, 5 in the census) and 125
(`test_s09m5_pilot.py`). `test_s09m5_pilot.py` shares the cause, confirmed
separately, since its fixture passes no gateway and takes the doubles path:

```
  P1: status=unavailable reason='policy constructor unavailable: construction
       call not admitted: study s09-m5-pilot-m5a cei'
  P2: status=unavailable reason='... same ...'
```

and 124 (`test_s09c3_policy_pilot.py`, `assert False`).

The census is right that these are one cause. It is one cause, and it is in
`scripts/s09_pilot.py`, not in any test file.

### R2. G6, `record_expenditure` without `operation_id`, is a caller update

Five rows across three files. `src/settlement/trials.py:209`:

```python
if not isinstance(operation_id, str) or not operation_id.strip():
    raise SettlementError("expenditure requires a durable operation_id")
```

The signature takes `operation_id` as keyword-only with a default of `""`, and
the guard refuses the default. The five callers pass none. This is a rule newer
than its callers. Mechanical, five independent files, no shared state. The
census's assessment is correct and nothing here contradicts it.

### R3. G5c is a contract contradiction and cannot be fixed without a decision

`src/settlement/broker.py:262-267` returns, without raising:

```python
if retries != 0:
    return CommandResult(code=ResultCode.INVALID_INPUT,
                         detail="retries must be zero; use distinct operation identities",
                         data={})
```

`tests/test_broker_prepare.py:51` passes `retries=2` and asserts
`result.data["exposure"] == 51`, which requires the broker to multiply exposure
by `retries + 1`. The same file's `_sandbox_exposure` helper still does that
multiply. Two assertions in one file cannot both hold, and no reading of the
code settles which is right.

This is structural in the weak sense that the test is red for a reason
unrelated to any defect. It is not in the structural class, because it needs a
decision, not a fixture edit, and a decision is not a repair. The census is
right to single it out.

### R4. G5b is a test passing an incomplete call

`tests/test_steward_leases.py:26` acquires with `allocation_id="a1"`, then
`tests/test_steward_leases.py:41` calls `prepare_operation` with only
`operation_id` and `attempt_id`. Same omission as S1 and S2, same one-line
shape. The store is refusing a genuinely inconsistent call. The census is
right that the test is the thing that is wrong.

### R5. G1 and G2, the conninfo rows, are already fixed

`9493f12` and `6fb883d`. Not re-verified by this lane, which does not re-run
suites. Listed so the next reader does not re-derive them. The census's own
counting note stands: G2's two rows sit inside G1's 29 and the exception class
cannot separate them.

## Cross-check of the catalogue

Every group and singleton in `reports/STAGE-09-FAILURE-CENSUS.md` that could
belong to this class, with the verdict and the evidence.

| Group | Rows | Verdict | Basis |
|---|---|---|---|
| G5a | 6 | **structural** | S2. Missing `advance_dispatch`; measured, two calls, green on the second. |
| G5b | 1 | **real defect, test at fault** | R4. Incomplete `prepare_operation`. |
| G5c | 2 | **contract contradiction** | R3. Needs a decision. |
| G6 | 5 | **real defect, mechanical** | R2. Rule newer than callers. |
| G8 | 8 | **real defect, product** | R1. `CONSTRUCTION_CALLS` spent by the dev phase. |
| G9 | 5 | environmental, not structural | Missing worktree at an absolute path. Not this class. |
| G10 | 6 | neither | Cannot-fail, already catalogued and owned. |
| UI views and commands | 5 | **structural** | S1. One fixture, five rows. |
| G1, G2 | 31 | already fixed | R5. |
| G3 | 0 in log | already fixed | `060d223`. Not re-verified. |
| G4 | 10 | environmental | Hardcoded dbname. Not this class. |
| G7 | 10 | already fixed | `060d223`, in this branch. |
| row 105, `test_conftest_isolation` | 1 | **already fixed** | See below. |
| row 109, `test_invc3_export` | 1 | not classified | Needs a probe I did not run. |
| row 110, `test_invc3_study` | 1 | real, not structural | See below. |
| row 123, `test_s09_test_db_safety` | 1 | **true positive** | See below. |

### Row 105 was already fixed, and the census is stale on it

The census records `KeyError: 'ec02test_bauth'` and marks it "fixed by
`060d223`". Measured at HEAD: `tests/test_conftest_isolation.py` is **14 passed
in 36.05s**. The assertion was not merely repaired, it was replaced with a
better one, and the file documents why at lines 268-274: the old line required
`ec02test_bauth` to be blocked by a substring check, no test file ever compared
a dbname against that name, so the seam was redirectable and always had been.
That is a shape from the census's own list, found and fixed inside the file the
census was counting.

### Row 123 is a true positive, and the assertion around it is still unfalsifiable

The census is right on both counts, and they are different findings. The finding
is real. Running the census module directly:

```
test_c14_live_already_spent_source.py: ['ad01-campaign-invl02-live-e0', 'ad01-campaign-some-other-study']
test_s09_test_db_safety.py:          ['s09o_pilot_full', 's09o_pilot_rerun_a', 's09o_pilot_rerun_b']
```

`tests/test_c14_live_already_spent_source.py:185` is a genuine
`DROP DATABASE IF EXISTS`. The other lane owns this file and the fix.

The assertion around it is still `HAZARD_CEILING = 0`, still the only shape in
this class the sweep found, and still cannot move in the direction the docstring
claims to care about. Noted, not actioned.

### Row 110 is a real failure, not structural

`tests/test_invc3_study.py:74`, `assert False` over a generator. Confirmed
present at HEAD (1 failed, 2 passed in 28.78s). The assertion reads a real
computed value, so it is not a constant pin. Not classified further.

## The sweep

Classes checked across `tests/`, and what each found.

**A slice, head, or first element applied before an equality check.** 465
matches on a naive `assert` plus index regex. The overwhelming majority are
`assert records[0]["x"] == "literal"`, which is sound, and `assert X[0] == 51`,
which is a pin. Two are worth naming.
`tests/test_s09_swe_experiment.py:202` is the census's sixth, confirmed below.
`tests/test_s09_swe_experiment.py:96` is
`assert [turn["action"] for turn in first["trace"]][:1] == ...`, a real `[:1]`
before a comparison, but the trace is asserted separately and this reads as a
deliberate first-turn check. Not proven, so not claimed.

**A constant compared against itself, or a ceiling defined as 0.** Two hits.
`tests/test_s09_test_db_safety.py:34`, `HAZARD_CEILING = 0`, the known one.
`tests/test_s0_manifest.py:66`, `assert manifest.build_manifest() == manifest.build_manifest()`,
which is the shape by form. **Cleared, and it can fail.** Probed by making
`postgres_version` return a varying value:

```
nondeterministic manifest detected by the test: True
constant-returning manifest, test still passes: True
```

`build_manifest` (`scripts/manifest.py:51`) rebuilds every field on each call
and holds no cache, so the two calls are genuinely independent. The test
detects a real defect. The self-comparison is a legitimate determinism check,
not a tautology.

**`assert x is x` or a value compared to a variable assigned from it.** Zero
hits beyond the one above.

**A module constant in the test that contradicts a changed product default.**
One: R1, `CONSTRUCTION_CALLS`.

**An assertion over a collection empty because an upstream filter returned
nothing.** Two. R1, where the filter is the study authority's ceiling, and
`tests/test_s09o_pilot.py:231`, `assert 0 == 2` on prompts the provider never
saw, which is the same ceiling seen from the request side.

**A test depending on a sibling having run first.** 29 module-scoped fixtures
shared across tests. Cleared as a class. The pattern is deliberate and
consistent: one study or one store, many assertions over it. A module-scoped
fixture makes ordering irrelevant, which is the opposite of the failure mode
being looked for. The risk is a test that mutates the shared fixture, which is a
different defect and did not appear.

**A count or set equality over a glob or a directory listing.** Cleared. The
only two are owned by another lane, and the census is right that one of them is
a 96-filename snapshot and the other a `HAZARD_CEILING`. The rest iterate
results and assert per item.

**A test that only passes in a specific working directory or with a specific
env var.** Zero `os.chdir` in `tests/`. The env-gate class is two
`xfail(strict=True)` decorators, `test_s09c1_continuity.py:393` and
`test_team_solver.py:318`, both carrying a reason string. No bare
`skipif`, no `importorskip`, no unmarked skip in the tree.

**A test whose body cannot reach its assertion.** An AST walk over every test
function for a `return`, `raise`, `continue`, or `break` preceding an
assertion in the same block. Zero hits.

**A fixture that builds the artifact when the real artifact exists.** No
instance found beyond S1, where the fixture fails to build the artifact at all.

**Tests reading their own source text.** Four files read `__file__`:
`test_ag01_policy.py`, `test_json_repair.py`, `test_m4_offline_recompute.py`,
`test_r123_gates.py`. Not read individually. Two commits in the last twenty,
`58f1d38` and `ff22d77`, are about gates that stopped reading text, so this class
has an owner. Flagged, not claimed.

## What I could not settle

**Row 109, `test_invc3_export.py`**, `{'checked': 4, 'problems':
['use-without-retained ad01-w0-I-13-I-ad01-w0-dev-sw-00']}`. Reads a real
computed value. Not structural on its face and not probed. A sibling memory,
`verified-entry-vs-executed-bytes`, describes a seed-id collision that makes a
use record name bytes that never ran, which is the shape this message has. That
is a lead, not a finding, and I did not confirm it.

**The four source-text assertion files.** Named above, not read. Another lane
appears to own that class.

**Row 124, `test_s09c3_policy_pilot.py`**, grouped with R1 on the strength of
the shared `assert False` and the shared pilot lineage. Not run. G8's mechanism
is confirmed in `test_s09o_pilot.py` and `test_s09m5_pilot.py`; this one is
inferred.

## Method, and its limits

Every claim marked measured came from a disposable database, named per run,
migrated from `migrations/`, and dropped after. No database was hardcoded and
every one created was destroyed. Three databases were created and dropped; the
run log line `S09ISO: dropped 36 database(s) for this run` belongs to the
project's own isolation fixture, not to mine.

Each test I claim is structurally broken was confirmed to have executed. Every
file reported here was run at HEAD with `--timeout` set:
`test_ui_views.py` 3 failed / 3 passed, `test_s09o_pilot.py` 6 failed / 3 passed,
`test_conftest_isolation.py` 14 passed, `test_invc3_study.py` 1 failed / 2
passed.

`tests/test_s09_swe_experiment.py` was collected, never run, per instruction.
Its census entry is confirmed by construction instead: `supported_lineages()`
returns four lineages, all `representation_kind == "python-step"`, and
`paired_comparisons` emits a pair only when the two sides differ in kind.

```
supported_lineages kinds: {'python-step'} count: 4
[:1] kinds: {'python-step'}
pairs from two same-kind rows: []
pairs across two kinds: 1
=> a [:1] slice of supported_lineages() can only ever yield 0 pairs
```

No test was edited. Two files need one line each and are not mine to touch.
