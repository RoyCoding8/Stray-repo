# The panel E2 needed, and the verdict it cannot supply

`TASKS.md` §D records four E2 attempts refused because the treatment arm's
experience was a constant, and prescribes a panel of tasks the authored
reducers genuinely fail. This is that panel, and it is the measurement that
the prescription is not available.

## The prescription cannot be carried out

A reducer's oracle and the campaign's grader are the same function, so both
`reduce_software` and `reduce_graph` accept a deletion only on a trial the
checker graded `preserved` and return either the task itself or a `keep` the
oracle already approved. Both grade `preserved`.

Measured on this panel, at every budget, exhaustively over every task and both
methods:

| budget | 1 | 2 | 4 | 8 | 16 |
|---|---|---|---|---|---|
| terminal verdicts | `preserved` | `preserved` | `preserved` | `preserved` | `preserved` |

**54 tasks × 2 methods × 5 budgets = 540 triples, one distinct verdict.** The
frozen `ad01` world gives the identical answer on its own 54 tasks
(`test_the_fixpoint_is_not_a_claim_about_these_tasks_only`). Two independent
generators agreeing is what makes this a property of the reducer rather than a
panel that happened to be easy.

`not_preserved` and `invalid` are reachable only from a task that does not
parse, whose witness does not hold, or whose candidate is not a legal
deletion. A panel of those is grading its own malformity.

**Difficulty is the wrong axis.** `initial-not-preserved` returns the incumbent
byte for byte, and the incumbent of a well-formed task grades `preserved` by
the well-formedness condition itself. A task that is too hard and a task that is
too easy are the same answer. Making this panel harder cannot make the answer
vary, and that is why the `reason` half of the prescription was already
withdrawn at `137b73c` without being the real blocker.

## What varies is the walk, and the walk is what a developing policy read

Every trial the reducer asks the oracle about is graded, and the trials a
reduction attempts are its failures. At the budget the freeze pins (`8`, the
E2 freeze's `MAX_QUERIES`):

| | measured |
|---|---|
| tasks | 54 |
| (task, method) pairs | 108 |
| pairs whose walk carries more than one verdict | **108 / 108** |
| trials graded | 855 |
| stream verdicts | `not_preserved`, `preserved` |
| tasks where `ddmin` and `greedy` return different candidates | 39 / 54 |

That is the quantity `control_distinctness.experience_varies` can be given
something to count, and `panel_variation.walk_observations` is the only
builder in this campaign that supplies it. The four attempts built their
experience from the candidate a reducer *returned*
(`e2_replication.measured_observations`), which is the fixpoint above.
`test_the_terminal_candidate_cannot_open_that_gate` pins both halves: that
builder cannot read a panel task at all, and the arm it did build for an
`ad01` task is refused anyway.

## The separations, measured

Three roles — `dev`, `within`, `transfer` — draw from **disjoint** spec tables.
That is stronger than `ad01`, where development and `within` share every spec
and only `transfer` is held out; the reason is that the walk is the observable
here, and a `within` task sharing a development spec would let a read be
scored on the same structure twice.

```
spec_overlap: []          audit: []          freeze_problems: []
```

Read off the frozen files, not off the generator's own tables, so a generator
that assigns a spec to two roles is caught by the artifacts carrying it. Every
assessment task is re-salting-rejected until its content key misses every
development task's across all three worlds. `audit` refuses a panel whose walk
is a constant on any task — the check that was missing when four dispatches
were spent.

Ten software cores were tried; **four cannot carry a witness disagreement at
all**, and a core that cannot disagree makes an ill-formed task rather than a
hard one. `core_disagrees` re-checks at generation, against the same renderer
the generator uses, so a table pairing a core with a fault it cannot witness is
caught rather than shipped.

## The instrument separates reading from echoing, and the C15 reader does not

The C15 lesson is that a policy copying verdicts into an input key scored 2.0,
identical to the reference reader, and the run read it as learning. The
qualification test is not "does it run" but "can a reader be distinguished
from an echoer on it".

Under the real `s09_e2_scored.Score.measure`, on a panel task where the two
authored methods return different candidates:

| policy | evidence leg | score |
|---|---|---|
| `COUNT_READS_THE_VERDICTS` | **1.0** | 2.0 |
| `ECHOES_WITHOUT_READING` | 0.0 | 1.0 |
| `e2_replication.PROMPTED_SHAPE_READER` | 0.0 | 1.0 |

**The `ad01` membership reader is vacuous here, and that is a finding.** It
asks whether *any* observation is `not_preserved`. On `ad01` the stream is all
`preserved`, so the predicate is false and the verdict flip makes it true — it
separated because the stream was constant. This panel's stream holds both, so
the predicate is true under either exposure and a policy that reads, re-plans
and is invisible scores 1.0. A panel that varies its stream invalidates a
reader qualified on a constant one. Pinned as
`test_a_membership_reader_is_vacuous_on_a_panel_that_varies`.

**The mutation.** `test_the_evidence_leg_goes_red_when_it_reads_echoable_inputs`
recomputes the evidence leg over the action's own inputs — the leg the C15 run
used. The echoer scores **1.0** there, because `read_verdicts` is not a
VERBATIM field and copying a verdict moves the thing being measured. The
shipped leg scores **0.0**, because `assessment_profile._resolve_method` builds
the candidate from the task and refuses a policy-supplied one, so writing
cannot move it. Re-injecting the C15 defect as a genuinely deciding echoer
(`COUNT` in the method choice) makes the reader test red.

## The mutation battery

| mutation | red on |
|---|---|
| walk returns one verdict | 4 tests, incl. the gate and the reader |
| a dev spec placed on the transfer table | the separation test |
| the `constant-walk` audit leg removed | the constant-walk refusal test |
| `walk_observations` reverted to the returned candidate | the gate test, the reader test |
| the echoer given a real count-based decision | the reader test |
| the spec-table audit leg removed | the two-roles refusal test |

## Identity

- **namespace** `ad01-panel-v1`, directory `experiments/ad01/worlds_panel/`
- **54 tasks**, 3 worlds × 3 roles × 2 families × 3 indices
- **18 specs** — 9 software cores, 9 graph structures — disjoint across roles
- **budget** 8, the E2 freeze's `MAX_QUERIES`
- The four retracted directories under `reports/evidence/inv_r1_e2_*` are
  untouched. `git status reports/evidence/` is empty.

## What is not claimed

This qualifies an instrument. It is not a result, and no dispatch was made.
The gate that refused four attempts now has a panel whose stream varies; whether
a *model* reads that stream is the question the next round asks, and nothing
here answers it.

Reproduce: `python -m experiments.ad01.panel_variation`.
