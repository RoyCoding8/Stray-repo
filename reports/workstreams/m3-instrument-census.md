# M3 instrument reconnaissance

Source `0ee4699`. Read-only census. No world was run, no matrix frozen, no
experiment executed. Re-verified claims are marked **[verified]**; the rest are
the reader's citations, unverified by me.

## Headline

Six worlds exist. **None can carry a discovery claim today.** Two are
structurally incapable of one, and the rest are unmeasured. The honest cluster
count is 2, not 6.

M3 forbids adding a world to raise a count. This census says the count should go
*down*.

## The AD01 software and graph worlds must leave M3's matrix

Four independent reasons, each sufficient alone. The first is mine.

**1. The task is regenerable from public values. [verified]** The whole task is a
pure function of `(world, kind, index)` — `splits.py:380` seeds from
`_ad01_seed("software", world, kind, index)`, and `task_id` is
`ad01-w1-within-sw-00`. All three are recoverable from the public `task_id`
string with no key.

Worse, `seed` is itself in `packet.PUBLIC_TASK_FIELDS` (`packet.py:78`), so it
reaches the policy's view directly. And the injected fault is
`software.FAULTS[index % 2]` (`splits.py:383`) — chosen by **index parity alone**,
and the index is the trailing number of the public `task_id`. A policy can
determine which fault was injected from the task id before reading the program.

Scope this honestly: this leaks to a policy that can import the generator, which
is exactly the in-child model this project uses (`method_exec` runs child
processes against the repo). It does not leak to a policy handed only the view
over a wire. It is fatal for the in-child model and irrelevant for the wire
model, so the fix is to state which model a study uses.

**2. The metric is reduction-only.** `benefit.py:18-32` freezes the rule as
`total.reduction: strictly-greater`, computed as `sum(normalized_reduction)`
(`benefit.py:82-89`), where reduction is `(initial-final)/initial`
(`checker.py:178-179`) over `len(ops)`. Nothing asks whether the candidate is a
correct program. A record at 0.167 and one at 0.786 are equally correct; only the
second is "better". This is the exact case WORKER-PROMPT names.

**3. Experience cannot vary.** `panel_variation.py:1-40` measures that every
reachable trial grades `preserved` or `not_preserved` with `preserved` near
universal, because the reducer's oracle and the campaign's grader are the same
function. M3's "relevant / absent / equal-size irrelevant" contrast is
unavailable: a treatment arm cannot observe two outcomes. The module says so at
`:5-13` — "this module is the measurement of that."

**4. The minimum is unique.** `tests/test_ad01_control_distinct_walk.py:14-17`
reports a unique preserved minimum on 18 of 18 tasks under 40 random deletion
orders. Where the answer is unique, "distinct programs" is not merely unproved,
it is measured false.

## The worlds that remain

**SWE (W3)** is the only world offering true interventions. `s09_swe_world.py:172-190`
gives the policy `construct/code.repair` and the world executes the replacement
source. Scoring is behavioural: `repaired` iff public **and** protected tests
pass (`s09_swe_tasks.py:644`). Not reduction, not a scalar.

Its leak was closed deliberately: the mechanism is withheld behind an opaque
hash because "the id reaches the policy view, so a suffix like `double_count`
would hand over the fault label the policy is meant to infer"
(`s09_swe_tasks.py:471-481`), and `public_view` is an allowlist excluding
`mechanism`, `patch` and `protected_test`.

Two residual leaks, both acceptable if stated: the id is an unkeyed hash over a
public tuple, so it inverts to at most 8 of a 9-program catalogue; and the fault
**role** (bound/guard/update/window) is always known even when the mechanism is
not. W3 supports "was a correct program produced", not "which mechanism was
inferred". That is the claim M3 wants, so state it and move on.

**Boolean (W4) and ordering (W5)** are clean function-identification instruments
after the N-34 keyed-id repair. W4 scores per-input agreement with an explicit
`unqueried` split (`boolean_rule.py:298-300`), which is exactly what separates
"memorised the probes" from "identified the function". W5 is exact-match, 0 or 1.

Their limit: both are declaration worlds. You probe, then you declare a
hypothesis; you never execute a program. Both are finite (24 targets for
ordering; a 224-member class for Boolean) and 8 of 8 probes are sufficient in
principle. They support **function identification by observations**, which is M3's
first clause, and nothing else. Label the scope; do not let a W4 score stand in
for a discovery claim.

Caveat on the fix: the HMAC key is `b"ad01-task-id-hmac-v1"`, committed at
`worlds.py:50`, and `worlds.py:44-49` says so — "It is a study constant, not a
secret in any operational sense: it is in the repository." It blocks a policy
holding the view alone. It does not block an adversary reading the source.

## The probe M3 requires does not exist

M3 requires a probe showing the action space "can express distinct programs (not
just one canonical solution)". Four expressivity probes exist
(`boolean_ast_policy.py:831`, `ordering_ast_policy.py:369`,
`ordering_graph_policy.py:640`, `s09_swe_ast.py:414`). Every one measures a node
set's **limits**. None measures an action space's **reach over distinct
programs**.

The closest is `s09_swe_experiment.search_span` (`s09_swe_experiment.py:56-67`),
which honestly labels itself a diagnostic rather than a score (`:1497-1499`).
But it measures reach of *one* reference program, so it cannot distinguish "the
space is rich" from "the space happens to contain the one answer."

`agreement_split.json` (18 rows) splits 9 `same_walk`, 3 `same_answer`,
6 `differ` — on half the frozen panel the two authored strategies take the
*identical walk*.

## Cell dispositions

| Cell | Decision | Reason |
|---|---|---|
| SWE × python-STEP × repair | candidate for SUPPORT | nothing says STEP is limited; `entry_contract` allows arbitrary Python (`method_exec.py:710`). **Unmeasured, so not freezable** |
| SWE × typed-AST × repair | CHANGE, then re-probe | the AST cannot choose the edit line (`s09_swe_ast.py:446-452`) |
| SWE × action-graph | CHANGE or REMOVE | `_parse_action` deep-copies the raw node, so a value a guard read never reaches an action input (`s09_swe_experiment.py:39-42`) — a loader defect, so repairable |
| Boolean × any | CHANGE, scope label required | clean identification instrument, zero intervention content |
| Ordering × any | CHANGE, scope label required | same |
| AD01 software × any | **REMOVE** | four independent reasons above |
| AD01 graph × any | **REMOVE** | same four |

## Prior studies: what actually ran

All five carry the same supersession — verdict `PARTIALLY_VOID`, finding `A20
panel regeneration / AD01 freeze digest`. No study is retracted and no record is
recorded as failing; the void is scoped to digest occurrences.

| Study | Records | Verdicts | Eligible artifact? |
|---|---|---|---|
| `inv_r1_m3` | 24 | 24 `refused` | no |
| `inv_r1_m3b` | 36 | 33 refused, 3 preserved | 3, one arm only |
| `inv_r1_e1_control_arm` | 54 | 54 `preserved` | yes, but reducer delegation |
| `invl02_liveacq_r3` | 20 | 20 `preserved` | yes, reducer delegation |
| `invl02_liveacq_r4` | 9 | 9 `preserved` | yes, reducer delegation |

The three "eligible" sets are not M3-eligible. Every `executed_source` begins
`def ENTRY(task, oracle, max_qu…` or `def acquired_order(task, oracl…` — thin
wrappers over `reduce_software`/`reduce_graph`. The ledger already records this
at `PROJECT-LEDGER.md:523`: "Six live executable STEP candidates were refused as
unchanged reducer delegation." And `control_distinctness.py:83-98` records that
`menu_answers_nothing` now exists to refuse this before dispatch.

**What these studies do prove,** and it is worth keeping: the pipeline carries an
artifact end to end, and the eligibility gate correctly refuses reducer
delegation. That is a real result and the right foundation for M3.

The "6 of 6 spent, 0 of 6 eligible" figure is confirmed at
`reports/evidence/inv_r1_e4/result.json`: `{"acquired":6,"dispatches":6,
"eligible":false,"verdict":"no-eligible-revision-acquired"}`, with
`acquisition.acquisition == "no-reply"` and `detail == "no dispatch was
attempted"`. Note the tension between "6 dispatches" and "no dispatch was
attempted" — the provider was called 6 times, 6 model artifacts came back, 0
were eligible. The ledger's caveat at `:93` is right to keep `c4-live` (never
ran) distinct from E4 (ran and spent 6).

## Disposition

**No cell freezable for a discovery claim.** M3 as written cannot be run
honestly against these instruments. Freezing AD01 cells would manufacture the
cluster count M3 warns against; freezing SWE would be freezing an unmeasured
cell.

Per WORKER-PROMPT's own rule — if construction produces no eligible artifact,
finish the bounded attempt and leave utility/transfer unmeasured — the correct
next step is to repair the instrument (a leak fix on AD01, the missing
expressive-action probe, the STEP cell measurement) and only then freeze. That
work is independent of M1 and can run in parallel.