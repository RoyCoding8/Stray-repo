> Historical batch report. Current scoped status is reconciled in [PROJECT-INVENTORY.md](PROJECT-INVENTORY.md) and [PROJECT-LEDGER.md](PROJECT-LEDGER.md). Read this file for its source revisions and measurements; its completion prose does not govern the current checkpoint.

# Stage 9 architectural recommendation

Replacement for §5 of `reports/STAGE-09-COMPLETION-MATRIX.md`. Written after three
independent review passes and after lane `w4-leakage` measured the E4 headroom
directly.

**What this replaces, and why.** A first draft of this file recommended passing
the real observation vector to `choose_query`. That recommendation is void. It
named a no-op as the mechanism, and anyone who had tried it would have seen no
change and concluded the reducer cannot choose well. §1 states the correct
diagnosis and §2 states the experiment that decides the part nobody has decided.

**What I ran.** No live model calls, no Jev, no paid route, no test files, no
suite. I read source lines, read committed JSON artifacts, ran `git log` and
`git show --numstat`, and read the r3 and r4 evidence directories. Every figure
below names its artifact or its `file.py:line`.

**Scope.** This file is the recommendation only. The coordinator owns replacing
§5 in the matrix and correcting the state labels. Every change named here is a
change to something that already exists. No new subsystem, no DSL, no framework.

---

## 0. The one correction that invalidates the draft

`experiments/ad01/learner_revision.py:966-977` builds the evidence sequence that
`evidence_ceiling` scores. The loop calls `choose_query` and records the pick.
It never calls `learner.observe`. Here is the whole loop.

```python
for _ in range(_rules.MAX_QUERIES):
    pick = learner.choose_query(
        {x: (0,) * _rules.N_OUTPUTS for x in queried})
    if pick is None:
        break
    chosen.append(pick)
    queried.add(pick)
```

`choose_query` (`rule_learner.py:40-50`) reads only `len(queried)` and
`x not in queried`. It never reads a value. So the zero vector at `:972` is
inert, and the sequence is a function of the seed and the tie-break RNG alone.

The draft read the zero vector as "no information yet" and recommended replacing
it. The defect is not the value. The defect is that no `observe` call ever
narrows `self._candidates` (`rule_learner.py:22`), so `_disagreement` (`:33-38`)
scores the full 224-table class at all eight steps. The object built at `:967` is
not a learner. It is a tie-break RNG over a static disagreement function.

**The factorial that settles it.** Lane `w4-leakage` ran a 2 by 3 design over
`observe` and over the value fill (the lane record `w4-leakage.md` restates the measurement; its three JSON artifacts are **not** on HEAD, 150 fresh seeds,
`audit` split):

| cell | unqueried | overall | distinct sequences | identical to shipped |
|---|---|---|---|---|
| observe=False, values=zero | 0.5208 | 0.7604 | 150 | 150 of 150 |
| observe=False, values=real | 0.5208 | 0.7604 | 150 | 150 of 150 |
| observe=False, values=garbled | 0.5208 | 0.7604 | 150 | 150 of 150 |
| observe=True, values=zero | 0.8958 | 0.9479 | 150 | 0 of 150 |
| observe=True, values=real | 0.8958 | 0.9479 | 150 | 0 of 150 |
| observe=True, values=garbled | 0.8958 | 0.9479 | 150 | 0 of 150 |

All three value fills give byte-identical sequences within an `observe` level.
The values are not the variable. `observe` alone moves the number.

**The note at `:992-994` is false as written.** It reads "the frozen reducer's
own eight-input evidence set". The number measures a disagreement-ordered
random subset, because the disagreement function is uninformative. That note is
what carried the wrong mechanism into the first draft, so it is named here rather
than patched around.

**The object is not a learner, and the draft's own experiment was the proof.**
The draft's recommendation was a no-op by construction. A reviewer who had
applied it and run the same factorial would have found the `values=real,
observe=False` cell identical to the shipped one, and the natural but wrong
conclusion is that the reducer cannot choose well. A freeze would have been
burned to discover nothing.

---

## 1. The E4 diagnosis, stated correctly

### 1.1 The effect is real and it is not leakage

Lane `w4-leakage` (`w4-leakage.md`; its `w4-leakage.json` is **not** on HEAD) ran the informed arm on three cohorts.
Disjointness is measured at the truth-table level, not the seed integer, because
`make_task` (`boolean_rule.py:151-163`) derives tables from a hash of
`split` and `seed`, so different seeds could in principle collide. They do not:
150 distinct tables per cohort and zero intersection in every pairing.

| cohort | metric | incumbent | blind (shipped) | informed | paired delta | z |
|---|---|---|---|---|---|---|
| original, seeds 0-149 | unqueried | 0.0587 | 0.5017 | 0.8500 | +0.3483 | +11.38 |
| fresh_a, seeds 1000-1149 | unqueried | 0.0591 | 0.5208 | 0.8958 | +0.3750 | +13.17 |
| fresh_b, seeds 2000-2149 | unqueried | 0.0596 | 0.5292 | 0.9142 | +0.3850 | +14.67 |
| original, seeds 0-149 | overall | 0.1175 | 0.7508 | 0.9250 | +0.1742 | +11.38 |
| fresh_a, seeds 1000-1149 | overall | 0.1179 | 0.7604 | 0.9479 | +0.1875 | +13.17 |
| fresh_b, seeds 2000-2149 | overall | 0.1183 | 0.7646 | 0.9571 | +0.1925 | +14.67 |

The effect grows on fresh cohorts rather than collapsing. On fresh_a the informed
mean sits at the 98.8th percentile of 400 random eight-input subsets (blind
distribution mean 0.5184, sd 0.1344, p05 0.365, p95 0.780).

**The clincher is the cross-split control.** Choose the sequence on a task that
shares no truth table with the task it is scored on:

| choose split | score split | truth-table overlap | informed | blind | delta | z |
|---|---|---|---|---|---|---|
| audit | audit | 150 of 150 | 0.8958 | 0.5208 | +0.3750 | +13.17 |
| qual | audit | 0 of 150 | 0.7883 | 0.5208 | +0.2675 | +8.38 |
| dev | audit | 0 of 150 | 0.7342 | 0.5208 | +0.2133 | +6.49 |

Leakage needs the arm to read what it is scored against. It cannot produce a gap
against a task it cannot see. The `qual` arm retains `+0.2675` at z=+8.38 with
zero overlap. The residual gradient is what transfer between independently
sampled target tables looks like.

A tripwire on the answer key reports 8 table reads per seed, all from `query()`
itself, and the public view carries no table
(the `answer_key_tripwire` control; `w4-leakage-controls.json` is **not** on HEAD).

### 1.2 The rival diagnoses are each excluded by measurement

**Not the revision boundary.** Its own reachable range is `0.00622` on the
original cohort and **`-0.000889` on fresh_a** at z=-0.33. On fresh seeds the
boundary expresses nothing at all. A revision of the boundary cannot reach
headroom the boundary cannot express.

**Not the query budget.** Both arms spend the full 8 of 8. At budgets 1 and 2
the informed-minus-blind delta is `+0.0000`. At budget 4 it is `+0.0150` at
z=+1.92 on fresh_a (`+0.0117`/z=+1.62 on original, `+0.0172`/z=+2.08 on
fresh_b; `paired`, `learner_revision.py:860-874`). The effect appears only at
the full budget, where both arms have identical budgets. An earlier revision
of this section gave `+0.0125` at z=+1.10; no cohort on the `audit` split
reproduces either figure, and `+0.0125` is the same fabricated value §3 was
corrected for.

**Not the denominator.** Both arms ask for 8 inputs, so both are scored over the
same 8. The gap is `+0.3750` on `unqueried` and `+0.1875` on `overall`. It halves
and survives.

### 1.3 The ceiling number

`0.00622` is a **selected max-minus-min over 16 inputs**. `z` is 1.42.

It is not chosen on the data it is scored on. `learner_revision.ceiling()`
(`learner_revision.py:909`) half-splits the cohort — `search =
list(search or seeds[0::2])` — and takes the argmax on that half while scoring
on the other. Its docstring at `:915-916` says the ceiling "is not the maximum
of the numbers it is reported next to."

The `2.33x` figure that an earlier revision carried does not compare anything.
It divided `0.00622` (`result.json` `$.ceiling`, `audit`, 75 scoring seeds, best
x=7 against worst x=15) by `0.002667` (`headroom.json` `$.ceiling.input_means`,
`dev`, 1500 population seeds, best x=13 against worst x=11, from
`make_evidence.py:147-166`). Different split, cohort, code path and selected
inputs; `result.json` carries no `input_means` key at all. The arithmetic was
right and the comparison meaningless.

Nothing in this recommendation needs a ceiling number. The two-element-menu
argument in §6 is arithmetic on `_STRATEGY_SOURCE` and needs no measurement.
Any recommendation that rests on `0.00622` rests on a **max-minus-min over 16
inputs** -- selected in the sense that it names the two extremes, and not
scored on its own selection data, because `ceiling()` half-splits for exactly
that reason.

### 1.4 What the diagnosis does and does not imply

The diagnosis says the capability is present, wired and correct, and disabled by
an omitted call. It does not say the algorithm is inadequate. The two imply
opposite recommendations, and the matrix's §3.6 still carries the first draft's
version of the second.

---

## 2. The open question, and the experiment that settles it

`WORKER-PROMPT.md:86` says a revision "must alter the learner, not just solve
the downstream task or add advice to a prompt". Whether restoring `observe`
counts as altering the learner is unresolved, and the distinction below is the
whole point.

**Question A, the reporting correction.** The shipped `evidence_ceiling` is a
measurement over a frozen reducer, not a run of the learner. Its note claims it
measures "the frozen reducer's own eight-input evidence set". It does not.
Making it measure what its own note claims is a reporting correction to a
harness, in the same class as adding the `overall` denominator in §3. No freeze
is required because no descendant's behaviour changes.

**My judgment: A is a reporting correction and needs no freeze.** Three reasons.
`evidence_ceiling` is computed inside the study, after the arms ran, and nothing
downstream consumes its value. It is the same class of object as `ceiling`
(`learner_revision.py:909`), which is also a measurement against the sealed
results and which nobody has called a change to the learner. And the number it
produces is currently wrong in the direction that overstates a gap. A number that
is mislabelled and too large is the thing a reporting correction exists to fix.

**Question B, the descendant's own evidence.** Whether a descendant may choose
its evidence against real observations, so that `descendant_score` (`:507`) and
the descendant-construction path gather informed evidence rather than a fixed
eight-element subset, is a different question and genuinely needs a fresh freeze.
It changes what a descendant is. It is not a reporting fix.

**Do not conflate them.** A reviewer who fixes A and then claims B is settled
has skipped a freeze. A reviewer who calls B unrunnable has misread the repair.

**The experiment that settles B.** Build the descendant path so the evidence
sequence is chosen by the reducer against the descendant's own observations, and
run three arms paired by seed under one fresh freeze, scoring on `overall`:

1. The incumbent as it is now, one input.
2. A descendant with a blind eight-input subset, a per-seed random draw with no
   selection.
3. A descendant with an informed eight-input sequence, the same
   `VersionSpaceLearner` given each observation as it is gathered, with
   `observe` called per pick.

Arm 3 must beat arm 2 by a margin excluding zero on `overall`, on a fresh cohort
whose truth tables are disjoint from the ones the sequence was chosen on. If it
does not, arm 3 is a task-solver change dressed as a learner change and the
descendant keeps a blind subset. If it does, the boundary is not the lever and
the evidence sequence is.

The `qual`-versus-`audit` control in §1.1 is the leak tripwire for this. A
descendant that needs the scored task's own truth table to choose shows the gap
collapsing when the choice task and the score task share no table.

**The offline precursor, which needs no freeze.** Restore the `observe` call
inside `evidence_ceiling` only, and re-run the three-cohort ladder plus the
cross-split control. If the `overall` deltas hold and the cross-split gap stays
well clear of zero, B has an offline measurement behind it before anyone spends a
freeze on it. This is Question A's repair, and it is the cheap half.

---

## 3. The `overall` denominator, and what `unqueried` was doing to the ladder

`RuleSession.score` (`boolean_rule.py:290-308`) reports `overall` as a mean over
all 16 inputs, `queried` over the inputs asked, and `unqueried` as a mean over
`N_STATES - n_queried`. **The `unqueried` denominator moves with the budget.** Ask
one input and the mean is over 15. Ask eight and it is over 8.

All four rows are measured, not carried: `audit` split, cohort
`fresh_a` `range(1000,1150)`, 150 seeds, both arms scored by
`improve_channel.descendant_score` (`improve_channel.py:507-535`). Regenerate
with `uv run python -m experiments.ad01.e4_budget_ladder`, which writes
[`evidence/inv_r1_e4/budget-ladder.json`](evidence/inv_r1_e4/budget-ladder.json).
The budget-8 row reproduces the `0.5208`/`0.8958`/`+0.3750` triple this
document already reports at `:93-95`, which is what fixes the construction as
the intended one.

| budget | n_queried | unqueried denominator | blind unqueried | informed unqueried | delta |
|---|---|---|---|---|---|
| 1 | 1.0 | 15 | 0.0547 | 0.0547 | +0.0000 |
| 2 | 2.0 | 14 | 0.0581 | 0.0581 | +0.0000 |
| 4 | 4.0 | 12 | 0.0950 | 0.1100 | +0.0150 |
| 8 | 8.0 | 8 | 0.5208 | 0.8958 | +0.3750 |

These four rows are measured and the artifact holds them. An earlier table in
this document carried no measurement behind it at all, and a `0.9083` in its
budget-8 informed cell — which decomposes to `0.5208 + 0.3750 + 0.0125`, the
budget-4 delta added into the budget-8 row. It survived eleven review rounds
because a grep for `0.9083` returns exactly one hit, and one hit reads as
clean. `e4_budget_ladder.py` exists so the next reader does not have to
re-derive this.

**Where it bites.** The incumbent (`improve_channel.py:496`,
`INCUMBENT_EVIDENCE = (3,)`) gathers one input, so it is scored over 15 on
`unqueried` while the reducer is scored over 8. The `0.0587`-versus-`0.5017` gap
in the shipped `evidence_ceiling` is partly that artifact. On `overall` the
incumbent is 0.1179 and the reducer 0.7604. Still a real gap, smaller and
better-founded.

**What `unqueried` was doing to the ladder.** It inflated every step. A
descendant that queries 1 input and gets them all right scores `unqueried`
1.0000 over the remaining 15, while `overall` is 0.0625. The reported budget
ramp is therefore not a statement about how much evidence is worth. It is partly
a statement about a shrinking denominator. The ladder in §3 above shows the
effect: at budget 1 both arms read `0.0547` and the delta is exactly zero.

**That zero is the arms choosing the same input, not the denominator pinning
them.** Both arms are scored over the *same* 15 unqueried inputs at budget 1, so
a shared denominator cannot by itself make two different choices score alike.
What makes them alike is that the zero vector is inert: on the un-narrowed
candidate set `_disagreement` returns `448` for every input, so `max` ties
across all sixteen and both arms draw the same one from the same seed. After a
single `observe` the disagreements collapse to one value again, so the informed
second pick is uniform too — which is why the arms still agree at budget 2 and
first diverge at budget 4 (measured: 0 of 150 seeds differ at prefixes 1, 2 and
3; 78 of 150 at prefix 4). The delta is zero because there is nothing to
separate, which is the opposite of a finding.

**`overall` is the defensible denominator for any cross-arm claim**, because it
is the only one that keeps arms with different evidence counts on the same set
and it is the only one that keeps the incumbent comparable. Report `unqueried`
beside it, never instead of it.

**One note, because the two denominators are not interchangeable in the other
direction.** `overall` counts a queried input as correct when the model happened
to predict it, which is a real thing to count. It is not the benefit metric a
sealed evaluator would pick for an evidence-quality claim, and `unqueried` was
not that metric either. `overall` is defensible for cross-arm comparison, not
because it is the right benefit statistic. The coordinator owns which is assigned.

---

## 4. Three bottlenecks

The cap is three, per `WORKER-PROMPT.md:104`. The matrix's own §1 calls the E2
re-run "the largest remaining question after E1" and §4 does not list it. All
three of the listed bottlenecks require building, and E2 requires running
something that already exists. That is why the list inherited the batch's
momentum toward construction.

### B1. The E2 contrast is null, and the panel closes its positive side

**This was "the E2 study is unrun" when written. It is now measured, and the
measurement changed the bottleneck rather than closing it.**

`5cf3fe8` ran the contrast across two namespaces with disjoint stores and
operation ids. The result is a null: relevant and irrelevant experience are
indistinguishable, and neither beats no-experience (both contrasts delta
-0.0909, deltas [0.0, 0.0, -0.2727], z -1.225). On `within-sw-02` both
experience arms switched to `seed-sw-greedy` and the control did not, so the
two moved identically. The separation that exists is experience-versus-none,
not relevant-versus-irrelevant.

**Two things make the null uninformative about experience, and both are
located, not guessed:**

1. **The contrast is not 0.0 by arithmetic.** `_reduction_of`
   (`e2_replication.py:1322`) reads `NORMALIZED_REDUCTION`, not `action`, and
   every row in `invr1e2contrastr2/report.json` carries both. The per-task
   values give delta `0.4545 - 0.7273 = -0.2727`, a real difference; the
   campaign's driver bypasses `_measured_row` deliberately. A wiring defect of
   that kind may still exist in `_measured_row` for callers that use it. It
   does not explain this contrast, and the bottleneck ordering below does not
   rest on it.

2. **The panel closes the positive side.** A reachability census over the
   whole decision grid, offline and with no model, shows `ddmin@8` -- the
   zero-information default -- is the best of twelve reachable cells on all
   three targets. The largest positive delta the panel admits is **0.0**; the
   negative side reaches 0.538. The instrument can report a policy that does
   worse and cannot report one that does better.

**So the bottleneck is not "run E2" any more. It is: wire the repaired leg to
the report, and give the panel a positive side.** The first is a wiring fix in
`e2_replication`. The second is a panel-construction change and needs its own
freeze. Neither is a new prompt and neither is a new subsystem, which is why
this remains first: it is the only item that can turn a null that is
structurally uninformative into an answer.

Two further defects of the same class are recorded and unpatched, because
`e2_replication` is not this lane's to edit: `verdict` is `preserved` on all
1728 reducer outcomes the panel can produce, because both reducers only emit
legal deletions that keep the witness, so a reducer's output cannot fail; and
the prompt names `reason` while `packet.project_observations` drops it.

**Evidence.** `WORKER-PROMPT.md:68-74` specifies four contrasts (relevant versus
absent versus irrelevant or shuffled; retained reuse versus cold reacquisition;
within-domain versus held-out-domain; controlled observation perturbations) plus
two independent campaign namespaces. The matrix's §1 and §3.4 record all of them
unrun or void. The `inv_r1_e2_transfer` contrast is **RETRACTED**: its scored
re-run is a three-way tie at `score: 1.0` on all three arms, computed through
the constant `QUALITY` leg that `d42049c` deleted.

**The chronology is the finding.** `d42049c` is dated 2026-09-29 21:31:41 -0400.
Every E2 evidence directory on disk predates it. I checked each with
`git merge-base --is-ancestor`:

| evidence directory | newest commit | date | relative to `d42049c` |
|---|---|---|---|
| `inv_r1_e2_relevance` | `4df45b2` | 2026-09-28 | pre-repair |
| `inv_r1_e2_scored` | `169c341` | 2026-09-27 | pre-repair |
| `inv_r1_e2_retention` | `8c35f13` | 2026-09-26 | pre-repair |
| `inv_r1_e2_transfer` | `567efae` | 2026-09-26 | pre-repair |

**Why this is the batch's only repaired-and-unrun artifact.** `d42049c` carries
a red-proof against old code (`assert [0.0, 0.0] == [0.5, 0.75]`) and no proof
against a real question. A repaired instrument that has never been run is an
untested repair, and E2 is the only one in the batch.

**Cost.** No new prompts, no new freeze, no new subsystem. The four contrasts are
written. `s09_e2_relevance.py:124` `score_from_proposals` is documented as
"Compare two already-settled acquisitions, no dispatch", which is what makes a
first pass cheap. I have not verified that a first pass runs against the settled
records on disk, and that is the one open question about this bottleneck's cost.

**What I expect.** A null, and I say so before the run. `invl02_liveacq_r4`
records `mean_acquired_minus_control: -0.1528` and `utility: "CONTROL_WINS"` over
three paired tasks. If the repaired metric also returns no separation, the
finding is that this instrument cannot demonstrate experience benefit on this
world, which is a real answer and the only kind this batch has produced.

**What would falsify the recommendation to run it.** If the offline path cannot
run without a fresh freeze, E2 stops being the cheapest item in the batch. I did
not verify that, and it is the one open question about this bottleneck's cost.

**The state label is wrong in the same edit.** The matrix's W2 row reads
`completed`, which contradicts the matrix's own reading rule at `:10`, "An unrun
study does not". It should read `implemented` or `qualified`. Pass 2 reached the
same conclusion independently.

### B2. E1 has one acquisition prompt for the Boolean output world, and the cap sheet marks all nine cells supported

**Evidence.** `render_output_prompt` (`live_construct.py:100`) is the only
acquisition prompt for the Boolean output task, and `OUTPUT_TASKS` (`:51`) holds
two seeds, `{"qual": 11, "audit": 23}`. `output_operation_id` (`:113-118`)
refuses any other split, seed or attempt. The cap sheet at
`reports/cap-sheets/w1-e1-cap.md:71-75` marks the Boolean and ordering rows
plain `supported` across all three representations.

**A correction to the draft and to pass 3, and it is not a small one.** Both said
E1 has one prompt and therefore one constructible cell of nine. That is wrong
about the tree. There is a second acquisition prompt path,
`experiments/ad01/packet.py:342` `render_construction_prompt`, reached from
`experiments/ad01/construct.py:56`, and the r4 campaign used it. The r4 evidence
records three `model-acquired` ENTRY programs with `bound_equals_candidate: pass`
and `executed_bytes_are_the_bound_policy: pass` (`invl02_liveacq_r4/verdicts.json`).

The precise scope is what matters. `candidate_shape` (`packet.py:263`) branches
on `family` and serves exactly two, `graph` and `software`. Neither is the
Boolean output world and neither is a typed AST. `ordering` does not appear in
`packet.py` or `construct.py` at all. So:

- The **Boolean output world** has one prompt (`render_output_prompt`).
- The **method-repertoire construction path** has a second prompt
  (`render_construction_prompt`), serving the `software` and `graph` families,
  and it has produced three live acquisitions.
- The **ordering world and the typed AST representation** have no acquisition
  prompt anywhere in the tree.

**The protocol offers 4 distinct prompts per arm and no repetition axis.**
`ModelRequest` (`src/settlement/gateway.py:72`) carries `model`, `messages`,
`max_output_tokens`, `deadline_ms`, `operation_id`, `dispatch_generation` and
`reasoning_effort`. It carries **no temperature, no top_p and no seed**. So the
only way to get variation is to change the prompt. The r3 manifest says this in
its own words: "the protocol offers 4 distinct prompts per arm and no repetition
axis. n is reported as draws, never as independent opportunities". **n is
draws.** The cap sheet's n=4 was never reachable, and pass 2's finding that r2's
four lineages per arm were four repeats of one prompt holds, with the mechanism
now named: there is no sampling parameter to vary.

**The 512-character cap is a protocol constant that no shipped code justifies.**
r3's manifest says the campaign "inherited the literal; no shipped code derives
the number". `live_construct.py` states the limit at `:44`, in the prompt at
`:61` and `:110`, and enforces it at `:1539`, `:1662` and `:1696` inside the
campaign lane's own verification path. No `render_output_prompt` or
`extract_and_validate_boolean` compares a response's length against it.

**It does not explain r3's outcome.** r3 ran at two caps, and cap B is the
unbounded parser-implied limit. Under cap A, 3 records are `invalid-program` for
over-length at 4,685, 5,425 and 4,805 characters. Under cap B, the same three
are `invalid-program` with `detail` "boolean payload is not JSON". **Cap A and
unbounded both give 0 constructed.** The cap is not the binding constraint on the
answer, and a conforming answer is 143 characters. The binding constraint is
that this model reasons in prose before it emits the object, and that is a
property of the protocol, not a verdict on the model.

**The route's failure at the protocol's own 2048 output tokens is the largest
single cause, and the mechanism is not established.** r3 carries 12 records: **9
`transport-loss` at HTTP 502** and 3 `invalid-program`. The route is answering --
the campaign prompt returns **200 at 16 and 256 output tokens**, and a frozen id
absent from the 256-entry catalog still answers when dispatched. At 2048 the
route stops answering, but **the probe does not establish why**: the campaign
prompt at 2048 is a `TimeoutError` after 182 s and the only 502 recorded is
against a *short* prompt at 2048. The probe never crosses budget against prompt,
so "the budget, not the prompt" is unsupported, and an earlier revision of this
document asserted it in this passage while withdrawing it in §6. **A re-run at a
budget the route accepts is the cheap measurement and it has not been made.**
Any plan that opens more E1 cells at 2048 tokens will spend its ceiling on
transport loss.

**Cost.** Four acquisition prompts with parsers and operation-id rules, following
the pattern `render_output_prompt` / `extract_and_validate_boolean` /
`output_operation_id` already set. `WORKER-PROMPT.md:62` forbids hiding a Python
interpreter under an AST label or building a DSL to fill the matrix, and one
prompt per representation is the honest version of that.

**What would falsify this.** A route that returns 200s again, plus one
construction recorded on the Boolean output path, and this stops being the
largest remaining question. The draft's B2, "a live construction on the repaired
path", is folded in here rather than taking a third slot, because it is a
precondition for this one and not an independent question.

### B3. The E4 boundary is a two-element selector, and the headroom above it is a blind-sequence artifact

**Evidence for the boundary.** `_STRATEGY_SOURCE` (`improve_channel.py:136`) has
exactly two members. `leaf_construct` (`:1198`) installs one of them.
`REACHABLE_EVIDENCE` is therefore a two-element tuple whatever the reviser does.
Six of six admissible revisions were refused as `delegates-to-unchanged-reducer`,
correctly, and each reply computed `x = len(view["experience"])`, which is 0 on
the step that spends the probe.

**Evidence for the headroom, and the correction.** The matrix's §3.6 and §5
called `0.5017` against `0.00622` the most decision-relevant number in the batch
and used it to argue the boundary was the wrong architecture. §0 and §1 above
show the mechanism behind `0.5017` is a missing `observe` call in the harness
that built the sequence, and that `0.00622` is a max-minus-min over 16 inputs that `ceiling()` half-splits, so it is not scored on its own selection data. The earlier '2.33x the unselected spread' figure is withdrawn as a cross-substrate comparison. The direction of the first draft's
recommendation was wrong. Widening `_STRATEGY_SOURCE` would not reach the
headroom, because the headroom was never there to be reached by a boundary.

**This is the old B3 with the mechanism corrected, and the direction reversed.**
The old §5 said the boundary was too narrow and recommended widening it. The
measurement says the boundary is a two-element selector and that is arithmetic,
and separately that the number cited as its headroom is a harness artifact. Both
are worth keeping. Neither supports widening the menu.

**Cost.** Two changes to what exists. Report the ladder on `overall` as well as
`unqueried`. Then, under a fresh freeze, run the three-arm experiment in §2 for
the descendant's own evidence. The first is a reporting correction and needs no
freeze. The second is a change to what a descendant is and needs one.

**What would falsify this.** Four things, and the load-bearing one is leakage: if
choosing a descendant's sequence against its own observations requires the sealed
evaluator or the held-out split, the improvement is an artifact, the current
measurement is fine, and the original direction survives. The other three: the
`qual`-versus-`audit` tripwire collapses when the choice task and the score task
share no table; a fresh cohort reproduces nothing of the gap; and
`MAX_QUERIES = 8` against `N_STATES = 16` turns out to be a deliberate
half-coverage design, in which case the ladder is measuring a cap and not a
headroom.

---

## 5. Where the effort went

Pass 3 measured `16f0784..HEAD` and reported "roughly 7,200 of 12,658
insertions, a majority" for runtime containment, and counted 85 renames as
insertions. Both are wrong in the way that matters, and a recommendation that
miscounts the batch cannot be trusted about it.

**The archive is 85 renames and 27 lines.** `7238352` moves 85 test files into
`tests/_heavy_archived/`. `git show --numstat` attributes 27 added lines and 0
deletions to that directory across the whole batch. A rename inflates a file
count without adding code. Pass 3's containment figure includes them as though
they were insertions.

**The real split.** Classifying the batch's code and test lines by the intent
the commit message states, over `16f0784..HEAD`, excluding the archive directory:

| line of work | commits | added lines | files |
|---|---|---|---|
| runtime and route (containment, staging, host authority, free signal, route contract) | 12 | 3,752 | 26 |
| research instruments (E1 campaigns r1 through r3, E2 repair, E4 qualification, lineage re-derivation) | 8 | 10,254 | 28 |

**Read that carefully, because it reverses the framing in both directions.** The
research line is the larger one by insertions, and I am not carrying the draft's
claim that containment was slightly the larger half. The reason is that four of
the research commits are E1 campaign drivers, and one of them
(`47bcca8`, "Freeze E1 r3") added 1,561 lines on its own. **The research line is
large because one experiment was written three times.**

Strip the E1 campaign drivers and the picture changes again:

| line of work | commits | added lines | files |
|---|---|---|---|
| runtime and route | 12 | 3,752 | 26 |
| research instruments, excluding the four E1 campaign drivers | 4 | 3,752 | 21 |

They are equal. **The runtime line and the research line are the same size**, and
the two figures in the table above describe the same work. What the numbers do
not support is a claim in either direction about which half the batch "was". The
honest statement is that a batch whose largest coherent engineering effort was
containment and whose second-largest was one experiment attempted three times
produces a keep/simplify/change split that names neither.

**Only 750 lines changed in `src/`.** Over the whole batch range `src/` is
+750 -236 across 4 files. The shipped library grew by a small fraction of the
batch. Most of what the batch did is tests and reports, which is what a batch
that repairs its own measurement apparatus looks like.

### 5.1 Was one cross-platform child-limit authority the right call

**Yes, and the second commit is the reason.** `98c23c7` "Give child limits one
cross-platform authority" created `src/settlement/child_limits.py` and
consolidated the declared limits. `655feb3` "Install the child limits the launcher
declares, and fix the prctl constant" then made the launcher actually install
them, and corrected `PR_SET_NO_NEW_PRIVS` from 1, which is `PR_SET_PDEATHSIG`, to
38. The first commit alone would have left the launcher declaring limits it did
not install, which is the same shape of defect as the E4 boundary: a decision
that exists in a structure and does not reach the descendant.

**The honest objection is that this front-ran a deployment that has not
arrived.** `AGENTS.md` records that confined read denial is NOT PROVEN, and
`WORKER-PROMPT.md:50` says a missing Unix resource module "requires a supported
Linux execution environment or an explicit deployment limitation, never removing
the child limits". The prompt required the limits to stay. The work was
mandatory, not speculative, and that is a different claim from saying the batch
chose well.

**What would falsify the judgment.** If the child-limits path is never exercised
on a host where Landlock is available, `98c23c7` and `655feb3` are a well-built
answer to a question this deployment has not asked. The code is small enough to
delete later and the tests would tell a reader what it cost.

### 5.2 Is the 85-file archive a containment measure or an untested regression surface

**Containment, with one named gap, and the gap is the whole of the evidence.**

The case for containment is made properly. `tests/_heavy_archived/README.md`
says the files are "moved, not deleted and not failing", that the cost is CPU and
memory rather than correctness, and that an xfail would be wrong because it
asserts they cannot pass. It names the ten files that stayed collectable and
gives the reason for each. It gives the exact command to run them deliberately,
one file at a time. `pyproject.toml` excludes the directory from the default
`testpaths`.

**The gap, stated exactly.** Two archived files have been **run**, and both
fail in the same way — the host cannot spawn a bounded child, not the tests
being wrong.

`c40388e` records the first: "Found by running exactly one archived file,
which is the first evidence against 'the archive is not failing'… That file
is **1 failed, 3 passed**", the failure being the Windows `preexec_fn`
refusal. That result was on HEAD and until this revision no document recorded
it.

The second is `tests/_heavy_archived/test_s09graph_budget.py`, run here for the
first time: **1 failed, 3 passed**, the failure
`GraphBudgetRefused: graph step failed in child: no receipt`. The cause was
queried rather than inferred — `child_limits.current_execution_host()` on this
host returns `ExecutionHost(kind='windows', child_setup=False, reason='CPython
refuses preexec_fn on Windows, so the child cannot limit itself before exec,
and this launcher installs every boundary it has through it')`. The three
passing tests exercise the bound logic itself and need no child. So the failure
is a **host limitation, reproduced across two independent files**, and the
archive's correctness is still unmeasured: **2 files measured, 83 with no
result.**

One caveat on how it was run, since it changes what the number means. The
command requires `S09ISO_DISABLE=1` on this host — without it the conftest
aborts at configure time trying to reach a Postgres socket that is not
running, before any test body executes. A file needing a database
(`test_bdr02_child_identity.py`) therefore yields 4 connection errors and
measures nothing. Of the 85 archived files, **a material fraction require a
database this host does not have**, so "run the rest" is not one command.


That commit also edited the archived tree: 29 files, 35 insertions and 35
deletions — 24 files by one line, five by two or three — correcting the `REPO`
root from `Path(__file__).parent.parent` to `Path(__file__).parents[2]` after
the archive move deepened the tree. `git log 7238352..HEAD --
tests/_heavy_archived/` returns that one commit; the count was zero when this
section was first written at `5b1479e`, nine minutes before it.

What remains unmeasured is collection: the commit reports collection dropping
from 402 files and about 45 seconds to 317 files and 27 seconds. **That is a
collection measurement, not a pass measurement**, and the two files measured so
far have both demonstrated that the two come apart.

**What would turn it into a measurement.** One command per file:

```
S09ISO_DISABLE=1 uv run pytest tests/_heavy_archived/test_<name>.py -q -p no:cacheprovider
```

**This is the one command I recommend running, and the reason is specific.** A
lane ran the full test suite four times in this batch, twice concurrently on
both operating systems, after being told explicitly not to, and the coordinator
had to scope a `pkill` to `*pytest*` without scoping it to its own repository. The
archive is a claim that 85 files are still good, and **two have now been checked
and neither passes in full** — both on the same host limitation. One more file
is the cheapest possible way to learn whether that limitation is the only thing
standing between the archive and a clean result, and the cost is bounded by
construction because the command names exactly one path.

**A failure would not condemn the archive.** It would mean the archive is a
regression surface and the collection measurement was the wrong evidence. That
is a finding, and it is worth more than the assertion it replaces. The two files
run so far both support that reading: each single failure is the
`preexec_fn` refusal this batch spent `8`-unblocking on, not an archived test
roting on its own. **Which of the two it is, one further file would show.**

---

## 6. Keep, simplify, change

Each clause states what would prove it wrong. A clause with no falsifier is a
restatement, and the matrix's old §5 had two of those.

### Keep

**K1. No DSL and no new subsystem.**
*Falsifier.* A concrete required action that no existing representation can
express, named with a witness in the shape `missing_cells()` returns, that a
prompt-and-parser addition cannot deliver. Until such a witness exists, the rule
stands. Unchanged from the old §5, and the clause I most strongly endorse.

**K2. No fourth arm to the E4 boundary as frozen.**
*Falsifier.* The clause is scoped to the freeze, and it is correct there.
`CONTROL_ROLES` (`improve_channel.py:888`) is `("known-effect", "no-op",
"disconnect")` and `WORKER-PROMPT.md:88` requires exactly those three. The freeze
is on the **interface**: what a revision may change, and that the reviser cannot
modify grants, accounting, execution limits, evaluators or sealed assessments
(`FROZEN_FIELDS`, `improve_channel.py:177`). An offline budget-matched control
touches none of those. It adds no revision arm, runs no dispatch, writes no
grant, and scores against the same sealed results. It is the same class of
object as `ceiling` (`:909`), which is already computed offline inside the study.

**The scope is the freeze, not the file.** Do not add a fourth arm to the E4
boundary as frozen, and do not let any control change what a revision may
express. Pass 3 read the old clause as forbidding the one control that would
settle the recommendation's own central question, and it was right about the
effect. Naming the scope this way keeps the freeze intact and permits the
measurement.

**K3. The failure taxonomy, with its honest state named.**
*Falsifier.* `PREFLIGHT_OUTCOMES` (`live_construct.py:1432-1440`) declares
**seven** outcomes, not the five the old §5 claimed. The batch exercised two of
seven. If any of the remaining five is unreachable, or if one event can produce
two of them, the taxonomy is not a partition and the claim is wrong. **Neither is
tested.** The honest state of this clause is "believed, not measured".

**K4. One owner for a route field.**
*Falsifier.* `route_matches` (`src/settlement/gateway_http.py:180`) is the
single comparison with three callers. The keep is a bet that a returned route
carries no legitimate field variation the two-member contract would wrongly
refuse. If a real provider returns a value the contract does not name, one owner
turns three partial contracts into one wrong contract, which is worse than the
split it replaced. Untested in both directions, and it is now the only thing
making that judgement.

**What I dropped.** "The accounting and provenance spine, which is why §2 can be
honest at all." Pass 3's objection is correct. The matrix's §6 records two files
in one evidence directory disagreeing about the same eight attempts. The spine
did not prevent that. What made the report honest was a human reading raw JSON.
The clause credits machinery for an outcome it did not produce, and no
experiment can falsify it.

**One clause is mine and it is narrow.** Keep the exposure accounting, because it
is separately falsifiable and it held where it mattered. r3's `exposure.json`
records `dispatches_spent: 16`, `attempts_settled: 8` and `dispatches_refunded:
0` against a `model_call_ceiling: 16`, and `retries.json` records
`guard_status.ceiling_reached: true`. That is a campaign that spent exactly its
ceiling and said so. The r2 disagreement is in one directory, not everywhere.

### Simplify

**S1. Carry the missing cells with witnesses. Do not delete the matrix.**
*Falsifier.* A cell witnessed only by a transport error, a route refusal or a
parser failure is a third category, and a two-part form would hide it. The cap
sheet's own limit 3 is exactly that case and is filed as a separate host fact
rather than as a cell state, which is the precedent that keeps the categories
apart.

`WORKER-PROMPT.md:62` requires the concrete limitation to be shown and the cell
left missing, and the mechanism is implemented at `s09_swe_ast.py:303`
`missing_cells()`, which returns each missing cell with a quoted `witness` and a
`consequence`. **The old §5's proposal to delete the nine-cell frame from
reporting is suppression and the prompt forbids it.** Deleting the table does not
delete the fact, but it removes the counted denominator, which is the part that
makes the gap legible.

The cap sheet's SWE row was already corrected on 2026-09-29 at `5d8f56e`, and it
now reads "executor supported; typed AST cannot repair" for the SWE world. Pass 3
cited that row as marking all nine cells supported, which was true when pass 3's
author read it. The rows that are still plain `supported` without a witness are
the Boolean and ordering rows, and §4's B2 names the reason.

**S2. Correct the E2 state label from `completed` to `implemented` or
`qualified`.**
*Falsifier.* None needed. The label contradicts the matrix's own rule at `:10`
and is a one-word edit. It is here because the label is what a manager reads.

**S3. Correct `$.acquisition` in `reports/evidence/inv_r1_e4/run/campaign.json`.**
*Falsifier.* Pass 2 found it records `{acquisition: "no-reply", detail: "no
dispatch was attempted"}` while `$.acquisition_summary.acquired` reads `6` in the
same file. Two fields in one artifact cannot both be authoritative. If the
`no-reply` block is a separately versioned record of a different attempt, it
needs a field saying so and the file is a schema problem rather than a stale
write.

**S4. Run one archived test file deliberately. Report the result either way.**
*Falsifier.* A failure, which is §5.2's named gap. One command, one file, by the
README's own instruction. This is the only execution I am recommending.

### Change

**C1. Report the E4 evidence ladder on `overall` as well as `unqueried`.**
*Falsifier.* If `unqueried` is the metric the sealed evaluator defines, changing
the denominator changes the question. Which one is the assigned benefit metric is
the coordinator's call. That they differ by a factor of two in opposite
directions at budgets 1 and 8 is a fact about the report, not a preference.

**C2. Restore the `observe` call inside `evidence_ceiling` and correct the note
at `:992-994`.**
*Falsifier.* If the corrected measurement stops showing a gap, the current number
was measuring something else and the correction is still right. The correction is
to the harness's reporting, and its own note is what mislabelled the number.
This is Question A in §2.

**C3. Under a fresh freeze, decide whether a descendant's evidence sequence may
be chosen against its own observations.**
*Falsifier.* The four stated at §4's B3. Leakage is load-bearing: if the informed
sequence needs the sealed evaluator or the held-out split to be chosen, the
improvement is an artifact and this recommendation is void.

**Nothing in this list is a new subsystem.** C1 is a reporting change, C2 is a
one-line repair inside an existing measurement, and C3 is a decision about a path
that exists, taken under the freeze that path needs. S1 is a reporting
correction with a mechanism already in the tree. S4 is one command.

---

### E1's largest cause is the route's output budget, not its availability

An earlier draft of this document, and the coordinator's summary, said route
*availability* was the largest single cause of E1's zero. The campaign's own
probe contradicts that and the correct claim is narrower and more actionable.
From `reports/evidence/w1-e1-boolean-r3/route-probe.json`:

- the same campaign prompt returns **200 at 16 and 256 output tokens** and
  **fails at the protocol's own 2048** -- `campaign-prompt-budget-2048` is a
  `TimeoutError` after 182 s, and `short-prompt-budget-2048` is the 502;
- the probe's own `findings` text says "a short prompt returns 200 at 2048" and
  **contradicts its own `probes` data**. An earlier revision of this document
  sided with the text. The probe never crosses budget against prompt, so
  "the trigger is the budget, not the prompt" is **unsupported**: what the data
  supports is that the route returns 200 at 16 and 256 and fails at 2048, and
  r3 ran at 2048;
- the frozen model id is **absent from the 256-entry catalog yet answers when
  dispatched anyway** -- "reachable and unpinnable at once";
- the route states price as `usage.cost` while the adapter reads
  `charge_units`, `charge_scale` and `billed`, none of which it returns, so
  every attempt records cost as unknown.

**So the route is demonstrably answering.** The zero is not explained by the
route being down, and a re-run at a budget the route accepts is a cheap
measurement that has not been done. That changes B2's falsifier: it may
already be met.

### E3 is reproduced, and two of its assertions cannot fail

`ffadf15` recomputed the ladder from source rather than from the recorded JSON
-- the check both independent review passes left undetermined. It **reproduces
to the printed digit** on the crossover and the arm counts: the crossover is
**20 and not 30**, and budget 14 is the agenda's only win against an opponent
scoring `0.000000` with all 196 rules vacuously tied. **The "ratio exactly 3.0
at every non-zero budget" is an identity, not a result** -- MEAN is defined as
SUM/3 over exactly three worlds, so the ratio must be 3. Presenting it as
reproduced arithmetic dressed a division restatement as a finding. The count columns also match
`STAGE-09-HANDOVER.md:157-158`, which neither lane produced, so three-way
agreement.

**The defect is still live in source**, proved by calling
`agenda_policy.py:424 _score_constant_rules` rather than reading it: it returns
a sum over worlds 0,1,2, while arm rows divide by `len(cells)`.

**And the guard on it cannot fail.** **Both guards cannot fail.** `test_s09_e3_control_competence.py:185-189` and `:236` each compare `_mean(...)` against `best_rule_held_out_reduction`, which traces to `_score_constant_rules` via `s09_e3_selection.py:293-294` -> `agenda_policy.py:505` -> `:480`. That is the **sum**. Both assertions compare a mean against a sum, both pass, and the headings at `:747` and `:772` say "two" correctly. An earlier revision of this section said "half wrong"; it was not. The ceiling and handicap that E3's
negative rests on are not machine-guarded today, and `w0-tr05.md:445` already
reports 37 passing tests with the defect present. This is the same shape as
the E1 preflight assertion that stayed green through every repair in this
batch: **two tests this batch were built to prove a defect fixed, and neither
can fail.**

## 7. Undetermined

Stated as such. I did not guess at any of these, and several are why a
recommendation above is conditional.

1. **Whether choosing a descendant's evidence against its own task is leakage.**
   The load-bearing open question. It decides whether C3 is a real improvement or
   an artifact. The `qual`-versus-`audit` control is the tripwire and the tripwire
   has not been run for the descendant path.
2. **Whether the E2 offline path can run without a fresh freeze.** This decides
   whether B1 is the cheapest item in the batch. I did not verify it.
3. **Whether E2's repaired metric produces any separation.** I expect a null and
   I have no measurement.
4. **Whether any archived test file passes.** Two have been run and both are
   1 failed, 3 passed, on the same `preexec_fn` host limitation. Whether that
   limitation is the only thing standing between the archive and a clean
   result, and whether any of the other 83 files pass, is unmeasured — as is
   every file needing a database, which this host does not have.
5. **Whether any of the five `preflight_verdict` outcomes beyond
   `route-refusal` and `transport-loss` has ever been produced by a real event.**
   Untested branches, not verified machinery. The taxonomy has seven members, not
   five.
6. **Whether a legitimate route field variation exists that `route_matches` would
   wrongly reject.** Now the single owner of that judgement.
7. **Whether the free route's 502s are rate limiting, transient strain, or
   something else.** r3 recorded nine of them. A ninth event changes nothing.
8. **Whether the `MAX_QUERIES = 8` cap against `N_STATES = 16` is deliberate.**
   A budget-16 arm is identical to a budget-8 arm. I cannot tell a deliberate
   half-coverage design from an oversight.
9. **Whether the E1 r1 `campaign.json` / `exposure.json` disagreement is a
   bookkeeping defect or a real double-spend.** Unresolved in the batch.
10. **Whether the second E1 acquisition path is a real acquisition surface or a
    one-campaign artifact.** `packet.py:342` served one campaign and produced
    three wrappers around an authored `ddmin`. Whether it generalises is
    untested.
11. **Whether a temperature or seed field on `ModelRequest` is a protocol
    omission or a deliberate constraint.** `ModelRequest`
    (`src/settlement/gateway.py:72`) carries neither. This decides whether E1 can
    ever reach the n=4 the cap sheet requires.

---

## 8. Corrections to the sources this document replaces

Two of the eight corrections a review pass required survive here, because
they change what a reader would conclude. The rest are recorded at their own
sites above and are not repeated.

1. **The E2 contrast is not 0.0 by arithmetic** (§4, B1). It was reported that
   way; `_reduction_of` reads `NORMALIZED_REDUCTION`, and the per-task
   difference is `-0.2727`.
2. **The E4 `0.00622` is not scored on its own selection data** (§1.3).
   `ceiling()` half-splits the cohort.

Both had the same cause: a claim written from a grep rather than from the
artifact the grep was standing in for.

---

## 9. What this document does not do

It does not replace §5 in the matrix. The coordinator owns that edit.

It does not claim the matrix's §3.6 diagnosis of E4's blocker is wrong. That
diagnosis stands. `_STRATEGY_SOURCE` has two members, the six refusals were
correct, and more dispatches cannot get past it. What does not stand is the
inference from a confounded and now-explained headroom figure to "therefore widen
`_STRATEGY_SOURCE`".

It does not soften the negatives. All four experiments are negative, E1's
output-world campaigns produced zero constructions across r2 and r3, the E2
transfer tie is void rather than weak, and the one live acquisition campaign
that ran lost to its control. Those are the findings.

**Traceability.** Every figure is from a named source line, a committed JSON
artifact, a `git log` or `git show --numstat` result, or the r3 and r4 evidence
directories. No figure is from a test run, because I ran none.
