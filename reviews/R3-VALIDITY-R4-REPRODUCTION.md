# R3 validity + R4 reproduction — independent challenger

Lane: R3 (experimental validity) and R4 (reproduction). Read-only; nothing under
`src/`, `experiments/`, `tests/`, `conftest*` or `reports/` was modified. All
reproduction scratch is under `/tmp/r3`. No branch switch, no commit, no push.

Tip reviewed: `254f43e` on `codex/implementation-investigation-learning-02`.
`reports/STAGE-09-COMPLETION-MATRIX.md` had uncommitted edits at the time of
review; those are called out where they matter.

Nine findings. Three are new defects the ledger does not carry; three are places
the matrix is factually wrong; one is a ledger row whose evidence is mislabelled;
two are R4 outcomes. The empty-list outcome is not what happened.

---

## Summary table

| id | severity | area | one line |
|---|---|---|---|
| N-400 | critical | R3 validity | The E2 relevance contrast's headline control — "both arms carry 382 characters" — is false for the prompts it committed. 166 against 59. |
| N-401 | high | R3 validity | `ScoredContrast.differs` is not a function of the fields it is derived from; the committed record is unsatisfiable under the property that produced it. |
| N-402 | high | matrix wrong | The matrix contradicts itself on whether the two-namespace E2 replication exists, and the row it edited is a malformed table. |
| N-403 | medium | matrix wrong | The matrix's E4 row says "two files, no other artifact"; 17 are committed. The row also predates them. |
| N-404 | medium | matrix wrong | The matrix's M4 section says the live bundle "fails at this tip with 52 problems"; it is deterministically 55, at HEAD and at the claimed tip. |
| N-405 | medium | R3 validity | E3's `e3-crossover.json` reports `agenda_ahead_on_held_out: true` at the one tight budget on a control denominator of zero retained behaviours. |
| N-406 | medium | ledger wrong | N-79's location field names two **git commit hashes** as if they were file digests. Its substantive claim survives; its evidence citation does not. |
| N-407 | low | R3 validity | E1's byte-identity defect (N-77) repeats across **five** committed use-policy files in two experiments, not three in one. |
| N-408 | info | R4 | All three reproductions succeeded. Recorded so the negative result is on file, with the one self-inflicted failure named. |

---

## N-400 — critical — the E2 relevance "equal context volume" control did not hold

**Location.** `reports/evidence/inv_r1_e2_relevance/contrast.json`
(`relevant_chars: 382`, `irrelevant_chars: 382`); `RESULT.md:28` and `RESULT.md:62`;
`prompts.txt`.

**Reproduction.**

```console
$ .venv/bin/python /tmp/r3/repro_eqlen.py
committed-prompt observation blocks:
  relevant   chars = 166
  irrelevant chars = 59
  EQUAL? False | delta = 107
  contrast.json asserts 382 vs 382

equal_length_experience_pair REFUSED: experience arms must carry equal character
length: 166 against 59. An unequal control confounds semantic relevance with
context volume.

_set_observations REFUSED the committed shape: TreatmentRefused an experience
record needs observation_id, task_id and verdict:
{'task_id': 'ad01-w1-dev-gr-00', 'verdict': 'unmeasured'}
```

Directly on the committed prompt bytes: the two rendered prompts in `prompts.txt`
are **843 and 736 characters**. Stripping the `Prior observations:` line leaves
**657 and 657** — identical scaffolding, unequal experience. The 107-character
difference is entirely the experience block. The relevant arm carries three graph
dev seeds; the irrelevant arm carries **one** software record.

`RESULT.md:28` states: *"both arms carry **382 characters** of experience. So a
difference in what the model returns is attributable to the content of the
experience, not to how much text it was shown."* That sentence is the control
doing its job, and it is false for the artifacts in the directory.

**The gate exists and would have caught it.** `learner.equal_length_experience_pair`
(`experiments/ad01/learner.py:407`) raises `TreatmentRefused` on an unequal pair,
and `learner._set_observations` (line 434) requires `observation_id`, `task_id` and
`verdict` on every record. **The records in `prompts.txt` have no `observation_id`** —
so the shape in the committed file could not have come through `_set_observations`
at all. The `382` was therefore not produced by the function that owns this
invariant.

**Impact.** This is a **third, independent** defect in the same contrast, distinct
from both already on record: N-78 (both arms empty) and the `RETRACTED.md`
attribution (the `diagnostic` field echoes). It is the one the contrast's own
*design* rests on. The directory is retracted, so no live claim is currently
overstated — but `RESULT.md` is deliberately left unedited as "the record of what
was claimed", and it currently carries a false statement about its own control.
A reader who reads the retraction learns about the echo; a reader who reads the
result learns a false equal-length claim. Neither learns the control was unequal.

This also weakens the retraction's stated scope. The retraction says the mechanism
claim "does not survive challenge" for the echo reason. If the volume was
confounded too, the contrast was never a clean relevance test on **either** ground.

**Owner.** E2 owner. Re-derive the pair through `_set_observations` and record the
`_observation_chars` values the gate actually enforces, or state in `RETRACTED.md`
that the volume control did not hold and why the `382` figure is not reproducible
from `prompts.txt`.

---

## N-401 — high — `ScoredContrast.differs` is not well-defined over its own record

**Location.** `experiments/ad01/s09_e2_relevance.py:68-70` (the property) and
lines 138-145 (where `outcome` is set); `reports/evidence/inv_r1_e2_relevance/contrast.json`.

```python
    @property
    def differs(self) -> bool:
        if self.outcome == "unscored":
            return False
        return self.relevant.digest != self.irrelevant.digest
```

**Reproduction.**

```console
$ .venv/bin/python /tmp/r3/repro_differs.py
both empty -> outcome = tie | differs = False
actually-different text -> outcome = differs | differs = True
one arm errored -> outcome = unscored | differs = False

rebuilt from committed contrast.json -> differs = False (file records True )
```

The committed record has both digests equal to `sha256("")` and
`outcome: "differs"`. `differs` is written into that file by
`ScoredContrast.as_dict()` (line 83) from the property above. For the file to say
`differs: true`, the `relevant.digest != irrelevant.digest` branch must have
returned true — but the two digests in the file are the same 64 characters. No
`ScoredContrast` whose `as_dict()` produced those digest values can also produce
`differs: true`.

The only way to reconcile the two is if the `digest` values in the file were
written by something other than the `_arm` helper at line 123-131 (which computes
`hashlib.sha256(text).hexdigest()` over `proposal["source"]`). The property is
therefore not the sole determinant of the committed field, which means the
artifact and the code that claims to produce it disagree about how `differs` is
decided.

**Impact.** The direction of the defect matters more than the arithmetic. The
property is a **non-total function of the record it is serialized into**: the same
`(digest, digest, outcome)` triple is not enough to determine `differs`, so the
committed `differs: true` is not reconstructible from the committed fields. Under
N-78's reading the value should be `False`; under the code's `outcome`-first
branch it is `False` for a different reason. Either way `true` is unsupported.
This matters beyond the retracted directory: `e2_replication.py:747` cites this
exact artifact as the precedent for the null-dispatch rule
(`require_no_empty_dispatch_is_compared`), so the rule's motivating example carries
an unsatisfiable field.

**Owner.** E2 owner / `s09_e2_relevance.py` owner. Either make `differs` a pure
function of the serialized record, or have `as_dict` persist whatever inputs
actually produced it.

---

## N-402 — high — the completion matrix contradicts itself on the E2 replication

**Location.** `reports/STAGE-09-COMPLETION-MATRIX.md` line 34 (milestone table) vs
line 163 (unavailable-treatments table, **uncommitted edit**).

Line 34, committed at `f668656` and unchanged in the working tree:

> **The handoff's two-namespace replication (line 67) was not run**: there is one
> namespace and no replication directory exists.

Line 163, as edited in the working tree:

> | E2: two-namespace replication | **DONE, inconclusive** — `inv_r1_e2_replica/` ran
> 10 dispatches …

**Reproduction.**

```console
$ ls -d reports/evidence/inv_r1_e2_replica && ls reports/evidence/inv_r1_e2_replica
reports/evidence/inv_r1_e2_replica
RESULT.md
report.json

$ git log --oneline --diff-filter=A -- reports/evidence/inv_r1_e2_replica/
254f43e E2 replication: inconclusive, and the first namespace's instrument had two defects
```

The directory exists, is tracked, and was added in `254f43e` — the tip the matrix
is nominally describing. Line 34 is stale.

Three further defects in the edited row 163, all in the same line:

1. **Malformed table.** The row has five `|` delimiters where the table has four
   columns. `Ledger N-84, N-85 | |` inserts an empty extra cell.
2. **Stale evidence citation retained.** The row's evidence column still reads
   *"absence of any second namespace directory under `reports/evidence/`"* — the
   citation for the "not run" claim the same row is now contradicting.
3. **Stale prose retained.** The same row still reads *"One exists. No replication
   is claimed, so the gap blocks a claim rather than a result."*

Section 2 of the document (line 109-111) is also un-updated: *"What is missing.
The two-namespace replication."*

**Impact.** The document's own stated rule is that a status is a claim a reader
acts on. A reader who reads section 1 gets PARTIAL-because-not-replicated; a reader
who reads section 6 gets DONE. The edit corrected one row of three and left the
other two asserting the opposite, so the correction currently makes the document
*less* internally consistent than before it, not more.

**Owner.** Matrix author. Propagate the `254f43e` result to line 34 and section 2,
fix the row's column count, and replace the evidence citation with
`inv_r1_e2_replica/report.json` (`independent_of: "inv_r1_e2_scored"`,
`shares_with_first_namespace` all false, `null_dispatches: []`).

**On the underlying claim itself:** the replica is sound and the matrix's summary
of it is accurate. Nine distinct `response_digest` values across nine dispatches,
zero nulls, a disposable store, and an explicit `census` block recording that with
two `(family, template)` clusters the minimum p is 1/2 against a required 1/20, so
no p-value it can produce is inferential. `RESULT.md` states that in the artifact
and declines to offer a correction. This is the strongest validity practice in the
tree.

---

## N-403 — medium — the E4 row is stale and understates the committed evidence

**Location.** `reports/STAGE-09-COMPLETION-MATRIX.md` line 36.

> `inv_r1_e4/headroom.json` (9056 bytes), `inv_r1_e4/make_evidence.py` (10722 bytes)
> — **two files, no other artifact**

**Reproduction.**

```console
$ git ls-files reports/evidence/inv_r1_e4/ | wc -l
17
$ git log --oneline --diff-filter=A -- reports/evidence/inv_r1_e4/result.json reports/evidence/inv_r1_e4/run/
111ec3a E4: a qualified negative, with two findings against the lane's own claims
$ git log --oneline -1 -- reports/STAGE-09-COMPLETION-MATRIX.md
f668656 M4 is COMPLETE; my completion matrix had it BLOCKED on a wrong reading
```

Seventeen tracked files exist, including `result.json`, `make_result.py`, and a
`run/` directory holding 13 artifacts (`admission.json`, `campaign.json`, four
`round-*.json` pairs, six `diagnosis-*` files). The row was authored at `200fee7`
and last touched at `f668656`, both **before** `111ec3a` added them.

The same pattern as N-402: the matrix header pins itself to tip `dad929a`, but the
E4 artifacts (`111ec3a`) and the E2 replica (`254f43e`) both landed after.

**Impact.** The row's conclusion — apparatus qualified, live campaign's benefit
`false` for want of an eligible revision — is **correct**; I reproduced it (R4-2
below). But "no other artifact" is now false, and the omitted files are precisely
the ones carrying N-81 (`authority_deviation`) and N-82 (`evidence_ceiling`). A
reader auditing E4 from this row would not find the two findings against E4's own
claims.

**Owner.** Matrix author. Update the artifact column to the 17 tracked files, or
state explicitly that the row describes the state at `dad929a` and that `111ec3a`
added the live-campaign artifacts afterwards.

---

## N-404 — medium — the M4 bundle problem count is wrong

**Location.** `reports/STAGE-09-COMPLETION-MATRIX.md:485`.

> The real bundle `reports/evidence/invl02-r123/e12/m4-bundle.json` was recorded
> `pass` on 2026-09-25 and now **fails at this tip with 52 problems**, and
> `export_m4_bundle()` refuses that directory outright.

**Reproduction**, at HEAD and again at the tip the matrix names:

```console
$ .venv/bin/python /tmp/r3/repro_m4_bundle2.py
=== export_m4_bundle(e12 dir) ===
  REFUSED: ValueError live protocol does not match the study root
=== verify_m4_bundle(e12 dir) ===
  status: fail  problems: 55

$ .venv/bin/python /tmp/r3/repro_tip.py     # dad929a extracted to /tmp/r3/tipchk
AT TIP dad929a -- verify_m4_bundle problems = 55 status = fail
```

**55, not 52.** Stable across both tips, and the verifier is unchanged in between:

```console
$ git log --oneline dad929a..HEAD -- experiments/ad01/offline_recompute.py scripts/invl02_live.py
(empty)
```

The `export_m4_bundle` refusal and the `fail` status are both correct as written;
only the count is wrong. Full breakdown of the 55, for the record: 12
`missing-operation`, 12 `missing-receipt`, 8
`accounting-measurement-status-missing`, 6 `child-result-missing`, 3
`accounting-unmeasured-value-invalid`, 2 `construction-dispatch-ledger-mismatch`, 2
`freeze-incomplete`, 2 `frozen-task-identity-missing`, and 8 singletons.

**Impact.** Low consequence in itself, and worth stating plainly: the paragraph's
*conclusion* is unaffected, because the claim being made is "this bundle does not
pass", which 55 supports at least as well as 52. The reason it is a finding is
that this is the paragraph the author added specifically to correct a previously
wrong BLOCKED verdict. A count that is wrong by three in the sentence written to
prevent an unverified claim is the wrong place to be imprecise, and a reader
re-deriving it gets a number that does not match the document.

**Owner.** Matrix author. Re-derive with
`scripts.invl02_live.verify_m4_bundle("reports/evidence/invl02-r123/e12")` and
record 55, or state how 52 was reached.

---

## N-405 — medium — E3's crossover reports an advantage on a zero denominator

**Location.** `reports/evidence/inv_r1_e3_selection/e3-crossover.json`,
`crossover.tight[0]`, `crossover.per_budget[0]`, and the `ladder[1]` block
(budget 14).

**Reproduction.**

```console
$ .venv/bin/python   # e3-crossover.json, budget 14
  agenda | held_out_reduction_mean = 0.1450565411349725 | retained_behaviors = 3
  control | held_out_reduction_mean = 0.0                | retained_behaviors = 0

held_out_reduction across budgets, per policy:
  budget 8   agenda 0.0273 retained=1  | control 0.0000 retained=0
  budget 14  agenda 0.1451 retained=3  | control 0.0000 retained=0   <- the only TIGHT budget
  budget 20  agenda 0.1569 retained=4  | control 0.2535 retained=3
  budget 30  agenda 0.2314 retained=7  | control 0.2009 retained=3
  budget 40  agenda 0.2187 retained=10 | control 0.2512 retained=3
  budget 60  agenda 0.2336 retained=17 | control 0.1226 retained=3
```

`TIGHT = (14,)` (`experiments/ad01/s09_e3_selection.py:58`). At budget 14 the
control retained **zero** behaviours, so its `held_out_reduction_mean` is 0.0
because there is nothing to reduce, not because it reduced nothing well. The
artifact nonetheless records `agenda_ahead_on_held_out: true` there, and budget 14
is the **only** member of the `tight` list.

**This is a fourth degenerate-evidence signature beyond N-78**, and the only one
in a single-campaign arm rather than a transport failure. The pattern recurs at
budget 8 (`control_held_out: 0.0`, `retained: 0`), but budget 8 is not in
`per_budget_budgets` at all, so only the budget-14 instance is load-bearing.

**Two things this is *not*.** It is **not** post-hoc selection: `TIGHT` and `LOOSE`
are module-level constants with a stated rationale in the docstring at lines 54-57,
fixed before the runs, and `tight`/`loose` are a partition of a pre-registered set —
not a split on the outcome. And it is **not** new information about E3: the whole
`crossover` block sits inside the artifact N-80 already records as retracted for
being cumulative prefix sums of one traversal. The 46/46/46 control plateau is
visible in the same table.

**Impact.** Contained, because the artifact is retracted. Recorded because N-80's
fix — add a `RETRACTED.md` — would leave a reader who opens the JSON still able to
read `agenda_ahead_on_held_out: true` off the tight band. The retraction notice
should name the zero denominator alongside the prefix-sum cause; they are
independent defects and only the first is currently in the ledger.

**Owner.** E3 owner. Fold into the N-80 `RETRACTED.md` as a second stated cause.

---

## N-406 — medium — N-79's location field cites commit hashes as file digests

**Location.** `reviews/STAGE-09-FINDINGS.md:343` (N-79).

> | N-79 | major | OPEN — two committed E3 artifacts with the same measure_digest disagree |
> `reports/evidence/inv_r1_e3_selection/e3-store-witness.json` (`52235a6`);
> `e3-admitted-operations.json` (`a3b6cae`) |

**Reproduction.**

```console
$ git log -1 --format='%H %s' 52235a6
52235a69539b219cd0b27129675d363da1719a8d  E3: the sever control ran, and it exposed a
worse gap than the one it fixed
$ git log -1 --format='%H %s' a3b6cae
a3b6cae7a41f75ab9f7df0e3016ac85248a2e5dc  N-51: E3's decisions now reach admitted
operations with receipts
$ sha256sum reports/evidence/inv_r1_e3_selection/e3-store-witness.json
42d16d458d304dbdfed6a622226549efd063289322d917e029a86669afe4dbb5
```

Both quoted values are **git commit hashes**, presented in a location column that
otherwise names files. The actual file digests are `42d16d45` and `8eb69e23`.
Neither quoted value is a digest of either file; `52235a6` occurs inside
`e3-admitted-operations.json` only as the phrase *"identical to the run at
52235a6, before the fix"* — a commit reference in prose.

**The substantive claim survives, and I checked it two ways.**

The claim is that the two files report opposite facts. They do:

```
e3-store-witness.json        connected  written=0 in_store=0 receipts=5
e3-store-witness.json        severed    written=0 in_store=0 receipts=4
e3-admitted-operations.json  connected  written=5 in_store=5 receipts=5
e3-admitted-operations.json  severed    written=0 in_store=0 receipts=0
```

So N-79's impact statement and its recommended fix (mark the witness superseded)
stand. Its `run_yield` blocks are **identical** across the two files for both arms,
so the disagreement is confined to the operation-persistence counters — narrower
than "report opposite facts" implies, and the reason to prefer supersession over
regeneration.

**One correction to the row's reasoning.** The row's framing — "two artifacts
sharing a digest report opposite facts" — implies the shared `measure_digest` is
part of the problem. It is not:

```console
$ .venv/bin/python   # experiments/ad01/selection.py:301
FROZEN_MEASURE_DIGEST literal = ce5a140aff83
yield_measure_digest()  now   = ce5a140aff83
identical: True
```

`measure_digest` is `sha256` of the `YIELD_MEASURES` *definition*
(`selection.py:301-308`), pinned as a literal and asserted by
`assert_measure_freeze` precisely so a redefinition after outcomes are visible
cannot silently keep the old value. It is a measure-definition freeze, not a
per-run identity, and every one of the four `e3-selection` files carries it
because every one emitted it. It cannot distinguish arms or files, so its being
shared is expected and carries no information about drift. The defect is the
unmarked supersession alone.

**Owner.** E3 owner / ledger. Repoint the location column at the files (or say
"as of `52235a6`"), and drop the shared-digest framing, which invites a reader to
infer measure drift that the freeze mechanism is designed to prevent.

---

## N-407 — low — N-77's byte-identity defect is wider than recorded

**Location.** All five committed `*-use-policy.py` files:

```console
$ find reports/evidence -name "*use-policy.py" -exec sha256sum {} \;
3011991aaae335d9d060a25d75096697243e17f33f986d64ee92738933246a06  .../inv_r1_m3b/repertoires/repertoire-w2-I-use-policy.py
3011991aaae335d9d060a25d75096697243e17f33f986d64ee92738933246a06  .../inv_r1_m3b/repertoires/control-sw-use-policy.py
3011991aaae335d9d060a25d75096697243e17f33f986d64ee92738933246a06  .../inv_r1_e1_comparison/acquired-greedy-use-policy.py
3011991aaae335d9d060a25d75096697243e17f33f986d64ee92738933246a06  .../inv_r1_e1_comparison/m3-fallback-use-policy.py
3011991aaae335d9d060a25d75096697243e17f33f986d64ee92738933246a06  .../inv_r1_e1_comparison/control-sw-use-policy.py
```

**All five are one file**, across two experiments. N-77 records three, in
`inv_r1_e1_comparison/`. The M3b pair is a separate finding: the M3b control-vs-acquired
tie (`CONTROL.md`, "identical to every digit on every task measured") rests on an
acquired repertoire and an authored repertoire that ran through a byte-identical
use policy.

**But this is a documented fallback, not a hidden defect, and the M3b documents
say so.** `scripts/inv01_study.py:1003` `_v1_use_policy_fallback` is the authored
selector used when no model policy was acquired, and its docstring is explicit that
it "is the fallback that takes the first eligible member, not a policy the model"
wrote. `inv_r1_m3b/RESULT.md:49` states it in the artifact. What differs from E1
is that E1's `RESULT.md:16` presents the two repertoires as differing in bytes —
"Bytes hashed `cfadd1a52120`" against "bytes hashed `db984e74726b`" — and:

- `db984e74726b` appears **nowhere in the repository** except that sentence and
  the two documents that quote it;
- the acquired `cfadd1a52120` **does** verify, as `sha256(method_source)`;
- `sha256` of the control's actual `method_source` is `c9f1f7f70d58`.

A related detail N-77 does not carry: the control's two members ship
`source_digest` values that are `sha256(capability_id)`, not `sha256(method_source)`
— `scripts/inv01_study.py:948` hashes the id deliberately, so `seed-sw-ddmin` and
`seed-sw-greedy` declare *different* digests over *identical* source text
(`e2ca3cf190c2` and `0ba85e817788`, both over `c9f1f7f70d58`). The repertoires are
distinguished by a `params` field over shared text. So the "different bytes"
framing fails twice over: the three policy files are one file, and the two
repertoires' own digests are digests of their names.

**Impact.** No new claim is invalidated. The E1 tie (23 against 23) stands on the
outcome table, which nothing here contradicts — the matrix says the same at section
7.1. Recorded so the fix is scoped to five files in two directories rather than
three in one, and so the M3b pair is not re-discovered as new.

**Owner.** E1 owner. Either re-derive both digests from the committed files, or
withdraw the byte-identity claim. The `db984e74726b` value should be removed from
`RESULT.md` rather than left to be re-derived from nothing.

---

## N-408 — info — R4: all three reproductions succeeded

Recorded so the negative result is on file, and so the one self-inflicted failure
is named rather than quietly dropped.

**R4-1 — E4 headroom: reproduced exactly.**

```console
$ cp reports/evidence/inv_r1_e4/headroom.json /tmp/r3/headroom.committed.json
$ .venv/bin/python reports/evidence/inv_r1_e4/make_evidence.py    # exit 0
$ diff <(json canonical committed) <(json canonical regenerated)
IDENTICAL: E4 headroom.json reproduced byte-for-byte (semantic)
```

Every number in `headroom.json` — the 0.00267 ceiling, the sixteen input means,
the three controls, the eight-entry `scaling` sweep, the 1500-seed population —
regenerates exactly from `make_evidence.py` against current code. The generator
also writes the cohort inputs beside the numbers, as its docstring promises. This
is the best-formed evidence in the tree.

**R4-2 — E4 live campaign: reproduced exactly, with one correction to my own method.**

The arms in `result.json` replay exactly through `learner_revision.compare` on the
recorded 150-seed audit cohort:

```console
acquired      x_revised=-1 -> compare() returns measured:false; reproduced
disconnect    x_revised=-1 -> compare() returns measured:false; reproduced
known-effect  x=8    EXACT MATCH
no-op         x=3    EXACT MATCH

E4 live-campaign arms reproduce exactly: True
```

Compared field by field across `delta, n, paired_sd, paired_se, z, mean_revised,
mean_incumbent, measured`.

**My first attempt failed and I record it as my error, not a finding.** I initially
replayed the arms through `improve_channel.evaluate_descendants`, got 0.0575 for
*both* arms against committed 0.0622 and 0.0609, and would have had a
reproduction-failure finding. `result.json` was not produced by that function —
`learner_revision.cohort_scores` (line 806) is the real path, and it applies
`descendant_of(x_probed, …)`, not the evidence-list form. The two APIs take
different arguments. No defect; noted because a reviewer who took the first path
would report a false failure against E4, which is the reason for writing it down.

**R4-3 — E1 ordering matrix: reproduced exactly.** No committed generator exists
for `inv_r1_e1_ordering_matrix/matrix.json` — the registry is only exercised from
`tests/test_ordering_step_arm.py` — so I reconstructed the run from
`build_ordering_registry()` over the five recorded tasks:

```console
audit/5 comparable=True  agree=True  overalls=[0.0, 0.0, 0.0]
dev/11 comparable=True  agree=True  overalls=[0.0, 0.0, 0.0]
dev/4  comparable=True  agree=True  overalls=[0.0, 0.0, 0.0]
dev/7  comparable=True  agree=True  overalls=[0.0, 0.0, 0.0]
qual/2 comparable=True  agree=True  overalls=[0.0, 0.0, 0.0]
```

All fifteen cells match the committed `matrix.json` on `overall` and on
`queries_spent`, with `agree: true` and `all_pairs_comparable: true` on all five.

**Also verified as a cross-check, not a reproduction:** the M3b refusal split that
the matrix quotes from `use_records.json` — 30 records with
`"use ran with no policy: the method identity must come from an admitted policy
action"` and 3 with `"admitted 'acquired-sw-5b65c917' is scoped to 'software' and
cannot answer a graph task"`. 30 + 3 = 33 refused, 3 preserved, 36 total. The
matrix's count at line 30 is exact.

---

## What I did not find

Stated explicitly so the negative results are legible.

**No post-hoc selection I can demonstrate.** I checked the one structure that
looks like outcome-defined banding — E3's `tight`/`loose` split — and it is not.
`TIGHT = (14,)` and `LOOSE = (20, 40, 60)` are module-level constants with a
rationale in the source docstring, and they partition the pre-registered
`per_budget_budgets` without reference to any outcome. The fact that budget 14 is
the only tight budget, and that it is the budget with a zero denominator (N-405), is
a coincidence of the substrate, not a selection. The expansion doc's "freeze the
core contrasts before assessment" is honoured in every artifact I read: the E2
replica records a `freeze_digest` and a `verify_freeze` that refuses drift, and
states the freeze preceded the effect.

**No uncorrected inferential claim outside the E2 replica.** I swept every
`reports/evidence/**/*.json` for `p_value`, `significance`, `bonferroni`, `holm`,
`multiplicity` and `correct` keys. The only hits are the E2 replica's `census`
block, which is the correction — it records `cluster_count: 2`, `minimum_p: "1/2"`,
`required_at_alpha_1_20: 6`, and `RESULT.md` states in plain text that no p-value
this contrast can produce is inferential. Every other paired estimate in the tree
either carries `z: null` because its variance is degenerate, or is reported as a
descriptive count. The `paired_sd: 0` instances (`inv_r1_e4/headroom.json`,
`inv_r1_e2_replica/report.json`) all have `z: null` beside them, which is the
correct handling and the opposite of the N-78 pattern.

**No false replication claim.** The E2 replica is the only result described as
replicated, and it holds up: `independent_of: "inv_r1_e2_scored"`,
`shares_with_first_namespace` false on all five axes, `null_dispatches: []`, nine
distinct response digests, a disposable store, and nine `dispatch_attempts` with
distinct operation ids. `RESULT.md` names what it did *not* replicate (retention
is arithmetic; substitution re-scores one acquisition) and why. E1's SWE
`RESULT.md:118` uses "replication" to mean "no replay or relabelling", which is a
different sense and correctly scoped. Nothing in the tree describes a
single-campaign result as replicated.

**The shared `measure_digest` across four E3 files is not a defect** (N-406). It is
a measure-definition freeze, working as designed.

---

## Method notes

- Every finding above has a reproduction I ran. Scripts are at `/tmp/r3/`
  (`repro_eqlen.py`, `repro_differs.py`, `repro_e4_correct.py`, `repro_e4_splits.py`,
  `repro_m4_bundle2.py`, `repro_m4_count.py`, `repro_tip.py`).
- The one pytest run (`tests/test_s09an_evidence.py`, 29 passed) used the repo's
  `tests/conftest_isolation.py`; it reported `S09ISO: dropped 20 database(s) for
  this run` and touched no shared `ec02test_*` database.
- `dad929a` was extracted with `git archive` into `/tmp/r3/tipchk` to re-derive the
  M4 problem count at the tip the matrix names. No worktree was created and no
  branch was switched.
- The M3b `use_records.json`, the E2 replica `report.json`, the E4 `result.json`,
  the E3 selection artifacts and the E1 comparison repertoires were all read
  directly and cross-checked against the code paths that produce them, rather than
  against the prose that describes them.
- A concurrent lane wrote `experiments/ad01/e3_ladder.py` and
  `reports/evidence/inv_r1_e3_ladder/` (both untracked) during this review. Neither
  is cited by any finding; N-405 concerns the committed
  `inv_r1_e3_selection/e3-crossover.json` only.
