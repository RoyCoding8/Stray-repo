# W2 retention and adaptation, measured

The two §W2 contrasts the E2 batch did not run. Both ran, on the one panel
that is both open and readable, and the retained-method leg is reported as
unmeasurable on this instrument rather than approximated.

## The result

**A measured null, on a panel whose positive side is open.** Every
experience arm chose `seed-sw-ddmin` at `max_queries: 8` on every target
where it scored, so the paired deltas are 0.0 by measurement and not by
arithmetic: the panel admits a positive delta of 0.285714, and
`ad01-w0-transfer-sw-01` is a task where a different budget reaches 0.7857
against the default's 0.5. The instrument could have reported a difference
and did not.

### Retention, the transfer-shaped leg

`software` / `transfer`, three targets, three arms.

| arm | target | normalized_reduction | scored | method |
|---|---|---|---|---|
| relevant | transfer-sw-00 | 0.7857 | true | `seed-sw-ddmin` |
| relevant | transfer-sw-01 | 0.5000 | true | `seed-sw-ddmin` |
| relevant | transfer-sw-02 | 0.5556 | true | `seed-sw-ddmin` |
| none | transfer-sw-00 | 0.7857 | true | `seed-sw-ddmin` |
| none | transfer-sw-01 | 0.5000 | true | `seed-sw-ddmin` |
| none | transfer-sw-02 | 0.5556 | true | `seed-sw-ddmin` |
| irrelevant | transfer-sw-01 | 0.5000 | true | `seed-sw-ddmin` |

| contrast | deltas | n | delta | unscored |
|---|---|---|---|---|
| relevant − none | [0.0, 0.0, 0.0] | 3 | 0.0 | none |
| irrelevant − none | [0.0] | 1 | 0.0 | 2 targets, no `none` reading |

The `irrelevant` arm lost two of its three dispatches, so its contrast runs
over one pair. The instrument drops an unscored task from the pair and
names it; the 0.0 over one pair is a measurement, not a zero written in
place of three.

### Adaptation, within-domain against held-out-domain

The same three arms on the held-out `transfer` split against the same
three arms on the `within` split, paired by position.

| position | within | held out | relevant within | held out | delta |
|---|---|---|---|---|---|
| 1 | within-sw-01 | transfer-sw-01 | 0.7692 | 0.5000 | **+0.2692** |

Two positions dropped for want of a reading on the `within` side: its
`none` and `irrelevant` arms each scored only `within-sw-01`. Named, not
averaged in as zeros.

Every arm moves by the same **+0.2692** from within to held-out. So the
domain costs each arm equally, and the experience contrast *within* each
domain is 0.0 on both sides: `relevant − none` is [0.0] and
`irrelevant − none` is [0.0] over the one matched position.

**A real domain effect, no experience effect.** The held-out domain is
harder for every arm by the same margin, and the experience arms do not
differ from the no-experience arm on either side of it.

### Two namespaces

| | `invr1w2retention` | `invr1w2retentionr2` |
|---|---|---|
| kind | first contrast | replication |
| receipts | 18 success, 0 lost | 17 success, 1 lost-response |
| constructions | 27 | 27 |
| dispatches with no constructible source | 22 | 12 |
| `relevant` on transfer | 3 of 3 | 2 of 3 |
| `irrelevant` on transfer | 1 of 3 | 3 of 3 |
| `relevant − none` | [0.0, 0.0, 0.0], n=3 | [0.0, 0.0], n=2 |
| `irrelevant − none` | [0.0], n=1 | [0.0, −0.1429, 0.0], n=3 |
| adaptation pairs | 1 of 3 positions | 0 of 3 positions |

**`invr1w2retentionr2` is the genuine replication.** It is a second
independent namespace with its own store, its own operation ids and its own
model bytes, run after the first left supported arms. It is not a rerun
after a failure: the first run's arms all scored and its null was a
measurement.

The two disagree on *which* arm lost dispatches, and the second namespace's
arms made genuinely different decisions. Across 19 scored readings the
first namespace chose `seed-sw-ddmin` 18 times and `seed-sw-greedy` once;
across 22 the second chose `seed-sw-ddmin` 13 times and `seed-sw-greedy`
nine. So the model did vary across namespaces, and the greedy choices
moved the reductions without moving the `relevant` contrast, which is
0.0 in both.

The second namespace's `irrelevant` contrast is −0.047619, driven by one
target where the irrelevant arm chose greedy and scored 0.3571 against the
none arm's 0.5. That is a single pair out of three, the sign is negative,
and the same contrast in the first namespace is 0.0 over its one surviving
pair. It is reported, not resolved: one cluster cannot carry a sign claim,
which is what the instrument's own `minimum_p = 1/2` on two `(family,
template)` clusters already said.

The adaptation contrast has **zero complete positions** in the replication
and one in the first. The within split's three targets each lost a
different arm, so no position carries all three arms on both sides. That
is a smaller denominator than the first namespace, not a contradiction of
it.

## What §W2 asked and what ran

`WORKER-PROMPT.md` §W2 asks for two things: *"Compare retained-method reuse
against cold reacquisition and within-domain versus held-out-domain
adaptation where applicable."*

One of the two is expressible on this instrument. One is not, and the
difference is a property of the frozen gate rather than of the campaign.

## 1. The retained-method leg is not measurable here, and that is measured

A retention contrast needs a policy to be able to **name a method it
retained**. It cannot. `assessment_profile.default_repertoire()` returns
four authored seed ids. `e2_replication.eligible_for(task)` returns the two
belonging to the task's family. Both are closed, frozen, and **identical
for every arm on every target**, so a method acquired on one task can never
enter another task's repertoire.

`measure_repertoire_closure()` re-measures this on all nine panel targets
with no model and no dispatch. Every row reports
`eligible_count: 2`, `retained_method_nameable: false`, and the campaign
observes exactly one distinct eligible set across all nine. There is no
arrival path.

So the `method_id` leg of retention has no lever. What is expressible is
the observable that survives: `normalized_reduction`, paired per task, with
the decision vector reported beside it. That is what the retention panel
measures.

The terminal `verdict` is **not** used. It is `preserved` on every reducer
outcome the panel can produce, so it is constant by construction. The report
carries `terminal_verdict_usable: false` and no claim rests on it.

## 2. The prior census's closed result does not transfer, and it was wrong on a family it never ran

`5cf3fe8` reported the panel closed on the positive side: max attainable
positive delta 0.0. That was measured on **`software` / `within`**, and on
that panel it reproduces exactly.

§W2 asks two other questions on two other splits. Recomputing the same grid
offline over all eighteen frozen targets, against a **family-aware**
default:

| panel | open rows | max positive delta |
|---|---|---|
| software / within (the prior panel) | 0 of 3 | 0.0 |
| software / transfer | 2 of 3 | 0.285714 |
| graph / within | 3 of 3 | 0.263158 |
| graph / transfer | 3 of 3 | 0.285714 |

Both live panels are therefore open, and a null measured on them is a null
the instrument could have contradicted. That is the difference between
"experience does not help" and "this panel cannot express a difference".
Choosing `software` / `within` for either contrast would have re-run the
closed panel and produced exactly the null the instrument was incapable of
contradicting.

The defect is invisible on a target whose real default happens to be zero,
because measuring the gap from nothing and measuring it from zero are the
same number there. It shows on 3 of 18 measured rows, and on every one of
those the inherited number is the larger.

### A defect in the inherited census

`e2_contrast_campaign.reachability_census` resolves each row's default from
a hardcoded `DEFAULT_METHOD = "seed-sw-ddmin"`. On a **graph** target that
cell does not exist in the row's grid, so `default` is `None` and the row's
positive delta is computed against `0.0` instead of against the real
default. Measured on `ad01-w0-transfer-gr-02`, the inherited function
reports a positive delta of **0.52381** where the true default of 0.2381
gives **0.285714**. It overstates its own reach.

The prior census never hit this because its panel was software only. The
frozen module is **not patched**. This campaign computes its own default per
family and reports the discrepancy.

## 3. The qualification gate is software-only, which fixes the panel

`replica.qualify_instrument` is the gate a run must pass before it will
trust a number, and it is the right gate: a contrast read off an
instrument that cannot separate a reader from a blind policy measures the
echo.

It is also written for one family. All five of its authored policies name
a `seed-sw-` method in their own bytes (`e2_replication.py:460, 481, 483,
499, 509`), and `score_response` refuses an action naming a method outside
the target's family. On a **graph** target every one of them is refused
before it can act, every reading comes back `scored: false` with *"the
returned bytes admitted no action that reaches a method executor"*, and
`qualify_instrument` reports `separates_reader_from_blind: false`.

Measured on `ad01-w0-within-gr-00` with no observations at all, so the arm
is not the variable: the software reader scores `true`, the graph reader
scores `false`. **The gate does not measure this instrument on a graph
target.**

`qualification_census()` measures which targets are readable rather than
assuming a gate that passed on one family passes on another. It reports 9
of 9 readable, all on `software`.

### Where that leaves the two constraints

The ceiling and the gate together leave exactly one place to run:

| constraint | measured |
|---|---|
| positive side open | open on 2 of 3 `software`/`transfer` rows, and on 3 of 3 rows of both graph panels; closed on 0 of 3 `software`/`within` rows |
| qualification gate can read | `software` only; 9 of 9 targets readable, 0 on `graph` |

So `retention` runs on **`software` / `transfer`** — open on 2 of 3 rows,
max positive delta 0.285714, and readable. `adaptation` runs its
held-out side there against its `within` side, which is the prior lane's
closed panel and is reported as the closed bound it is.

The graph censuses are still computed and reported. **A ceiling is a
property of the decision grid and needs no policy**, so a graph census is
valid even though a graph contrast is not runnable. Both graph panels are
open on 3 of 3 rows.

## 4. A second inherited constant that had to be searched, not carried

`EVIDENCE_MAX_QUERIES = 3` is *"the largest whole budget at which the
graded outcome still varies"* **on the software dev pool**. It is a property
of that pool, not of the instrument.

Carried onto a graph panel, it measures every dev graph task at 3 queries,
where the graded outcome is `ok-incumbent, reduction 0` on all three, and
`require_varying_graded_outcome` then refuses the arm. **The first live run
of this campaign produced exactly that**: a named refusal on every target,
no reading anywhere, and three panels of zero. The refusal was correct and
the artifact was void.

The budget is now searched per family over a range declared in the freeze,
so a wider search is a different frozen experiment rather than an unnoticed
change. Measured: **graph 6**, **software 2**. With the searched budget the
graph arms build, size-match to 768 characters each, and read.

## 5. A bug this campaign shipped, and the fix

The first run of the adaptation table reported **1.0 for every pair**. The
readings were never wrong: `within-sw-01` scored 0.7692 and
`transfer-sw-01` scored 0.5. The pairing re-derived each side with
`replica._normalized_reduction`, which reads the **checker's report**
shape, whose measure key is `measure`. A `Reading` carries the same
number as `candidate_measure` and has **no `measure` key at all**, so the
re-derivation found `None`, subtracted nothing, and returned 1.0 for every
pair. A uniform 1.0 is a result the campaign never observed.

The verifier did not catch it, and that is the worse half. `check_readings`
re-derived with the same wrong function, so it compared 1.0 against 1.0
and passed. The `paired` check passed because `replica.paired_report` reads
the stored field, which was correct.

Fixed in both places, and pinned three ways: the pairing now reads the
reading's own `normalized_reduction`; `check_readings` re-derives from
`initial_measure` and `candidate_measure` in the shape a `Reading` really
holds; and `test_a_reading_carries_no_measure_key_and_the_reduction_rule_needs_one`
asserts the frozen rule returns 1.0 on a `Reading` so the trap cannot be
re-entered silently. The corrected table is recomputed from the stored
readings, offline, and the report carries a `recomputed_offline` note
saying so.

With the fix, `check_readings` catches the self-consistent inflation that
it previously missed.

## Live calls and accounting

**54 constructions across the two namespaces, plus 2 route probes.** 27
per namespace. `max_output_tokens` was **1024**, not the inherited cap
sheet's 2048, because this route fails at 2048 on these prompts.

Route outcomes: the first namespace recorded 18 receipts, all `success`.
The second recorded 17 `success` and **1 `lost-response`**. Of 27
constructions, **22 in the first namespace** and **12 in the second**
returned no constructible source. So the *first* namespace is the one that
lost most of its dispatches, and the second is the cleaner of the two on
that axis. The route degraded unevenly across both and is reported as an
external dependency, not absorbed into a result.

`billed` and `charge_units` are **null on every receipt in both
namespaces**. The route states its price as `usage.cost` and the adapter
reads the other two, so no receipt carries either. The campaign asserts
no cost in either direction: it does not claim a receipt was free and does
not claim one was billed. The verifier enforces both directions and fails
a report that turns absence into a number.

## What §W2 now shows, and what it does not

1. Retained-method reuse is **not measurable** on this instrument: the
   repertoire is four authored seeds and identical for every arm, so no
   acquired method can be named.
2. The leg that is measurable is a **measured null** on a panel open to
   0.285714, replicated in two independent namespaces.
3. The held-out domain costs every arm **+0.2692** more than the within
   domain, and the experience arms do not differ from the no-experience
   arm on either side of that gap.
4. The prior lane's closed-panel result **does not transfer**: three
   inherited constants and one hardcoded family default each had to be
   measured rather than carried.
5. It does **not** show that experience does not help. It shows that on
   this instrument, on these three tasks, with this repertoire, it did not.

## Layout

| file | role |
|---|---|
| `experiments/ad01/w2_retention_campaign.py` | freeze, arms, census, run, report |
| `experiments/ad01/w2_retention_verify.py` | offline verifier, re-derives every claim |
| `tests/test_ad01_w2_retention.py` | 28 behaviour tests |
| `scripts/w2_retention_run.sh` | WSL runner, verifies the relay before spending |
| `reports/evidence/invr1w2retention/` | first namespace |
| `reports/evidence/invr1w2retention-census/` | the offline closure and census |

## Verification

The verifier re-derives rather than compares. Every reduction is recomputed
from the `initial_measure` and `measure` the same reading stores, every
paired delta is recomputed by the frozen `paired_report` over the stored
readings, every census cell is recomputed by re-enumerating the grid with
no model, and the retention blocker and the census defect are re-measured
against the frozen gate.

A skipped check is reported as skipped, never as passed. An offline-only
report declares itself, and a live report that lost its readings still
fails.

Six forgeries are built and each is rejected by the check that owns it.
