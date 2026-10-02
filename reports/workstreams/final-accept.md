# Lane FINAL-ACCEPT — independent acceptance over the merged tip

Branch `wt/final-accept`, base `b2a60e5c3e9b115e1a7e9ec2e7066142d8f2adac`
(`Merge lane DECOY-FIX: repair the decoy's justification rather than remove
it`).

I authored none of this work. I edited no tracked file, committed nothing,
pushed nothing, and merged nothing. This report is the only file I created.
Every finding below is either a measurement I made or a quotation with a
path. Anything I could not determine is in its own section at the end and is
not counted as a finding.

---

## Verdict summary

| milestone | verdict | one line |
|---|---|---|
| A — causal path, freeze half (X3) | **not established** | the guard's hole is genuinely narrowed and the deleted backstop promise is honest, but the guard has no production caller and three admitted write forms survive it |
| A — causal path, causal half (X4b) | **established, with a stated limit** | `effect_id` now names a real settled `operations` row; I reproduced the round trip and probed the filter's edges |
| B — informative comparison | **honestly recorded, with two overstatements and one missing caveat** | the negatives are stated correctly in the ledger, matrix, roadmap and bottleneck documents; two live files still overstate |
| C — inherited learning and Stage 10 | **not established** | the inheritable construction procedure is real, but the acquisition gate has a vacuous third control, the live gate does not consult the freeze, and the ledger says a lane ran that has evidence on this tree |

The honest outcome of this pass is three "not established" and one
"established". None of the four is refuted.

---

## The governing constraint, and what it does to every verdict

`reports/workstreams/bottlenecks.md` records that the design supplies one
independent unit of variation per structure, so every contrast above
acquisition is n=1 regardless of row count. I confirmed the mechanism in
source rather than taking it on trust.

`experiments/ad01/boolean_rule.py:228-233`:

```python
def _class_descriptor(self) -> dict:
    return {"form": instrument_spec(
        self._task["split"])["form"],
        "n_inputs": N_INPUTS, "n_outputs": N_OUTPUTS,
        "class_digest": class_digest(),
        "class_size": len(CLASS_TABLES)}
```

`class_digest()` at `:76-78` hashes `CLASS_TABLES`, a single global constant,
and `instrument_spec` returns a `form` that does not vary by split. The
descriptor is therefore byte-identical across every task, while the 72 hidden
tables differ. The tasks differ; the class does not, and it is a published
constant carried by construction, so no panel choice over the existing tasks
moves it.

Consequence for this pass: a negative disposition obtained at n=1 is not weak
evidence, it is a statement about the one structure measured. I apply that
below rather than treating the row counts as strength.

---

## Milestone A, freeze half (X3) — NOT ESTABLISHED

### What is genuinely repaired

Two things, both verified by reading the code.

The enforced freeze no longer matches only `ast.Assign` and `ast.AugAssign`.
`experiments/ad01/improve_channel.py:1319-1341` walks the parse and asks which
nodes carry a `Store` or `Del` context, which is the language's own answer
rather than a hand-kept enumeration. The dead `_frozen_key` helper is gone
from the module; its only surviving mentions are in tests that name what was
deleted (`tests/test_inv_x3_freeze_methods.py:13,488`,
`tests/test_r_final_freeze_and_chain.py:144`).

The deleted runtime backstop is not papered over.
`_frozen_write_reason`'s docstring at `:1274-1280` says the deferral was
removed because the comparison "cannot fire", and `X3`'s own test
`test_no_surviving_comment_promises_a_runtime_backstop_that_cannot_fire`
asserts no docstring defers to it. That is the honest form of the repair and
I credit it.

### Finding A1 (most serious in this pass): the freeze has no production caller

`admit_revision_under_freeze` is the only entry that reaches
`_frozen_write_reason`. I mapped the call graph with an AST walk rather than
grepping names (`experiments/ad01/learner_revision.py:560` is the sole
non-test call, and `learner_revision.acquire` itself has no non-test caller).
Result:

```
_frozen_write_reason   called by: admit_revision_under_freeze, _attempts_frozen_write
admit_revision_under_freeze  called by: NOTHING in the module
classify_revision     called by: admit_revision_under_freeze
```

The chain that actually executes a model's improver bytes is:

```
scripts/invl02_live.py:1987
  -> live_construct.parse_and_build_live_package
  -> live_construct._build_live_package   (live_construct.py:1160)
       -> method_exec.verify_step_source   <-- the ONLY gate
  -> live_construct.run_live_improve_round
  -> improve_channel.drive_improve_round -> run_improve_step -> _run_source
```

`run_improve_step` at `improve_channel.py:1912-1938` calls
`_frontier.validate_view` and then `_run_source` directly. It does not
reference `_frozen_write_reason`, `classify_revision`,
`admit_revision_under_freeze` or `_attempts_frozen_write` — I checked the
function's own source segment for each of those four names and all four are
absent.

I proved the consequence at runtime rather than by inference. I took the
exact bytes the X3 suite proves overwrite the grant
(`(view.update({"grant": ...}) or 3) if not view["experience"] else 8`, whose
execution the suite asserts lands in `test_the_smuggled_bytes_still_write_the_grant_when_executed`)
and pushed them through the real production entry:

```
A. _build_live_package           ACCEPTED the bytes
   package_digest: b87390e71670f465
B. _frozen_write_reason          view.update writes the frozen field 'grant'
C. verify_step_source            ACCEPTS the same bytes: confirmed
```

`verify_step_source` (`method_exec.py:1281-1311`) gates empty source,
unparseable Python, a missing entry function, entry arity, imports, dunder
access and forbidden calls. It has no frozen-write rule and no length rule.
So the live acquisition path admits bytes that the frozen-write guard
rejects.

This does not refute the X3 repair as a repair. The guard itself is real and
its hole is genuinely narrower than it was. What it refutes is any reading of
the freeze as an enforced property of the running system, which is how
`FINAL-ACCEPTANCE.md:23` describes it ("an enforced freeze"). On the live
path it is a function that tests call.

I could not test whether `invl02_live.py` has some other gate upstream of
`_build_live_package` that I did not find. I read that function and the module
around it; the only admission it performs is `verify_step_source`. A reader
who knows of such a gate should weigh this finding accordingly.

**Closed by lane FREEZE-WIRING, by measurement rather than by reading.** The
shipped improver path in `scripts/invl02_live.py` runs
`guard.infer(ModelRequest(...))` and then, at `:1987`,
`parse_and_build_live_package`. `LiveGuard` is documented as "a ceiling on
sends" (`live_construct.py:436-437`) and holds the route check, the cost block
and the evidence ledger — it inspects no source bytes, so it is not a source
gate. There is no further gate: `verify_step_source` is the only one. Probing
that exact function with a `STEP` entry that writes all six `FROZEN_FIELDS` by
subscript and through `view.update({"grant": ...})` returns **admitted**, while
the same bytes through `_frozen_write_reason` return
`writes view['grant'], a frozen field`. The live `IMPROVE` view carries none
of the six names, so there is no live frozen write to catch either. A1 stands,
and the guard is correctly dead rather than mis-wired.

### Finding A2: three write forms are admitted as `eligible`

I drove the public entry with revisions built from the real control template,
so each differs from the incumbent at the probed input and nowhere else, and
is eligible on every axis except the one under test. For each case I asserted
two independent things, following the X3 suite's own discipline: that the
bytes actually clobber the frozen grant when executed as the bounded child
executes them, and what admission says.

```
case                           grant       admission                detail
BASELINE view.update literal   CLOBBERED   mutates-frozen-field     (correctly refused)
comprehension __setitem__      CLOBBERED   mutates-frozen-field     (correctly refused)
for-target alias clear         CLOBBERED   eligible                 grant REMOVED   <== HOLE
walrus alias clear             CLOBBERED   eligible                 grant REMOVED   <== HOLE
nested-func alias clear        CLOBBERED   eligible                 grant REMOVED   <== HOLE
one-hop nested mapping update  INTACT      eligible                 (writes nothing frozen)
```

The three holes are the probed expression
`([v.clear() for v in [view]] and 3) if not view["experience"] else 8`, its
walrus form `(((v := view).clear()) or 3) ...`, and
`(lambda v: ((v.clear()), 3)[1])(view) ...`. All three are admitted
`eligible` and all three remove the frozen field from the view when executed.

The cause is the one-hop alias rule at `_names_bound_to_view`
(`improve_channel.py:1362-1376`). It walks `ast.walk` in source order and
adds a name only when the assignment's value is already a known view name, so
it follows `v = view; v.clear()` but not `v = w; w = view; v.clear()`, and it
does not see a name bound by a `for` target, a walrus, or an `AnnAssign` at
all. The docstring at `:1344-1358` states this limit honestly for the
two-hop and call-derived cases. It does not mention the three binding forms I
found, and those are not the "computed key" or "call-derived" cases it
declines.

This finding is real but bounded, and the bound is the module's own stated
argument, which I checked rather than accepted. I read the view the child
actually receives (`channel._step_view` over `frontier.step_view`):

```
wire keys: [authority_remaining, contract_versions, eligible_methods,
            environment_digest, environments, experience, frontier,
            frozen_source, improvement_budget, instruments, last_result,
            mission, obligations, observations, open_questions, purpose,
            remaining, retained, target_digest, task_content]
frozen names present: NONE
```

None of the six `FROZEN_FIELDS` is in the view, so a write to one lands on
nothing. The driver also serialises the view to `step.json` and the parent
reads back only the returned action and state, so a child-side mutation
cannot reach the parent store by construction. The module states this at
`:1306-1311` and it is correct.

So A2 is a real admission gap that is currently unexploitable, and it is the
same class of gap as the one X3 repaired. A2 becomes exploitable the moment
the view carries a frozen field, which is the exact trigger the module's own
docstring names.

### Finding A3: the guard raises instead of refusing on a tuple key

```
update tuple key         -> ESCAPED ADMISSION: AttributeError: 'Tuple' object has no attribute 'value'
update list key          -> ESCAPED ADMISSION: AttributeError: 'List' object has no attribute 'value'
```

`_keys_named_by_update` at `improve_channel.py:1514-1515` calls
`key.value` on any key for which `_readable_key` is true. `_readable_key`
accepts a `Constant` string, a `Tuple`, or a `List`
(`:1534-1539`), but only a `Constant` has `.value`. So
`view.update({('grant', 'x'): 1})` raises out of `_frozen_write_reason`,
which `admit_revision_under_freeze` calls at `:1191` before any other check.

The freeze's stated design is default-deny: "A key this check cannot resolve
is refused rather than admitted" (`:1268-1269`). A raise is not a refusal. It
escapes admission rather than refusing the revision. I checked the reachable
caller: `learner_revision.acquire` at `:560` has no `try`/`except` around
that call, so the exception propagates out of `acquire`.

Severity is limited by reachability. `acquire` has no non-test caller, and the
live path never calls the guard at all (A1), so this is not a production
crash today. It is a guard that fails open by crashing in a module whose
stated policy is to fail closed, and a tuple-keyed dict is ordinary Python.

No test covers a tuple or list key in `update`; I grepped the test tree.

### Reproducibility

I re-ran the two probes that carry the most weight, in a second WSL
invocation, to confirm neither finding is a transient. Both reproduced
identically, including the same `package_digest: b87390e71670f465` from the
live-gate probe. The three alias holes reproduced with the same three
verdicts and the same mechanism (`grant REMOVED from the view`).

### What I could not falsify

`_frozen_write_reason` refused all 18 unambiguous forms I threw at it,
including the `update` keyword spelling, `|=` on an alias, `pop` with a
default, `__setitem__`, `setattr`, `del`, walrus-bound frozen names, `except
as grant`, and the one-hop alias. The narrowing the X3 claim describes is
real. I could not construct a form that reaches a frozen field through a
literal key and is admitted.

---

## Milestone A, causal half (X4b) — ESTABLISHED, with the stated limit holding

I read `_effect_operation_id` (`trajectory.py:257-302`) and then probed it
against a real disposable PostgreSQL database, planting four operations with
different settle states.

```
C. what does WHERE settled alone accept?
  fa-op-settled      settled=True  observed   cancel=none    -> ACCEPTED
  fa-op-unsettled    settled=False sent       cancel=none    -> refused
  fa-op-cancelled    settled=True  cancelled  cancel=confirmed-> ACCEPTED
  fa-op-prep         settled=True  prepared   cancel=none    -> ACCEPTED

  unsettled only                     -> '(empty)'
  settled observed                   -> 'fa-op-settled'
  construction repair only           -> '(empty)'
  top-level first, construction 2nd  -> 'fa-op-settled'   (falls through correctly)
  construction 1st, top-level 2nd    -> 'fa-op-cancelled' (first settled candidate wins)
  id that exists nowhere             -> '(empty)'
  empty episode                      -> '(empty)'
```

The core claim holds. An unsettled name is refused, a name that resolves to no
row is refused, and the fallback from `_s09_effect_id` to
`_effect_operation_id` agrees with the database rather than deriving a second
answer. `_s09_effect_id` (`:305-314`) is a reader, as claimed.

The honest limit also holds as stated. A host-side diagnostic boundary
(`controls.diagnostic_resolves` has no dsn) returns empty rather than
synthesising an id, and the row then carries an empty identity. I confirmed
the empty-episode and no-dsn paths both return empty.

Two limits worth recording, neither of which I believe is a defect:

The query is `SELECT id FROM operations WHERE id = ANY(%s) AND settled`, with
no `attempt_id`, `allocation_id` or `study_root` filter. Any settled operation
id resolves, including one belonging to a different campaign. The id is
supplied by the episode, which the campaign itself produced, so this is a
weaker binding than a foreign key but not a fabricated identity.

`settled` alone does not mean "produced an effect". My planted cancelled and
never-dispatched rows were both accepted. I checked whether that is reachable
in production: `settled` is set at `store.py:2054-2057` only on the receipt
path, and `_refuse_terminal_unknown` guards cancellation. So the rows I
planted are not reachable through the real code, and I am not reporting this
as a defect. It does mean the guard's criterion is "settled", not "settled
with a success or failure receipt", and the X4b test asserts the stronger
property (it checks receipts) while the implementation asserts the weaker
one.

X4b's own tests pass (9 passed) and they prove a positive database round trip
rather than merely the absence of the old constant. I read them before
running them: `test_an_admitted_effect_id_is_a_settled_operation_with_a_receipt`
asserts the id names a row, that the row is settled, that it carries an
allocation, and that it has a receipt with a decided outcome.

---

## Milestone B — the informative comparison

The brief told me these must stay negative. They are negative, and I checked
how they are written rather than taking the framing on trust.

### Acquisition, 0 of 4

Confirmed from the evidence, not the summary.
`reports/evidence/invr1b12-swe/store-rows.json` holds five operations and five
receipts: one `unknown` with a `lost-response` receipt identity, three
`failure` receipts carrying `http 502` and `response_status: 502`, and one
`success`. Exactly one artifact was ever returned.

The denominator caveat is stated in the four documents that own current
status: `reports/PROJECT-LEDGER.md:63-70` ("rests on one returned artifact",
"one observation, not a rate"), `reports/STAGE-09-10-COMPLETION-MATRIX.md:95-99`,
`docs/design/REFINEMENT-ROADMAP.md:34`, and
`reports/workstreams/bottlenecks.md:185-192`.

**Overstatement 1 (live file, small but it is the acceptance document).**
`reports/FINAL-ACCEPTANCE.md:93-94` reads "This is a bounded zero resting on a
rate, not a proof the route cannot acquire." It is the only current document
that says "rate" rather than "not a rate", and the only one of the five with
no "one returned artifact" denominator anywhere in it. Honest version:
"resting on one returned artifact, not a rate."

### Utility, transfer, learner improvement

Negative, and the guard that matters is present. `STAGE-09-10-COMPLETION-MATRIX.md:106`
says utility is "NEGATIVE and not measurable", not measured-and-negative, and
"this is not a mechanism result becoming a utility result". The mechanism
verdict is labelled "confirmed (mechanism only)" at `:141`. `PROJECT-LEDGER.md:156`
refuses to read a null as a verdict. These are honest.

### Retention, 0 of 3 over 27

**Overstatement 2 (missing caveat, batch-wide).** No current document states
that retention was never under pressure. I verified the reason in source.
`experiments/ad01/experience_axis.py:17-30`: the returned candidate is either
the whole task (the `ok-incumbent` branch) or a `keep` the oracle already
graded `preserved`, so the verdict axis has exactly one reachable value and
"a walk that only ever deletes atoms cannot produce any of those from a
well-formed task". There is no removal, eviction or pruning field in
`reports/evidence/invr1b14-retention/retention.json` at all.

So "0 of 3 members, all `preserved`" is recorded at
`STAGE-09-10-COMPLETION-MATRIX.md:198` as a bare NEGATIVE. The honest reading
is an instrument-degeneracy observation: a constant verdict is the only
outcome the instrument can produce, so retention was never at risk and
cannot be distinguished from doing nothing. The source says this at line 27;
no disposition inherits it.

This is the same shape as the acquisition fix. The fix there was to replace a
denominator with the observation count. Here the fix is to replace a learner
claim with an instrument claim.

### Autonomous frontier selection

Not established, and every specific detail in the brief checks out in source.
The crossing order is hardcoded at `experiments/ad01/twodomain.py:339`
(`for split, seed in (("dev", 4), ("dev", 11), ("qual", 7))`) and `:348`
(`for split, seed in (("dev", 0), ("dev", 1), ("held_out", 2))`), with
`"entered": "first"` and `"entered": "second"` as literals at `:354` and
`:366`.

The union is at `twodomain.py:126`:
`return len(set(swe_tasks.DEV_TEMPLATES) | set(swe_tasks.HELD_OUT_TEMPLATES))`.
Per split that is 3 dev templates or 6 held-out, against the 6 required by
`minimum_clusters_for_alpha`. The union is what reaches 9. The leak is stated
in the bottleneck document (`:49-67`), the matrix (`:121`), the ledger
(`:120-127`) and the roadmap (`:36`). No document claims selection was
established.

### Served budget

Verified rung by rung in `reports/evidence/invr1b11-budget/budget-probe.json`:
rungs at 16, 64, 256, 1024 and 2048 all return HTTP 200 with
`stop_reason: length`; the 4096 rung has no `stop_reason`, `dispatch_state`
`unresolved`, `response_received: false` and reason "gateway read timed out".
The distinction between a token-limited response and a lost response is
recorded correctly at `STAGE-09-10-COMPLETION-MATRIX.md:218`.

---

## Milestone C — inherited learning and Stage 10

### What is real

The inheritable construction procedure is real and I confirmed the repair by
name. `improve_channel._descendant_source` splices the spent input into the
parent's own bytes at the parent's probed-input site, and `leaf_construct`
refuses the old `low`/`high` menu labels by name
(`improve_channel.py:2100-2106`). A descendant is provably the parent's
procedure with one decision substituted.

The one mission entry is real. `migrations/0019_mission_entry.sql:23-30` is
an `ALTER TABLE investigations` adding six columns to the row that already
owns investigation identity, not a new table, and
`experiments/ad01/mission.py:30-37` refuses a seventh mission key. I
cross-checked every `investigations` column referenced in Python against the
migrations and found no orphan column.

The suspend/resume lost-update defect is genuinely repaired. The three writers
in `mission.py` at `:422`, `:496` and `:543` each take `FOR UPDATE` in one
transaction, and `run.py:599-607` documents the removed unlocked path.

**One clarification on scope.** The claim is that the acquisition *procedure*
is inheritable and revisable. The procedure is inheritable. It is not
revisable: `construction_from_evidence` (`improve_channel.py:879`) is a
module-level function hard-coded to return the last spent input, and nothing
in the revision interface reaches it. `REVISION_INTERFACE` names one AST path
and the scope check enforces it. WORKER-PROMPT §C asks for the decision to be
executable and inheritable, which is met; a claim that the *procedure* itself
can be revised by the system overstates by one level.

### Finding C1: the no-op control cannot fail

`experiments/ad01/channel_controls.py:409-415`:

```python
"decision_changed": 0 <= x_probed != INCUMBENT_X,
...
record["as_expected"] = (
    refused if control.get("refused_by_instrument")
    else record["decision_changed"] == bool(
        control["expects_changed_decision"]))
```

For the no-op, `expects_changed_decision` is `False` (`:123`), so the pass
condition is `x_probed == 3`. The no-op's source is
`_selector(channel._revision_source("3"), "3", "8")` (`:115`), and it is
driven with `view["experience"] = []` (`:375`). An empty experience makes the
selector's set empty, so the expression evaluates to 3, which is
`INCUMBENT_X` (`channel.INCUMBENT_EVIDENCE[0]`, `improve_channel.py:817`).

The no-op therefore passes by construction. It cannot distinguish "the no-op
correctly chose the incumbent's input" from "the fixture was built to name
that integer". Its own `known_effect` string at `:116-122` says the
difference is "exactly zero by construction rather than by a measurement that
happened to be small", which is honest about the effect and does not notice
that the pass condition is the same tautology.

Two of the three controls do carry information. `known-effect` names 8 against
a fixture of 3, so a non-zero delta is a real measurement. `disconnect` names
16, outside the valid range, so the refusal is a real outcome of the
validator. One third of the apparatus qualification is decoration.

### Finding C2: `EXPECTATION` is dead code whose comment claims it is a safeguard

`channel_controls.py:266-274`:

```python
# What each role must do, stated before the run. The check reads the
# declaration rather than restating it next to the number, so a control
# cannot quietly agree with itself.
EXPECTATION = {
    "known-effect": "changes the decision",
    ...
}
```

`grep -rn "EXPECTATION" --include=*.py .` returns exactly one hit, the
definition. Nothing reads it. The actual check reads
`control["expects_changed_decision"]` and `control.get("refused_by_instrument")`,
both hand-written per builder immediately adjacent to the number. The
declared protection against a control agreeing with itself is not the thing
that provides it.

### Finding C3 (overstatement 3): the ledger says a lane never ran that has evidence on this tree

`reports/PROJECT-LEDGER.md:201,226,229`, `reports/PLAN.md:87`,
`reports/STAGE-09-10-COMPLETION-MATRIX.md:140,302`,
`reports/FINAL-ACCEPTANCE.md:151,276,501` and
`reports/workstreams/bottlenecks.md:219` all record that no live revision
attempt ran and that there is no evidence directory.

`evidence-ad01/c4-live/` contains 22 files at this tip, 11 JSON and 11 log,
of which 9 traces are readable and 2 are zero-byte stubs. I verified this by
listing the directory.

Two things must not be conflated, and no document disambiguates them. Lane
C4 in `reports/workstreams/c4-construction.md` is the inheritable construction
procedure, offline, with no live call. `evidence-ad01/c4-live/` is the AD01
live qualification directory. `PLAN.md:87` describes the never-run item as
"C4" and cites the C4-construction lineage, which would make the ledger's
"no evidence directory" true for that workstream and false for the directory
that exists.

I am not calling this a research finding. It is a stale index in the document
the governing instruction tells a reviewer to trust for current status, and
the honest fix is to disambiguate the two C4s rather than to delete the
evidence.

### Finding C4: the live path's admission gate is `verify_step_source` only

This is the same finding as A1, seen from the Milestone C side, and I record
it once here rather than twice. `_build_live_package` at
`live_construct.py:1160-1170` calls only `verify_step_source` before the
model's bytes become a bound package. The frozen-write guard and the scope
check are not consulted. Whatever the freeze is worth, it is not a gate on
this path.

### Milestone C test scope

`tests/test_s09_learner_revision.py` and `tests/test_inv_x2_subscript_freeze.py`
pass together, 74 passed. The mission-entry and suspend/resume mechanism is
therefore exercised and green, which supports the mechanism claims and not the
dispositions, since every disposition above acquisition is n=1.

---

## What the batch's own record got right

I want to be as clear about this as about the findings. Four things in this
tree are unusually well done and I tried to break each of them.

The freeze's own docstring tells the truth about its limit, at
`improve_channel.py:1306-1311`, and names the exact trigger that would make
the gap exploitable. That is the standard the rest of the tree should meet.

`experience_axis.py:27-46` states plainly that the verdict axis has one
reachable value, that difficulty and triviality are the same answer, and that
making the panel harder cannot help. The finding I report as Overstatement 2
is written there. It simply never reached a disposition.

`_effect_operation_id`'s docstring explains why the order of the read and the
check is the point, and calls empty "a real answer rather than a fallback".
That is correct and the code does it.

`bottlenecks.md` and the DECOY-FIX repair commit treat the n=1 limit as a
property of the design rather than a caveat on a result, and the census
iteration is now covered across every lane rather than one tree.

---

## Test results, by scope, never summed

One pytest at a time, WSL Ubuntu, PostgreSQL live, no full suite.

| scope | result |
|---|---|
| `tests/test_inv_x3_freeze_methods.py` | 38 passed in 89.70s |
| `tests/test_inv_x4b_effect_identity.py` | 9 passed in 66.66s |
| `tests/test_inv_c2_freeze.py` + `tests/test_inv_p2_frozen_write_binding_forms.py` | 23 passed in 118.44s |
| `tests/test_s09_learner_revision.py` + `tests/test_inv_x2_subscript_freeze.py` | 74 passed in 199.52s |
| `tests/test_r_final_freeze_and_chain.py` | 2 failed, 9 passed in 39.17s |

**The two failures are stale defect records, not regressions, and I verified
that rather than assuming it.**

`test_the_smuggled_write_lands_and_still_reports_a_decision` fails on
`assert verdict.get("informs_decision") is True`. The verdict it received is
`{'eligibility': 'mutates-frozen-field', 'reason': "view.update writes the
frozen field 'grant'"}`. The test asserts the *pre-repair* behaviour, that the
verdict still claims a decision while hiding a write. X3 repaired exactly
that, so the record now fails. Its sibling in the same file,
`test_the_smuggled_bytes_still_write_the_grant_when_executed`, passes, which
is what keeps the refusal honest.

`test_one_protocol_cannot_be_amended_into_four_frozen_children` fails on
`assert len(bodies) >= 2` with `0 >= 2`. It asserts that `amend_protocol`
opens two connections. `trials.amend_protocol` (`src/settlement/trials.py:191-243`)
now delegates to `freeze_protocol` on one connection, and its docstring
documents the two-connection version as the repaired defect. The test is a
frozen record of RF-03.

Both are named in `reports/workstreams/r-final-review.md:320,330` as the
reviewer's defect records. They are not among the three standing reds I was
told to disregard, and they are not in-flight-lane work. They are tests that
correctly record a defect the batch then fixed, left asserting the defect.

**Standing reds I was told to discount, re-verified:**
FA-02 confirmed. `reports/evidence/invr1b4-mean-score/b4-crossover-mean.json`
does not exist, and neither does its parent directory, at this tip. I did not
independently re-verify FA-04; it is a test-file assertion about a deleted
menu and was verified by a prior lane.

---

## Findings I could not test

One sweep of the eight most load-bearing test files for non-failing guards
produced these, and I re-verified each of the three strongest against source
before recording it.

**G1 (certain). `tests/test_inv_x2_subscript_freeze.py:240`.**
`test_the_binding_forms_are_the_ones_the_language_has` asserts
`len(OTHER_WRITES) == 26`, and its docstring claims "The set is closed, so
the guard cannot have a hole by omission... A site added to the language
would need a case here and would fail loudly". A length assertion over a
module-level literal list defined 20 lines above cannot detect a site added to
Python. The list has 26 entries but only 25 distinct strings:
`'if (grant := {"queries": 99}): pass'` appears at both line 205 and line 211,
so the parametrized test collects 26 test IDs for 25 distinct positions. A
reader counting 26 green tests reads 26 covered; 25 are covered and one runs
twice. I read the list and confirmed the duplicate.

**G2 (certain, and the most misleading of the three). `tests/test_s09_learner_revision.py:189-194`.**
The test is named
`test_the_frozen_prompt_cannot_be_answered_with_the_incumbents_own_input` and
its docstring says "the prompt withholds the incumbent's value, so agreement
is not free... the template itself is not a giveaway". Its two assertions are:

```python
assert str(channel.INCUMBENT_EVIDENCE[0]) not in prompt["user"].split(
    "```python")[0]
assert '"x": %d' % channel.INCUMBENT_EVIDENCE[0] in template
```

Line 192 scopes its check to the text *before* the fenced code block, i.e. the
instruction prose only. Line 194 then asserts the incumbent's input **is** in
the template. `template_for()` returns `IMPROVE_LOW_SOURCE`
(`learner_revision.py:151-153`), `USER_TEMPLATE` embeds that whole source at
the `{template}` slot (`:108-110`), and `IMPROVE_LOW_SOURCE` contains
`{"kind": "probe", "inputs": {"x": 3}}` at `improve_channel.py:88`.
`INCUMBENT_EVIDENCE = (3,)` at `:817`. So the prompt hands the model both the
incumbent's own input and the exact bytes to copy, and the test asserts the
presence of the answer while its name asserts the absence.

I want to be precise about the weight of this. It does not mean a fixed guess
would be admitted, and the docstring says so itself ("the eligibility rule
would catch it"). What it means is that the second half of the pin, "the
template is not a giveaway", is not established by the assertion and is
contradicted by it. This sits directly under Milestone C's "executable
inheritable revision" claim, because it is the acquisition prompt that would
have to elicit a genuinely new decision.

**G3 (certain). `tests/test_r_final_freeze_and_chain.py:254-257`.**
The RF-02 mechanism record asserts `"operations" in inspect.getsource(trajectory._effect_operation_id)`
with the message "the derivation no longer asks the operations table; the
identity is being minted rather than derived". `_effect_operation_id`
(`trajectory.py:257-302`) contains the word `operations` three times: twice in
its docstring and once in the SQL. Deleting the `SELECT id FROM operations ...`
and leaving the prose passes this guard. It cannot distinguish *asking* the
table from *documenting* that it asks it.

Note that this does not weaken my own Milestone A finding on X4b. I established
that claim by reading the SQL directly and by planting rows in a real
database, not by relying on this test. The X4b file itself is clean: its
assertions are queries against a real disposable store.

**G4 (certain, minor). Two assertions that cannot fail independently.**
`tests/test_inv_x2_subscript_freeze.py:99` asserts `len(SUBSCRIPT_WRITES) == 6`
where `SUBSCRIPT_WRITES` is a comprehension over `channel.FROZEN_FIELDS`, so it
equals a length the test already asserted two lines above.
`tests/test_inv_x3_freeze_methods.py:523` asserts `"_frozen_write_reason" in
names` after line 521 already indexed the same dict by that key, so a rename
raises `KeyError` first and the assert never runs.

**G5 (certain on the gap, medium on impact). `tests/test_inv_x3_freeze_methods.py:485-509`.**
The test is named
`test_no_surviving_comment_promises_a_runtime_backstop_that_cannot_fire`, but
its `_docstrings()` helper walks only module, function, async-function and
class nodes. It cannot see a `#` comment. A `# the runtime comparison is the
backstop` comment, exactly the promise the test exists to catch, passes it.

I did not treat the docstring-scanning tests as defects. Scanning docstrings
for honesty claims is this repo's established pattern and, on the merits,
`_frozen_write_reason`'s docstring does contain the terms those tests require.
The defect is the gap between the name's word "comment" and the mechanism's
docstring-only reach.

**Silent-skip check: clean.** No `pytest.skip`, `skipif`, or early return in
any of the eight files. One thing worth knowing rather than counting as a
defect: `tests/conftest.py:20` skips on an unset `SETTLEMENT_TEST_DSN`, but
`test_inv_x4b_effect_identity.py:48-58` defines its own fixture that calls
`s09_run_isolation.create_disposable_db`, falling back to
`s09_run_isolation.py:202-206` `DEFAULT_ADMIN_DSN`. That file therefore does
not skip on a missing DSN, it fails loudly. A reader who assumes database
tests skip cleanly is wrong about that one file specifically.

**Files with nothing genuine.** `tests/test_inv_p2_frozen_write_binding_forms.py`
(its negative control at lines 45-47 is what stops a blanket-refusal guard from
satisfying the file), `tests/test_inv_x4b_effect_identity.py`,
`tests/test_inv_c4_inheritable_construction.py`.

---

## What I could not determine

Four things, none of which I am counting as findings.

Whether `scripts/invl02_live.py` has an admission gate I did not find upstream
of `_build_live_package`. I read the function and the module around it; the
only gate there is `verify_step_source`. A reader who knows of another should
weigh Finding A1 accordingly.

Whether the union of dev and held-out templates in `_swe_clusters` produces a
defensible selection result even though it defeats the generalization question.
`bottlenecks.md:59-61` argues it is defensible for selection and indefensible
for generalization. I did not adjudicate that, and it is not mine to.

Whether the AD01/c4-live aggregate spend respected its declared bound. Every
readable trace records `charge_units: 0` and no receipt file exists, so no
breach is detectable and no bound was enforced by a mechanism. That is
unverified, not a breach, and I make no claim about it beyond that.

Whether any document's claim about Milestone B is load-bearing on a
hypothesis I could falsify in one pass. The dispositions are negative and the
structure is n=1, so a negative here is a statement about the one structure
measured. I did not attempt to manufacture an independent unit, which is the
recommendation the bottleneck document reaches and which is a human decision
about the instrument, not mine.

---

## Recommendations, in priority order

Repair the admission boundary before anything else. The freeze needs a
production caller, or the claim that it is "enforced" should be withdrawn from
`FINAL-ACCEPTANCE.md:23` and from any document that says the freeze is a
property of the running system. Right now a reader who greps for the guard
finds a real function with a real improvement and no path that calls it.

Fix the alias rule or state its limit. `_names_bound_to_view` follows one hop
in source order. Two options: iterate to a fixed point over the binding forms
the parser already marks, or extend the docstring at `:1344-1358` to name the
`for`-target, walrus and `AnnAssign` bindings alongside the two it already
names. The second is honest and cheap; the first closes it.

Make the tuple-key case refuse instead of raise. `_readable_key` should agree
with `_keys_named_by_update` about what it accepts, or the guard should return
a reason for a key it cannot read. The module's stated policy is default-deny
and a raise is not a refusal.

Say what the no-op control is. It is a restatement of its own fixture. Either
give it a pass condition that can fail, or record in the apparatus verdict that
two of three controls discriminate and the third confirms wiring only.

Disambiguate the two C4s in the ledger, and correct the "no evidence
directory" line if it refers to `evidence-ad01/c4-live/`.

Carry the retention instrument-degeneracy caveat into the disposition. The
source already says it; the matrix records a bare NEGATIVE.

Fix `FINAL-ACCEPTANCE.md:93` to say "one returned artifact" rather than "a
rate", and note that the document's line 68 repeats the runtime-backstop
promise that X3 deleted from the code.

---

## Method note

Every finding above is a measurement or a quotation. I wrote four independent
probe scripts, all outside the repo, and re-ran each after fixing a bug in my
own detector rather than adjusting an expectation to fit the result. Two of
those bugs were mine: my first smuggle probe compared the wrong value and so
missed that the baseline form did write, and its replacement still missed
`clear()` because removal is not overwrite. The version reported above asks
whether the frozen field *survived*, which is the right question. I also built
my first freeze cases against a wrong revision shape, got an unrelated
ineligibility back, and rebuilt them on the real control template before
drawing any conclusion.

I did not run the full suite, per the thermal constraint. The sweep for
non-failing guards covered the eight most load-bearing test files and is
recorded above; I did not sweep the whole tree, and I make no claim about
files outside that set.
