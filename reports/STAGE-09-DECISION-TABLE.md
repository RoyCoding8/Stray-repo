# Stage 9: decision table and completion matrix

Against tip `464f155` on `codex/implementation-investigation-learning-02`. The five research
questions are verbatim from `WORKER-STAGE-09-PARALLEL-EXPANSION.md` lines 15-19. **Every number
below was read from an evidence artifact at this tip, not from a report and not from a lane
summary.** Where a claim was retracted during this assignment, the retraction is stated in the
row rather than the original wording being quietly replaced.

**Nine claims in this branch's own earlier reports were retracted during the assignment.**
That is recorded here rather than smoothed over, because the reader is deciding what to build
next and a report that hides its own corrections cannot be trusted on the rest. The largest:
E1's original "software world runs", E3's "the numbers above are post-fix", E3's "reaches real
admitted operations", and E4's `channel_headroom` negative.

## Table 1: research question to architectural implication

| Question (verbatim) | Intervention | Result | Evidence | Architectural implication |
|---|---|---|---|---|
| **1.** "Which representations can a model acquire and execute, and which fail because of language limits, construction difficulty or runtime defects?" | Three representations against a real executable fault-repair world: an executable program, public failure symptoms, bounded inspect/test/localize/repair tools, fault label and hidden patch never exposed to the policy. Four independent acquisition lineages per supported cell. | **16 of 24 families fully repaired, 3 at 0.500, 5 at 0.000.** All four STEP lineages returned **31 of 39** independently: 39 instances minus the 8 whose reference repair is not in any candidate space. `typed-ast` and `action-graph` returned 0 repairs and 39 refusals each, recorded as missing cells. `probe_reach` 30/30 held-out, 9/9 dev. | `inv_r1_e1_swe_ceiling/matrix.json` (5.1MB, 468 rows, 12 lineages); `RESULT.md`; `inv_r1_e1_swe/` is the **RETRACTED** before-picture, banner included. | **The boundary is the panel, not the solver.** Where the reference repair is in the candidate space, STEP repairs it; where it is not, nothing does. So the useful next question is about *candidate generation*, not about representation strength. A ranking that put the fault line first would need to know which line it is, so the cap was changed and the order was not. |
| **2.** "Does accumulated experience improve acquisition and later action choices? Does relevant experience help more than irrelevant or shuffled experience?" | Five contrasts: relevant vs none, relevant vs size-matched irrelevant, retained vs cold reacquisition, held-out families and source-to-target adaptation, observation substitution. | **The first two are retracted, not negative.** Both used a `diagnostic` field that echoed its input; a charter test falsified even the echo mechanism. Re-run on a scored observable, **all three arms score 1.0 and 0.0 - none reads its observations.** Retention survives as a *cost* result (crossover at 5 uses; 16345 vs 19614 units). Transfer is a tie. | `inv_r1_e2_scored/readings.json`; `inv_r1_e2_retention/costs.json`; `inv_r1_e2_challenge/` including the falsifying charter test; `inv_r1_e2_noexp/`, `_relevance/`, `_transfer/` carry `RETRACTED.md`. | **A dependent variable that echoes its input cannot support a claim in either direction, and the retraction is the finding.** The scored re-run is a real negative backed by a verified discriminating instrument (reader 2.0, blind 1.0). The retention result is arithmetic over a cap sheet, not model behaviour, and cannot be retracted by a better observable. |
| **3.** "Does retained behavior help on new task families or domains after its acquisition cost is included?" | Retained policy vs cold reacquisition, with construction and use costs separated; held-out families within a world; bounded source-to-target adaptation vs an equally budgeted target-only constructor. | **Costs separate cleanly; quality does not.** Retained wins on cost after 5 uses. On transfer, both arms select the same member. **The two relevance arms returned no model bytes at all** - `sha256("")`, `prompt_chars: 0` - filed as a contrast with `differs: true`, and nothing in that directory records it. | `inv_r1_e2_retention/costs.json`; `inv_r1_e2_scored/CONTRASTS.md`; `inv_r1_e2_relevance/contrast.json` (the empty digests). | **A null-dispatch must be recorded as a null dispatch.** Two arms that returned nothing were read as differing, and the defect is silent: the artifact looks like a result. Any future relevance contrast must assert non-empty model bytes before it is allowed to compare arms. |
| **4.** "Can the system choose useful investigations from its own failures and results, rather than follow a human-authored task sequence?" | Adaptive agenda vs a fitted constant under one finite envelope, three worlds, six budgets, four frozen yields, plus a severing control and a store-binding witness. | **Two-sided; no benefit claimed.** The agenda retains and diagnoses more at every budget; the control holds out better at 20 and 40. **The sever control ran: the severed arm is a strict prefix of the connected arm in all 24 cells, and the effect vanished in every one, 18 of which had an effect to lose.** Decisions now reach **5 admitted operations with 5 receipts**, read back by SELECT; the severed arm writes none. | `inv_r1_e3_selection/e3-sever-control.json`, `e3-admitted-operations.json`, `e3-store-witness.json`; `e3-crossover.json` and `e3-divergence.json` are historical and **the ladder is retracted**. | **The effect is caused by the decision, not by the schedule - established on executed evidence for the first time.** But the original explanation was a harness artifact: `crossover()` built the policy once and looped worlds and budgets, so the control's totals were cumulative prefix sums of one traversal and 46 was the full six-step total. The no-benefit conclusion survives; the reason it was given does not. |
| **5.** "Can it acquire an executable revision of its learning procedure that improves a later acquisition cohort? A better task solver alone does not answer this." | `imp_source` picks a probe input, `drive_improve_round` spends it, the output bit selects the descendant. Three qualification controls over 24 seeds. | **A completed negative on a qualified apparatus.** Known-effect +0.2596, no-op exactly 0.0, disconnect exactly 0.0 against a descendant that learned nothing. `measurable: false`. The ceiling over **every input the instrument accepts** is 0.00267, with all sixteen input means between 0.0588 and 0.0609. | `inv_r1_e4/headroom.json` (regenerated against the repaired estimator), `make_evidence.py`, `inv_r1_e4_channel.py` and `inv_r1_e4_evidence.py`. | **Probe choice is the channel's only lever, and it is exhausted, so a wider menu cannot help either.** The honest answer is *not until a specific measurement exists*: a written description of a non-probe learner decision and its effect on descendants. A qualified apparatus returning a negative completes the experiment. |

## Table 2: milestone completion

| Milestone | State | Evidence | What remains |
|---|---|---|---|
| M0 inventory and map | done | `reports/PLAN-STAGE-09-CONNECTED.md`, findings reproduced at source | nothing |
| M1 budget and authority | done for the study | `s09_cap_sheet.py` `Sends`; `s09_exposure_ledger.py` `Units` / `ProviderCharge`; the three currencies cannot be folded | **N-71/N-73: a ceiling declared authoritative and never enforced.** `CEILING_COUNTERS` names 9, the walker built 5, and `calibration`/`development`/`repair`/`use` read 0 and enforced nothing. Repaired. |
| M2 representations and worlds | partial | three real registrations; three representations cross-compared; the SWE world is now world-addressable | **N-58: the common harness still refuses the SWE arm** (it requires 8 public-state fields, the world publishes 12), so SWE numbers are comparable within their own driver and not across E1's worlds. |
| M3 prospective live pilot | run; the negative is honest | `inv_r1_m3b/` - 30 model calls, 3 executed use records, 33 refused, and the acquired member reproduces the authored `ddmin` control | Nothing. The caveat is stated in the artifact. |
| M4 independent verification | **partial - a corrected blocker** | `offline_recompute.py:1910-1917` now *reports* `verifier_digest()` rather than checking it, and the verifier left `OUTPUT_CODE_PATHS` | **No clean baseline, so no tamper test.** The self-hash defect is closed; the open blocker is that the model will not answer in the admitted format. |
| E1 connected comparison and SWE | **run on the qualifying instrument** | `inv_r1_e1_swe_ceiling/`; the before-picture is banner-marked invalid | **N-72: one test file mis-parses the DSN shape every other file uses**, so a single-DSN compliant run needs a dual-form `_base` or a documented exception. |
| E2 experience interventions | run; two contrasts retracted | see Table 1 row 2 | The empty-model-bytes guard (Table 1 row 3) is the concrete next fix. |
| E3 autonomous selection | run; two-sided, no benefit | see Table 1 row 4 | The pre-fix ladder should be regenerated or withdrawn. |
| E4 executable learner revision | **completed negative, apparatus qualified** | see Table 1 row 5 | Nothing tonight. `N-26` (`informs_decision` was a literal) is repaired and must stay so. |

## Table 3: the engineering passes and what each cost

| Pass | State | The finding that mattered |
|---|---|---|
| 1. contract and source | done | N-31: **a declared ceiling was never enforced** - four of nine counters had no key. |
| 2. behavioural on the integrated system | done | N-47: `dispatch_pending` hardcoded `repair=False`, stranding work permanently. N-68: **a binding attested a probe as evidence for a construct's package.** |
| 3. evidence after experiments | done | N-63: **an estimator that could not return a positive number produced the headline negative.** N-70: three tests asserted that estimator's output as a property. |

## Table 4: what is still open, ranked

| rank | item | why it constrains the rest |
|---|---|---|
| 1 | **N-36, critical — SETTLED.** A policy recovered an invertible seed through the real launcher, whose own docstring said it was not containment. The claim was true and understated. | Every acquisition result above depends on it. The keyed digest improved the id but **did not close the leak**; repair is a sandbox change, not a digest change. |
| 2 | **N-65, critical — SETTLED.** The 18688-unit figure is a pre-flight campaign sizing in broker reservation units, not held liability, and it is sourced: `4 × 2294 + 4 × 2378`. | 2294 is the only recorded exposure; 18688 = 8 x 2336 is the shape of a pre-flight sizing. Either three documents overstate the liability by 16394 units, or an artifact is missing. Not resolvable from this branch. |
| 3 | **N-74, high.** 30 pre-existing `agenda01` failures, and the suite has 44 failures and 2 errors overall. | The full suite does not pass. That is a measurement, not a suspicion, and it is the first honest one in this record. |
| 4 | **N-53, blocker.** Jev returned 403 for the whole assignment. | **No decision in this batch was reviewed by dissent**, and no Jev artifact exists for E1, E3 or E4. The next conceptual decisions belong where Jev works. |
| 5 | **N-23 / N-24, critical.** The model narrates the task and the 512 cap falls between derivation and payload. | A real substrate finding, and the choice among three options is the researcher's. |
| 6 | **N-66, medium.** Under contention a decided receipt can be lost and never land. | Every concurrency check so far counted only upward, so a loss was invisible until a lane looked downward. |
| 7 | **N-46, high.** 98 files take the `migrated_db` fixture, which `TRUNCATE`s the whole store. | The widest shared surface is not isolated. Redirecting it changes behaviour for 98 files and was flagged rather than done. |

## Closing note on method

Of 12+ lanes run during this assignment, **every correction to this branch's own work came from
a lane, and none from re-reading that work.** The failures were consistently of one shape: a
measurement that could not measure what it claimed - a `grep -c '^FAILED'` on a `-q` log, a
line-index slice that removed 153 lines instead of 20, a parser that split on escaped pipes and
declared good work lost, a "0 failures" reading that was 69 failures, an estimator that could not
return a positive number. A branch that trusts its own summaries should not be trusted on any of
it.
