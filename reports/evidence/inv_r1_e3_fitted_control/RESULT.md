# E3: a competent fixed-allocation control

New namespace. Nothing under `inv_r1_e3_selection/`, `inv_r1_e3_ladder/` or
`inv_r1_e1_control_arm/` is modified or superseded by this directory; the artifacts there
record the runs that produced them and stay byte-unchanged.

Source: `experiments/ad01/agenda_policy.fitted_fixed_rule`, wired into
`s09_e3_selection.crossover` as a third arm. Gate:
`tests/test_s09_e3_fitted_control.py` — 10 passed at this tip, on an isolated
disposable database per test.

## The premise this lane was given was wrong

The assignment states that "no fixed-allocation control exists anywhere in the repo" and
that this lane is adding the arm that makes E3 mean anything. That is false.
`agenda_policy.FixedPolicy` (`:186`) has been the control arm of
`s09_e3_selection._arms()` since the study was written, `e3-crossover.json` is committed
with both arms, and `reports/evidence/inv_r1_e3_ladder/RESULT.md` reports a two-sided
result across 18 cells. Nothing was missing that a new arm would supply.

What *was* missing is that the committed control was never checked for competence, and
when checked it is not competent. That is the finding below, and it is smaller and more
specific than "there is no control".

## Decision 1: the fixed rule

`FixedPolicy.DEFAULT_RULE = {"software": ("ddmin", 5), "graph": ("ddmin", 1)}` carried this
docstring:

> The default rule is the strongest world-blind constant pair, chosen by an exhaustive
> search over every (capability, depth) combination scored on the three qualified worlds
> at once.

Measured at this tip, that claim does not hold across the ladder. An exhaustive search
over the same space — both capabilities, depths 1-7, mean held-out reduction over the
three qualified worlds — scores strictly higher at budgets 20, 30 and 60, and ties at 40:

| budget | `DEFAULT_RULE` | best in its own space | gap |
|---|---|---|---|
| 20 | 0.000000 | 0.139776 | control weaker |
| 30 | 0.111111 | 0.175257 | control weaker |
| 40 | 0.359281 | 0.359281 | tie |
| 60 | 0.391007 | 0.414277 | control weaker |

### The claim is tested, and the test is narrower than the claim

This is the more precise finding, and it is a correction rather than an absence.
`tests/test_s09sel_divergence.py:135` **is** a competence test — it searches all 196
constant pairs and asserts none beats `DEFAULT_RULE`. It is real, it passes, and it is
sound at the budget it runs.

It runs at **`BUDGET = 40`**, and 40 is one of only two budgets in the ladder where
`DEFAULT_RULE` is in fact optimal. Counting how many of the 196 constant pairs beat it,
per budget:

| budget | rules beating `DEFAULT_RULE` | the committed test covers it |
|---|---|---|
| 8 | 0 of 196 | no |
| 14 | 0 of 196 | no |
| 20 | **96 of 196** | no |
| 30 | **94 of 196** | no |
| 40 | 0 of 196 | **yes** |
| 60 | 4 of 196 | no |

At budgets 20 and 30 the default is beaten by roughly half the search space. The claim is
true where it is checked and unverified everywhere else, and
`reports/STAGE-09-CONNECTED-STATUS.md:93` reports it unqualified — "The control is the
strongest world-blind rule pair, fitted by exhaustive search over all 196 combinations …
so this is adaptation against a genuinely competent baseline, not a strawman" — while
citing that test as the proof.

So the defect is not a missing check. It is a check whose scope is narrower than the claim
made from it, which is worse in one specific way: a reader who goes to verify finds a
green test and concludes the claim holds. The fix is to state the budget the search
covers, or to run it at every budget the ladder reports. `DEFAULT_RULE` is retained — the
committed evidence was produced under it and rewriting it retroactively would make that
evidence unreadable — and the unqualified claim is withdrawn from the docstring and from
this record.

`tests/test_s09_e3_selection.py` is unaffected by the withdrawn claim: all 10 of its tests
pass unchanged against the three-arm crossover, and the ones that matter here
(`test_the_control_stops_spending_while_the_agenda_does_not`,
`test_the_control_stops_adding_investigations_past_saturation`) are about saturation
behaviour, not competence.


**What it would take for the agenda to beat the default meaninglessly:** the agenda would
have to beat a rule that is not the best its own family contains. That is now measured
rather than assumed, and the answer is that the default *is* beatable, so any agenda
advantage quoted against it alone is an advantage over an unstated-strength opponent.

**Rejected: round-robin / first-N in a fixed order.** Rejected because it confounds
selection with portfolio order. The portfolio is built in `Agenda._offered` as
family-major, method, then target, then depth, so first-N spends the envelope on one
family and one capability. The result would measure the enumeration order of a list, not
the quality of a rule, and the agenda would win or lose for reasons that have nothing to
do with choosing.

**Rejected: per-world oracle.** Rejected because it is not pre-committed in the sense
that matters — fitting per world uses the world identity, which is legitimate, but a rule
fitted on the reported metric is not a control at all. See decision 2.

## Decision 2: the yield metric

The fit reads **`retained_behaviors`** and never `held_out_reduction`. This is the whole
reason the new arm is a control rather than a restatement of the metric.

The circularity is measurable, not asserted. At budget 60:

- development-fitted rule → **0.187032** mean held-out reduction
- exhaustive held-out search → **0.414277**

A fit that could see held-out quality would approach the oracle's number. A fit that
cannot is nowhere near it, and the 0.23 gap is the evidence that the objective is
genuinely a different signal. `test_the_fitted_rule_is_not_a_held_out_oracle` pins the gap
at more than 0.05 so a future edit to `FITTED_OBJECTIVE` cannot quietly make the arm an
oracle.

This is C15's shape one level up. C15's arm was byte-identical to a recording double and
the instrument read the echo as success. An arm fitted on the reported metric is the same
defect with a different mechanism: it is not an echo, it is a cheat that the metric cannot
detect in itself.

## Decision 3: the budget unit

The E3 envelope is spent in **allocation units**: `Candidate.cost()` is
`1 + diagnose_queries + max_queries`, a count of query allowance requested from the local
instrument substrate. It is not a dispatch allowance, not an internal reservation, and not
provider billing. Declared at `agenda_policy.ALLOCATION_UNIT`.

The honesty point: **provider billing in this study is not zero — it is absent by
construction and unmeasured.** `selection.py` contains no gateway import of any kind, and
both arms' diagnostics and reductions run through `trajectory.run_diagnostic` and
`trajectory.dev_episode`, which are local. No E3 number in this module is a cost figure in
any other currency, and none should be read as one. This lane spent **zero** live
dispatches; the router was not contacted.

`cost` is derived from the request rather than the outcome, so a failed operation still
charges. That is what lets the envelope actually bind rather than under-spending on
failures.

## Equal resources, and where they are not

All three arms are constructed with the same `authorized` at a given budget and spend
from their own `Allocation`. `test_no_arm_charges_more_than_its_envelope` reads the charge
back off each run rather than trusting the argument.

The arms are **not** equal in schedule width, and this is named rather than hidden. The
historical rule's schedule is 6 investigations wide; the fitted rule's is narrower. At
loose envelopes the historical arm saturates and stops while the agenda keeps converting
envelope. That is a property of the rules, not a difference in what they were given, and
each arm's own `resources_used` is reported so saturation is visible in the result rather
than inferred from it.

## What the third arm does to the result

Three arms, one envelope, three worlds, frozen measures (`measure_digest` unchanged,
`ce5a140a…`):

| budget | agenda held-out / retained | historical control | fitted control |
|---|---|---|---|
| 14 | 0.1451 / 3 | 0.0000 / 0 | 0.0000 / 0 |
| 20 | 0.1569 / 4 | 0.2535 / 3 | 0.0466 / 1 |
| 40 | 0.2187 / 10 | 0.2512 / 3 | 0.0702 / 3 |
| 60 | 0.2336 / 17 | 0.1226 / 3 | 0.0613 / 6 |

Against the fitted control the agenda leads on held-out quality at every reported budget
(`fitted_control_ahead_on_held_out_at` is empty). Against the historical control the sign
flips at 20 and 40.

**The fitted control is strictly stronger than the historical one on its own objective**
and strictly weaker on the reported one: at budget 60 it retains 6 against the historical
3, and reaches 0.0613 held-out against 0.1226. It is a better control by the only signal it
was allowed to see and a worse one by the signal the study reports. That divergence is the
result, and it is the reason the control has to be stated rather than assumed: a control's
strength is relative to a named objective, and the two objectives disagree here.

## Tests, and the mutation that made each one red

A test that cannot fail is worse than no test, so every assertion here was
mutation-verified: the pinned thing was broken, the file was run, the red output was read,
and the change was reverted. Two of the mutations exposed tests that were themselves
defective, and both are recorded below rather than quietly fixed.

| test | mutation | result |
|---|---|---|
| `test_the_search_space_is_not_flat` | none needed — it is the guard for the fitted comparisons | green |
| `test_the_fitted_rule_beats_the_historical_default_on_its_own_objective` | `FITTED_OBJECTIVE = "held_out_reduction"` (make the fit circular) | **red** — `assert not True` |
| `test_the_fitted_rule_is_not_a_held_out_oracle` | same mutation | **red** — `assert not True` |
| `test_the_fitted_rule_depends_only_on_pre_run_inputs` | covered by the coverage pin below | green |
| `test_the_committed_competence_test_covers_only_one_budget` | the search narrowed to the tested budget alone | **red** — the `beaten_at_20 > 50` count |
| `test_the_control_cannot_observe_run_time_state` | `agenda.cheapest` → `agenda.untried(...) or agenda.cheapest(...)` — a control that re-targets on run-time state | **red** — `at step 1 the control proposed ('ad01-w0-dev-gr-01', …) … and ('ad01-w0-dev-gr-00', …) from a clean agenda` |
| `test_the_fit_is_memoized_without_changing_what_it_returns` | cache key omitting the objective | **red** — the two objectives returned the same rule |
| `test_a_caller_cannot_edit_the_cached_rule_in_place` | `dict(payload)` instead of `_copy_fitted(payload)` | **red** — `got ('greedy', 1), expected the fitted ('greedy', 4)` |
| coverage pin inside the improvement test | `FITTED_DEPTHS = (5,)` (narrow the search to one depth) | **red** — depth list mismatch |
| `test_the_crossover_reports_the_fitted_control_as_a_third_arm` | `arms[FITTED_ARM] = …` → `del arms[FITTED_ARM]` | **red** — `1 failed, 10 deselected`, the arm absent from the ladder |

Nine mutations were run and their red output read. Two further tests —
`test_no_arm_charges_more_than_its_envelope` and
`test_the_fitted_control_is_blind_while_beating_the_default_on_dev` — are **not**
mutation-verified. They assert on a run's own charge and on the fitted rule's reported
provenance. The 2-core box was under load from thirteen concurrent lanes and those runs
did not complete inside the 250 s bound; a timeout is not a pass, so they are recorded as
unverified rather than counted.

### A mutation was committed, and how

The fifth mutation was applied by editing `s09_e3_selection.py` in the worktree, the test
was launched against it, and the file was restored by a `cp` that ran **concurrently with
the test process finishing its own write**. The restore lost the race, `git status` showed
the file clean, and `f6b27ce` was committed with `del arms[FITTED_ARM]` in it — the arm
absent, the crossover silently two-armed.

It was caught by reading `git status` after the mutation's own notification arrived, not by
a test. The next commit repairs it.

The generalisable point is narrow and worth stating: on a loaded box, a background
mutation run and a foreground restore are the same file, and "the file looks clean" is not
evidence that the restore won. Read the committed bytes back, not the working tree's
mtime.

### The two defective tests this lane found in its own work

Both were mine, and both passed against a control that was demonstrably broken. They are
recorded because the failure shape is the one this repo keeps finding.

**The blindness test could not fail.** Its first version advanced both agendas with the
same call, which marked them identically and hid exactly the leak it was looking for. It
passed against a control that read `agenda.state["ran"]`. The fix reads each proposal index
from a *fresh* pair carrying that index's worth of history and nothing else, so a leak at
any depth is visible at that index. The first mutation attempted for it — clamping `step`
upward when `ran` is non-empty — was *inert*, because the graph step's committed depth is 1
and `min(step + 1, depth)` clamps straight back. A mutation that cannot be observed is not
a mutation, and the second attempt (`untried`) was the one that discriminated.

**The search-space test could not fail either.** A `>` assertion on retained count, and
even a 2x margin, both survived `FITTED_DEPTHS = (5,)`, because depth turned out to bind so
weakly on this substrate that a one-deep search still reached the same 18 retained
behaviours. The margin was measuring nothing. Replaced with a direct coverage pin on
`FITTED_DEPTHS == SEARCH_DEPTHS`, which is what the property actually was.

## What this does and does not establish

It establishes that the E3 control arm was weaker than advertised, that a competent
alternative exists and is buildable without reading the reported metric, and that the
agenda-versus-fixed-allocation sign depends on which of two defensible controls is used.

It does not establish that the agenda is a better investigator. Three worlds, one
substrate, six budgets, no independent replication namespace, and both policies are
authored rules over a synthetic portfolio — the fitted control is fitted, not acquired.
Bounded autonomous investigation management, nothing wider.
