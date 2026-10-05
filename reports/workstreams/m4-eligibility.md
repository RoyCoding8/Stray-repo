# M4 eligibility: does an eligible revised learner exist?

**Verdict: yes, an eligible revision is constructible from the same prompt
against the same rule. It is reachable. The E4 negative is a property of the
acquisition prompt, not of the eligibility rule and not of the underlying
tasks.**

That makes M4's deliverable the acquisition attempt, not a comparison panel.
`WORKER-PROMPT.md:132-134` reserves the honest negative for the case where no
eligible revision can be had, and that case does not apply here.

Read this alongside the correction the ledger has not yet taken up. The ledger
records two different experiments under one row: `PROJECT-LEDGER.md:599` says
"M4 is not started", while `PROJECT-LEDGER.md:1143` records E4's six refusals.
Both cannot be true. `PROJECT-LEDGER.md:707-712` states the discrepancy
explicitly and assigns the correction elsewhere. This document establishes
which is the current fact.

## What I ran, what I read, what I inferred

**Ran.** Every classification below is executed against the code at base
`e3be0703`, not read off a docstring. `classify_revision` itself needs a live
PostgreSQL (`improve_channel.py:1892`), which this host does not have, so the
four tests in `tests/test_m4_eligibility.py` exercise every gate that does not
need one and read the probed expression directly for the fifth. All four pass
locally. **CI must confirm them** under the postgres:18 service container,
because pytest's `conftest_isolation.py:751` acquires a run claim before
collection and cannot start here at all.

**Read.** `improve_channel.py`, `channel_controls.py`, `learner_revision.py`,
`rule_learner.py`, `PROJECT-LEDGER.md` in full, `WORKER-PROMPT.md:119-134`,
and the twelve prior workstream reports that touch eligibility.

**Inferred, and labelled as such.** That a fresh model on a fresh route would
now produce a non-zero x. The rule and the construction are measured; the
model's behaviour is not. Nothing in this document claims it.

## The eligibility rule as implemented

`classify_revision` (`improve_channel.py:564-628`) applies six gates in order.
A refusal names the boundary that held. One gate sits ahead of all six and
belongs to the rule as a caller meets it:
`_frozen_write_reason` runs first, ahead of every eligibility question, so a
revision that both smuggles a frozen write and fails a shape check is reported
for the write rather than hidden behind a cheaper verdict
(`improve_channel.py:1194-1196`, `mutates-frozen-field`).

| # | Gate | Refusal | Line |
|---|---|---|---|
| 1 | non-empty executable STEP source | `prose-recommendation` | `:595-603` |
| 2 | at least one learner view | `no-boundary-action` | `:604-606` |
| 3 | bytes emit a probe | `no-boundary-action` | `:607-609` |
| 4 | the probed `x` is computed from the view | `task-solver-not-decision` | `:610-614` |
| 5 | differs from the incumbent at `x` and nowhere else | `changes-an-unauthorised-decision` | `:615-621` |
| 6 | does not reproduce the frozen reducer's choice | `delegates-to-unchanged-reducer` | `:622-624` |

Every reason is a distinct string in `INELIGIBILITY_REASONS`
(`improve_channel.py:225-227`).

Gate 5 is the load-bearing one for M4, and it is newer than the E4 run.
`unauthorised_change` (`:377-405`) parses both sources, blanks every `"x"`
site on both (`_program_shape`, `:408-432`), and compares what remains. A
revision that rewrites allocation, construction, target or the step skeleton
is refused by name (`_SITES`, `:445-451`). This was added by lane C2, which
found the rule previously admitted every one of six variants that should not
have been admitted (`reports/workstreams/c2-freeze.md:44-58`).

Gate 6 is the one that refused all six E4 replies, and its implementation does
not do what its name suggests. `delegates_to_frozen_reducer` (`:544-561`)
compares the revision's executed choices against `_incumbent_choices`
(`:495-517`) and `_reducer_argmax` (`:520-541`). I verified by execution that
`_reducer_argmax` **ignores its `view` argument entirely** and returns `[0]`
for every view, including the string `'anything'`, because every input's
disagreement ties at the empty version space. At the admission view
`_incumbent_choices` returns `[0, 1, 2, 3, 4, 5, 6, 7]`. So gate 6 at the
first step reduces to a single test: **does the revision name 0?**

Executed, at the view `_admit` builds (`learner_revision.py:1283-1286`,
`experience` empty):

```
x   0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15
    R  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -     R = refused as delegation
```

Naming anything but 0 clears gate 6. Nothing else about a non-zero revision is
in question.

## The enumeration

Every candidate in the tree, classified against the bar M4 sets: does the
change alter *how acquisition happens*, or only *what the acquired program
does*?

**The bar, read off the code.** Every candidate below changes the program that
gathers diagnostic evidence. That is an inherited change to the acquisition
procedure by construction, and it is the authorised one (`:372`). The
distinction WORKER-PROMPT draws is not "which of these alters acquisition"
and "which alters the solver"; it is between a revision that *reaches* the
decision and one that reproduces the frozen reducer's answer to it. Gate 6 is
the code's expression of exactly that sentence, and gate 4 is its expression
of "a task solver delegating to a fixed reducer is not a revised learner."

| # | Candidate | Site | G4 | G5 | G6 | Class |
|---|---|---|---|---|---|---|
| A1 | `IMPROVE_LOW_SOURCE` (incumbent, x=3) | `improve_channel.py:108` | fail | n/a | n/a | Not a revision. A constant is a solver. |
| A2 | `IMPROVE_HIGH_SOURCE` (incumbent, x=11) | `:135` | fail | n/a | n/a | Not a revision, same reason. |
| A3 | known-effect control, x=8 | `channel_controls.py:82-99` | pass | pass | pass | Eligible, reviewer-authored. Changes how evidence is chosen. |
| A4 | no-op control, x=3 | `:102-126` | pass | pass | pass | Eligible, reviewer-authored. Deliberately decides as the incumbent does. |
| A5 | disconnect control, x=16 | `:129-165` | pass | pass | pass | Eligible, reviewer-authored. Refused downstream by the instrument's range check. |
| A6 | disconnect-bytes (C15), x=7 decoy | `:209-256` | pass | pass | pass | Eligible, reviewer-authored. Bytes differ, decision does not. |
| A7 | `_revision_source(expr)` | `:170-190` | **expr-dependent** | pass | **expr-dependent** | The builder. Its output is the A8 family. |
| A8 | a model reply | `live_construct.py:907-931` | model | model | model | The only route M4's "live acquisition" describes. |
| A9 | descendant source | `_descendant_source` `:674` | inherits parent | pass | inherits parent | A descendant of A3-A6 stays data-dependent. A descendant of A1/A2 is a fixed literal, hence a solver. |

The three controls A3, A4 and A6 are the evidence that the rule admits
eligible revisions at all. They are authored, and `learner_revision.py:1184-1192`
keeps them out of the acquired arm, which is correct: M4 asks for an inherited
change, not a reviewer's.

**A1 and A2 are the sharpest negative.** The incumbent itself fails gate 4.
It is the authored evidence-selection procedure, it selects one input, and it
selects a constant. This is what "an eligible revision changes how acquisition
happens, and the incumbent does not" looks like in code. It is also why
`INCUMBENT_EVIDENCE = (3,)` (`:840`) is the right comparison arm and not a
second learned thing.

## The verdict

**An eligible revision is constructible and reachable. Measured.**

Constructing one is two lines. Take the builder at `:170` and give it an
expression that reads the view and still names a non-zero integer:

```python
source = channel._revision_source('(len(view.get("experience", [])) or 12)')
```

Executed result: gate 1 pass, gate 3 pass, gate 4 pass (it reads the view),
gate 5 pass (`unauthorised_change` returns `{}`), and it names 12, so gate 6
does not refuse it. This is `test_an_eligible_revision_is_constructible_from_the_same_prompt`.

The path by which it becomes an acquired arm, all of it existing:

1. `run_campaign` (`learner_revision.py:1104`) dispatches on the frozen prompt.
2. `judge_acquisition` parses the reply; `_admit` (`:1275-1288`) builds the
   admission view and calls `acquire` → `admit_revision_under_freeze`
   (`improve_channel.py:1165`) → `classify_revision`.
3. An eligible reply is packaged `acquired` with its dispatch provenance
   (`revision_package`, `:599-635`). `frontier` refuses an `acquired` package
   whose provenance does not resolve to a recorded dispatch and finalization,
   so provenance is not a label this study chooses.
4. `drive_arm` (`:721-766`) adopts it onto a fresh store and runs a real
   improve round; `run_campaign:1194-1200` then compares it paired by seed
   against `INCUMBENT_EVIDENCE[0]`.

Everything in that chain is in place and has run before. It ran for three
reviewer-authored arms in E4, all three recorded `"eligibility": "eligible"`
(`result.json:17-254`), and the fourth slot is exactly the one E4 could not
fill.

## Why E4 got zero, which is the actual finding

E4 dispatched six times on a free route, all six returned executable STEP
bytes, and all six were refused `delegates-to-unchanged-reducer`
(`result.json` `live_claim`: `dispatches: 6, eligible: 0`). Read the six
replies rather than the verdict, and the cause is in the prompt.

The prompt asks for a value computed from the view
(`learner_revision.py:124-125`):

> The integer must satisfy 0 <= x < 16. It must be computed from the view or
> the state, never written as a constant.

The only view the rule ever judges on is the one carrying no observation,
because the decision is made on the step that spends the probe
(`learner_revision.py:1283-1286`). I extracted the probed expression from each
of the six replies. There are three distinct ones:

```
len(view["experience"])                            -> 0
len(view.get("experience", []))                     -> 0
len(view.get("experience", [])) % 16                -> 0
```

All six model-written x expressions are correct implementations of the
instruction. All six evaluate to 0 at the view they are judged on. 0 is
precisely the integer gate 6 refuses. The prompt and the rule meet at a single
point, and it is the refused point.

The other side of the same trap is closed by gate 4. A reply that writes a
non-zero constant is refused `task-solver-not-decision`. So the instruction
forbids the literal that would work and asks for the computed value that
lands on the refused one. This is `w4-e4-interface.md:270`, which recorded the
six-for-six as unexplained and untested. It is now explained, and the test file
pins it.

**This corrects the direction of the recorded negative.** `c4-construction.md`
attributed E4's zero to a two-member authored menu and deleted the menu. That
repair was real and necessary. It was not the cause of the six refusals: all
six replies fail gate 6 before any of them reaches a descendant, and gate 6 is
a comparison against the frozen reducer's choice at the admission view, which
no menu could have influenced. The menu could not have rescued these six
replies either, because the decision was refused before construction. The
prompt was the cause. `c4-construction.md:198-200` proposes re-running E4
because its cause changed; the cause that mattered was never the menu.

Note also what the artifact already says about itself. `result.json:657-663`
records `benefit: false` with the basis "no eligible revision was acquired, so
there is no arm whose descendants could differ." The artifact never claimed
the tasks lack headroom, and it was right not to. `evidence_ceiling`
reports a paired delta of 0.443 at z 17.4. The headroom is real. The boundary
could not express it.

## The nameless store

`drive_arm` creates its store with no `identity` (`learner_revision.py:737-739`),
which the assignment flagged. Checked, and it does not affect eligibility.

- `create_store` takes `identity=None` as its default
  (`frontier.py:2352`) and `drive_arm` is a fixture path: it is what the four
  controls and the acquired arm are driven through inside one process.
- `drive_improve_round` refuses a store that names an owner and is given no
  authority (`:2328-2332`), which is the opposite condition. A nameless store
  with no authority is explicitly the fixture boundary (`:2310-2315`) and mints
  a disposable ledger.
- The production continuation path does carry identity.
  `fresh_round` (`:2597-2632`) opens under `_round_identity`, and the
  docstring at `:2600-2610` says why it used to open namelessly and why that
  made it unable to continue any store a live run produces.

So the nameless store is the fixture boundary working as designed, not a
defect. It matters to M4 for one reason: a restarted descendant-producing
episode, which `WORKER-PROMPT.md:124-125` requires of the effectful control,
goes through `fresh_round`, and that path already requires the caller to supply
`dsn`, `investigation_id` and `allocation_id` together. M4 would have to pass
them. That is a caller obligation to meet, not an eligibility obstacle.

## What M4's deliverable therefore is

**Run the acquisition again under a new freeze. A comparison is reachable and
should not be built until an eligible arm exists.**

The preconditions, in order.

1. **Repair the acquisition prompt.** This is the whole finding. It is
   `USER_TEMPLATE` (`learner_revision.py:114-125`), and it asks for a computed
   value that evaluates to the refused integer at the only view that is
   judged. The change is small: ask for a value that is well-defined at an
   empty experience. The three reviewer-authored controls in
   `channel_controls.py` already answer it, `"x": 8 if 8 not in set(o.get("x")
   for o in view["experience"]) else 3`, which is the shape a prompt should
   elicit. Repairing the prompt is a protocol change, so it needs a new
   freeze, which is what makes step 2 unavoidable rather than optional.
2. **Re-freeze and re-run `run_campaign`.** `WORKER-PROMPT.md:150` forbids
   comparing across a changed freeze, and the freeze has already changed twice
   since E4 (C2's scope check, C4's construction). `c4-construction.md:198-200`
   reached the same conclusion for its own reason.
3. **Only then** build the parent-versus-revised comparison, and keep the
   four controls as the qualification that licenses it. `qualify`
   (`learner_revision.py:938-972`) already refuses to call the apparatus
   qualified unless all four pass, and it records the expected effect from
   `CONTROL_BUILDERS` rather than from the number beside it.

**What must not be built.** No comparison panel whose two arms are the same
thing. `run_campaign:1201-1212` already does the honest thing when acquisition
fails: it writes `x_revised: -1`, `measured: False`, `delta: None`, and an
explicit `error`, rather than scoring a missing arm as zero. That path is
correct and should be left alone.

**One thing remains unmeasured, and it is not eligibility.** Whether the
widened construction lifts a single input above the noise floor is a
measurement nobody has made (`w4-e4-interface.md:269`,
`c4-construction.md:198-200`). It bounds whether an eligible arm would show a
*benefit*, not whether one can be acquired. Those are different questions and
the project has been treating them as one. Note that
`channel_headroom` (`:1024-1095`) is built to answer it with a split-half
selection and a measurable flag, so the instrument exists.

## A code defect found on the way, not fixed here

Gate 6 does not compare per view, so a revision is refused for delegation iff
its first probe is 0. `_reducer_argmax` (`:520-541`) takes a `view` parameter
and never reads it. This is a real mismatch between the gate's documented
meaning (`:550-552`, "the choice is drawn from this set ... under these
views") and what it computes.

It does not change the verdict. Gate 6 still refuses 0 and admits everything
else at the admission view, and the verdict rests on that. **I did not fix it,
and it is out of my owned scope**: `improve_channel.py` is a lane another owner
has touched, and a correct fix changes what the gate means rather than
patching it, which is a decision for that owner. It is recorded here as a
finding with a line number rather than as a diff.

One further note for whoever takes it. The claimed dead code in
`_revision_source` (`:181-188`) is not dead. I verified that
`IMPROVE_LOW_SOURCE` and `IMPROVE_HIGH_SOURCE` differ at exactly one line, the
probe input, so the loop returns on the first iteration every time and the
HIGH template is never used. That is harmless today and the docstring's claim
that both procedures are independently reachable is true in effect, because
rewriting the one integer reaches either. Worth knowing before anyone
"repairs" the loop.
## How the repaired prompt was checked, and what was not executed

The prompt repair (`eb0538fa`, content identical to `6fa5130f`) is justified
gate by gate: `_emits_probe`, `_x_is_data_dependent` and `unauthorised_change`
were each **executed**, and the two worked examples name 8 and 12 at the
admission view against a reducer first choice of 0.

**Gate 6 was not executed.** It was checked by reading the probed expression
and evaluating it against `_reducer_argmax(ADMISSION_VIEW) == [0]`, because
`classify_revision` opens a disposable PostgreSQL database and this host has
none. So the claim "the repaired prompt's guidance passes every gate" rests on
four gates run and one gate read. CI with the `postgres:18` service is what
closes the fifth.

This note exists because the commit that carried this reasoning was re-authored
during a merge, and the re-authored message dropped the caveat. The caveat
belongs to the claim, not to a message that can be overwritten.
