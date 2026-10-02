# Independent review of the final acceptance pass

Reviewer lane `r-final`, against `8a207ab`. I authored none of the ~53
lanes and did not write `reports/FINAL-ACCEPTANCE.md`. Everything below was
measured by running the product, not by reading its reports. No live model
call, no network, no Jev.

Runtime: WSL Ubuntu, real PostgreSQL, `PYTHONPATH=src` into
`/home/ubuntu/.venvs/as9`, `SETTLEMENT_CLAIM_LEDGER` under `/home/ubuntu`.
No test was weakened, skipped or xfailed. No file under `reports/evidence/`
was touched. No production code was repaired.

---

## Headline

**Five of the six dispositions are right. The sixth, mechanism CONFIRMED,
is over-claimed, and it is over-claimed on the freeze.**

The chain is real. The rows are real. The tamper cases are proved against
genuinely green baselines, which I verified rather than assumed. But the
freeze, which the report calls "enforced against the parse, not a hand-kept
list" with "zero mismatches" across 19 binding forms, admits a revision that
writes the grant and reports it as an eligible intervention that informed a
decision. And the documented second layer that was supposed to catch exactly
this cannot fire.

The freeze is one layer deep, and that one layer has a door beside it that
the 19 probes did not open because all 19 were subscript or attribute
spellings.

---

## The six dispositions

### 1. Mechanism — **TOO GENEROUS**

The machinery works and the batch built it well. What it does not do is
establish what the report says it establishes.

**The freeze admits a revision that writes a frozen field.**
`improve_channel.py:1301` `_frozen_key` resolves a subscript key only when
it is an `ast.Constant` holding a `str`. Every other way of naming a frozen
field is admitted. I probed `improve_channel._attempts_frozen_write` with
five writing forms and confirmed each one writes `view["grant"]` at runtime:

| form | `_attempts_frozen_write` | writes grant at runtime |
|---|---|---|
| `view["grant"] = 1` | `True` | yes |
| `view.update({"grant": 1})` | `False` | yes |
| `view \|= {"grant": 1}` | `False` | yes |
| `view.pop("grant", None)` | `False` | yes |
| `view.clear()` | `False` | yes |
| `view[k] = 1` where `k = "grant"` | `False` | yes |

All six are admitted by `method_exec.verify_step_source`, which forbids
imports, dunder access and a list of reflective builtins, none of which
`dict.update` is.

The decisive case is end to end, through the boundary a caller reads. Take
the authorised revision and smuggle the write into the probed-input
expression:

```
(view.update({"grant": {"queries": 999999, "steps": 999999}}) or 3)
    if not view["experience"] else 8
```

`update` returns `None`, so the expression is still `3` and the revision is
still the authorised kind. `admit_revision_under_freeze` returns:

```
{'eligibility': 'eligible', 'decision': 'diagnostic-evidence-selection',
 'selected_evidence': [[3], [3], [3], [3]], 'informs_decision': True,
 'frozen_state_digest': 'a141eb20f33e059d1cee41f81418d52ab2e0ad421853edee581797c700025fbd'}
```

and executing those bytes sets `view["grant"]` to `{"queries": 999999,
"steps": 999999}`. The scope check cannot see it because `unauthorised_change`
blanks the `x` site before comparing shapes (`improve_channel.py:407`), and
the write lives inside that site.

**The documented backstop does not fire.** The report says the runtime
`frozen_state` comparison in `admit_revision_under_freeze`
(`improve_channel.py:1181-1191`) is "the layer that catches it". It cannot.
The revision executes in a bounded child process (`_run_source` calls
`method_exec.run_step_out_of_process`) against a JSON view. I instrumented
`create_disposable_db`: `classify_revision` opens five `invl02-revision`
disposable stores. Nothing in that path can reach the store being compared.
The view the child receives carries none of the six frozen fields at all:
`_step_view` produces `authority_remaining` and `improvement_budget`, and
`frozen_state(store)` reads `grant`, `used`, `authority`, `evaluator`,
`sealed_results`, `execution_limits` from the parent. Two disjoint sets.

I proved the comparison is not dead code by mutating the parent store from
inside `classify_revision`; it raised `FrozenFieldViolation` immediately. So
the check works, and it guards a boundary no revision byte can reach.

**The 19-form probe was sound and the number is right.** I re-ran the
literal-key forms and got `True` for all of them, `False` for reads and for
non-frozen keys. Zero mismatches on what it probed. The probe asked "which
syntactic spellings of a subscript write are refused", and the answer is
correct. The freeze's coverage is simply narrower than "enforced" reads.

What is genuinely correct here: `_attempts_frozen_write` replaced a
hand-kept list with the parser's own `Store`/`Del` contexts, which is the
right repair and closes `AnnAssign` and `NamedExpr` for good. X2's finding
was real. This is a gap beside it, not a regression from it.

**The causal gap.** Arrow 3 of `tests/test_inv_a_chain.py` asserts each
admitted operation settled with a receipt. That holds. But the arrow from
the effect to the observation has no join. `s09_policy_state.effect_id` is
written as a synthesized constant, `ad01-<cid>-b<seq>-effect`
(`experiments/ad01/trajectory.py:257`, used at `:284` and `:307`), and it
names no row anywhere. I ran a real three-boundary campaign against
PostgreSQL and checked every synthesized id against `operations`:

```
seq=0 effect_id=ad01-ad01-w0-I-771-b0-effect   in operations? False
seq=1 effect_id=ad01-ad01-w0-I-771-b1-effect   in operations? False
seq=2 effect_id=ad01-ad01-w0-I-771-b2-effect   in operations? False
any observation carries an operation_id/effect_id: False
```

`attempt_observations` has columns `(id, attempt_id, content, created_at)`.
`operations` has its own `id TEXT PRIMARY KEY`. Nothing joins them. Both
sides of the arrow are durable rows and the row that ought to bind them is
a derived string that was never an identity. `_publish_boundary`
(`trajectory.py:1150-1160`) writes a boundary observation carrying `seq`,
`task_id`, `decision` and `observation_id`, and no operation reference.

This is the shape the batch's own `IMPLEMENTATION-WORKFLOW.md` warns about,
and it is what makes "durable row exists" weaker than "the arrow is causally
connected". The chain's seven arrows are structurally present and four of
them are causally bound. Arrow 3 and the observation arrow are bound by
`(investigation_id, seq)` alone.

**The tamper baselines are real.** I drove two of them myself with the
tamper removed. Counterexample 2: the member runs through the real broker,
`status` absent, source digest matches, operation `settled=True` in state
`observed`, one receipt `local:rf-bytes-clean-op_exec-default.result`
`success`. With the substitution in place the same call refuses
`refused: staged source digest mismatch` and `dispatch` is never called.
Counterexample 6: the terminating program produces one episode with
`disposition = inspected`. Both baselines are green before the tamper fires.
The report's count of four real green baselines is not inflated.

### 2. Acquisition — **CONFIRMED**

Recomputed from `reports/evidence/invr1b12-swe/campaign.json`, not the
summary: `acquired_lineages 0`, `independent_acquired_lineages 0`,
`distinct_acquisition_digests 0`, `lineages_attempted 4`,
`no_acquisition_lineages 4`.

I checked the lane the report waves at, the r4 archive, for an acquired
artifact under another name. `reports/evidence/invr1b14-retention/retention.json`
carries three `live_acquired_members` with `acquired_from_provider: true`,
real `operation_id` and `receipt_identity` (`gw:ad01-r4acq-t1-…-construct-l1-init`),
and `distinct_verdicts: ["preserved"]` on every member. Those are genuinely
acquired bytes and they are recorded as such, with `routable: false` and a
`not_claimed` that says the ceiling rests on a rate.

Nothing here contradicts the negative. The distinction the report draws,
fixture qualification held apart from live acquisition, is real and the
offline demonstration is labelled `OFFLINE DEMONSTRATION, NOT A LIVE
ACQUISITION` with `acquired_from_provider: false`. A negative that is this
well annotated is not a negative hiding a positive.

### 3. Utility — **CONFIRMED**

B12 acquired nothing, a failed acquisition is not promoted to an authored
learned arm, and no authored substitute appears. I confirmed
`acquired_artifacts: []` and `improvement_mode: "operate"` on the two-domain
entry and no learned arm in either evidence directory. "Not measurable" is
the correct word, and the report is explicit that a mechanism result is not
becoming a utility result.

### 4. Transfer — **CONFIRMED**

Two independent zeros, both real. The retention leg is 0 of 3 over 27
executions with every verdict `preserved` and
`same_reduction_as_seed` true throughout, so nothing retained is
distinguishable from the seed. The C7 crossing transfers a classification
predicate, not answers; `permitted_experience.by_structure[SWE]` carries
`transferred: "value-fault classification"` and nothing else. The report
calls this a demonstration and not a result, which is right.

### 5. Autonomous selection — **CONFIRMED**

I recomputed `twodomain.cluster_census()` from source and got the report's
numbers exactly: boolean 1 cluster against 6 required, shortfall 5,
`powered: False`; SWE 9, `powered: True`; `powered_structures` is
`['software-fault-repair-v1']` and `crossing_powered` is `False`.

I read the crossing itself. The order is hardcoded at
`experiments/ad01/twodomain.py:340-349`: three Boolean episodes at
`(("dev", 4), ("dev", 11), ("qual", 7))` then three SWE episodes at
`(("dev", 0), ("dev", 1), ("held_out", 2))`. `"entered": "first"` and
`"entered": "second"` are literals in the returned dict. The entry is
written with `improvement_mode="operate"` and
`frontier["acquisition"] = "not-attempted"`. No frontier is consulted, no
candidate is chosen, nothing selects. "Not established" is correct and, if
anything, generous: the crossing does not attempt selection at all.

### 6. Learner improvement — **CONFIRMED**

`c4-live` has no workstream report, no evidence directory and no test. I
confirmed the mechanical part of the report: `_revision_source(3)` is 1067
characters, `(8)` is 1067, `(11)` is 1068, and none of the three trips
`_attempts_frozen_write`. The authorised kind stays eligible after X2
widened the guard. `CONTROL_ROLES` is a strict subset of
`WRITTEN_CONTROL_ROLES`. Mechanism without a revised descendant cohort is
exactly what exists.

One caveat, not a defect in this disposition. The `_revision_source` family
is the same construction the freeze does not cover, so "the authorised kind
of revision stays eligible" is true for authorised bytes and says nothing
about what else is admissible. That caveat belongs to disposition 1.

---

## The freeze's computed-subscript-key limit, answered directly

**The claim does not hold. The runtime comparison does not fire.**

The report states the limit correctly and then states the mitigation
incorrectly. Three things are wrong with it.

1. The gap is wider than documented. A computed subscript key is one form.
   So is `dict.update`, `|=`, `pop` and `clear`, all of which write a
   frozen key the guard never inspects and which need no taint analysis to
   express.

2. The mitigation is unreachable. `admit_revision_under_freeze`'s
   before/after `frozen_state` comparison cannot observe a revision's
   writes, because the revision runs out of process against a JSON view that
   carries none of the six frozen fields, and the store being compared is
   never in the child's reach.

3. The consequence is not a narrower freeze but a false one. A revision that
   overwrites the grant is admitted as `eligible` with
   `informs_decision: True`. That is not "one layer deep", it is a grant
   authority a revision can rewrite while being told it informed a decision.

The honest statement of the limit is that the freeze is an AST check on
subscript and attribute spellings, and the runtime comparison is redundant
belt-and-braces that no candidate byte can currently reach. `w4-e4-interface.md:159`
calls that redundancy "justified by a cross-process boundary the AST scan
cannot see". The boundary is real; the reasoning is inverted, because the
cross-process boundary is exactly why the AST scan is the only layer that
sees anything.

---

## The fifth lock defect

**Found one, in the same shape. `src/settlement/trials.py:66-97`.**

`amend_protocol` reads the superseded protocol on one connection, calls
`conn.commit()`, closes it, builds the replacement through
`freeze_protocol`, then writes `UPDATE trial_protocols SET supersedes = %s,
frozen = TRUE` on a second connection with `autocommit=True`. The read and
the write are in different transactions and nothing serialises them. There
is no `FOR UPDATE`, no `ON CONFLICT`, and no command journal between the
two, because the `freeze_protocol` call in between carries its own
`request_id` and the final `UPDATE` is a bare autocommit statement.

Measured against real PostgreSQL: four concurrent amends of one parent all
return `ResultCode.APPLIED`, and the table is left with four frozen children
of the same parent and no unique successor.

```
id=proto-amend-0  supersedes=proto-base  frozen=True
id=proto-amend-1  supersedes=proto-base  frozen=True
id=proto-amend-2  supersedes=proto-base  frozen=True
id=proto-amend-3  supersedes=proto-base  frozen=True
```

This is the fourth element of the same generalisation the two search passes
named. Its severity is bounded: `trial_protocols` is not on the
milestone-A chain, and nothing in this batch claims an amended protocol has
a unique successor. The row carrying `supersedes` is what a reader would use
to find the successor, and four of them is a row that answers the wrong
question.

**What I looked for and did not find.** I probed the three sites the batch
itself repaired, and they hold. `accept_action` reads `s09_policy_state` on
one connection and inserts on another, which looks like the pattern, but
eight threads offering eight different decisions for one `(cid, seq)` all
fail with `ConflictPayload: request identity decide-<aid> reused with
different payload`. The command journal closes it, correctly and for a
reason the code does not state. `mission.admit_operation` is read and write
under one `FOR UPDATE` on one connection; six concurrent admits of six
distinct operations all landed, seqs `[0,1,2,3,4,5]`, no lost update.
`_s09_ensure_incorporated`'s `ON CONFLICT DO NOTHING` then `UPDATE` is
idempotent under six concurrent writers and left one row. The four defects
the passes found are four real fixes and I found no regression among them.

---

## Failing-first tests

`tests/test_r_final_freeze_and_chain.py`. Two tests fail against the current
tip and are the RF-01 record. The other nine pass and are the evidence that
each fixture writes what it claims to write and that the batch's own freeze
suite is untouched.

```
2 failed, 9 passed in 63.12s (0:01:03)
```

- `test_the_guard_refuses_a_frozen_write_made_through_a_dict_method` fails.
- `test_a_revision_writing_a_frozen_field_is_not_admitted_as_eligible` fails.

Passing, and load-bearing:

- `test_every_writing_form_reaches_the_frozen_key_at_runtime` runs all five
  forms and asserts each actually overwrites `grant`. This is what stops the
  refusal test from passing on a program that writes nothing.
- `test_the_smuggled_write_lands_and_still_reports_a_decision` asserts the
  write lands, the action is still a well-formed probe, and the verdict
  still claims `informs_decision`. That triple is the finding.
- `test_the_runtime_comparison_cannot_see_a_childs_write` runs admission
  and then asserts the store is untouched.
- `test_the_policy_states_effect_id_names_no_operation` asserts
  `effect_id` names no `operations` row and that
  `attempt_observations` carries no `operation_id`. It passes, and it is
  the RF-02 record; the defect is a missing join, so the test that detects
  it passes until someone adds the join.
- `test_one_protocol_cannot_be_amended_into_four_frozen_children` asserts
  `amend_protocol` opens two connections and writes `supersedes`. It is a
  source-shape record rather than a race harness, and the live measurement
  above is what makes it a finding.

## Baseline runs, reported separately, never summed

```
R1  tests/test_inv_a_chain.py test_inv_a_counterexamples.py
    test_inv_a_reviewer_source.py
    29 passed in 80.64s (0:01:20)

R2  tests/test_inv_x2_subscript_freeze.py
    test_inv_p2_frozen_write_binding_forms.py
    test_inv_c4_inheritable_construction.py
    74 passed in 73.86s (0:01:13)

R3  tests/test_r_final_freeze_and_chain.py
    2 failed, 9 passed in 63.12s (0:01:03)
```

Zero skips in all three. R3 is red by design and is mine. The batch's own
freeze suite is green on this tip, so RF-01 is a gap the suite does not
cover, not a regression I introduced.

---

## What the batch got right

Worth stating, because the batch was under no obligation to any of it.

The numeric layer is sound. I re-derived the cluster census, the B12
acquisition summary and the `_revision_source` sizes from source and
evidence, and every one agreed with the report. Four headline numbers
recomputed with zero disagreements is a real result.

The tamper discipline is real. Seven counterexamples, each with a clean
baseline in the same test on the same store, each asserting a literal
refusal rather than an exception type. I verified two of those baselines
myself and both are green before the tamper fires. That is the standard the
batch set, and it held.

Four live production defects found and fixed by two search passes, all
verified in source rather than trusted from a report. I re-probed three of
the four sites under concurrency and found no regression. The pattern the
passes named is the right generalisation.

Four negatives, each annotated well enough that a reader cannot mistake a
bounded zero for an impossibility, and each with the provenance that makes
it checkable. A batch that reports four negatives and means them is rarer
than a batch that reports one positive and over-claims it.

## What I would change in the report

The mechanism disposition should read: the chain's rows are durable and the
machinery holds under every tamper case the batch probed; the freeze is an
AST check that does not admit a revision writing a frozen field through
`dict.update`, `|=`, `pop` or `clear`, and the runtime comparison documented
as the second layer cannot observe a revision at all; arrow 3 and the
observation arrow are bound by `(investigation_id, seq)` rather than by
effect identity.

That is a smaller claim than "mechanism CONFIRMED with one limit". It is
also a claim the evidence supports.

## Final live process count

**0.** No Monitor armed, no subagent spawned, one pytest process at a time,
no network, no live model call, no Jev. Scratch probes under `.rf/` were
deleted before commit. Added here: this report and
`tests/test_r_final_freeze_and_chain.py`.

`git diff --name-only 8a207ab HEAD -- reports/evidence/` is empty.

Reviewed tip `8a207ab`.