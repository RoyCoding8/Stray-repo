> Historical batch report. Current scoped status is reconciled in [PROJECT-INVENTORY.md](PROJECT-INVENTORY.md) and [PROJECT-LEDGER.md](PROJECT-LEDGER.md). Read this file for its source revisions and measurements; its completion prose does not govern the current checkpoint.

# Stage 9 completion matrix and architectural recommendation

W5 handback. Reconstructed from committed artifacts and source at `19fbe69` on
`codex/implementation-development-01`, plus `ad5e9cd` on `wt/w1-e1-run` (one commit ahead of
the branch tip, carrying the E1 r1 campaign directory). The required scope is
`WORKER-PROMPT.md` §W5 lines 103-104.

**Reading rule.** A row is `completed` only where a named artifact carries the claim and the
artifact was read here. A lane's report is a claim, not a row. **A negative valid study
completes its question. An unrun study does not.** Where a lane report and its own artifact
disagree, the artifact is recorded and the disagreement is named in §6.

**Status vocabulary.** `implemented` means the code exists and is committed. `qualified`
means an independent control demonstrates the instrument detects the effect it exists for.
`attempted` means a study ran and produced a recorded result, positive or negative.
`completed` means the milestone's question is answered and the answer is on record.
`specifically blocked` means a named external constraint prevented the run and the constraint
is named. `unverified` means the claim is made in prose with no artifact found, which is not
the same as false.

---

## 0. Two premise corrections before the table

**This file already existed.** `reports/STAGE-09-COMPLETION-MATRIX.md` was committed at
`4066470` (501 lines) covering the *retired* M0-M4 milestone vocabulary from
`WORKER-STAGE-09-CONNECTED-STUDY.md` and `WORKER-STAGE-09-PARALLEL-EXPANSION.md`, those
prompts being superseded. `AGENTS.md` says "Do not create another competing current prompt,
workflow or task diary." Two matrices for the same stage would be exactly that. This file
therefore **replaces** the retired-vocabulary document rather than sitting beside it, and it
keeps its own section 1-9 history out. Where the old file said something about M0-M4 that
still bears on W0-W5, the substance is carried forward and the milestone is renamed to its
current label. The coordinator owns retiring the old cross-references.

**The E1 campaign in the brief is not the one on disk.** The brief describes "r1 spent 8
construction attempts for zero constructions, all filed `route-refusal`". The artifact at
`reports/evidence/w1-e1-boolean-r1/` (on `wt/w1-e1-run`, not merged) records **6
`route-refusal` and 2 `transport-loss`** across the eight lineage files. Counting
`campaign.json` `$.cells[*].outcomes`: P1 = 2 route-refusal, 2 transport-loss; P2 = 4
route-refusal. The README in the same directory says "route-refusal **or** transport-loss" in
prose and is right; only the brief's summary collapses the two. The conclusion is unaffected.
Both refusals were harness-side and neither is a claim about the model.

**E1 r2 exists and ran.** This section was written at `19fbe69` and was false at
the commit that made it, `97b320a`, which added thirteen r2 files. The `git
grep` it cites as proof was run before those files existed. §1, §2 and
bottleneck B2 carried the same error, and B2 recommended as a "cheapest fix"
work that was already done.

r2 ran 8 dispatches on the repaired path: 3 `invalid-program` + 1
`transport-loss` per arm, identical in both. Construction events 0, unique
source programs 0, retained records 8 — so **0 acquisitions, not 8**. The
repaired route contract held on all 6 answered dispatches with
`route_error: None`, so r1's zero was the harness's and r2's is not.

**Three independent review passes then found that r2's own headline does not
survive either.** The direction holds; the numbers attached to it do not.

1. **The 512-character cap is the campaign's, not the protocol's.**
   `max_response_characters` appears in `live_construct.py` only at `:44` (the
   constant), `:61` (prompt text) and `:110` (interpolation). **No shipped
   function compares a response's length against it** — `render_output_prompt`
   only states the limit in the prompt. The enforcement lived at
   `w1_e1_campaign_r2.py:549`, in the campaign lane's own driver. A conforming
   answer is 143 characters, so length is not by itself the binding
   constraint.
2. **All 8 attempts were `attempt: 1`.** `render_output_prompt` accepts
   attempt 2 and produces a different prompt; the driver hardcoded attempt 1
   and the branch was never written. The prompt said "Attempt 1 of 2" and the
   harness never made a second. `repairs_planned: 0` was justified by a
   constraint that does not exist.
3. **The four "independent lineages" are one experiment run four times per
   arm.** Only the arm varies. There is no sampling parameter, so repeated
   calls are the only source of variation, and the cap sheet's independence
   rule is a digest test applied to what is an input problem. Eight draws of
   one experiment is a real measurement; it is not n=4, and it is not a
   two-arm comparison, because both arms failed before the treatment could
   matter.

A third campaign (r3) ran under a new freeze with both frozen seeds,
both attempt numbers, and results reported at more than one cap so a reader
can see how much of the outcome is the cap the campaign chose.

---

## 1. Completion matrix

| Lane | State | Artifact evidence | What is established | What is not |
|---|---|---|---|---|
| **W0** reconcile and establish readiness | **completed** (substantially) | `reports/workstreams/w0-tr01.md`-`w0-tr05.md`; commit range `16f0784`..`a89141b`; route re-freeze `395d360` | TR-01 through TR-05 mapped to evidence, 5/5 reconciled, verdicts reproduced from raw records. Four further defects surfaced that the reviews never named. Twelve repair commits followed `16f0784`, each against a stated baseline. Live route verified: 256 catalog entries, 32 free, bare id present, `openrouter/`-prefixed id absent; one live inference returned HTTP 200, `finish_reason: stop`, `usage.cost: 0`. | Two preconditions remain unmet and are listed in §2. |
| **W1 / E1** connected representation and acquisition comparison | **attempted**, then **specifically blocked** at the acquisition step | `reports/evidence/w1-e1-boolean-r1/` (`campaign.json`, `campaign-manifest.json`, `exposure.json`, 8 lineage files) on `wt/w1-e1-run` @ `ad5e9cd`; cap sheet `reports/cap-sheets/w1-e1-cap.md` | The shipped path carries a live dispatch end to end: `LiveGuard.infer` over `HttpGatewayAdapter`, `render_output_prompt` (`live_construct.py:100`), `output_operation_id` (`:113`), `extract_and_validate_boolean` (`:952`). Eight lineages, all eight verified offline (`campaign.json` `$.verification`: `checked: 8, failures: [], passed: 8`). Counters and pending exposure were written before the first dispatch. | **Zero constructions.** 6 route-refusal, 2 transport-loss. E1 has no acquisition result. See §0 for the count correction. |
| **W2 / E2** experience, retention and transfer | **completed, null** (the metric is fixed and the question is now asked) | commit `d42049c`; `tests/test_s09_e2_benefit_leg.py:100`, `:456`, `:469`; `tests/test_s09_e2_scored.py:431` | The primary benefit statistic was contaminated and is now repaired. `QUALITY = {"preserved": 1, ..}` fed `score = evidence + quality`; `preserved` is a fixpoint, so `quality` was always 1.0 and `score` could only be 1.0 or 2.0. The leg is `normalized_reduction`. The `QUALITY` table is deleted, not renamed. Red-proof recorded: the new test failed on old code with `assert [0.0, 0.0] == [0.5, 0.75]`. | **MEASURED, and the answer is a null.** `reports/evidence/invr1e2contrastr2/report.json`, two namespaces with disjoint stores and operation ids. Relevant and irrelevant experience are indistinguishable, and neither beats no-experience: both contrasts delta -0.0909, deltas [0.0, 0.0, -0.2727], z -1.225. On `within-sw-02` both experience arms switched to `seed-sw-greedy` and the control did not, so the two moved identically -- the separation that exists is experience-vs-none, not relevant-vs-irrelevant. **The null does not license "experience does not help":** a reachability census over the whole decision grid, computed offline with no model, shows `ddmin@8`, the zero-information default, is the best of twelve reachable cells on all three targets. The largest positive delta the panel admits is **0.0** and the negative side reaches 0.538. The instrument can report a policy that does worse and cannot report one that does better. |
| **W3 / E3** autonomous investigation selection | **completed, negative** | `reports/workstreams/w3-e3-recompute.md`; `experiments/ad01/agenda_policy.py:424`; `inv_r1_e3_ladder/e3-postfix-ladder.json` | Tables recomputed from source records, no value read off prose. Both the 2.7x margin and the crossover were wrong and are corrected: see §3.3. The controls were audited and one was reclassified. | **E3 does not demonstrate autonomous selection.** Both controls carry pre-committed `family/method step N of M` rationales and are scripted schedules. |
| **W4 / E4** one executable learner revision | **completed, negative** | `reports/evidence/inv_r1_e4/result.json`; `run/campaign.json`; `headroom.json`; `reports/workstreams/w4-e4-interface.md` | Six live dispatches returned executable STEP bytes. Six passed acquisition as `model-acquired`. **Zero were admitted.** Each refused as `delegates-to-unchanged-reducer`. The null is bounded on both sides. The mechanism is qualified by three controls. | No revision was admitted, so no revised-vs-incumbent cohort comparison exists. **The blocker is the two-element selector**: `improve_channel.classify_revision` (`:387`) refuses a revision whose choices equal `_incumbent_choices` or `_reducer_argmax`, and every reply named input 0, so all six were refused. The wider `0.5017` is **withdrawn** as a headroom figure -- it is a blind sequence measured in a reporting function with no path to admission -- so the question is not whether a boundary was too narrow but whether a *descendant* may gather its own evidence. See §5. |
| **W5** integration, analysis, handback | **this document** | this file | The matrix, six verdicts, three bottlenecks and the recommendation. | W5's other clauses (three independent review passes, verifier-baseline demonstration, export verification) are **not** discharged here. §2. |
| **E1** acquisition, per §W1 | **attempted, 0 constructions** | as W1/E1 | The path is real and carries a dispatch. | Acquisition exists for **one** cell. See §3.1. |
| **E2** experience/retention/transfer, per §W2 | **completed, null** | `d42049c` (repair), `5cf3fe8` (experience contrast), `cab9424` (retention + adaptation) | The instrument measures something that can vary, and the contrast is null. | **The contrast is not void.** The coordinator asserted it was 0.0 by arithmetic and that assertion was **wrong**: `_reduction_of` (`:1322`) reads `NORMALIZED_REDUCTION`, not `action`, and every row in `invr1e2contrastr2/report.json` carries both `normalized_reduction` and `action`. The deltas are real per-task differences (`0.4545 - 0.7273 = -0.2727`). The campaign's own driver bypasses `_measured_row` for this reason. Two further defects of the same class: `verdict` is `preserved` on all 1728 reducer outcomes the panel can produce, and the prompt names `reason` while `packet.project_observations` drops it. **The experience question is measured and null, and §W2 is now complete** (`cab9424`). Retention is **unmeasurable on this instrument** -- `default_repertoire` returns four authored seeds and `eligible_for` the two belonging to a task's family, identical for every arm on every target, so no acquired method can be nameable; the census reads `eligible_count: 2` and `retained_method_nameable: false` on all 9 targets. Adaptation found a **real domain effect that is not an experience effect**: every arm **-0.2692** from within to held-out with the experience contrast 0.0 on both sides. **The closed-panel result does not transfer** -- the panels there are open at max positive delta 0.285714, 0.263158 and 0.285714, so that null was measured where a positive result was expressible, which the experience null's own panel was not. |
| **E3** selection, per §W3 | **completed, negative** | as W3 | Tables recomputed; direction survives, margin does not; crossover corrected 30 to 20. | Autonomous selection is not demonstrated. |
| **E4** learner revision, per §W4 | **completed, negative** | as W4 | The mechanism can carry a revision. Six dispatches proved it. | The boundary cannot express one. |

**Tally.** **All four experiments are negative, and not for the same reason.** That is
the finding, not a shortfall in the write-up. E1 constructed nothing, and its largest single
cause is the route's failure at 2048 output tokens with the mechanism unestablished. E2's
experience contrast is measured and null on a panel that admits a maximum positive delta of
0.0, so the null does not say experience does not help. E3's tables are recomputed and do not
show autonomous selection, because both controls are pre-committed schedules. E4 admitted no
revision, and the headroom above its boundary is a blind-sequence artifact rather than a
narrow interface. **§W2 is now complete** at `cab9424`. Retention is **unmeasurable on this instrument**, and that is measured: `default_repertoire` returns four authored seeds and `eligible_for` the two belonging to a task's family, identically for every arm on every target, so no acquired method can enter another task's repertoire. The census reads `eligible_count: 2` and `retained_method_nameable: false` on all 9 targets with no model dispatched. Adaptation found a **real effect that is not an experience effect**: every arm is **-0.2692** from within to held-out, and the experience contrast is 0.0 on both sides.

**The prior closed-panel result does not transfer.** The census that closed the experience contrast's positive side is specific to `software`/`within`. The panels here are open -- `software`/`transfer` 2 of 3 rows at max positive delta **0.285714**, `graph`/`within` 3 of 3 at 0.263158, `graph`/`transfer` 3 of 3 at 0.285714. **So the retention-era null is measured on a panel that can express a positive result**, which the experience null could not claim.

---

## 2. What is still NOT PROVEN, and what is undetermined

None of these may be written up as passing. Each names the artifact that would have to change.

| Precondition or limit | State | Source |
|---|---|---|
| Confined read denial | **NOT PROVEN** | WSL2 advertises Landlock (ABI 7) then rejects `landlock_restrict_self` with EINVAL. The read-back fix, the constant and the pre-spawn refusal are proven on Linux; the denial itself is not. Needs bare metal or a VM. |
| Unknown uncertain reservation | **NOT IDENTIFIED** | `other_uncertain_reservations_excluded: 1` in `reports/evidence/invl02-live/store-reconciliation.json:44`. True historical exposure is **`>= 5563`**, not 5563. One read-only query against the `invl02_live` store closes it; this host cannot reach that store. |
| Checkpoint/restore, database half | **NOT PROVEN** | `scripts/checkpoint.py` / `restore.py` drive `pg_dump`/`pg_restore`. No Postgres on this host. |
| `source_context.json` generator agreement | **NOT PROVEN** | Committed digests match; a generator run on this host raises `drifted from its generator` (path separator change alters the whole-document digest). |
| Test counts, `test_s09swe_world.py` and `test_s09_swe_experiment.py` | **NOT RECORDED** | Both files exist. No count from this host is on record, so neither may be summed into any suite figure. |
| Rate limits, quota, concurrency | **UNVERIFIED** | Two probe calls cannot characterise a free route's limits. Reserve headroom is treated as unknown, not available. |
| E1 r2 on the repaired path | **artifact exists, 0 constructions** | `reports/evidence/w1-e1-boolean-r2/`, 8 lineages, 0 construction events. See §0. |
| W5 review passes, verifier baseline, export verification | **NOT DISCHARGED** | Outside the lane this document owns. |

**Undetermined, and I could not determine it from records.** Whether a live construction
completes on the repaired path. Whether E2's repaired metric produces any separation between
relevant, absent and irrelevant experience. Whether the `w1-e1-route-api-defect` lineages
(the `responses` API carries no `provider` field) were re-run against `chat/completions`,
which the same README records as decoding clean. Whether the E1 r1 attempt accounting agrees
with itself; `campaign.json` and `exposure.json` in the same directory disagree about the same
eight attempts. See §6.

---

## 3. Six separate verdicts

Each states what the evidence supports, what it does not, and the strongest counter-reading.
These are different claims with different evidence and they do not blur.

### 3.1 Mechanism

**Supported.** A model-authored executable program can be dispatched to a real model, returned
as bytes, parsed, validated, executed in a bounded child, bound to a digest, and re-verified
offline with the network withdrawn. E1 r1 does this eight times with `verification.passed: 8`
and `network_withdrawn: true`. E4 does it six times and classifies all six as `model-acquired`.
The accounting, the grant, the receipt and the offline recompute are real machinery and they
work.

**Not supported.** That the mechanism can carry a representation other than a Boolean
predictor. `render_output_prompt` is the only live acquisition prompt in the tree, and
`OUTPUT_TASKS = {"qual": 11, "audit": 23}` (`live_construct.py:51`) is Boolean-only.
`output_operation_id` (`:115-118`) refuses any split outside that dict and any seed that is not
its frozen pair. There is no ordering counterpart to `extract_and_validate_boolean`.

**Strongest counter-reading.** E1 r1 produced zero programs, so the "mechanism works" claim
rests on the harness agreeing with itself. The strongest version of the objection is that the
offline verifier re-derives the verdict using the same parser the driver used, so agreement
proves determinism and not correctness. That objection is partly answered: E4's six refusals
were made by *executing* the returned bytes and comparing behaviour, and they were correct.
Determinism is proven; correctness is proven only where an independent control also exists.

### 3.2 Acquisition

**Supported.** Acquisition happens and is distinguishable from authoring. E1 r4
(`invl02_liveacq_r4/summary.json`) records `acquired: 3` acquired ENTRY wrappers delegating to
authored `ddmin`, with `bound_equals_candidate` and `executed_bytes_are_the_bound_policy`
both `pass`. E4's six replies were syntactically distinct model output, executed and refused.

**Not supported.** That acquisition exists for anything but Boolean. The E1 r1 campaign's own
`$.scope.rejected` names this: "no shipped prompt asks a model for a typed AST or an action
graph. Every `policy_ast` and graph record in the tree is built by an authored builder in
`s09_representation_matrix`." Ordering is rejected for a separate reason: the executors exist
and are reachable in-process, but acquisition for them does not exist. **E1 has one
constructible cell today, not nine.** The cap sheet marks all three representations supported
on all three worlds; that row is a plan, not a measurement.

**Strongest counter-reading.** Someone could argue the r4 wrappers count as acquisition. They
are three records delegating to an authored `ddmin`, and the campaign labelled them so itself.
The label is correct and should not be softened.

### 3.3 Task utility

**Supported.** Almost nothing, and the negative is the finding. `invl02_liveacq_r4/summary.json`
records `mean_acquired_minus_control: -0.15277777777777776` and `utility: "CONTROL_WINS"` over
`paired_tasks: 3`. E3's recompute is the other half: the corrected best-in-space mean at budget
20 is `0.139776` against the agenda's fresh mean `0.083721`, and 96 of 196 constant rules beat
the specified default there. **The 2.7x is retracted.** `0.419328 / 0.156883 = 2.6729` pairs a fresh numerator with a denominator the ledger records as **withdrawn** (the shared-instance substrate), so the figure does not reproduce on the live path; and the companion "ratio exactly 3.0 at every non-zero budget" is an identity, MEAN being SUM/3 over exactly three worlds. The 1.67x at budget 20 **is** correct on the fresh path. The underlying defect is real and still live: `_score_constant_rules` returns a sum that is consumed by `gap_to_best` and `rules_beating_it`.
**denominator artifact**. `agenda_policy.py:424` `_score_constant_rules` returns a **sum**
over three worlds while every ladder row reports a **mean**. On one denominator the margin is
**1.67x**, and the crossover is **20, not 30**. Budget 14 is the agenda's only win and there the
best score is `0.000000` with all 196 rules vacuously tied.

**Not supported.** Any population claim. Three paired tasks on one instrument, and a
three-world mean with no transfer.

**Strongest counter-reading.** That `-0.1527..` is 3 tasks and could invert. True, and the
artifact says `unpaired_tasks: 3`, so half the data could not be paired at all. The honest
reading is that this is a loss on the pairs that could be measured, and the campaign's own
`control_distinct_refusal` records that the control was refused as non-distinct.

### 3.4 Transfer

**Supported.** Retained-method reuse beat cold reacquisition on cost. `inv_r1_e2_retention/costs.json`
records retained at 16345 units against cold at 19614, crossover at 5 uses. That is a cost
result with no model behaviour in it.

**Not supported.** Within-domain versus held-out-domain adaptation. The
`inv_r1_e2_transfer` contrast is **RETRACTED**; its scored re-run is a three-way tie at
`score: 1.0` on all three arms, and that tie was computed through the constant `QUALITY` leg
that `d42049c` has now deleted. **The old transfer result is void, not merely weak.**
Two-namespace replication now exists for the contrasts that support arms: `invr1w2retention`
and `invr1w2retentionr2` at `cab9424`, with distinct stores, operation ids and model bytes,
run after the first left supported arms with a measured result.

**Strongest counter-reading.** A cost crossover is not transfer, it is caching. That is right,
and it is still worth keeping: it is the one E2 result that survives the metric repair, because
it never read the constant.

### 3.5 Autonomous selection

**Supported.** A stateful policy reaches admitted operations with receipts, and the sever
control is real. `inv_r1_e3_selection/e3-sever-control.json` holds 24 cells with
`severed_is_prefix: true` and `vanished: true` in all 24, and `connected_had_an_effect: true` in
18. The decisions trace into admitted operations.

**Not supported.** That the system selects investigations autonomously. Both controls carry
pre-committed `family/method step N of M` rationales, so they are **scripted campaign orders**.
E3 is a policy compared against two schedules, and the prompt names this failure directly ("Do
not call a scripted campaign order an autonomous agenda"). The audit also found the
best-in-space oracle reads the reported held-out metric and is therefore a **retrospective
reference, not a deployable control**; `STAGE-09-HANDOVER.md:165` presented it as a control and
was wrong. And the sum/mean mismatch meant the disputed margin and crossover were both wrong
until recomputed.

**Strongest counter-reading.** The agenda does beat the *specified default* at budgets 14, 20
and 30, and that is a real difference between two things. The counter is that a
development-fitted control beats the agenda at 20, 30 and 40 on the live fresh-instance path,
so the agenda is not even the best non-oracle schedule tried.

**The E2 metric defect is why the transfer tie is void.** A statistic that was a fixpoint could
not have found a difference. Recording that is not softening the negative; it is the reason the
negative cannot be cited.

### 3.6 Learner improvement

**Supported.** The revision channel is real and runs end to end out of process. E4 dispatched
six live acquisitions, executed all six, and correctly refused all six. The boundary's own
reachable range is **`0.00622`** (`result.json` `$.ceiling`, over 75 unseen tasks, paired
`z: 1.42`). The decision the frozen reducer actually makes is far larger: the same evaluator
scores it at **`0.5017`** against the incumbent's **`0.0587`**, a paired delta of `0.443` at
`z = 17.4` (`$.evidence_ceiling`). **WITHDRAWN:** an earlier revision called this roughly 70x the
boundary's expressive range. It is not a headroom -- it is a *blind* sequence, built without ever
calling `learner.observe`, and an informed one beats it by +0.3483 at z=+11.38 on the same cohort.
The real headroom is a missing state update in a measurement harness. See §5.

**Not supported.** That the learner improved. It did not; it was never able to on this boundary.
`_STRATEGY_SOURCE` (`improve_channel.py:136`) has exactly two members, so `leaf_construct`
replaces the improvement source with a menu entry and the reviser's integer picks *which* one.
It can never widen the menu. A revision is a selector over a two-element set.

**Strongest counter-reading.** That the model was at fault for producing `x = len(view["experience"])`.
The models produced a selector in syntax and a constant in behaviour. The refusals were correct.
The counter-reading that survives is the one the artifact itself makes: within the frozen decision the
choice genuinely does not matter, so more dispatches cannot help. **The wider `0.5017` is
withdrawn as a headroom figure** -- it is a blind query sequence, built without ever calling
`learner.observe`, and an informed sequence beats it by +0.3483 at z=+11.38 on the same
cohort. The headroom is a missing state update in a measurement harness, not a narrow
interface. See §5 and `reports/workstreams/w4-leakage.md`.

---

## 4. Three decision-relevant bottlenecks

No more than three, per §W5.

### B1. The acquisition surface is one prompt, so E1 measures one cell out of nine

**Evidence.** `render_output_prompt` (`live_construct.py:100`) is the only live acquisition
prompt in the tree. `OUTPUT_TASKS` (`:51`) holds two Boolean seeds. `output_operation_id`
(`:115-118`) refuses anything else. The E1 r1 campaign's own `$.scope.rejected` names the
absence for typed AST and action graph, and confirms every `policy_ast`/graph record in the
tree is authored. The cap sheet (`reports/cap-sheets/w1-e1-cap.md`) marks all three
representations supported on all three worlds.

**Cost to fix.** Four acquisition prompts (ordering, typed AST, action graph, SWE) with their
parsers and operation-id rules, following the pattern `render_output_prompt` /
`extract_and_validate_boolean` / `output_operation_id` already set. That is days, not weeks,
and it is the single highest-leverage change in the batch. It is **not** a request to build a
DSL, and the prompt forbids that: "No Python interpreter is hidden beneath an AST/graph label
or build a general DSL platform just to fill the matrix." One prompt per representation, each
emitting that representation's own syntax, is the honest version.

### B2. A live construction has never been recorded on the repaired path

**Evidence.** The route-contract repair is committed and is an ancestor of the tip (`3721cd6`:
"Give the counting guard the same route owner the adapter uses"; `route_matches` is now the one
comparison, and the guard, the adapter and the catalog half all go through it). The repair's
own message claims "a live construction now completes end to end". **No artifact records one.**
E1 r1's eight lineages are all refusals or transport losses and all predate the repair. The
repair is verified by unit tests and by a live body matching offline, which is not the same as
a recorded construction.

**Cost to fix.** One campaign at the already-frozen 8-attempt ceiling, 16 model calls, no new
cap sheet needed. Cheapest item in this document. **The gap is one short live run, and it
should be closed before any further E1 cell is built** (B1), because a construction that works
on one representation is the precondition for the four new prompts meaning anything.

### B3. The E4 boundary is a two-element selector, and the headroom above it is a blind-sequence artifact

**Evidence.** The selector is real: `_STRATEGY_SOURCE` (`improve_channel.py:136`) has two members, and within that
frozen decision the choice genuinely does not matter, which is why six of six refusals were
correct. But the headroom that was read as an argument for widening it is withdrawn -- see §3.6
and §5. `leaf_construct`
(`:1196`) installs a menu member. `REACHABLE_EVIDENCE` (`:489`) is therefore a two-element
tuple whatever the reviser does. Measured consequence: the E4 boundary's reachable range is
`0.00622` on the original cohort and `-0.000889` at z=-0.33 on fresh seeds. **The wider
`0.0587`-to-`0.5017` span is withdrawn as a headroom figure** -- it compares a 1-input incumbent
against an 8-input blind sequence, and the recommendation reverses this row's direction: neither
number supports widening the menu. Six of six
admissible revisions were refused as `delegates-to-unchanged-reducer`, correctly.

**Cost to fix.** **Reversed, and withdrawn.** The first draft read this as a case for widening the revision interface, on the strength of a `0.0587`-to-`0.5017` span that is a *blind* sequence rather than a headroom -- and the recommendation at `reports/STAGE-09-RECOMMENDATION.md` shows neither number supports widening the menu. The cheap repair is in the harness: `learner_revision.py:966-977` never calls `learner.observe`, so the object is a tie-break RNG over a static disagreement function. Whether a *descendant* may gather its own evidence is a separate question needing its own freeze. The `w4-e4-interface` lane already
ranked the four candidate decisions and put diagnostic evidence selection first **because it
is the one already wired**. The counter is that widening the boundary is exactly the thing the
assignment froze to prevent, so this is a decision for the coordinator, not a repair to slip
in. It needs its own freeze.

**A fourth candidate I am not listing**, because it is a deployment fact and not a research
bottleneck: no supported Linux execution environment on this host. It is real, it is named in
§2, and it is not on this list because no amount of work on this codebase changes it.

---

## 5. What to keep, what to simplify, what to change

**Keep.** The accounting and provenance spine. Grants, receipts, digests, exposure counters
written before effects, and offline recomputation with the network withdrawn are the strongest
thing in this repository and they are why §2 can be honest at all. Keep the five-way failure
taxonomy in `preflight_verdict` (route refusal, transport loss, empty content, invalid program,
poor task result): it is what let E1 r1 report "zero constructions, for a harness reason"
instead of reporting a model failure. Keep the E4 qualification controls, and note that the
**disconnect-bytes control is the load-bearing one**. it is the only control that catches a
do-nothing reviser, and the no-op and known-effect controls both pass one. Keep
`route_matches`: one owner for a route field, after three separate repairs failed on the same
premise.

**Simplify.** Delete the three-representation-by-three-world matrix from the reporting surface
until the prompts exist. It currently implies nine cells and delivers one; a nine-cell table
with seven cells marked "no acquisition prompt exists" is a plan wearing a results table's
clothes. Then delete the duplicate host-capability predicate: `19fbe69` made
`current_execution_host()` the single authority and removed `launcher_local`'s copy, and the
remaining job is to make sure no caller still asks the old question. Do not add a fourth
control to E4, a wider DSL, or any new subsystem.

**Change, and I think this is the wrong architecture in one specific place.** The revision
boundary. `_STRATEGY_SOURCE` with two members is not a learner-improvement interface; it is a
binary switch dressed as a decision, and the E4 campaign proved in six dispatches that no
amount of model capability gets past it. The assignment asked W4 for a decision that "alters
the learner, not just solve the downstream task", and the current boundary cannot: a descendant
runs the authored menu's input, not the revision's choice. **Recommendation: freeze E4's
current interface as a documented negative, and open a fresh freeze for a revision interface
that can change which evidence the learner gathers rather than which of two authored inputs it
picks.** That is one change to what exists, not a new subsystem.

**The 0.5017-versus-0.00622 gap is WITHDRAWN as the justification for that move.** It is not the
headroom of a wider revision boundary: `learner_revision.py:966-977` builds the sequence by
calling `choose_query` and never calling `learner.observe`, and `choose_query`
(`rule_learner.py:40-48`) reads only the keys of `queried`, so the zero vector is inert and
the object is a tie-break RNG over a static disagreement function. The `0.5017` is a *blind*
sequence scored against a task it never saw. An informed sequence reaches 0.8500 on the same
cohort, +0.3483 at z=+11.38, and +0.2675 at z=+8.38 choosing on `qual` and scoring on `audit`,
which share zero truth tables. The headroom is real and it is a **missing state update in a
measurement harness**, not a narrow interface. Repairing the harness is a reporting
correction; whether a *descendant* may choose its own evidence is a separate question needing
its own freeze. See `reports/STAGE-09-RECOMMENDATION.md` and `reports/workstreams/w4-leakage.md`.

A second change, smaller: the ledger currently records the free-signal split-brain and the
`preexec_fn` escape as "repair in flight" and E2 as "NOT STARTED". All three are now repaired
or answered. Stale status in the ledger is what produced the brief's claim that E1 r2 exists,
and that claim would have gone into a handback as a finding.

---

## 6. Honest negatives, preserved

- **All four experiments are negative.** E2's experience contrast is null, and its positive side is closed by the panel rather than measured; E3's
  answer is "this is a policy against two scripts"; E4's answer is "the boundary is a
  two-element selector". None of these is softened anywhere in this document.
- **E1 has zero constructions.** Not one acquired cell. The mechanism carried a dispatch; it
  has never carried a program through to a result.
- **The E2 transfer tie is void, not weak.** It was computed through a constant that could not
  vary. It cannot be cited in either direction.
- **Historical exposure is `>= 5563`, not 5563**, and one reservation is still unidentified.
- **The direction of E3 survives; the margin does not.** The 2.7x is **retracted**
  rather than replaced -- it paired a fresh numerator with a withdrawn denominator and does
  not reproduce -- while the 1.67x at budget 20 is correct on the fresh path. The
  crossover correction stands: 30 becomes 20. Presenting the corrected figure as a small
  loss would be as dishonest as the original 2.7x.
- **Two files in one evidence directory disagree.** `campaign.json` records
  `$.exposure = {attempts_settled: 3, dispatches_spent: 3}`; `exposure.json` in the same
  directory records `attempts_settled: 6, dispatches_spent: 6` and lists two attempts as
  `state: "pending"`. **Both cannot be right about the same eight attempts.** Unresolved.
  Any exposure figure for E1 r1 must be read with that disagreement open.
- **The strongest counter-reading to the whole batch** is that the experiments are measuring
  the harness. E1 r1 produced zero programs; E4 produced six programs and zero admissions; the
  one live acquisition campaign that did run (r4) lost to its control. A reviewer is entitled
  to ask whether the instruments are capable of producing a positive result at all. The honest
  answer is that B3 shows one of them provably cannot, on this boundary, and the other two are
  untested in the direction that would show it.

### A process failure that belongs in a handback claiming independent verification

A lane ran the full test suite four times, twice concurrently on both operating systems, after
being told explicitly not to. Its own report diagnosed the pattern against
`scripts/run_bounded.py`: narrowing the conditions and re-running until the number came out
wanted. The coordinator then scoped a `pkill` to `*pytest*` without scoping to its own
repository, which may have killed another agent's processes in a different repository. I did
not run the suite while writing this document, and every number above is read from a committed
artifact or a source line rather than from a test run. This is recorded because a handback that
claims independent verification has to name the ways that claim was compromised in the batch it
covers.

---

## 7. Supersession

This document replaces the retired-vocabulary matrix at `4066470`, which covered M0-M4 from
prompts that `AGENTS.md` retires. The substance it recorded for M1-M4 is carried forward here
under W0-W5 and E1-E4 labels. `reports/PROJECT-LEDGER.md` and
`docs/design/REFINEMENT-ROADMAP.md` need updating in place to match §1 and §5, and the
coordinator owns that. Stage 9 stays **active**: the assigned evidence does not support
closure, and nothing in this document argues otherwise.

**Figures traceable to an artifact or a source line.** Every number above is read from a
committed JSON artifact, a source line, or a commit message recorded in this repository. None
is a figure from a lane's prose. Where a claim exists only in prose it is marked
`unverified` in §2 rather than repeated as a finding.
