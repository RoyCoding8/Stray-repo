# M3 expressive-action probe: design, measurement, and verdict

Base `a687259`. One owned file. Read-only elsewhere; nothing in
`experiments/ad01/` was modified.

## Headline

The probe M3 asks for can be run today, offline, with zero dispatches,
and it has been run. On the SWE world it reports **degenerate**: the
action space reaches two distinct accepted repairs on 6 of 39 instances
and exactly one on the other 33. That is a per-task property of a finite
panel, not a sample, and the number carries no significance claim.

Two findings matter more than the count, and both cut against M3 as
written.

1. **Where two programs are reachable, they are not equally plausible.**
   All 8 distinct second repairs carry a *reversed* or *widened* window
   alongside the reference edit. They pass all three scorer cases while
   disagreeing with the reference on 81 to 1575 of 2106 swept inputs.
   They are overfitted coincidences on three inputs, not alternative
   correct repairs. No instance offers two semantically plausible
   repairs.
2. **The scorer cannot tell the two apart.** `score` decides from two
   public cases plus one protected case. So the world already scores
   coincidental programs as `repaired`, and M3's "was a correct program
   produced" support, which the census granted W3, does not hold on the
   measured instances. The claim needs an equivalence clause the scorer
   does not currently enforce.

The second finding is a defect to fix, not a threshold to lower.

## What the world exposes, and what "reach" has to mean

`s09_swe_world.action_schema` (`:172-190`) publishes five actions.
`observe/test.run` and `check/test.run_all` read, `construct` inspects,
localizes or dry-runs, `use/code.repair` applies policy-supplied edits,
`stop` ends. `SweSession.repair` (`:353`) takes a list of
`{"line", "op", "text"}` and runs the resulting source;
`tasks.apply_edits` (`:484`) admits `replace` and `delete` only, and
`_validate_edit_inputs` (`:410`) requires each edit to carry a line
number. So the reachable program set is **all multi-line single-edit-set
substitutions of the source**, not a variant catalogue.

That matters. A probe that enumerates `program.variants` measures the
*generator's* table, not the action space. The census was right that the
four existing probes measure a node set's limits; a fifth that measured
the variant table would repeat the mistake one level down. The probe
below enumerates edits, not variants.

Scoring is `tasks.score` (`:644`): `repaired` iff both public cases and
the protected case pass (`s09_swe_tasks.py:644-664`).

## The probe

**Name.** `action_space_expressivity`, a sibling of `search_span`.

**Input.** One `(split, task_id)` pair, plus the panel role table. It
reads `record["patch"]`, `record["reference_source"]` and the variant
tables, so it is an **assessor-side** probe exactly as `search_span` and
`probe_reach` already are (`s09_swe_experiment.py:1439-1440`,
`:1524-1525`). No policy may hold it. The asymmetry is the same one the
budget derivation already makes at `s09_swe_world.py:111-116`.

**What it measures.** For each task, the set

> `S = { distinct source texts L : score(record, L) == "repaired" }`

restricted to sources reachable by `use/code.repair`, and for each
member of `S`, whether it is **semantically distinct** from the
reference. Two members count as distinct only when they differ as source
texts *and* disagree on at least one input in an exhaustive sweep.

The two-part test is the whole probe. The first part alone is what
`search_span` already does for one program. The second part is what
makes "distinct programs" mean what M3 intends, and it is the part that
is missing today.

**Verdict per task**, exactly three values:

| Verdict | Meaning |
|---|---|
| `degenerate` | `len(S_semantically_distinct) == 1`; only the reference repair |
| `ambiguous` | `len(S_semantically_distinct) > 1`, and every distinct member disagrees with the reference somewhere, i.e. the alternatives are coincidental on the scorer's three cases |
| `expressive` | `len(S_semantically_distinct) > 1`, and at least one distinct member agrees with the reference on every swept input while differing as text, i.e. a genuinely equivalent alternative program |

`ambiguous` is the state that matters and it has no name today.
`s09_swe_ast.expressivity` (`:414`) has `can`/`cannot`; `boolean_ast_policy
.expressivity_limits` (`:831`) has frozen limits. Neither can report "the
space admits a program that is right on three cases and wrong on the
rest", because neither looks at what the scorer decided.

**Expressive vs degenerate, as the pass criterion.** A cell is
`expressive` when the probe returns at least one `expressive` verdict,
and the count of such tasks is reported per cell with its task ids. A
cell returning `degenerate` on every task is a cell whose space is
measured to contain one canonical solution, which is what M3 asks us to
rule out. **No rate, no fraction, no test.** The output is a list of
task ids and a verdict per task. A reader who wants a proportion may
count; the probe does not hand them a number that invites one.

**Dispatch cost.** **Zero.** Every input is a finite local computation.
`tasks.score` (`s09_swe_tasks.py:644`) execs a candidate program against
three cases and returns a dict. No provider is called, no executor is
spawned, no credential is read. This is why the probe could be run and
reported here, and it is the property that makes it cheap enough to run
on every task of every world rather than on a sample.

**Cost in compute, which is the real budget.** The exhaustive variant
sweep is 81 combinations per task (4 roles x 3 variants, one mechanism
per instance) and about 9,700 scored candidates in total across 39
tasks, measured. That is minutes, not seconds, on this host. The
edit-shape sweep is 3 lines x 4 roles x lines x 39 tasks and lands in
the same order. A per-task input sweep of 2,106 cases is 2106 x 3 extra
program calls per distinct candidate and dominates everything else; it
runs only on the handful of tasks that produce more than one accepted
repair.

## What it reports today, measured

All figures below were produced on this host by importing
`s09_swe_tasks` and `s09_swe_world` directly and driving
`world.apply_action`. No episode needing a live route was run, and no
live route is configured (`SETTLEMENT_GATEWAY_ENDPOINT` and
`SETTLEMENT_GATEWAY_KEY` are both absent; the same requirement is
enforced at `experiments/ad01/e2_replication.py:1131-1139`).

**Panel.** 39 instances, 9 dev and 30 held out, from
`tasks.enumerate_instances`. Probe budget 303, edit budget 1, max turns
307, suspect cap 10, all derived at `s09_swe_world.py:574-583`.

**The two-part test across the whole panel.**

| Measure | Count |
|---|---|
| Tasks whose variant table admits one repair | 33 of 39 |
| Tasks whose variant table admits more than one | 6 of 39 |
| Distinct second repairs found | 8, all on those 6 tasks |
| Second repairs that disagree with the reference somewhere | 8 of 8 |
| Second repairs that agree with the reference on every swept input | **0 of 8** |
| Tasks with two semantically plausible repairs | **0 of 39** |

The 6 multi-repair tasks are `swe-dev-scan-depth-8790c0`,
`-5968e4`, `-e69659`, `swe-held_out-scan-climb-5773ee`, `-ef26ea`, and
`swe-held_out-token-gaps-c5f507`. Three are dev, three held out.

**The alternatives are overfitted coincidences, and the shape says so.**
All 8 alternatives widen or reverse the `window` role, and every one
carries the reference edit at the injected fault line alongside it. The
per-task disagreements against the reference range from 81 to 1575 of
2106 inputs. That is a program tuned to three cases, not a second
correct repair. A candidate that reinterprets the window and compensates
at the fault line is not a repair any reader would call plausible.

**Reach is real, not a budget artifact.** Driving the actual
`s09_swe_world` action path with a scripted policy, both repairs arrive
as `use/code.repair` actions the world admits (`world.admits` returns
true), each in 3 turns, each scoring `repaired` by the assessor. 6 of 6
tasks admitted two distinct repairs through the real action vocabulary.
So the 6-of-39 count is a property of the task set, not of the action
space being unable to express anything.

**8 further byte-distinct repairs are semantically free.** Across the
panel, replacing a *different* line with reference text is also accepted
in 8 cases, always a `carry` line whose text is already identical to the
reference, so the edit is a no-op the scorer cannot see through. On 39
tasks the single-line edit shape yields 47 accepted repairs: 39
byte-identical to the reference, 8 semantically equivalent no-ops.
None is a distinct program. This is why byte-distinctness alone is the
wrong criterion, and it is the concrete reason the probe needs the
semantic half.

## The SWE repair is unique, and that decides whether the probe is needed

The census's AD01 finding was a unique preserved minimum on 18 of 18
tasks under 40 random deletion orders, reported at
`tests/test_ad01_control_distinct_walk.py:14-15` and again at `:26-28`,
and `agreement_split.json` splits 9 `same_walk`, 3 `same_answer`, 6
`differ` across 18 rows. For the SWE world the answer is the same and
sharper.

**The correct repair is unique on 33 of 39 tasks, and no task has two
semantically plausible repairs.** So "distinct programs" is measured
false on the SWE world too, on every instance. The SWE cell needs the
same scoping label the census gives the AD01 cells.

The census's own summary that SWE is "the only world offering true
interventions" still holds. Interventions are real. What does not hold
is the inference that a successful intervention implies a rich
candidate space, and the measurement here separates the two.

## One defect this probe exposes in the scorer

The scorer cannot distinguish an overfitted program from a correct one,
because it decides from three cases. Eight programs that disagree with
the reference on up to 1575 of 2106 inputs are scored `repaired`. Any
claim resting on "a correct program was produced" is therefore
overstated on this instrument today.

The fix is not a threshold change in the probe. It is a scorer change:
add a held-out equivalence check, so a candidate is credited only when
it matches the reference across the full input domain rather than on
three sampled cases. That is another owner's file
(`s09_swe_tasks.py`), it rewrites `score` for every existing consumer,
and it is out of this lane's scope. It is recorded here because M3
freezing any SWE cell on the current scorer would freeze a cell whose
verdict over-counts.

**A platform fact that will bite a runner.** `s09_swe_tasks._bounded`
(`:580`) guards a non-terminating candidate with `signal.setitimer`
behind `hasattr` (`:588`). That is `False` on win32, so the guard is
inert on this host and a looping candidate hangs rather than returning
`NonTerminating`. My measurements used a local line-event step bound
instead, and reported 702 non-terminating candidates among the 9,711
scored. A reviewer running this probe on Windows without its own bound
will hang. On POSIX the existing guard applies and the caveat does not.
This is a property of the host, not of the probe, and the fix belongs
with the scorer change above.

## Arm dependence, per the census constraint

`s09_swe_ast.py:446-452` records that the typed AST cannot choose an edit
line from the program under repair, because the frozen `_VIEW_TYPES`
publishes no field carrying it. The census is right that reachability may
depend on the arm.

It does, and this probe makes the dependence measurable rather than
assumed. The reach measured above is a **STEP-arm** fact. It was
established by handing the world a scripted policy the AST cell could
not have written. An arm that cannot read the program cannot derive
either repair from the view, so the AST cell reports `degenerate` on all
39 tasks by a route that has nothing to do with the task's solution set.

So the probe has **two** required arms, not one:

- **world arm**, what this document measures. `S` over the action space.
  Answers M3's question about the instrument.
- **arm arm**, whether a given representation can put a member of `S` on
  the wire. Answers M3's question about the cell.

A cell whose world arm is `degenerate` cannot be rescued by an expressive
arm. A cell whose world arm is `expressive` but whose arm arm is empty is
a cell whose fault is its representation. Reporting one number for both
would hide exactly the distinction the census drew, so the probe returns
both and the cell disposition reads them together.

## Disposition

**The probe is needed, it is now specified, and on the SWE world it does
not clear the bar M3 set.** Measured: 0 of 39 tasks admit two
semantically plausible repairs, so freezing a SWE cell as `expressive`
would be freezing a cell on a claim its own instrument refutes.

Three things follow, in order.

1. **Label the SWE cell the way the census labels the AD01 cells.** Unique
   repair, one canonical solution, scope stated. This is a scoping label,
   not a removal. SWE keeps its interventions.
2. **Repair the scorer before any freeze.** A three-case scorer that
   credits an overfitted program is a measurement defect. Fix it in
   `s09_swe_tasks.py`, in the scorer's own lane.
3. **Do not build the probe into the other three worlds yet.** W4 and W5
   are declaration worlds with no intervention, and the census already
   scopes them. Carrying an edit-enumerating probe there would measure a
   catalogue the world does not execute, which is the mistake this
   document exists to avoid.

The probe earns its keep on one thing: it turned "the space is rich",
which was assumed, into a measured verdict, which was not.