# M3 revalidation after the rule-learner freeze

Base `8f10cd6e`. Owned files: `experiments/ad01/e4_budget_ladder.py`,
`experiments/ad01/evidence_ceiling_diagnostic.py`, `tests/test_e4_budget_ladder.py`,
`tests/test_evidence_ceiling_diagnostic.py`, and the new
`experiments/ad01/m3_revalidate.py` with `tests/test_m3_revalidate.py`.
`rule_learner.py`, `learner_revision.py` and `PROJECT-LEDGER.md` were read, not
edited.

**This is an apparatus repair, not a replication.** `44ec6c52` changed the
query-selection rule after M3's numbers were taken. Re-running anything under
the new rule repairs the instrument and re-measures. It is not a second
independent run, it grants no replication credit, and no count here should be
added to the original measurement as though it were another observation of the
same thing.

Every figure below is produced by one command:

    uv run python -m experiments.ad01.m3_revalidate

Nothing in this document was inherited from the ledger, the census, or the
recommendation. `m3_revalidate.py` reconstructs the pre-freeze learner verbatim
from `44ec6c52~1` and replays the ladder under both, which is what attributes
the recorded numbers rather than assuming them.

## Headline

**M3's valid null survives the freeze. All three legs, none weakened.** No leg
of it cited the blind arm or the tie-break. What the freeze invalidated is a
*separate* claim, the E4 ladder's `reconciles` check, and that check has been
deleted rather than re-pinned.

The one figure I could not pin to a reproducing convention is the ledger's
chance-level pair `0.5138 / sd 0.0169`. Its mean half reproduces under 28
swept conventions and its sd half comes within 0.0001, so it is very likely a
real measurement whose convention was never recorded. The *qualitative* claim it
supported, that the old blind figure was chance, holds and is now measured more
firmly than before.

## 1. Which figures reproduce

| Figure | Recorded | Re-derived, pre-freeze learner | Re-derived, frozen learner |
|---|---|---|---|
| `original` blind budget-8 | 0.5017 | **0.5017** exact | 0.0600 |
| `original` informed budget-8 | 0.8500 | **0.8500** exact | 1.0000 |
| `fresh_a` blind budget-8 | 0.5208 | **0.5208** exact | 0.0592 |
| `fresh_a` informed budget-8 | 0.8958 | **0.8958** exact | 1.0000 |
| `fresh_b` blind budget-8 | 0.5292 | **0.5292** exact | 0.0583 |
| `fresh_b` informed budget-8 | 0.9142 | **0.9142** exact | 1.0000 |

All six reproduce to four decimals under the reconstructed pre-freeze learner,
and none survives under the frozen one. That is the attribution: the
recommendation's table is a measurement of the old tie-break, and the freeze
moved every cell of it.

The three deltas follow: 0.3483 / 0.3750 / 0.3850 recorded, re-derived under the
frozen rule as +0.9400 / +0.9408 / +0.9417.

### Identification over the whole class

Measured per class member, never per sample, because the claim is a worst-case
bound over a finite class of 224.

| Query rule | Members not identified within 8 probes |
|---|---|
| frozen (largest total disagreement, smallest index on ties) | **0 of 224** |
| fixed input order `x = 0..7` | **224 of 224** |
| pre-freeze random tie-break | 64 / 125 / 126 of 224, by seed convention |

The frozen rule's per-member probe histogram is 32 members pinned after seven
probes and 192 at eight, so `MAX_QUERIES = 8 = ceil(log2(224))` is a tight
worst-case bound rather than a modal outcome. Both halves reproduce.

**The pre-freeze "64 of 224" does not reproduce as a class property.** It
appears only under the seed convention `always_zero`. Under `class_index` the
count is 125, under `class_table_value` it is 126, and over 200 arbitrary seed
conventions it ranges from 0 to 192 with median 128. The seed is precisely what
the freeze removed, so no single number for this row is defensible. It is
reported as a range in `m3_revalidate.py` and as a range here.

## 2. The blind arm, and why `0.0600` is not a competence score

This is the mechanism the ladder's means could not show, and it is the reason
`reconciles` had to go rather than be re-pinned.

**Before the freeze**, the tie-break was `cands[self._rng.randrange(len(cands))]`
with `random.Random(seed)` from `__init__`. The blind arm therefore drew a fresh
random 8-subset per seed: 150 distinct sequences over 150 seeds, measured on
every cohort. Its `0.5017` is one draw from the uniform-subset distribution.

**After the freeze**, with nothing observed, every open input's total
disagreement is identical at 448, measured. So "smallest index on ties" always
returns the lowest unqueried input, and the blind arm emits `[0, 1, 2, 3, 4,
5, 6, 7]` on every one of 450 cohort seeds. It is no longer a sample. It is one
fixed subset, and that subset is not typical: ranked exhaustively against all
12870 eight-subsets on 40 seeds, `[0..7]` is **22nd from the bottom**, against
a mean of 0.5161 and a worst subset scoring 0.0125.

So the two regimes fail to be a competence number in opposite directions. The
old `0.5017` was the mean of a distribution the arm did sample from. The new
`0.0600` is the score of the single subset the tie-break happens to select, and
that subset is near-worst. Neither supports a four-decimal pin against a
document.

The informed arm's `1.0000` is earned rather than defaulted. After eight
informed probes the max version-space size is 1 on every seed of all three
cohorts, measured, so the committed rule is right on every input it did not
ask. `descendant_score` reports `unqueried = 1.0` for a seed whose evidence has
actually identified the task.

## 3. Which legs of M3's null survive

The null has three legs. Each is assessed by dependency on `rule_learner`, not
by re-assertion.

**Leg (a), the four independent AD01 grounds. Survives, untouched.** The
grounds are a literal `fault` key in the frozen task dict, a reduction-only
metric in `benefit.py`, an experience axis that cannot vary in
`panel_variation.py`, and a unique minimum under a deletion-order walk. None
constructs a `VersionSpaceLearner`. Grep for the ladder in
`m3-instrument-census.md` and `m3-expressive-probe.md` returns zero hits, so
the null never rested on the invalidated claim.

**Leg (b), the SWE cell is `degenerate` on every instance. Survives, untouched.**
That probe enumerates edits, scores candidates through `tasks.score`, and
compares on a swept input domain. It never builds a version space. Its inputs
are the task's source text and the scorer's three cases, neither of which
`44ec6c52` touched.

**Leg (c), Boolean and ordering are function-identification instruments that
cannot execute a program. Survives as stated, and its own numbers improve.**
The claim is about the world's grammar, not a learner's score: you probe, then
you declare, and no program is executed. `RuleSession` exposes no execution
action, so freezing a query selector cannot change it.

One distinction matters inside leg (c). The census asserted "8 of 8 probes are
sufficient in principle" for the 224-member Boolean class. That is an
information-theoretic statement and the freeze cannot move it. What the freeze
changed is **attainment**, not sufficiency: the pre-freeze rule left a
non-singleton version space on a seed-dependent fraction of members, and the
frozen rule reaches the bound on all 224. The census's conclusion that W4 and
W5 support function identification and nothing else is unaffected, and its
warning against letting a W4 score stand in for a discovery claim is if
anything better founded now, because the instrument's score went up while its
scope did not.

**So M3 still closes as a measured zero.** The supported-cell count is zero,
and it is measured zero for reasons that never touched the learner. What the
freeze removed is a separate and now-withdrawn claim about the E4 blind arm.

## 4. What changed, and whether it re-derives or repairs

**`e4_budget_ladder.py`. `EXPECTED_BUDGET_8` deleted, `reconciles` replaced.**

The question asked first was whether the expectation or the reconciliation was
wrong. The answer is that the expectation could not be right in either regime,
so re-pinning it would have been cosmetic. The reconciliation was measuring the
wrong thing: it asked "does this number match a copied literal", which is a
check on the document, not on the instrument, and it was checking a cell whose
value is a property of the tie-break.

Replaced by `attains_bound`, computed from the instrument and holding on its
own:

- `bound = ceil(log2(len(CLASS_TABLES))) = ceil(log2(224)) = 8`.
- The informed arm must reach `unqueried == 1.0` on **every** seed at that
  budget, reduced with `all` so one short seed fails the check.

**There is no blind-arm half, and that absence is the finding.** A learner
given no observation retains the whole class by construction, so any test
asserting it identifies nothing is a tautology. I wrote that half first and
deleted it. The blind column's honest content is which subset the tie-break
picks, and the artifact reports that (`blind_sequence`,
`blind_sequence_is_seed_independent`) instead of scoring it.

The artifact now also carries `blind_sequence` and
`blind_sequence_is_seed_independent`, so a reader sees that the blind column is
one subset before reading its mean.

**This check fails on the pre-freeze tree**, which is what makes it a test
rather than a description. Verified by restoring `44ec6c52~1`'s
`rule_learner.py` and the original ladder, then running the new suite: 5 failed.
The informed means were 0.8500 / 0.8958 / 0.9142, none of which is 1.0.

**`evidence_ceiling_diagnostic.py`: labels added, no logic changed.** It
recomputes `learner_revision.evidence_ceiling` under the current tree and
publishes it under the key `withdrawn_blind8`, which now returns 0.06 rather
than the 0.5017 the withdrawn artifact holds. Unlabelled, a reader would take
0.06 for the historical value and conclude the withdrawal had corrected an
error, when the freeze is what moved it. The output now says
`RECOMPUTED` and names the distribution the 0.5017 was a draw from.

## 5. Honest reporting

**Ran here, on Windows, Python 3.14.5, at base `8f10cd6e`, and re-verified after
rebasing onto `f3145187`.** Every figure above. Three commits from other lanes
(`learner_revision.py`, `s09_verdict.py`, `PROJECT-LEDGER.md`) landed on the
branch mid-task and are in the pushed history; none is mine and none touches
the learner or the ladder. The base commit the freeze sits behind is still
`8f10cd6e`.

**Inferred.** That the pre-freeze learner reconstruction is faithful. It is
verbatim from `44ec6c52~1` apart from an explicit rng attribute, and its
fidelity is evidenced by six four-decimal reproductions from it, which a wrong
reconstruction would not produce.

**Not reproduced exactly, but closer than a first pass suggested.** The ledger's
chance-level pair is `0.5138 / sd 0.0169`. Across 192 cohort/offset conventions
at 20 reps, the mean ranges 0.5000 to 0.5353 and the sd 0.0151 to 0.0363. No
convention lands on both at once, but the reason is narrow: 28 conventions fall
within 0.001 of the target mean, and the closest any sd comes to 0.0169 is
0.0170, a gap of 0.0001. So the pair is very likely a real measurement under an
unrecorded rep-seed convention, and I am not claiming it is fabricated. What
cannot be recovered from this tree is which convention produced it, because the
convention was never recorded and the pair does not uniquely identify one.

The claim the pair supports stands, and on firmer ground than the pair gave it:
the uniform-8-subset mean is 0.5195 / 0.5182 / 0.5134 for the three cohorts, so
the old blind figures 0.5017 / 0.5208 / 0.5292 sit inside that distribution,
which is what "chance" means here.

**Descriptive only.** No p-value, no significance claim, no effect size. The
exhaustive 12870-subset ranking and the 200-convention sweep are enumerations
of finite sets, not samples from a population, so the ranks and ranges are exact
statements about those sets and nothing more.

**CI must confirm.** The 24 errors seen locally in `tests/test_s09_e3_ladder.py`
and its neighbours are all `psycopg.OperationalError` against a local socket,
with `S09ISO_DISABLE=1` set and no Postgres on this host. They are the missing
database, not a regression from this lane. CI carries postgres:18 and must
confirm that shard. A green local run of this lane's own files does not
license anything about the rest of the suite.

## 6. Disposition

1. **M3 closes as a measured zero, and the null is stronger than recorded.**
   Its three legs never touched the learner, and leg (c)'s instrument now
   attains the bound its census asserted.
2. **The E4 blind arm is withdrawn as a competence figure in both regimes.**
   The ledger already withdrew the old number; the new `0.0600` should be
   withdrawn for a second and different reason, that it is the tie-break loser's
   subset rather than a sample. `e4_budget_ladder.py` no longer offers it as
   something to reconcile.
3. **The ledger needs one clarification the ledger owner must make**, since
   `PROJECT-LEDGER.md` is not this lane's file. The chance-level pair
   `0.5138 / sd 0.0169` should record the rep-seed convention that produced it,
   because 28 of the 192 conventions I swept reproduce its mean to within 0.001
   and its closest sd is 0.0001 away, so the pair cannot be checked by a later
   reader. Its conclusion does not need the correction.
4. **No M3 cell needs re-measuring.** The instrument got better; the null did
   not get worse.

**A valid null closes a study. This one still does, and it closes for reasons
that a change to a query tie-break cannot reach.**