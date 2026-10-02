# Stage 9 transfer assessment

Reviewed implementation `c06b3e90e6daf5b95238707664364f48abb73044` on 2026-09-29, starting with `reports/STAGE-09-TRANSFER-BRIEF.md` and `reports/STAGE-09-HANDOVER.md`.

## Decision

Accept useful engineering and instrument progress. Do not accept completion of the expanded research assignment. Preserve the reported negative outcomes at their measured scope. Resume the unfinished experiments under the existing assignment rather than commission another general audit.

Jev's free period has ended. Do not call it. Independent reviewers, counterexamples and direct measurements remain available. Jev was always advisory; its absence does not prevent a reviewed decision or require accepting decisions without challenge.

## Findings that affect the next decision

### TR-01: the reason for closing E2 and E4 contradicts the governing assignment

The handover, section 5.1, closes E2 and E4 unrun because 5563 historical units remain uncertain and unreconcilable. It cites a ledger prohibition and says reconciliation was not authorized. The cited current ledger line 110 is a historical supersession notice, not an authority rule.

`WORKER-STAGE-09-CONNECTED-STUDY.md` M1 explicitly permits a separately bounded new allocation while preserving old holds. The expansion authorizes larger prospective free-route campaigns. The current ledger itself says the 5563 units stay under their own grants, and records later studies that ran while carrying them. The repaired `s09_exposure_ledger.launch_plan` reports carried units without subtracting them from dispatches or requiring settlement.

The review reran all 29 tests in `test_s09cs01_budget_denominations.py` successfully. That includes the calculator-level new-allocation check. It does not independently prove a physical dispatch with a held reservation; the worker's own M1 audit acknowledges that evidence limit.

**Disposition:** reopening E2/E4 does not mean settling unknown effects or replaying r4. Inventory all subsequent uncertain operations as well as the original 5563, preserve their state, and allocate a new finite campaign through durable authority. The 5563 is not necessarily the current total: the ledger records further uncertainty from later runs. A later explicit user cancellation would take precedence, but no such cancellation is supplied in this handback. A worker decision inferred from old prose is not a cancellation. If one exists in the worker chat, cite that instruction explicitly.

### TR-02: E1 combines two experiments into one completion claim

The transfer brief puts "three representations", "312 rows" and "loss" into one completed E1 row. They describe different evidence:

| Evidence | What it supports |
|---|---|
| `reports/evidence/invl02_liveacq_r4/` | Six construction attempts, three acquired ENTRY wrappers and three paired use results. All three acquired wrappers delegate to authored ddmin reducers. The three paired normalized-reduction deltas are -1/6, -1/8 and -1/6, averaging -0.1527777778. |
| `s09_swe_experiment` and the SWE qualification | Authored Python STEP policies and fixture AST/graph policies exercise representation/world bindings. No live provider constructs those lineages. |

The reviewer independently recomputed the three paired deltas from initial/final measures and checked each of the three acquired source hashes. The construction/use export carries live-acquisition attestations; this review did not contact the provider or the original database to independently reproduce that history. The arithmetic is a descriptive result on the three available pairs, not an estimate over all six construction attempts.

The loss is useful and should remain a loss. It is not the result of the expanded STEP/AST/graph acquisition matrix, an experience ablation, or a general transfer study. A wrapper selecting an authored reducer also does not satisfy executable learner revision.

**Disposition:** keep separate names and completion rows for the live reducer comparison, authored SWE qualification and requested live representation comparison. The last remains unfinished.

### TR-03: distinct record hashes are being used as independent acquisition lineages

`s09_swe_experiment.py` describes lineage independence as a record digest. `build_step_lineages` builds four authored-control search-order variants. `build_ast_lineages` creates four fixture records; `build_graph_lineages` creates four records from the same authored graph builder with different policy IDs.

The reviewer invoked these builders at the reviewed tip. There are four AST records but **one unique AST entry program**, with `acquisition_evidence.earned == false` for all four. There are four graph records but **one unique graph node program**. The four STEP origins are all `authored-control`.

These are valid fixtures and some are useful behavioral controls. They are not four independent acquisitions. Conversely, independent model calls may legitimately converge to identical programs; requiring different digests would bias acquisition sampling.

**Disposition:** define acquisition replication by separate construction opportunities and recorded lineage/feedback history. Report behavioral duplicates rather than manufacturing diversity with names. Retain the existing fixtures as qualification evidence; do not count them toward the requested live lineages.

### TR-04: E2's failed observable is not an impossibility result for experience

The worker found a genuine flaw: terminal "preserved" is constant because a reducer retains a valid incumbent. Repeating that label cannot distinguish useful experience from echoing. The intermediate-trace instrument is useful progress.

This establishes a limit of that observable and task setup, not that no experience panel can exist. Reduction quality already varies in the live reducer comparison. Intermediate failures, probe choice, repair choice and resources also vary. The learning question is whether relevant experience changes those decisions and improves held-out outcomes relative to equally budgeted controls.

**Disposition:** freeze an experience hypothesis with a nontrivial observable and execute it. Do not require benefit, different terminal labels, or different candidate bytes as a precondition for running a valid experiment. Qualification should demonstrate that the intervention can reach decisions and that the measurement can distinguish known controls. A real model may then ignore experience, converge or lose.

### TR-05: E3 and the completion record require a scoped interpretation

The handover says the agenda beats the default at budgets 20 and 30, then says it is behind the default at 20, 0.157 versus 0.253. Those cannot describe the same arm/world aggregation. The source distinguishes the historical default, a fitted control and a held-out best-in-space reference. `qualified_ladder` correctly calls the last an oracle reference, not a deployable control.

Do not infer that every valid control must maximize the held-out score. Select a competent control using development data; report the held-out oracle only as a diagnostic upper reference. Keep per-world, pooled and historical results separate. The source still labels `crossover` as a retracted shared-state path while another path produces fresh cells.

**Disposition:** generate the current result table from the corrected path and name the exact controls, world set, budget and freeze in each comparison. Retain the narrower supported result; do not declare general autonomous-selection benefit or refutation from the contradictory prose. Old artifacts need an explicit supersession pointer, not rewritten measurements.

## Independent verification in this review

- Fetched the remote tip and inspected the assignment, transfer brief, handover, ledger, relevant sources and committed experiment records. This was a consequential-claims review, not a review of all 794 changed files.
- Confirmed `evidence_s09_m3_live/` remains byte-identical to `96dfa18`.
- Recomputed the three available reducer quality deltas and source hashes from committed records.
- Invoked the actual SWE lineage builders and measured authored origins and duplicate executable bodies.
- Ran `tests/test_s09cs01_budget_denominations.py` and `tests/test_s09_swe_binding.py` together: **43 passed, one failed in 7.11 seconds**. Python 3.12 on Windows, no DB/gateway configuration, automatic DB isolation disabled, external pytest plugins disabled. The failed AST child imports the Unix `resource` module and exits with `ModuleNotFoundError`; the driver returns a stop/refusal. This is a Windows qualification limit, not evidence that the worker's Linux test result was false. Do not weaken the child limits to make Windows green.
- An earlier combined run including `test_s09_e3_control_competence.py` was interrupted during its exhaustive search. It has no completed suite result. No complete E3 sweep, full-suite run, DB-backed integration check, live model call or Jev call was performed by this reviewer.

The focused command used `python -m pytest tests/test_s09cs01_budget_denominations.py tests/test_s09_swe_binding.py -q -p no:cacheprovider` with `PYTHONPATH` containing the repo and `src`, `S09ISO_DISABLE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, and DSN/gateway variables removed. Dependencies were supplied by an ephemeral uv Python 3.12 environment. The Windows-only child failure was then reproduced by invoking `s09_swe_ast.choose_action` on the first held-out task.

## Research direction and continuation

The strongest architectural lesson so far is that the restricted AST/graph interfaces omit data access and value flow needed by the SWE world. Their failure cannot establish that graphs or typed programs are intrinsically worse learning representations. Python currently has capabilities those versions lack. Measure these language limits explicitly; compare learnability on their common supported behavior. Do not keep expanding a separate domain-specific language for every new task merely to fill a table.

Keep the typed action/authority boundary and the executable-policy path. Use the remaining acquisition, experience, transfer, agenda and learner-revision experiments to decide which retained representations deserve continued investment. The original expansion remains the scope. This review adds no new framework or broad audit requirement.

The worker should first correct the completion matrix and decision provenance, then qualify the public launch path under a new allocation with old holds preserved. Run the unfinished experiments and export their complete construction and use receipts before cleaning their databases. Keep independent lanes busy on experiment implementation, execution and analysis. Fix only defects that invalidate those paths or their conclusions on the critical path; parallel maintenance need not stop the studies. Jev is removed from the workflow, with direct and independent review taking its place.

Report a real result, a valid negative, or an observed external blocker for every assigned milestone. "Closed unrun" based on the superseded exposure rule is not accepted completion.
