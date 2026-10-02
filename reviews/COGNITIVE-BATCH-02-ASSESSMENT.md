# Cognitive Batch 02: useful substrate, live learning comparison incomplete

## Follow-up at `44de83e`: vertical gate accepted

The correction now provides a real repair path in `solver.py` and a committed six-record bundle under `experiments/team01/evidence-live2-vertical/`. The historical hybrid evidence is also tracked separately. Source inspection followed constructor parsing, `_submit_nodes` and `_final_tree_live`: the inspected path uses returned/submitted files rather than the old reference-overlay reconstruction.

Independent local check: reparsed the committed S constructor response using the current parser and its owned paths, computed `team.output_digest`, and matched both the parsed record and `submitted_digests.w1` at `940f57aa4827954646788b81e040faa5684944e029102bf16eef0262a4ba1862`. The six stored records report S/P/T success with 6/6 protected cases each; substitution fails with 0/6; disconnect refuses without scoring; the labeled incompatible control fails with 0/6. This review checked the stored records and source, not a fresh provider run, full sandbox replay or the worker's 67-test PostgreSQL result.

**Proceed through the remaining assignment.** CB2-01's one-task model-to-artifact gate is satisfied; full-panel baseline/resource validity remains to be demonstrated. CB2-02 actual template construction and the final live comparison/transfer are still open. CB2-03 has progressed: historical hybrid and new vertical bundles are tracked, but the final campaign's evidence cannot close until that campaign runs. No new small-defect review was commissioned.

The earlier instruction to prove a vertical path before panels was an execution dependency, not a request to stop and await another approval. The [updated continuation](../docs/HISTORY.md#worker-cognitive-batch-02-live-completion) explicitly authorizes completing the remaining sequence without intermediate handback gates. All evidence and findings below remain the historical assessment of `6942fa2`.

Reviewed worker `6942fa22444485739782f48e28a82ff413748bc3`, against assignment `895afd3`. This is a bounded assessment of the experiment-defining path, not another whole-repository audit. No production code was changed, no paid inference was run, and the 872-test PostgreSQL suite was not independently rerun.

## Disposition

Retain the delivered team substrate, task apparatus, gateway wiring and reported real-PostgreSQL verification. The reported Team 01 campaign is a hybrid planner/fixture exercise, not the required live S/P/T learning comparison. Its raw scores and failed token-ratio clause do not establish a null effect of team organization. The experimental contrast itself is missing.

The published representation live3 records are useful separate evidence. Independently recomputed: 48 arm-task records, 12 controls with no control-check problems, matching means and decision clauses, `promising=false`. C-source has no candidate (`not-json,timeout`); C-transfer has no frozen core. Accept the reported live campaign as a scoped unsuccessful acquisition/fallback attempt. Do not demand a positive C result or reopen its implementation here. Actual provider execution remains worker-reported; this review recomputed stored outcomes, not provider history or the full DB-backed checker.

Three connected obligations below require completion. These affect what experiment ran and whether its evidence was delivered; they are not cosmetic or speculative hardening.

## CB2-01 — live repair and comparators are replaced by authored outcomes

**Source:** `experiments/team01/live.py:156–171,189–208,630–646`; `panel.py:129–134,221–275,307–354`; `oracle.py:217–228`.

`LivePlanner` makes a live shape-selection call for T. S/P return without model inference. `_kinds` then selects authored valid/invalid implementations by arm and task family: S receives invalid sequential work; P receives two invalid coupled-interface attempts; T receives valid work. `panel._submit_real` loads those reference trees and registers them as child outputs. `_final_tree_real` reconstructs the scored tree from the same reference material. A real broker receipt and subprocess around these operations do not make the repair model-generated.

Direct execution of the current `_kinds` function on evaluation task IDs reproduced:

| Family | S, single | P, alternatives | T, single |
|---|---|---|---|
| Coupled | valid | invalid / invalid | valid |
| Independent | valid | invalid / valid | valid |
| Sequential | invalid | invalid / valid | valid |
| Adequate single | valid | invalid / valid | valid |

This arm-specific answer injection determines important performance differences before a model repairs anything. Zero comparator tokens are a consequence of missing baseline inference. Relaxing the ratio would conceal the missing comparison, not repair it. The planner also receives family-derived diagnosis/stability features rather than discovering them from the public source and task.

**Required completion:** route actual S, P and T repair work through live model calls, public source/context, observable tool feedback and bounded revisions. Bind the returned patch/artifact bytes through submission, assembly, freeze and final evaluation. Keep reference overlays in explicitly labeled apparatus controls only. Obtain policy features from visible task information or recorded, costed diagnostics; do not provide answer-bearing family lookups. Preserve the strong iterative S baseline and real independent P attempts. Re-run the live comparison under a new freeze after the live path is complete.

Before spending on a panel, demonstrate one task through S/P/T and a response-substitution probe: replace a child constructor response with a syntactically valid wrong patch and observe that the submitted/scored behavior follows that patch. Disconnect the child output and refuse. A completed planner call without a repair response cannot pass these checks.

## CB2-02 — template construction is an authored menu with a nonempty fallback

**Source:** `experiments/team01/template.py:14–25,37–84,128–143`; `live.py:343–407`.

The model is asked to select one of two hardcoded `BUILDS`. `build_candidates` copies these definitions and attaches the same aggregate development win/failure counts to both. If the model produces no usable selection, `build_live_template` sorts those candidates and freezes the first. It does not freeze `none`.

A direct call using one synthetic development record produced both authored candidates, identical evidence scores and `build-1-bind-first` as the fallback winner. This confirms the branch mechanics; it is not a replay of the missing live campaign records. Even a successful model menu selection would not satisfy the assigned model-generated executable template construction. After two empty model builds, the resulting authored template is not a no-candidate outcome.

**Required completion:** have the model propose a bounded executable coordination plan with parameters/checks/bindings from actual live development evidence. Reuse the existing bounded node vocabulary and compiler; no unrestricted code generator or new graph framework is needed. Validate and test the returned candidate on development work, then freeze one eligible candidate or `none`. A candidate's evidence must describe its own checked behavior, not an identical aggregate copied onto every option. Empty/invalid responses may consume the remaining predeclared construction attempt; after exhaustion, use explicit no-candidate fallback.

Transfer must reload and instantiate these bytes on new public inputs. Record applicability/binding checks and actual changed operations. A real candidate that fails to help is a valid negative; a missing candidate yields a completed no-acquisition/fallback experiment. Neither permits replacing it with an authored winner. Existing authored templates remain useful controls.

## CB2-03 — the Team 01 campaign evidence is absent from the pushed tree

**Source:** Git tracked-file inventory at `6942fa2`, compared with `reports/TEAM-01.md` references to `evidence/template-frozen.json`, `evidence/continuity-probe.json`, `evidence/reconciliation.json`, episode records and verdicts.

The only tracked Team 01 JSON outside task/public/protected fixtures is `experiments/team01/manifest.json`. No Team 01 live episode set, template freeze, continuity record or reconciliation bundle was found. Representation live3 evidence is present; it does not establish the Team 01 claims. The report's assertion that both raw evidence roots were committed is therefore unsupported by the delivered tree.

**Required completion:** recover and commit the existing hybrid evidence if still available, labeled as historical diagnostic evidence. If it was deleted, report it as unavailable; do not reconstruct raw receipts or responses from prose. Commit the corrected live campaign's redacted requests/responses, operation and artifact bindings, candidate/template bytes, exact freeze, phase records, complete episode membership, continuity proof, costs and standalone recomputation entry. Ensure a fresh checkout can verify the stored results without temporary directories or a live provider. DB receipt verification can remain an additional, separately labeled check.

## Live-row status at this review

| Row | Current support and remaining work |
|---|---|
| LIVE-01 | Real gateway inference worker-reported; representation stored usage present. Team raw provider/receipt evidence not delivered. |
| LIVE-02 | Scoped representation live3 unsuccessful acquisition/fallback accepted; stored decision arithmetic independently matches. Successful acquired C transfer remains unexercised, which is allowed. |
| LIVE-03 | Planner inference plus reference child work reported; actual live repair/context/tool loop incomplete. |
| LIVE-04 | Authored menu and fallback implemented; required live template construction/no-candidate semantics incomplete. |
| LIVE-05 | Hybrid panel cannot answer the assigned comparison; live S/P/T and transfer remain open. |
| LIVE-06 | Reported continuity is useful substrate evidence; raw Team bundle absent. Repeat required live-child/fresh-process branch on the corrected path, conditionally on a real eligible template. |
| LIVE-07 | Team reconciliation worker-reported but raw bundle absent; deliver and recompute complete live operation costs. External provider billing remains explicitly unknown where unavailable. |

## Architectural consequence

We remain at stage 8.6, with team infrastructure delivered and the live cognitive loop incomplete. The model currently influences a routing choice; the fixture machinery supplies most task competence. Complete the point where model work actually creates the artifact before using the result to change the architecture.

Do not select the first learner revision from these scores. Empty-output retry is a candidate operational intervention, not an established learning improvement. First distinguish truncation/reasoning-only output, protocol/decoder failure, unavailable source/tool context and ordinary proposal failure on the actual worker path. Bounded development calibration is already assigned. A general retry-learning system is not needed to complete it.

## Task list and verification

- [x] Fetch the exact worker revision into a separate assessment worktree.
- [x] Inspect the central live planner -> child submission -> scored tree and template construction paths.
- [x] Execute `_kinds`, template candidate generation and fallback selection without a DB or gateway.
- [x] Enumerate tracked evidence and independently recompute representation live3 control/decision arithmetic.
- [x] Retain useful mechanisms and issue a three-part completion assignment.
- [ ] Worker supplies real repair/baseline behavior, real template construction or `none`, and committed live evidence.
- [ ] Interpret corrected team/retention results before selecting learner revision or consolidating the architecture.

No new review findings were pursued outside these central obligations. A valid completed negative remains acceptable. The next packet is [Cognitive Batch 02 live completion](../docs/HISTORY.md#worker-cognitive-batch-02-live-completion).
