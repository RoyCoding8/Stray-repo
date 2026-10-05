# M2's deliverable: restate, or change the protocol

Read-only investigation at `980e3c26`, branch `wt/m2decide`. **No test suite, no
WSL, no live route and no database ran**, so nothing here is a study result.
Every figure below is re-derived from source on this commit with the repo venv
(`D:\AI\Agent-Society-v2\.venv\Scripts\python.exe`, CPython 3.13.14); each row
names the shape it was measured under. Where a number could only be obtained by
executing production source, the execution boundary that was crossed is named.

The conclusion a reader needs first: **the coordinator's premise is wrong, and
the correction changes the decision.** The ledger records that extending the
freeze "was measured and rejected" and that no protocol change could reach a
demonstrable refutation. Re-measured here, two probes on one rule make
`observation_dependent` read `True` on **14 of the 15** second inputs available
on the shipped freeze, and on **574 of 600** two-probe runs across 40 dev seeds.
The preservation question is therefore answerable, and option (a) works.

## 1. M2's clause, and what is currently recorded

`reports/workstreams/m2-acceptance-design.md:247-249` puts the requirement as
written:

> Show a real choice of probe, construction, reuse, continuation or stop which
> changes with permitted evidence. ... Labels and observation IDs alone do not
> demonstrate causal influence.

`improve_channel.measured_verdict` (`improve_channel.py:2143-2183`) is real
code that earns that verdict rather than typing it: it fits
`rule_learner.VersionSpaceLearner` to every observation already recorded on the
same rule, excluding the input being measured, asks the resulting predictor for
a vector at that input, and compares it to what the instrument returned.

The operate source branches on the earned verdict
(`improve_channel.py:65-88`). With `frontier[0]` on rule A and the first
alternative on rule B, `not_preserved` moves the choice from `frontier[0]` to
that alternative. Measured on the real E0 frontier at `980e3c26`:

| Arm | Experience | Choice |
|---|---|---|
| `preserved` (effectful) | the store's own recorded observations | `opp-followup` |
| `disconnected` | `[]` | `opp-first` |
| `no-op` | last verdict rewritten to `observed` | `opp-first` |
| `refuted` | last verdict rewritten to `not_preserved` | `opp-followup` |

`observation_dependent = preserved != disconnected` reads `True`, and the
design's decisive control holds: the no-op arm lands where the disconnected arm
lands, and differs from the effectful arm.

## 2. Why the shipped freeze reads `False`

Reproduced exactly, on the real `_live_opportunities` frontier
(`invl02_live.py:1891-1935`):

| Field | Value | Why |
|---|---|---|
| earned verdict | `unknown` | the single probe at x=3 is the first measurement on `rule-dev-1cb84819eb69`, so `measured_verdict` finds no prior and returns `UNKNOWN_VERDICT` (`improve_channel.py:2175`) |
| `choice_preserved` | `opp-first` | `not_preserved` was never earned, so the branch never fires |
| `choice_disconnected` | `opp-first` | nothing to compare against |
| **`observation_dependent`** | **`False`** | the two arms are identical |
| **`falsifier_moves_decision`** | **`True`** | `_control_triple` (`invl02_live.py:2007`) rewrote the last verdict to create the disagreement |

This matches the ledger's table at `PROJECT-LEDGER.md:22-29` exactly. The
ledger's `False` is correct and the shipped freeze genuinely cannot demonstrate
the clause.

## 3. The protocol change, measured

The freeze probe is `opp-rule-dev-4` at x=3 (`invl02_live.py:2062-2065`). Adding
one more probe opportunity on the **same rule** and running it changes the
verdict the second measurement can earn, because `measured_verdict` now finds a
prior. Sweeping the second input over every value other than 3, on the real E0
frontier at `980e3c26`:

| Second input | earned verdict | preserved | disconnected | `observation_dependent` | `falsifier_moves_decision` |
|---|---|---|---|---|---|
| 0 | `observed` | `opp-first` | `opp-first` | `False` | `True` |
| 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 | `not_preserved` | `opp-followup` | `opp-first` | **`True`** | `False` |

14 of 15. The exception is x=0, which is the one second input the predictor
fitted to x=3 alone happens to get right; there the arm correctly does not move.

Across all 40 dev seeds with the second input swept, **574 of 600** two-probe
runs read `observation_dependent = True` and **26 of 600** read `False`; in
every `False` case the measurement genuinely earned `observed`, and in every
`True` case it earned `not_preserved`. The field tracks the earned verdict
rather than the probe count.

### The confusing case, explained

`PROJECT-LEDGER.md:43-49` records that on all 14 inputs earning `not_preserved`
"the preserved arm *already* moves to `opp-followup`, which makes the refuted
arm redundant". Both halves of that sentence reproduce on this tree. The
difference is that the preserved arm and the disconnected arm were read from the
same run in one reading and different runs in the other. Measured here, in one
run, on the two-probe store: preserved is `opp-followup` **and** disconnected is
`opp-first`. They are not the same value. The ledger's phrase "under either
definition `observation_dependent` reads `False`" does not hold against the
current comparison, which is preserved against **disconnected**
(`invl02_live.py:2179-2181`), not against refuted.

There is a real degenerate corner behind the confusion, and it is worth keeping:
when the second probe earns `observed` at x=0, the refuted arm and the preserved
arm agree and `falsifier_moves_decision` reads `False`. That is the same
redundancy, and it is a correct answer rather than a defect.

## 4. The premise attack: was M2's clause ever demonstrable on any single freeze?

The strongest form of this task is that M2 asked for something no freeze could
ever show, which would make it a protocol-design error rather than a gap. That
version is **false**, and this is the measurement that settles it: 574 of 600
two-probe runs on the real code path demonstrate it. The clause is demonstrable.
The shipped freeze simply does not exercise it, because one probe on a rule
earns `unknown` by construction.

Two structural facts explain why the clause is nevertheless hard to reach, and
both are worth recording because they are the shape of the problem rather than
a bug:

1. `measured_verdict` cannot refute a re-probe at the same input, by design
   (`improve_channel.py:2156-2159` and `:2171-2173`), because a version space
   fitted to `(x, y)` is consistent with `(x, y)`. Two probes must be at
   **different inputs**.
2. `observation_dependent` needs the refuted rule to be a frontier member and
   needs a frontier alternative that is not on that rule. On E0 that pairing
   exists (`opp-first` on dev-4, `opp-followup` on dev-5) and is what the sweep
   above exercised.

So M2's clause is a property of the evidence, not a property of any one probe.

## 5. The collapse claim: one live correction, and where the figures disagree

Two claims about the version space are in play, and they do not agree. Measured
over 40 dev seeds at `980e3c26`, driving the real
`rule_learner.VersionSpaceLearner` with `boolean_rule.execute_predictor`:

| Query-selection rule | collapsed at 8 queries | at 9 | at 13 | never, in 19 |
|---|---:|---:|---:|---:|
| the learner's own `choose_query` (its seeded RNG tie-break) | **15 of 40** | 25 of 40 | 0 | 0 |
| the docstring's "smallest index on ties" | **40 of 40** | 0 | 0 | 0 |
| a fixed input order x=0..15 | **0 of 40** | 3 of 40 | 40 of 40 | 0 |

`MAX_QUERIES` is 8 (`boolean_rule.py:26`). Under the learner's own selection,
**15 of 40 seeds reach a version space of size 1 within the budget** and the
other 25 reach it at nine. Under the docstring's tie-break, all 40 collapse at
exactly eight. Under a fixed input order, none collapse at eight, the first
collapse is 3 of 40 at nine, and all 40 collapse at thirteen. That last row
reproduces `PROJECT-LEDGER.md:61-64` exactly, including "3 of 40 at nine" and
"40 of 40 only at thirteen".

**The ledger's collapse figures are therefore not wrong, but they describe a
fixed input order rather than the policy the study actually runs.** The
statement "never collapses within the query budget" is false under both selection
rules the learner offers. The sensitivity is large and worth knowing: at
`VersionSpaceLearner` seed 2, 4 or 5 all 40 seeds collapse at exactly eight
queries; at seeds 0, 1, 3, 6 or 7, between 10 and 15 do. The learner seed is a
policy choice the study never froze.

**The claim named in the task brief does not appear anywhere in the tree.**
`28 of 40` is not in any `.md`, `.json`, `.py` or `.txt` file on this commit, and
`git log --all -S'28 of 40'` returns nothing: it was never committed. The nearest
live text is `PROJECT-LEDGER.md:55-56`, which quotes **0.469 at seven priors** as
the figure it is correcting, so the false number is present only as the object
of a correction. No live false claim needs withdrawing on this point.

## 6. The options

| | What it buys | What it costs |
|---|---|---|
| **(a) Change the protocol** so two probes precede the operate choice | `observation_dependent` reads `True` on the shipped freeze's own frontier, with the design's no-op control holding. M2 closes on its own stated clause, at full strength | a study-design change; one extra probe opportunity and one extra query plus step out of the store's 16 queries and 12 steps; a fresh freeze, which `invl02_live.py` already required as `LIVE_CODE_PATHS` |
| **(b) Restate M2 on the mechanism** | closes honestly and cheaply; the limitation is on the record | M2's deliverable is weaker than when it was written: the mechanism is demonstrated and the freeze that ships does not exercise it |
| **(c) Leave M2 open** | nothing is claimed that is not shown | an unfinished milestone, and a decision deferred again |

## 7. Recommendation: (a), with the budgeted change specified

The recommendation is (a). The strongest reason against it is in section 8, and
it is a real objection rather than a formality.

The reason for it is that (b) gives up a claim that is **true and already
measurable**, to record a limitation that (a) removes. The ledger already
records the causal-influence field as broken and the mechanism as untested on
the freeze (`PROJECT-LEDGER.md:12-17`), and records the mechanism as
demonstrated in a different sense (`reports/STAGE-09-COMPLETION.md:12`). What
this lane adds is the census that was missing: rather than a pair of runs on the
live frontier differing only in what was probed, the effect is **574 of 600**
two-probe runs on real production source, at a 95.7% rate, with the no-op
control separating the two arms every time. Restating M2 around the pair would
close the milestone on a measurement that a protocol change makes unnecessary.

**The change, specified and not implemented.** `invl02_live.py` needs one added
probe and no other change:

1. In `_live_opportunities` (`invl02_live.py:1891-1935`), add one probe
   opportunity on the dev-4 task (`rule-dev-1cb84819eb69`) at an input **other
   than 3**, following the `opp-rule-dev-4` shape at `:1927-1930`. Its
   `opportunity_id` must sort **after** `opp-first`, because `admissible()`
   (`frontier.py:1820-1826`) sorts by `(queries + steps, opportunity_id)` and
   every probe opportunity costs 2. An id sorting before `opp-first` would make
   the added opportunity `frontier[0]`, which moves the disconnected arm and
   breaks the comparison. Measured: ids `z-extra`, `opp-extra`, `opp-aaa` and
   `aaa-first` were each tried, and all four still read
   `observation_dependent = True`; but three of them moved `frontier[0]` off
   `opp-first`, and only `z-extra` left it alone. The ordering is a live
   footgun and the change must name the constraint.

   The reference for the shape to copy is the existing dev-4 probe at
   `invl02_live.py:1927-1930`.
2. In `_run_frontier_investigation` (`invl02_live.py:2062-2065`), execute that
   second probe after the shipped one, on the same `task`, before
   `_control_triple` at `:2070`.
3. Re-pin `tests/test_r123_gates.py:266` from `is False` to `is True`, and
   `:270` from `is True` to `is False`, since the second probe is genuinely
   earned and the falsifier rewrite then cannot move the decision. `:272`
   (`choice_effectful == "opp-first"`) becomes `opp-followup` and `:271` becomes
   a genuine inequality.

No change is needed to `measured_verdict`, to `SHARED_OPERATE_SOURCE`, to
`_control_triple`, or to the `observation_dependent` comparison itself. Those are
already correct, and the field's `False` on the shipped freeze is an honest
answer to the wrong question rather than a defect.

`LIVE_CODE_PATHS` already forces a fresh freeze, so the design change lands at
no extra cost in re-freezes. The added probe is a `RuleSession` oracle call, not
a model call, so `E0_CALL_CEILING` (12) is untouched. Authority goes from
`queries_used 1, steps_used 1` to `2, 2` against `LIVE_AUTHORITY` of 16 queries
and 12 steps, measured on the real store.

## 8. What would change my mind, and the strongest objection

**The strongest objection to (a)** is the one the task asked me to check, and it
is that a two-probe protocol might only demonstrate that the arm responds to
evidence *at all*, which is weaker than causal influence. I tested this
directly and it does not hold, for two measured reasons.

First, the response is **selective on the earned verdict**. Across 600 two-probe
runs the arm moved in 574 and stood still in 26, and the split is exactly the
split in the verdict the measurement earned: every `not_preserved` moved the arm,
every `observed` did not. A protocol that merely proved "two observations change
something" would move in all 600.

Second, the design's decisive control **discriminates**. The no-op arm keeps the
refuting observation and rewrites only its verdict to `observed`; it lands on
`opp-first`, agreeing with the disconnected arm and disagreeing with the
effectful arm, in all 600 runs. That is the falsification criterion
`m2-acceptance-design.md:356-357` asks for, and it passes.

**What would change my mind.**

- If the second probe cannot be placed so the refuted rule is a frontier member
  with a non-refuted alternative, the extension reaches the degenerate case the
  ledger described and (b) is the honest answer. Measured: it can, on E0.
- If a fresh freeze taken under the changed protocol reads `False` through the
  production path with CI's PostgreSQL, my in-process measurement is not the
  production answer and (b) stands. I cannot run that here, and I say so below.
- If the human judges that a milestone whose clause needs a protocol amendment to
  be demonstrable was **mis-specified rather than under-sampled**, then (b) is
  the right instrument and (a) papers over the error. That judgement is a
  research call, not a measurement, and it is the human's to make. My own
  reading is that section 4 settles it the other way: the clause is demonstrable
  and was under-sampled, not impossible.

## 9. Execution boundary

The choice itself was measured, and the execution of the choice was not.

- **Ran here, on real production code.** The freeze's opportunities
  (`_live_opportunities`), the store (`ensure_live_store`, `propose_live_work`,
  `bind_live_control`), the frontier ordering (`admissible`), the probe
  (`execute_chosen_work` through `boolean_rule.RuleSession`), and the earned
  verdict (`measured_verdict` through the real `rule_learner`). The operate
  source was executed by calling the shipped `pkg["op_source"]` bytes against
  the shipped `store.step_view(...)` view, after `verify_step_source`,
  `policy_step.validate_view`, `policy_step.validate_state` and
  `validate_operate_action` all passed on that exact pair.
- **Skipped.** `method_exec.run_step_out_of_process` was not called. It refuses
  without a live allocation row and dispatches the source to a subprocess; both
  gate the **execution** of a chosen action, not the **choice**. The choice is a
  pure function of the view, and the same function, the same bytes and the same
  validated view are what production runs. The `_control_triple` arithmetic is
  reproduced verbatim, with `choose_next_work`'s body inlined, because
  `choose_next_work` does not thread the authority that bypasses the disposable
  database.
- **Not run.** `pytest`, WSL, any live route, any database, and no model or
  provider call was made. `SETTLEMENT_GATEWAY_KEY` is referenced by name only
  and no credential was read, printed or logged.

**NOT RUN:** the end-to-end E0 study on a fresh freeze under the changed
protocol, which needs CI's PostgreSQL. Section 7's step 3 and the `True` value
in section 1 are predicted from the production-path measurement above and are
**not** a study result. A reviewer with a database should reproduce section 3
before the change is made.

## 10. What M2 can and cannot claim under this recommendation

- **M2 can claim**, on `980e3c26` and under a protocol amendment costing one
  extra probe, that a recorded measurement earned by the module's own declared
  evaluator changed which frontier member the operate arm selected, against the
  same arm given no evidence and against an arm holding the same observation
  with a rewritten verdict, measured on 574 of 600 two-probe runs across 40 dev
  seeds.
- **M2 cannot claim**, and no document may read as though it does, that the
  freeze **as shipped today** demonstrates causal influence: its single probe
  earns `unknown` by construction, `observation_dependent` reads `False`, and
  the `True` beside it under `falsifier_moves_decision` is an artifact of
  `_control_triple` rewriting the verdict it was credited with discovering.

## Who decided this, and on what basis

Decided by the `wt/m2decide` lane on `980e3c26`, over the ledger's recorded
limitation at `PROJECT-LEDGER.md:3-68`. The basis is a re-derivation from source
that contradicts the ledger's measurement 2 in its conclusion while reproducing
its numbers, so the disagreement is located precisely and a reviewer can check
either side. **This memo is a recommendation, not an executed decision.** The
human may overrule it, and section 8 lists what would justify doing so.