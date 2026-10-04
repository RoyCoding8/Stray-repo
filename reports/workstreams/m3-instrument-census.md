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

**1. The task hands over the answer. [verified]** This is worse than "the task
is regenerable", and the correction is recorded in
`reports/workstreams/ad01-leak-assessment.md`.

The frozen task carries the fault as a **literal key**: `ad01-w1-within-sw-00.json`
has keys `family, fault, ops, seed, task_id, template, witness` with
`fault = "stale-read"` and `template = "stale-read-2chain"`. Six call sites pass
the raw task into a member (`trajectory.py:1839`, `records.py:1617`,
`s09_m3_pilot.py:229,494`, `s09_m2_reload_proof.py:67`, `construct.py:129`).
No import, no inversion, no source read — the answer is a key in the dict.

`method_task_view` (packet.py:121-130) is a **denylist** (`SEALED_KEYS`,
packet.py:42-45) and passes `fault` and `witness` through at both call sites.
`public_task_view` is the allowlist and still leaks, because `template` is
`"stale-read-2chain"` — the fault name is a substring of a public field on
**27 of 27** frozen software tasks. `packet.py:137-143` documents exactly this,
which is why the existing leak checks are blind to it: `held_out_values` must
exclude any value the public view already shows, so a check for `stale-read`
would fire on every arm including one carrying no experience.

`packet.py:78` also listed `seed` in the allowlist, a second copy of what
`task_id` already publishes, since `_ad01_seed` is arithmetic on the three
integers in the id. Removed in `wt/instr-ad01` (`21b4c17`), `+7/-1` in one
file. It was redundant authority, and removing it closed no hole.

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

## The probe M3 requires — now measured, and negative

**Superseded by `reports/workstreams/m3-expressive-probe.md`.** The probe is
specified, runnable, and measured. It reports **degenerate**.

It enumerates edits, not `program.variants`, because `SweSession.repair` admits
`replace` and `delete` over any line (`s09_swe_world.py:353`,
`s09_swe_tasks.py:484`). Enumerating variants would have measured the generator's
table, which is the mistake this census made one level down. It separates
"scorer accepts it" from "semantically distinct", and returns a verdict per task
with no rate, so no reader is handed a number inviting a significance claim. Zero
dispatches — every input is local.

**The result.** 33 of 39 tasks admit exactly one repair. Where two are reachable,
both widen or reverse the `window` role alongside the reference edit, pass all
three cases, and disagree with the reference on 81 to 1575 of 2106 swept inputs.
That is overfitting to three cases, not a second correct repair. **Zero tasks
have two semantically plausible repairs.**

**This closes the last cell M3 was counting on.** Distinct-programs is now
measured false on SWE as well as AD01, on every instance. Combined with the
AD01 removals above, the supported-cell count for M3 is **zero, measured**, not
merely unproven.

**A scorer defect, which outranks the freeze question.** `score`
(`s09_swe_tasks.py:644`) decides from `record["public_tests"]` plus one protected
case — verified at source — and already credits programs that disagree with the
reference on up to 75 percent of inputs. Any SWE freeze taken before that is
repaired would freeze an over-counting verdict. The fix belongs to
`s09_swe_tasks.py`.

**A local hazard.** `_bounded` (`s09_swe_tasks.py:580`) guards a
non-terminating candidate behind `signal.setitimer` under a `hasattr` check that
is False on win32. The probe hung once until a local step bound was applied. On
POSIX the existing guard applies. Recorded so the next Windows reader is not
surprised.

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

**The supported-cell count for M3 is ZERO, measured.** Not unproven — measured.
Every cell that survived the first pass now fails on the probe, and the probe was
run rather than designed-and-hoped.

- AD01 software and graph: four independent grounds, the first being that the
  frozen task carries `fault` as a literal key.
- SWE: `degenerate` per the probe above — 33 of 39 tasks admit one repair, and
  no task admits two plausible ones.
- Boolean and ordering: clean function-identification instruments, but they
  cannot execute a program, and `boolean_rule.key_id`'s key is committed at
  `worlds.py:50` so it blocks a view-only policy and not an adversary reading
  the source.

M3 as written cannot be run honestly against these instruments. That is a
measured negative and it is the correct disposition for this batch — a valid
null closes a study, and the WORKER-PROMPT is explicit that missing arms and
unsupported significance claims cannot.

**What must be repaired before any M3 freeze**, in dependency order:

1. The task-view seam (`ad01-leak-assessment.md`, and the correction in this
   document above). Six raw call sites, but the repair is one executor.
2. The scorer (`s09_swe_tasks.py:644`) crediting programs that disagree with the
   reference on up to 75 percent of inputs. This outranks the freeze question:
   fixing it first would mean measuring against a broken verdict.
3. Only then a world whose action space is genuinely expressive. On present
   evidence that means a NEW world, which M3 forbids unless it earns its place —
   and the probe is now the tool that would justify one.

**Correction to this census's own threat model.** The first version claimed the
leak was fatal only for an in-child policy that could import the generator, and
irrelevant for a wire policy — so the fix was "state which model a study uses."
`ad01-leak-assessment.md` refutes that by measurement. A child **cannot** import:
`verify_member` refuses `ast.Import`/`ImportFrom` at `method_exec.py:738`, and
zero of 4421 committed member sources contain the word. Reachability was inferred
from the driver; the member is more contained than that.

The real exposure needs no import. The answer is a key in the dict handed to the
member, and `template` still names it by substring on 27 of 27 tasks. Declaring a
threat model changes instructions to the study, not one line of what any member
observes.