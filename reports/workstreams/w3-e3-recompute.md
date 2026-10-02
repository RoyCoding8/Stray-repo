# W3/E3 — recompute of the disputed budget tables

Lane: `w3-e3-recompute`. Read-only. One new file. No commit, no edits elsewhere.

Recomputed at this tip with the worktree's own `src` on the path.
Measure freeze `ce5a140aff83bccc55a916958fdbaf568cb7c576d5c6a66361510181c83cf7e8`,
identical across every path below. Worlds `(0, 1, 2)`. Budgets `(8, 14, 20, 30, 40, 60)`.
Constant rule space: 196 = 2 methods x 2 methods x 7 depths x 7 depths.

No model calls. No Jev. No database configured (`S09ISO_DISABLE=1`, no DSN set).
No test file was run for this report.

---

## 1. Where the primary records live

| Path | What it holds | Status |
|---|---|---|
| `reports/evidence/inv_r1_e3_selection/e3-crossover.json` | the **shared-instance** ladder, two arms | **withdrawn** (N-80) |
| `reports/evidence/inv_r1_e3_selection/RETRACTED.md` | the three retraction causes for the above | live |
| `reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.json` | the post-fix ladder; `$.postfix_fresh` is the fresh-instance two-arm run, `$.regenerated_shared` reproduces the withdrawn ladder, `$.shared_versus_fresh` is the per-cell diff | live except `$.committed_ladder` |
| `reports/evidence/inv_r1_e3_ladder/committed-ladder-status.json` | marks `$.committed_ladder` **withdrawn** (B6/N-80) | live |
| `reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.supersession.json` | `PARTIALLY_VOID` on `$.committed_ladder` only | live |
| `reports/evidence/inv_r1_e3_fitted_control/e3-fitted-control.json` | the **three-arm shared** crossover plus the fitted-rule records | live but shared-path |
| `reports/evidence/inv_r1_e3_selection/e3-admitted-operations.json` | decisions traced into admitted operations and receipts | live |
| `reports/evidence/inv_r1_e3_selection/e3-store-witness.supersession.json` | `$.severed` void, `$.connected` survives | live |

The records are real and the retractions are real. The confusion is entirely about which
path a number came from, and the two paths disagree.

---

## 2. The two paths, and why they differ

`crossover()` at `experiments/ad01/s09_e3_selection.py:133` builds **one** policy instance
and then loops worlds and budgets under it:

```python
policy = make_policy()          # line 177, outside the world loop
for world in worlds:
    run = run_policy(policy, world, budget)
```

Both policies are stateful. The agenda pops from `_untried`; `FixedPolicy` advances `_step`.
So one instance walks all three worlds and all six budgets. Its `resources_used_total` series
is a **cumulative prefix sum of a single traversal**, not six independent runs. That is N-80,
and it is the cause of the whole dispute.

`qualified_ladder()` and `e3_ladder.ladder(shared=False)` build a **fresh instance per
(arm, world, budget)**. Their agenda and default rows are identical to each other, and
differ from the shared path wherever the state carried across worlds mattered.

Both were recomputed below. The fresh path is the one that answers the assignment.

---

## 3. Recomputed budget table — fresh instance per (arm, world, budget)

**Denominator stated for every cell: the mean over three worlds `(0, 1, 2)` of
`held_out_reduction`, one independent run per world.** Per-world values are given because
the pooled sign hides a reversal at 30.

| budget | arm | w0 | w1 | w2 | pooled mean | resources | choices | diagnoses | retained |
|---|---|---|---|---|---|---|---|---|---|
| 8 | agenda | 0.000000 | 0.000000 | 0.000000 | **0.000000** | 21 | 3 | 0 | 0 |
| 8 | default | 0.000000 | 0.000000 | 0.000000 | **0.000000** | 18 | 3 | 3 | 0 |
| 8 | fitted | 0.000000 | 0.000000 | 0.000000 | **0.000000** | 18 | 3 | 3 | 0 |
| 14 | agenda | 0.084656 | 0.081890 | 0.084615 | **0.083721** | 42 | 6 | 0 | 3 |
| 14 | default | 0.000000 | 0.000000 | 0.000000 | **0.000000** | 36 | 6 | 3 | 0 |
| 14 | fitted | 0.000000 | 0.000000 | 0.000000 | **0.000000** | 36 | 6 | 3 | 0 |
| 20 | agenda | 0.084656 | 0.081890 | 0.084615 | **0.083721** | 42 | 6 | 0 | 3 |
| 20 | default | 0.000000 | 0.000000 | 0.000000 | **0.000000** | 57 | 9 | 3 | 0 |
| 20 | fitted | 0.139776 | 0.139776 | 0.139776 | **0.139776** | 57 | 9 | 3 | 3 |
| 30 | agenda | 0.112216 | 0.110833 | 0.112196 | **0.111748** | 84 | 12 | 6 | 6 |
| 30 | default | 0.166667 | 0.166667 | 0.000000 | **0.111111** | 81 | 12 | 5 | 2 |
| 30 | fitted | 0.175257 | 0.175257 | 0.175257 | **0.175257** | 81 | 12 | 6 | 6 |
| 40 | agenda | 0.145057 | 0.144135 | 0.145043 | **0.144745** | 108 | 15 | 9 | 9 |
| 40 | default | 0.317460 | 0.301407 | 0.458974 | **0.359281** | 108 | 15 | 8 | 5 |
| 40 | fitted | 0.210738 | 0.210738 | 0.210738 | **0.210738** | 108 | 15 | 9 | 9 |
| 60 | agenda | 0.206063 | 0.205510 | 0.206055 | **0.205876** | 165 | 21 | 15 | 15 |
| 60 | default | 0.367725 | 0.346320 | 0.458974 | **0.391007** | 138 | 18 | 11 | 8 |
| 60 | fitted | 0.183852 | 0.187259 | 0.189984 | **0.187032** | 180 | 24 | 18 | 18 |

**Sign of the comparison, on this table:**

| budget | agenda vs default | agenda vs fitted |
|---|---|---|
| 8 | tie (0 = 0) | tie (0 = 0) |
| 14 | **agenda ahead** | **agenda ahead** |
| 20 | **agenda ahead** | **fitted ahead** |
| 30 | **agenda ahead** (pooled) | **fitted ahead** |
| 40 | **default ahead** | **fitted ahead** |
| 60 | **default ahead** | **agenda ahead** |

**The 30 cell is a per-world reversal.** The default scores 0.166667 on worlds 0 and 1 and
0.000000 on world 2. The agenda's pooled lead of **0.000637** is produced entirely by world 2,
where the default has nothing to reduce. On worlds 0 and 1 the default is ahead of the agenda.
The pooled sign at 30 is a tie decided by one degenerate world and must never be reported
without the per-world row beside it.

**This table agrees with the committed fresh path** (`e3-postfix-ladder.json` `$.postfix_fresh.ladder`)
to every digit.

### Does it agree with the prose?

`reports/workstreams/w0-tr05.md` §4b agrees exactly. But **§4b's summary sentence does not
agree with the table it sits above**, and this is a real error in the current tree:

> "Pooled sign vs development-fitted control: agenda ahead at **every** budget
> (`fitted_control_ahead_on_held_out_at` is empty)."

That is wrong on the fresh path. The fitted control is ahead of the agenda at **20, 30 and 40**.
The reason the sentence looks true is that `fitted_control_ahead_on_held_out_at: []` is a
field in `e3-fitted-control.json`, which is a **shared**-path three-arm artifact. Its fitted
column there reads 0.046592 / 0.070246 / 0.061284 at 20/40/60, values that exist only because
the fitted policy's state carried across worlds. On the fresh path the fitted control reads
0.139776 / 0.175257 / 0.210738 and beats the agenda. The sentence read a shared-path field and
attached it to a fresh-path table.

The task brief's instruction to resolve the control conflict is therefore not only a prose
problem. One of the two controls was being read off the wrong path.

---

## 4. The 2.7x and the budget-30 crossover: REPRODUCIBLE

**Both reproduce from source records, and the reverted ledger line was correct.**

### The oracle, recomputed from scratch

All 196 constant rules, one fresh policy instance per (rule, world), 1176 runs per budget,
368.4 s total. No value read off any prose.

| budget | best-in-space **mean** | best-in-space **sum** | sum / mean | rules beating default | rules beating fitted | rules tied at best |
|---|---|---|---|---|---|---|
| 8 | 0.000000 | 0.000000 | n/a | 0 | 0 | 196 (vacuous) |
| 14 | 0.000000 | 0.000000 | n/a | 0 | 0 | 196 (vacuous) |
| 20 | **0.139776** | **0.419328** | 3.0 | **96** | 0 | 84 |
| 30 | **0.175257** | **0.525770** | 3.0 | **94** | 0 | 10 |
| 40 | **0.359281** | **1.077842** | 3.0 | 0 | 8 | 8 |
| 60 | **0.414277** | **1.242831** | 3.0 | 4 | 84 | 4 |

The counts column matches the committed table in `reports/STAGE-09-HANDOVER.md:157-158`
(beats `DEFAULT_RULE`: 0/0/96/94/0/4; beats the fitted control: 0/0/0/0/8/84) at every budget.

### The defect that produces 0.419 and 0.526

`experiments/ad01/agenda_policy.py:424`, `_score_constant_rules`:

```python
scores.append((sum(
    selection.run_investigations(...)...yield_.as_dict()[objective]
    for world in worlds), rule))
```

It returns a **sum over three worlds**. Every arm row in the ladder reports a **mean**
(`s09_e3_selection.py:281`, `"held_out_reduction_mean": sum(reductions) / len(reductions)`).
So `best_held_out_reduction` is exactly **3x** the scale of every number it is read beside.
My run confirms the ratio is 3.0 to floating-point at every non-zero budget.

That is the whole of it. The fix is not a better denominator, it is the same denominator.

### The two figures, derived

- **0.419** = `best_sum` at budget 20 = `0.139776 x 3` = `0.419328`, rounded to 3 places.
- **0.526** = `best_sum` at budget 30 = `0.175257 x 3` = `0.525770`, rounded to 3 places.

Both are in `reports/STAGE-09-HANDOVER.md:165` and in commit `73dc7fd`. Neither is in any
committed JSON. They are the sum-denominated oracle, written down.

### The 2.7x, derived

`0.419328 / 0.1568834941383961` = **2.6729**, which rounds to **2.7**.

- Numerator: best-in-space, budget 20, **summed** over three worlds.
- Denominator: agenda, budget 20, **averaged** over three worlds, on the **shared** path
  (`e3-crossover.json` `$.crossover.per_budget[1].agenda_held_out`).

So the 2.7x is real arithmetic over two real record values. It is also a denominator
artifact, and the reverted line's description of it is exactly right.

**Corrected, on one denominator.** Using the fresh mean for both sides:

| comparison at budget 20 | value | ratio |
|---|---|---|
| oracle sum / agenda shared mean (as reported) | 0.419328 / 0.156883 | **2.67x** |
| oracle **mean** / agenda **shared** mean | 0.139776 / 0.156883 | 0.89x — **agenda ahead** |
| oracle **mean** / agenda **fresh** mean | 0.139776 / 0.083721 | **1.67x** — oracle ahead |

The 2.7x does not survive. But the corrected 1.67x is still the oracle ahead, so the
substantive claim underneath it — that a rule in the space beats the agenda at budget 20 —
survives the correction. The margin does not; the direction does.

### The budget-30 crossover: NOT REPRODUCIBLE as stated

The reverted line read "loses to best-in-space **from budget 30 up**". On the corrected
mean denominator the crossover is at **20**, not 30:

| budget | agenda (fresh mean) | best-in-space (mean) | verdict |
|---|---|---|---|
| 8 | 0.000000 | 0.000000 | tie, 196 rules vacuously tied |
| 14 | 0.083721 | 0.000000 | **agenda ahead** |
| 20 | 0.083721 | 0.139776 | **oracle ahead** |
| 30 | 0.111748 | 0.175257 | **oracle ahead** |
| 40 | 0.144745 | 0.359281 | **oracle ahead** |
| 60 | 0.205876 | 0.414277 | **oracle ahead** |

The first budget at which the agenda is below best-in-space is **20**. Budget 14 is the
only budget where the agenda beats it, and that is because the best-in-space score there
is 0.000000 with all 196 rules tied.

Where "from 30 up" most likely came from: on the fresh path the agenda **does** beat the
*specified default* at 14, 20 and 30, and loses to it at 40 and 60. Reading the default's
crossover as the oracle's crossover gives 30. The two controls cross at different budgets,
and the line attributed 30 to the oracle.

**Verdict: the line was half right and half wrong, in a way that understated the loss.**
The 2.7x denominator-artifact half is fully correct and fully reproducible. The budget-30
half is not reproducible and the true crossover is 20.

---

## 5. The control conflict, resolved

There are **four** quantities in play, not three. The fourth is the one the prose mixes up.

| # | Thing | Identity | Reads | Deployable? |
|---|---|---|---|---|
| 1 | **Specified default** | `FixedPolicy.DEFAULT_RULE = {"software": ("ddmin", 5), "graph": ("ddmin", 1)}`, `agenda_policy.py:212` | nothing at run time | yes |
| 2 | **Development-fitted allocation control** | `fitted_fixed_rule(budget)`, `agenda_policy.py:292`, objective `retained_behaviors` | development retention only | yes |
| 3 | **Held-out best-in-space oracle** | `constant_rule_search` / `control_competence`, `agenda_policy.py:382` / `:455`, objective `held_out_reduction` | the reported metric | **no — retrospective reference** |
| 4 | **The sum/mean mismatch** | `_score_constant_rules` returns a sum; ladder rows report a mean | — | not a control at all |

**1, 2 and 3 are three genuinely different things**, and the source distinguishes them
correctly. `s09_e3_selection.py:295` writes `best_rule_is_an_arm = False` on every row.
`constant_rule_search` carries `use: "qualify a control; never an arm in a reported ladder"`.
That part of the labelling discipline is already in the source and needs no repair.

**4 is what the prose was actually arguing about**, and the source does not carry a label
for it because it is a defect rather than an entity. It is a scale mismatch between two
numbers that were never on the same scale.

**What each source calls "the control":**

| source | calls it | actually is |
|---|---|---|
| `WORKER-PROMPT.md` §W3/E3 | "a competent development-fitted allocation control and the specified default" | items 2 and 1 — **correct** |
| `s09_e3_selection.py:94` docstring | "the historical `control`" | item 1 |
| `s09_e3_selection.py:102` docstring | "`fitted_control`" | item 2 — correctly described as reading no held-out score |
| `STAGE-09-HANDOVER.md:165` | "the best rule in its own family" | item 3 — **an oracle, presented as a control** |
| `w0-tr05.md:87` | "0.419 against 0.157" | items 3 and the agenda, **on different denominators** |

The conflict is therefore resolvable without choosing a winner. The assignment already
named the two deployable controls. The handover's "best rule in its own family" is neither
of them.

### Labelling rule applied

`best-in-space` is a **retrospective reference**, not a deployable control, in every place
it appears in this report. It is fitted by exhaustive search on `held_out_reduction`, the
metric the study reports. No run-time control may read that metric, so the rule it selects
could not be deployed — a control that needs to see the answer. It qualifies arms. It never
measures an arm against another arm.

**No cell in the table above is a win for the agenda against it**, and the `gap agenda→oracle`
column is a diagnostic, not a result.

---

## 6. Decisions traced into admitted operations

One concrete cell, fresh instance per arm, world 0, budget 20, from source. This is the
budget-20 cell where the oracle crossover lives.

**Agenda** — `ad01-policy-portfolio-agenda-v1`, stop reason `budget exhausted`

| seq | capability | target | charge | rationale |
|---|---|---|---|---|
| 0 | `seed-sw-ddmin` | `ad01-w0-dev-sw-00` | 7 | untried capability ddmin in the software line |
| 1 | `seed-sw-greedy` | `ad01-w0-dev-sw-01` | 7 | untried capability greedy in the software line |

yield `{"held_out_reduction": 0.084656, "resources_used": 14, "diagnoses_correct": 0, "retained_behaviors": 1}`,
2 choices, 2 executions, 0 refusals.

**Specified default** — `ad01-policy-portfolio-fixed-v1:graph=ddmin/1;software=ddmin/5`

| seq | capability | target | charge | rationale |
|---|---|---|---|---|
| 0 | `seed-gr-ddmin` | `ad01-w0-dev-gr-00` | 6 | pre-committed graph/ddmin step 1 of 1 |
| 1 | `seed-sw-ddmin` | `ad01-w0-dev-sw-00` | 6 | pre-committed software/ddmin step 1 of 5 |
| 2 | `seed-sw-ddmin` | `ad01-w0-dev-sw-00` | 7 | pre-committed software/ddmin step 2 of 5 |

yield `{"held_out_reduction": 0.0, "resources_used": 19, "diagnoses_correct": 1, "retained_behaviors": 0}`.

**Development-fitted control** — `ad01-policy-portfolio-fixed-v1:graph=greedy/2;software=ddmin/1`

| seq | capability | target | charge | rationale |
|---|---|---|---|---|
| 0 | `seed-gr-greedy` | `ad01-w0-dev-gr-00` | 6 | pre-committed graph/greedy step 1 of 2 |
| 1 | `seed-sw-ddmin` | `ad01-w0-dev-sw-00` | 6 | pre-committed software/ddmin step 1 of 1 |
| 2 | `seed-gr-greedy` | `ad01-w0-dev-gr-00` | 7 | pre-committed graph/greedy step 2 of 2 |

yield `{"held_out_reduction": 0.139776, "resources_used": 19, "diagnoses_correct": 1, "retained_behaviors": 1}`,
stop reason `pre-committed schedule complete`.

### What the system actually chose

**The agenda did not reuse a target it had already worked.** It picked two different
software targets (`sw-00`, `sw-01`) and never revisited either. It ignored the graph family
entirely at this budget. It **diagnosed zero** times while both fixed controls diagnosed
once each — the agenda is not spending envelope on diagnosis at all, and it still scored
higher held-out reduction than the default.

**The two fixed controls are a scripted campaign order, not an agenda.** Every choice above
carries the rationale `pre-committed <family>/<method> step N of M`. Nothing was selected in
response to anything. The default's schedule is 6 investigations wide; at loose budgets it
saturates and stops while the fitted rule keeps converting envelope, which is why the
default's `resources_used` plateaus at 46 on the shared path. That is a property of the two
rules, not a difference in what they were given.

**The agenda's choices are genuinely made, and the record is thin but real.**
`e3-admitted-operations.json` `$.connected.admitted_decisions` carries the same shape —
`operation_id`, `capability_id`, `charge`, `max_queries`, `dispatch_state: observed`,
`receipt_outcome: success`, `settled: true` — read back out of the receipts table by SELECT.
So the decisions do reach admitted operations and outcomes, not just a policy object's
internals. In the fresh, database-free run above, `adopted_operations` is 0 and
`adoption.adopted` is false, because that run has no study store attached; the admitted
operations live in the recorded artifact, not in this harness.

**The fresh-instance defect is visible in the traces.** Under `crossover()` a single
`FixedPolicy` walks worlds 0, 1, 2 in sequence, so `step 1 of 5` in world 1 is the step that
world 0's consumption left it on. The two sets of numbers above are not reachable from each
other, and the shared path's is the wrong one.

---

## 7. What E3 demonstrates, and what it does not

E3 demonstrates that a stateful selection policy, given the same finite envelope as a
pre-committed schedule, chooses different targets than the schedule does, reaches admitted
operations, and scores higher held-out reduction than the specified default at budgets 14,
20 and 30. It demonstrates that no constant rule in its own 196-rule space beats the
development-fitted control at 14, 20 or 30, and that the specified default is beaten by
96 of 196 rules at 20 and 94 at 30.

E3 does **not** demonstrate autonomous selection. Both controls are scripted campaign
orders, so the comparison is a policy against two schedules, and the agenda's only
discriminating behaviour at the traced cell was declining to diagnose and declining to
reuse a target. It does not demonstrate agency: three worlds, one finite budget ladder, one
metric, no transfer, and a pooled sign at 30 that a single degenerate world decides. Its
own ledger line records that an agenda advantage would be "an advantage over a rule most of
the space beats," and the records confirm that for the default at 20 and 30.

**No cell is a win for the agenda against the oracle, and the corrected crossover is 20,
not 30.** The agenda is below best-in-space at 20, 30, 40 and 60.

---

## 8. Undetermined

- **Whether the fitted control's inflation from fitting and evaluating on the same `dev`
  targets is material.** The overlap exists in the code. Sizing it needs a holdout-split fit,
  which is a redesign and out of scope here.
- **Whether `retained_behaviors` and `held_out_reduction` correlate across the 196-rule
  space.** I have per-budget agreement at the optimum and no rank correlation. My 196-rule
  run kept only the aggregates, so this is not recoverable from what I computed.
- **Whether any test guards the sum/mean mismatch.** `w0-tr05.md:445` records 37 tests passing
  with the oracle defect present, and names
  `test_the_agenda_never_beats_the_best_rule_where_any_rule_qualifies` as comparing a mean
  against a sum. I did not run it, so I report that as read, not as measured.
- **The three unrun confirmations named in `w0-tr05.md:459-470`** (rank correlation, the
  holdout-split fit, and the interrupted competence suite) remain unrun by this lane.

## 9. Proposed correction for the coordinator

The reverted line should be restored in corrected form, not as written. Every clause of it
is traceable, and one clause is wrong:

> E3 recomputed from source at the measure freeze. On fresh policy instances per
> (arm, world, budget), with the mean over worlds as the denominator, the agenda is below
> the held-out best-in-space oracle from **budget 20 up**, not 30. The apparent 2.7x margin
> at budget 20 (0.419 against 0.157) was a denominator artifact: 0.419 is three worlds
> **summed** and 0.157 is three worlds **averaged**, a ratio of exactly 3.0 between the
> oracle's scale and the arms'. Corrected to one denominator the margin is 1.67x. The oracle
> is a retrospective reference, not a deployable control.

I did not edit `reports/PROJECT-LEDGER.md`. That is the coordinator's call, and the line as
previously written is half wrong in a way that understates the loss.
