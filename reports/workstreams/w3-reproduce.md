# W3/E3 — reproduction of the disputed budget tables

Lane: `w3-reproduce`. Read-only. One new file. No commit, no edits to any other file.

This is the check two review passes left undetermined. `reports/workstreams/w5-review-pass1.md:708-711`
records *"I did not re-run 1176 simulations per budget"* and *"[whether] the ladder numbers
themselves reproduce is **undetermined**"*; `:256-260` says the same of the recomputation
itself. This lane ran it once, from source, and reports the outcome.

**Verdict: REPRODUCES.** Every disputed figure matches the prior lane's to the printed
digit, and one value the reviews had not checked is corrected.

---

## 0. The one run

One script, once. No retries, no second parameterisation, no subset re-run.

```
cd /d/AI/Agent-Society-v2/.worktrees/w3-reproduce
export PYTHONPATH="D:/AI/Agent-Society-v2/.worktrees/w3-reproduce;D:/AI/Agent-Society-v2/.worktrees/w3-reproduce/src"
S09ISO_DISABLE=1 python -u w3_recompute.py
```

- Script `C:\Users\roysh\AppData\Local\Temp\w3_recompute.py`, outside the worktree so it
  adds no file to the repo.
- **Wall time: 287.1 s (4 min 47 s)**, single process, against a 20-minute cap. 3528 runs
  in the space search, plus the two source cross-checks and the two ladder passes.
  `dsn=None` on every run, so no store and no database. `S09ISO_DISABLE=1` and no DSN
  set. No model call, no network, no gateway probe, no Jev, no child process, no
  subprocess, no test file. Nothing else was run.
- Prior lane recorded 368.4 s for the same 3528 runs. Mine is faster, which says the
  earlier figure was not inflated and the substrate is the same speed order.
- No file in the worktree was modified. `git status --short` shows only
  `?? reports/workstreams/w3-reproduce.md`.

Measure freeze digest at run time:
`ce5a140aff83bccc55a916958fdbaf568cb7c576d5c6a66361510181c83cf7e8`, identical to the
prior lane's and to the recorded artifact's `measure_digest`. The measure set was the
same frozen thing in both runs, so a match is a like-for-like comparison.

---

## 1. Headline: reproduces

### 1a. The best-in-space table, both denominators

**Denominators.** `SUM` = the sum of `held_out_reduction` over worlds (0, 1, 2). `MEAN` =
that sum / 3, the scale every ladder arm row is reported on. This is the whole defect
(see §2), so both are printed on every row.

| budget | best **SUM** | best **MEAN** | SUM/MEAN | beats default | beats fitted | tied at best |
|---|---|---|---|---|---|---|
| 8 | 0.000000 | 0.000000 | n/a | 0 | 0 | 196 (vacuous) |
| 14 | 0.000000 | 0.000000 | n/a | 0 | 0 | 196 (vacuous) |
| 20 | 0.419328 | 0.139776 | 3.0000000000 | 96 | 0 | 84 |
| 30 | 0.525770 | 0.175257 | 3.0000000000 | 94 | 0 | 10 |
| 40 | 1.077842 | 0.359281 | 3.0000000000 | 0 | 8 | 8 |
| 60 | 1.242831 | 0.414277 | 3.0000000000 | 4 | 84 | 4 |

Claimed values from `reports/workstreams/w3-e3-recompute.md:134-141`: `0.419328`,
`0.139776`, `0.525770`, `0.175257`, `1.077842`, `0.359281`, `1.242831`, `0.414277`,
ratio 3.0 at every non-zero budget, counts 0/0/96/94/0/4 and 0/0/0/0/8/84.

**Every cell matches.** The counts also match the independent committed table at
`reports/STAGE-09-HANDOVER.md:157-158`, which was produced by neither this lane nor the
prior one. Three-way agreement.

### 1b. The 2.7x, and the corrected margin

Both sides of the 2.7x are single denominators, and the mixed one is identified.

| quantity at budget 20 | value | denominator | where |
|---|---|---|---|
| oracle **SUM** | 0.419328 | 3 worlds, summed | my run; source `constant_rule_search(20)` |
| oracle **MEAN** | 0.139776 | 3 worlds, averaged | my run |
| agenda **MEAN**, fresh per cell | 0.083721 | 3 worlds, averaged | my run; `$.postfix_fresh` |
| agenda **MEAN**, shared instance | 0.156883 | 3 worlds, averaged | my run; `$.regenerated_shared` |

| comparison at budget 20 | ratio | reading |
|---|---|---|
| oracle SUM / agenda SHARED mean (as reported) | **2.67x** | the 2.7x claim; mixed denominators |
| oracle MEAN / agenda SHARED mean | 0.89x | agenda ahead |
| oracle MEAN / agenda FRESH mean | **1.67x** | oracle ahead |

The prior lane reported 2.6729 and 1.67x. My run gives the same 0.419328 and 0.139776 to
six places, so both ratios are the same arithmetic over the same real values.

### 1c. Crossover

**Denominator: mean over 3 worlds on both sides.** The first budget at which the agenda
is below best-in-space is **20**, not 30. Budget 14 is the agenda's only win, and there
the best-in-space score is 0.000000 with all 196 rules vacuously tied.

| budget | agenda MEAN | best MEAN | verdict |
|---|---|---|---|
| 8 | 0.000000 | 0.000000 | tie, 196 rules vacuously tied |
| 14 | 0.083721 | 0.000000 | **agenda ahead** (over an opponent that qualifies nothing) |
| 20 | 0.083721 | 0.139776 | **oracle ahead** |
| 30 | 0.111748 | 0.175257 | **oracle ahead** |
| 40 | 0.144745 | 0.359281 | **oracle ahead** |
| 60 | 0.205876 | 0.414277 | **oracle ahead** |

The first budget at which the agenda is below best-in-space is **20**, not 30. The
agenda's only win is 14, and there the best-in-space score is 0.000000 with all 196 rules
vacuously tied, so it is a lead over an opponent the envelope never let play. The
committee's `direction` code in `e3_ladder.py:184-190` records this as a lead too, for
the same reason, and the ceiling test at
`tests/test_s09_e3_control_competence.py:186-188` exempts exactly budgets 8 and 14 on the
same grounds.

Matches the prior lane's corrected crossover table at `w3-e3-recompute.md:199-206`, and
the agenda column matches the recorded `$.postfix_fresh` per-world values exactly.

---

## 1d. The three arms, one denominator

**Denominator: mean over 3 worlds, fresh instance per cell, for all three columns.**

| budget | agenda | specified default | fitted control | best-in-space |
|---|---|---|---|---|
| 8 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| 14 | **0.083721** | 0.000000 | 0.000000 | 0.000000 |
| 20 | 0.083721 | 0.000000 | 0.139776 | 0.139776 |
| 30 | 0.111748 | 0.111111 | 0.175257 | 0.175257 |
| 40 | 0.144745 | 0.359281 | 0.210738 | 0.359281 |
| 60 | 0.205876 | 0.391007 | 0.187032 | 0.414277 |

This settles the open ledger row *"E3 control conflict, unresolved"*
(`reports/PROJECT-LEDGER.md:46`), which records that `w0-tr05.md` §4b claimed the agenda
leads the fitted control at *every* budget. **It does not.** The fitted control beats the
agenda at 20, 30 and 40, and the agenda beats it at 60. The `w0-tr05` claim rests on
`fitted_control_ahead_on_held_out_at` being empty, and that field lives in the withdrawn
shared-instance artifact. On the live fresh path it is not empty.

It also corrects the handover's `0.157 against 0.253` at 20 (§3): on the fresh path the
default scores 0.000000 at 20, not 0.253. The default ties the best-in-space at 20 and is
beaten by 96 of 196 rules, which is what makes the agenda's lead there a lead over a
handicapped opponent.

The two fitted controls are chosen, per budget, on `retained_behaviors` and never read
held-out. My run's fitted rules matched the source `fitted_fixed_rule` exactly at
budget 20 (`{'software': ('ddmin', 1), 'graph': ('greedy', 2)}`), and its
`objective_reads_held_out` is `False` as required. Per budget, the fitted and
best-in-space rules coincide at 8, 14, 20 and 30 and diverge at 40 and 60, which is why
`beats_fitted` is 0 at the first four budgets and 8 then 84 at the last two.

---

## 2. The sum/mean defect is still live in source

**Yes. Not fixed.** `experiments/ad01/agenda_policy.py:424-441`, `_score_constant_rules`:

```python
scores.append((sum(
    selection.run_investigations(
        None, FixedPolicy(rule),
        selection.Allocation(authorized=budget),
        world=world).yield_.as_dict()[objective]
    for world in worlds), rule))
```

It returns a **sum over three worlds**. `selection.py:465-486` types
`held_out_reduction` as a rate in `[0, 1]`, so three of them sum to roughly three times
one average. `experiments/ad01/e3_ladder.py:117-118` divides by `len(cells)` for the
arm rows, and `s09_e3_selection.py` does the same, so every arm row is a **mean** while
this function returns a **sum**.

**Proved by calling the source function, not by reading it.** My own traversal and the
repository's own `constant_rule_search(20)` agree to the last digit:

```
source best_score  = 0.419328  (searched=196, reads_reported_metric=True)
my    best_sum(20) = 0.419328
match: True
source score / 3 (mean) = 0.139776
my    best_mean(20)      = 0.139776
```

The two paths are independent: mine calls `FixedPolicy` directly with a fresh instance
per (rule, world); the source function is the shipped one. They agree exactly, so the
claimed 3.0 ratio is a property of the code, not of a stale artifact.

**The defect is load-bearing on the reported margin.** `0.419328 / 0.156883 = 2.6729`,
which rounds to the 2.7x in `reports/PROJECT-LEDGER.md:44`. The numerator is a sum and
the denominator a mean. Corrected to one denominator the margin is 1.67x. The direction
survives; the margin does not.

### 2a. Two tests compare a mean against the sum, so they cannot fail

Not asked for, and found while checking whether anything guards the defect. Neither
review pass raised it, and the ledger does not record it.

`tests/test_s09_e3_control_competence.py:185-189` asserts the agenda never beats
best-in-space:

```python
best = step["best_rule_held_out_reduction"]
...
assert _mean(_arm(step, "agenda")) <= best + 1e-12
```

`_mean` is `held_out_reduction_mean` (`:93-94`), an average. `best_rule_held_out_reduction`
comes from `control_competence` via `s09_e3_selection.py:293-294`, which is the
**sum**. The right side is 3x the scale of the left, so the assertion holds for any
agenda that could ever run. The same mix appears at `:236`.

The docstrings at `:166-185` and `:202-224` state the ceiling and the handicap as though
they were being enforced. They are not. A test that cannot fail is worse than no test
here, because `w0-tr05.md:445` already reports 37 passing tests while the defect is
present and the ceiling reading is the specific one the whole E3 negative rests on. I did
not run the suite, so I am not claiming a count; I am reporting the comparison.

**This does not change any number above.** It means the corrected 1.67x and the
crossover at 20 are not machine-guarded today.

---

## 3. The oracle labelling

**The source labels it correctly. One live prose file does not.**

Source, `agenda_policy.py:399-421`, on `constant_rule_search`:

> "It is an oracle by construction and says so: it reads the reported metric to rank
> rules, which no run-time control may do. It exists to qualify other controls, never to
> be an arm. The `reads_the_reported_metric` flag is the machine-readable version of that,
> so a caller wiring this into a ladder cannot do so by accident."

My run read that flag directly: `reads_reported_metric=True`, and
`use = "qualify a control; never an arm in a reported ladder"`. The payload also carries
`best_rule_is_an_arm: False` on every ladder row (`s09_e3_selection.py:295`), and
`qualified_ladder`'s docstring at `:229-232` repeats it. The code does what
`WORKER-PROMPT.md:79` requires.

**The place that does not.** `reports/STAGE-09-HANDOVER.md:165-166`:

> "it loses to the best rule in its own family at both (0.419, 0.526); at 20 it is
> *behind* the default, **0.157 against 0.253**"

Two defects in one sentence, and this file is still live at HEAD (last touched by
`f461f63`, not archived):

1. It presents the held-out best-in-space as a **control** to lose to. It is a
   retrospective reference. `reports/PROJECT-LEDGER.md:45` and
   `reports/STAGE-09-COMPLETION-MATRIX.md:226-228` both already flag this, so it is a
   known-open item rather than a new one, but the file itself is uncorrected.
2. The `0.157 against 0.253` pair is the **shared-instance, withdrawn** path
   (defect N-80). My run's shared agenda mean at 20 is 0.156883 and the recorded
   `$.regenerated_shared` is 0.1568834941383961, the same number. On the live fresh path
   the agenda is 0.083721. So that sentence compares a retracted arm against a control on
   a third basis.

`reports/STAGE-09-HANDOVER.md:157-158` (the counts table 0/0/96/94/0/4) is **correct** and
my run reproduces it. The defect is confined to the 165-166 sentence.

---

## 4. The "scripted schedules" finding holds against the records

**It holds. Verified in the artifacts, not by repeating the prose.**

`FixedPolicy.plan` (`agenda_policy.py:236-251`) builds the schedule before any
observation, and `propose` (`:266-270`) emits a rationale naming its own position in it:

```python
"pre-committed %s/%s step %d of %d" % (family, method, step, depth)
```

The rationale is generated from the pre-committed rule, not from anything the run
observed. The recorded evidence carries 188 such strings, and the complete set of
distinct control rationales in `e3-postfix-ladder.json` is:

```
pre-committed graph/ddmin step 1 of 1
pre-committed software/ddmin step 1 of 5 ... step 5 of 5
pre-committed schedule complete
```

Every one has the `step N of M` form the ledger describes. The agenda's own rationales
read `untried capability <method> in the <family> line` and `<family>/<method> is retained
at N queries, so deepen while the envelope allows`, which is state-dependent rather than
positional.

So the comparison really is a policy against two schedules, and the `WORKER-PROMPT.md`
instruction not to call a scripted campaign order an autonomous agenda applies with the
force the ledger gives it. The rationales **are** pre-committed. The finding is right.

---

## 5. What E3 shows, and what it does not

**Shows.** A stateful policy that reaches admitted operations and receipts, and that
beats the *specified default* at budgets 14, 20 and 30 on the fresh path. That is a real
difference between two things, and my run reproduces the agenda column exactly.

**Does not show.** Autonomous selection. The controls are schedules (§4), the comparison
is against opponents most of the space beats (96 of 196 at 20, 94 at 30), and on the
corrected denominator a rule in the space is ahead of the agenda at every budget from 20
up. Three worlds, one metric, no transfer.

**The negative is robust.** It does not depend on the sum/mean defect. Fix the
denominator and the direction is unchanged, only the margin moves from 2.7x to 1.67x.
That is a real strengthening of the prior lane's conclusion: the recomputation makes the
negative better evidenced, and it was already negative before.

---

## 6. What the re-check adds beyond the prior lane

1. **The two ceiling guards are unfailable** (§2a). Neither review pass raised it. The
   corrected 1.67x and the crossover at 20 are correct but not machine-guarded today.
2. **The `fitted_retained` field is a sum too, on a count metric.**
   `agenda_policy.py:333-339` accumulates `score += run.yield_.retained_behaviors` over
   worlds and stores it in `fitted_retained`, which my run read back as `3` at budget 20
   while the fitted rule is the one retaining a behaviour in all three worlds. That is
   harmless for the argmax (it is a constant scale on a count, and every rule is compared
   on the same denominator), but it is the same habit as the held-out sum: a per-world
   quantity accumulated across worlds and stored under a name that reads like a per-world
   value. Worth renaming if the function is ever touched.
3. **The shared-path denominator is confirmed, not inferred.** The 2.7x uses
   0.1568834941383961. My run of `ladder(shared=True)` produced that same float, and the
   recorded `$.regenerated_shared` holds it. The retracted path is the only place that
   number lives, which is why the headline ratio is not reproducible from live evidence.

---

## 7. What remains undetermined

**Reproduced exactly:** the six-budget best-in-space table on both denominators, the 3.0
ratio, both count columns, the 2.6729x and the 1.6696x, the crossover at 20, the vacuous
tie at 8 and 14, all three arms on the fresh path, the shared and fresh agenda means at
20, the fitted rules per budget, and the measure freeze digest. The one script ran
287.1 s and is described in §0.

**Undetermined, and I am not going to close any of it by running more:**

1. Whether the two unfailable tests in §2a are load-bearing for any currently passing
   suite state. Verifying that needs the suite, which this lane is forbidden to run.
   Reading them is all I did, and reading them is enough to say the comparisons are
   mixed-scale.
2. Whether the counts in `STAGE-09-HANDOVER.md:157-158` were produced by the same world
   set. My run reproduces the numbers, and `s09_e3_selection.py:235-239` warns the
   counts are world-set dependent, but I did not re-derive that doc's world list.
3. The world-2 degeneracy the ledger records for the pooled sign at 30. My run
   reproduces world 2 as the outlier at budget 30 on the default arm
   (`0.166667, 0.166667, 0.0`), which is consistent with it, but reproducing the sign is
   not the same as auditing it.
4. Whether `STAGE-09-HANDOVER.md:165-166` has been corrected on a branch. I read HEAD
   only, and said so rather than guessing about other lanes' work.
