# Stage 09: the acquired arm was a stand-in, and five more sites said so

Every site that writes or gates on a policy `origin`, what each one now does,
and what `task_utility_verdict` concludes about this stage's own results.

Measured on this branch at `8a231dd`. Nothing under `reports/evidence/` was
modified, regenerated or deleted. Where a committed record is named below it is
named as a record of what ran, and the finding is about it rather than in it.

## 1. What the stage's results now say

`task_utility_verdict` chose which rows went on the acquired side of a paired
mean by reading `freeze.policy_identities[arm].artifact.origin`. That field is
a claim the freeze makes about itself, and the check that read it could not
distinguish a claim from a receipt. So the comparison the stage reported was
computed over an arm that never acquired anything.

The committed verdict for the E1 control-arm run is
`reports/evidence/inv_r1_e1_control_arm_result/summary.md`, which reads
**CONTROL_WINS** over 18 paired tasks, mean acquired-minus-control normalized
reduction -0.009149184149184145.

Run against the same bundle with the origin re-derived, that run now reads:

```
task_utility_verdict = not_comparable
  [fail] arms_execute_their_own_bound_policy :: P0 executed source hashes to
         3834317f66d4, its bound policy is f92058cf6c04
  [pass] normalization_rule_stated
  [fail] shared_tasks_present :: acquired arms [], authored arms ['P0']; the
         freeze labels P1 'model-acquired' and its own construction record
         carries no evidence that a live provider wrote it
```

`CONTROL_WINS` is not a finding about acquisition. It is a constant measured
against two authored controls. The acquired arm executed
`experiments/doubles.py::ACQUIRED_ORDER_SOURCE`, byte for byte:

```
sha256(experiments/doubles.py::ACQUIRED_ORDER_SOURCE)
  = b0bd83b7ec80e6c23ba670da9fe2ba594139b9c98f8a113ae19a275e3c59a35c
acquired-gr-b0bd83b7 method_source == ACQUIRED_ORDER_SOURCE  -> True
acquired-sw-b0bd83b7 method_source == ACQUIRED_ORDER_SOURCE  -> True
```

Both members of the treatment arm carry the same digest, so the "acquired"
policy is one constant for the whole study. A mean over that constant against
`ddmin` and `greedy` measures the constant.

**The finding survives, and it is worth stating carefully.** The control arm
was authored and executed as authored, so the control side of every one of
these comparisons is sound. What is void is the treatment side. The correct
reading of the E1 result is "an authored control and a hand-written fixture
produced a difference of -0.009 over 18 paired tasks", which is a fact about
two constants and says nothing about whether a model can acquire a method.

### The other three bundles

`task_utility_verdict` run over every bundle in the repository at this commit:

| bundle | claimed acquired | earned acquired | verdict |
|---|---|---|---|
| `evidence_s09_m3_live` | `P1` | none | `not_comparable` |
| `evidence_s09_live_opus` | none | none | `not_comparable` |
| `evidence_s09pilot/doubled-r1` | none | none | `not_comparable` |

None of them carries an earned `model-acquired` arm. `evidence_s09_m3_live` is
the only one that claims one, and its construction record has no
`acquisition_evidence` key at all.

### E4 is a different case and is not on this list

`reports/evidence/inv_r1_e4/result.json` carries `model-acquired` eight times.
It is not a stand-in. Its six dispatches each record an `operation_id` of the
form `invl02-e4-revision-000N`, a `reached_a_route` of true, and the pinned
model `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`. The constant
`ACQUIRED_ORDER_SOURCE` does not appear anywhere in it. That run dispatched a
live provider and the provider's replies were all refused as
`delegates-to-unchanged-reducer`, so it acquired nothing, but for the opposite
and stated reason. `learner_revision.ACQUIRED` labels that judgement and is
correct to.

## 2. Every site, and what it does now

### Sites that wrote the label with no evidence

**`experiments/ad01/control_arm.py:485` `acquisition_identity`**

This is the site that produced the E1 freeze. It is handed member ids and
digests and can see nothing about who wrote the bytes. It wrote
`origin: "model-acquired"` unconditionally.

Now: the `origin` key is written only when a caller passes
`acquisition_evidence` with `earned` true. Absent it the key is missing, and a
missing origin reads as unknown. Evidence saying `earned: false` produces no
key, so a recording double cannot be labelled by handing over its own record.

**`experiments/ad01/e2_replication.py:1141` `score_acquired`**

Passed `origin="model-acquired"` into `scored.score_response` for every arm.

Now: `origin` is a required keyword. The caller at line 1249 holds the dsn and
the operation id, derives the origin with `construct.acquisition_origin`, and
falls back to `fixture-stand-in` when there is no settled text to compare.

**`experiments/ad01/s09_e2_scored.py:196` `Score.from_response` and `:288`
`score_response`**

Both defaulted `origin` to `"model-acquired"`. Both receive response text, which
a live provider and a recording double produce identically, so neither could
earn the label it asserted.

Now: `origin` is required on both. A caller holding a receipt and not passing
it gets a `TypeError` rather than a claim.

**`experiments/ad01/learner_revision.py:108` `ACQUIRED`**

Kept, and this is the one site that is not a defect. It is a judgement about a
reply that came off an `HttpGatewayAdapter`, reachable only through
`LiveAcquisition.dispatch`, which refuses without a pinned route in the
environment. No recording double can produce it, and `live_attributable` at
line 1314 independently re-checks `route`, `model` and `source_digest` on the
dispatch record before any report may claim the bytes are live. E4's own
artifact is the proof that the distinction is real.

The boundary is now written at the constant, because the string is shared with
the policy vocabulary and the next reader cannot tell them apart. `ACQUIRED_LABELS`
was defined, never used anywhere, and is deleted.

**`experiments/ad01/control_arm.py` was not the only writer of an acquired
origin in the freeze.** `policy_identities` at line 449 writes
`ORIGIN_AUTHORED` for the control arm. That one is earned: the study wrote
those bytes and the study is entitled to say so.

### The site that gates

**`experiments/ad01/s09_verdict.py` `Bundle.earned_origin`**

`arms_by_origin` is kept and still means "what the freeze claims".
`earned_origin` is new and is what every gate now reads. An arm claiming
`model-acquired` must carry `acquisition_evidence` with `earned` true in its
own construction record; absent that it reads `fixture-stand-in`. A bundle that
cannot show a provider is not evidence of one.

Five call sites moved from `arms_by_origin` to `earned_arms_by_origin`:
`live_acquisition_verdict`, `task_utility_verdict`, `transfer_verdict` and
`recursive_improvement_verdict`.

`live_acquisition_verdict` gained a fifth leg, `no_earned_acquired_arm`, which
names the demotion. The four provenance legs are asked of the arm that
*claimed* to be acquired rather than of the empty set, because its receipts are
still evidence about it, and a reader who has just been told the arm is a
stand-in is owed the specific reason rather than one generic sentence repeated
four times. On `evidence_s09_m3_live` the verdict still reports
`declared_model_matches_freeze` failing on `recorded-double` and
`dispatch_was_live_not_a_recording` failing for the same reason, which is
information the demotion does not replace.

### Sites that read an origin and are correct as they stand

`scripts/s09_verify.py:171` and `:191` treat an origin containing `authored` as
authored. They exclude authored digests from a set of constants, so reading the
label there makes a control more likely to be caught, not less. Not weakened.

`experiments/ad01/policy_step.py:194` `POLICY_ORIGINS` is the vocabulary
`make_policy_artifact` validates against. It is a closed set and a wider one
would let a record name an origin nothing else knows. Left as it is; the check
that matters is that the *writer* earns the value now, not that the reader
re-derives it twice.

`experiments/ad01/frontier.py:41` `PACKAGE_ORIGINS = ("authored-control",
"acquired")` is a different vocabulary in a different module, and
`frontier.validate_acquisition_evidence` at line 447 already refuses an
`acquired` package whose provenance does not resolve to a recorded gateway
dispatch and a finalization. That module got this right before anyone noticed
the problem elsewhere.

`experiments/ad01/s09_study_protocol.py:802` `classify_acquisition` reads
`receipt["provenance"]`. No code in this repository writes that field with the
value `model-acquired`; `settlement.broker` writes `provenance="gateway"`. The
function compares a field nothing populates, so it is inert rather than wrong,
and the one test that exercises it hand-builds the receipt. It is outside the
five named sites and outside this lane's ownership, so it is reported rather
than changed.

## 3. Tests that pinned a false value

Seven tests, all of which asserted something that was only true while the code
believed its own label.

| test | pinned | now pins |
|---|---|---|
| `test_s09_verdict.py::test_contaminated_run_names_its_three_failing_provenance_legs` | three failing legs, `bound_equals_candidate` among them | four failing legs plus the demotion, and `bound_equals_candidate` passing |
| `…::test_contaminated_utility_is_not_comparable_on_the_executed_digest` | P1's bytes counted on the acquired side | P1 absent from the paired contrast, and the demotion named |
| `…::test_contaminated_transfer_excludes_every_fallback_graph_record` | graph-record legs on P1 | the earned-origin refusal naming the demotion |
| `…::test_contaminated_recursive_improvement_is_ineligible_with_m4s_reason` | `task_solver_only` on P1 | the M4 refusal naming the demotion |
| `…::test_contaminated_run_does_not_decide_keep` | three legs in the rationale | four, with `no_earned_acquired_arm` last |
| `test_s09_e2_scored.py::test_a_parsed_proposal_scores_identically_to_its_response` | `model-acquired` for a literal in that file | `authored-control` for the study's own bytes |
| `control_arm.acquisition_identity` origin | no test existed | three new tests, one of them running the output through the verdict reader |

Four tests are new. `test_the_freeze_label_and_the_earned_origin_disagree_on_this_run`
asserts both reads side by side, so a test that exercised only the claim fails.
`test_evidence_that_says_not_earned_is_read_as_not_earned` builds the shape a
recording double really produces, a full record with `earned` false rather than
a missing one. `test_an_earned_arm_and_a_demoted_one_are_different_arms` holds
the label fixed and varies only the flag, so a gate that demoted every claim
fails it. `test_from_response_will_not_label_a_response_on_its_own` pins the
`TypeError`.

### Proof each rewrite can fail

Each mutation below was applied to the working tree, the named tests were run,
and the tree was restored. All three mutations fail at least one test.

1. `Bundle.earned_origin` returns `self.arm_origin(arm)` for every arm, which
   is the original defect. **6 tests fail**, including all four repaired
   contaminated-bundle tests and the discrimination test.
2. The earned check `evidence.get("earned") is True` is weakened to a presence
   check `isinstance(evidence, Mapping)`.
   **`test_evidence_that_says_not_earned_is_read_as_not_earned` fails.** This
   mutation passed before that test existed, which is the reason it does.
3. `control_arm.acquisition_identity` writes `artifact["origin"] =
   "model-acquired"` unconditionally again. **Both new control_arm tests
   fail.**
4. `Score.from_response` gets its `origin="model-acquired"` default back.
   **`test_from_response_will_not_label_a_response_on_its_own` fails.**

## 4. Artifacts whose acquired arm was a stand-in

By the measured digest `b0bd83b7ec80e6c23ba670da9fe2ba594139b9c98f8a113ae19a275e3c59a35c`.
These are records of what ran. They are not corrected in place, because a
corrected label applied retroactively would make a reader believe a run
measured something it did not.

### Committed result records

```
reports/evidence/inv_r1_e1_control_arm/freeze.json
reports/evidence/inv_r1_e1_comparison/acquired-greedy.json
reports/evidence/inv_r1_e1_control_arm_result/study_accounting.json
reports/evidence/inv_r1_e1_control_distinct_mechanism/result.json
reports/evidence/inv_r1_e1_control_distinct_mechanism/acquisition_provenance.json
```

`reports/evidence/inv_r1_e4/result.json` and
`reports/evidence/inv_r1_e4/run/campaign.json` carry an acquired-versus-control
comparison and are **not** on this list. Their dispatches reached a live route
and the double's bytes appear nowhere in either file.

### The result directory that states the comparison

```
reports/evidence/inv_r1_e1_control_arm_result/arms.json
reports/evidence/inv_r1_e1_control_arm_result/control_distinct.json
reports/evidence/inv_r1_e1_control_arm_result/summary.json
reports/evidence/inv_r1_e1_control_arm_result/summary.md
```

`summary.md` is the artifact that reads CONTROL_WINS. `arms.json` carries 162
references to the constant.

### The run's own inputs and outputs

```
reports/evidence/inv_r1_e1_control_arm/use_records.json          (144 refs)
reports/evidence/inv_r1_e1_control_arm/exports/export-w{0,1,2}-{I,R}.json
reports/evidence/inv_r1_e1_control_arm/repertoires/repertoire-w{0,1,2}-{I,R}.json
reports/evidence/inv_r1_e1_control_arm/repertoires/repertoire-w{0,1,2}-{I,R}-use-policy.py
```

### Built by a later lane on the same stand-in arm

```
reports/evidence/inv_r1_e1_control_walk/arms.json            (162 refs)
reports/evidence/inv_r1_e1_control_walk/control_distinct.json
reports/evidence/inv_r1_e1_control_walk/mechanism.json
reports/evidence/inv_r1_e1_control_walk/study_accounting.json
reports/evidence/inv_r1_e1_control_walk/summary.json
reports/evidence/inv_r1_e1_control_walk/summary.md
```

This directory was written after the provenance work began and rests on the
same stand-in treatment arm. Its `summary.md` reads CONTROL_WINS over 18
paired tasks at a mean of -0.0036. It is named here so the lane that owns it
is not surprised.

`reports/evidence/inv_r1_e1_exp_axis_arm/` also reads CONTROL_WINS and is
**not** on this list. Its `arms.json` carries no reference to the constant and
no `model-acquired` string. Whatever its treatment arm was, it was not this
one, and it is outside what was measured here.

### The record of the finding itself

```
reports/evidence/inv02_acquisition_provenance/affected_artifacts.json
reports/evidence/inv02_acquisition_provenance/real_double_database_check.json
reports/evidence/inv02_acquisition_provenance/seam.json
```

### Prose that states the comparison

Ten reports and reviews name the comparison in words. They are listed in
`affected_artifacts.json` and none was modified by this lane, because marking
superseded text in ten documents is a separate piece of work and the current
headings would need the surrounding argument read first.

## 5. Found and not fixed

**`tests/test_inv01_control_arm_in_study.py::test_experience_varies_reports_its_own_numbers`
fails on this branch.** It asserts the string `"72 observations, 1 distinct
verdict"`. Commit `b4d8862` changed
`control_distinctness.experience_varies` to count outcomes and now emits
`"1 distinct outcome(s)"`. That commit did not update this test. The assertion
is stale and the module is correct. The file is one this lane edited for a
different reason, so the one-word fix is available, but the module belongs to
another lane and the fix is theirs to make with their change. Left as it is and
reported.

**`s09_study_protocol.classify_acquisition` compares a field nothing
populates.** It reads `receipt["provenance"] == "model-acquired"`, and no
writer in this repository produces that value. It is inert, not wrong, and
outside both the five named sites and this lane's ownership. Reported.

**`reports/evidence/inv_r1_e1_control_walk/` is live in another lane.** It
rests on the stand-in arm above. Not modified. A sibling directory,
`inv_r1_e1_exp_axis_arm`, also reads CONTROL_WINS and was measured not to
contain the constant, so it is not on the list above and its provenance was
not established here.

**`scripts/inv01_study.py:1578` calls `acquisition_identity` without passing
evidence**, which is now correct behaviour rather than a bug: the study has no
receipt to pass at that point, so the freeze it writes carries no origin and the
verdict layer reads the arm as unknown. The file belongs to another lane, so
the call site was left alone and its new behaviour follows from the signature.

## 6. The broader pattern

Six sites wrote an origin they could not earn, and the one that gated on it
read a claim. Every fix here is the same shape: the function either receives
the receipt or refuses to write the label. There is no third option, and the
one site where a receipt genuinely exists (E4's dispatch) was already correct
and is now documented so the next reader knows which of the two vocabularies
they are looking at.

The generalisation worth carrying: an `origin` field in this repository is a
claim about authorship, and any code path that cannot name the operation
identity that produced the bytes is in no position to make it. Absence is a
valid answer and reads as unknown, which is a safer thing for a downstream
gate to encounter than a string it has no way to check.
