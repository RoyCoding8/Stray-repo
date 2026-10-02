# Settlement: philosophy to final implementation

Updated 2026-09-12. This is the maintained project map and design task list. The product is infrastructure for a persistent, general, autonomous society; the early work determines the behavior that infrastructure must support.

**Stage 8.6 has a real-repair prototype and completed live panels at a qualified scope; stage 9 architecture consolidation has begun.** Worker `5864740` delivers non-promising real S/P/T and warm/cold results. The design role independently recomputed their arithmetic and confirmed that correcting the known refusal usage does not change either decision. The retained artifact is advisory prose, so executable coordination-template acquisition remains open. [The final assessment](../../reviews/COGNITIVE-BATCH-02-FINAL-ASSESSMENT.md) records what this supports and what remains unmet.

**Current worker assignment:** [Executable Coordination 02](../../WORKER-EXECUTABLE-COORDINATION-02.md), including the pending historical delivery corrections as one independent lane. The [selected design](EXECUTABLE-COORDINATION-02.md) specifies acquired decision programs for binding, diagnostics, ownership and selective rework; four comparison arms; six workload families; causal controls, live acquisition and fresh-process transfer. This is a new informative study, not a rerun or retrofit of Team 01. General learner revision and final infrastructure release remain later milestones.

## The mental model

Purpose -> intuitive behavior -> precise semantics -> architecture -> representation and technology -> buildable specification -> prototype -> behavioral experiments -> revised design -> complete system -> operational qualification -> final implementation.

This sequence has feedback. We revisit an earlier decision when evidence challenges it; we do not restart the whole project after each defect. Design levels R0-R7 describe precision. Build slices S0-S7 describe executable milestones. They are different axes, not competing roadmaps.

“Done” means the stated deliverable exists at its stated scope. A selected design is revisable. A built mechanism is not necessarily empirically useful. A simulated test is not a live experiment.

## Overall stages

| Stage | Purpose and existing mapping | Status | Evidence or next completion condition |
|---|---|---|---|
| 1. Philosophy | Purpose, generality, growth, human relationship; R0 | **Done: baseline selected** | [Conceptual architecture](REFINED-ARCHITECTURE.md), sections 1-2. Broad competence and useful discovery remain aims. |
| 2. Intuitive picture | The society working, exploring, remembering and changing; R1 | **Done: baseline selected** | Conceptual parts and end-to-end narratives in the architecture. |
| 3. Precise and formal description | Meanings, entities, transitions, obligations and limits; R2-R3 | **Done: baseline selected** | [Glossary](GLOSSARY.md) and architecture sections 3-4. Conditional arguments exist; no machine-checked proof or proof of intelligence is claimed. |
| 4. Abstract architecture | Connect execution, development and agenda; R4 | **Done: baseline selected** | Architecture section 5. Responsibilities do not prescribe permanent agents or services. |
| 5. Representation and technology | State, executable packages, interfaces and supporting tools; R5-R6 | **Done: provisional choices** | [Representation design](REPRESENTATION-DESIGN.md) and [technology decisions](TECHNOLOGY-DECISIONS.md). Experiment-driven revision remains possible. |
| 6. Practical specification | Builder protocols, requirements and acceptance conditions; R7 | **Done: baseline specified** | [Practical specification](PRACTICAL-SPECIFICATION.md). Later cognitive mechanisms still need policy-level refinement. |
| 7. Foundation prototype | S0-S3: bounded execution, persistence, evidence, continuity, candidate/trial/release machinery | **Built; validation partial** | Worker report at `be1730d`: R03 fixes merged, 456 tests passed; its verification section identifies tested code `42caa1e`. The design role has not independently rerun that suite. Live gates and empirical learning remain open. |
| 8. Learning and cognitive policy refinement | Specify and test acquired competence, memory, background development, agenda and teams | **Ongoing: current stage** | Scoped agenda prototype accepted; memory/context integration remains partial. Representation acquisition-to-use mechanics are connected; their live empirical result remains open. Temporary teams now have a buildable contract. No useful learning gain demonstrated. |
| 9. Evidence-driven architecture consolidation | Confirm, narrow, replace or remove mechanisms; revisit R2-R7 | **Started: scoped synthesis, not complete** | [Team 01 final assessment](../../reviews/COGNITIVE-BATCH-02-FINAL-ASSESSMENT.md): retain checked work and conservative single-worker baseline; distinguish advisory memory from executable retained behavior; no stack rewrite or general learner selected. |
| 10. Complete system prototype | S4-S6: representations/transfer, autonomous agenda/teams, learner revision/consolidation | **Not completed** | Each slice needs its own end-to-end demonstration. Scaffolding does not complete it. Stage 8 can deliver portions incrementally. |
| 11. Operational qualification | S7: real profiles, recovery, controls and supported deployment | **Partial groundwork; qualification not done** | Verify real components and the declared failure model for the chosen deployment. Explicit stack revisions can replace earlier targets. |
| 12. Final implementation and release | Consolidate the validated architecture into a supported infrastructure product | **Not started as a release milestone** | Complete chosen scope, migrations, installation, documentation, lifecycle UI and release evidence. Retain sound prototype code; “final” does not mean replacing everything or ending research. |

## Stage 8 design task list

| Order | Design part | Current state | Required result |
|---|---|---|---|
| 8.1 | Acquired competence and development episodes | **Selected for the first experiment** | [Learning model](LEARNING-MODEL.md): method/representation/policy distinctions, transitions, evidence and failure cases. |
| 8.2 | First complete development episode | **Live rejection/fallback exercised; baseline solver path corrected; competence gain open** | Historical four-episode campaign remains confounded, with zero releases. New clean-source live baseline solves a visible regression task with reconciled internal cost. It does not retroactively validate the historical comparison or exercise learned-method transfer. |
| 8.3 | Memory and decision context | **Integrated prototype; validation remains scoped** | Experience, opposition, packet delivery/binding and stale-state contracts have deterministic evidence in the refreshed [compatibility mapping](../../reviews/COGNITIVE-DESIGN-COMPATIBILITY.md). The whole runtime suite is worker-reported 590 green. Universal context sufficiency and live semantic benefit are unproven. |
| 8.4 | Background development and autonomous agenda | **Scoped prototype experiment accepted; operational limitation retained** | Worker `324174f`: v3 stored traces and source freeze independently checked, grades 288–288, 16-unit Q saving in family 1. Same-DB resume path inspected; real-PG tests remain worker-reported. Claimed/partially receipted mid-send recovery is not qualified. |
| 8.5 | Representation invention and transfer | **Connected prototype; live unsuccessful acquisition observed** | Worker `6942fa2` publishes live3: 48 held-out records and 12 controls; means/clauses independently recompute. C produced no usable source candidate and therefore no transfer core. The scoped no-acquisition/fallback result is accepted; successful acquired C transfer and useful learning remain unproven. |
| 8.6 | Temporary teams and collective reasoning | **Live repair/advisory pilot accepted; executable procedure design selected, implementation pending** | `5864740`: eval 16/15/16, transfer 8/8/8; neither rule promising, even with corrected refusal usage. [Coordination 02](EXECUTABLE-COORDINATION-02.md) now tests actual executable acquisition, applicability, probes, partitions, rework and transfer. Historical delivery fixes are included; old panels are not repeated. |
| 8.7 | Learner revision and consolidation | **First semantic and study draft complete; working mechanism pending** | [Learner revision](LEARNER-REVISION.md): whole trajectories, bounded self-revision, consolidation, evaluator corrections/epochs and rollback. S6/E7 implementation and empirical qualification remain pending. |

The order expresses dependencies, not a demand to finish each part globally. Agenda 01 tested scheduling without waiting for a learned-method release; Representation 01 tested narrow mathematical transfer without waiting for autonomous scheduling. Coordination 02 follows the scoped Team 01 findings. Learner revision remains deferred until an observed development bottleneck identifies a useful intervention. The [checkpoint](COGNITIVE-DESIGN-CHECKPOINT.md) records this progression; it does not authorize building every cognitive draft at once.

## Current synthesis and closure tasks

- [x] Recompute the 48-cell evaluation and 24-cell transfer results from committed records.
- [x] Check refusal usage sensitivity: the non-promising decisions survive correction.
- [x] Classify prompt advice separately from executable retained coordination.
- [x] Begin scoped architecture consolidation; preserve working substrate without a stack rewrite.
- [ ] Worker publishes missing executed modules and corrected derived accounting/reporting.
- [x] Refine executable memory into a specific decision-program interface, with binding, diagnostics, ownership, selective rework and bounded failure.
- [x] Select an informative four-arm study, transfer and intervention panel, primary-source precedents and decision rules for the next architecture turn.
- [x] Prepare one combined worker assignment with explicit contract-first parallel workflow and independent integrated verification.
- [ ] Worker completes Coordination 02 mechanics, actual model acquisition or honest none, frozen live comparison, diagnostics and replayable delivery.
- [ ] Interpret execution, acquisition, conditional behavior, benefit and transfer separately; choose the next measured bottleneck.

## Cognitive Batch 02 completion task list (historical progression)

- [x] Fetch `6942fa2`, inspect model-to-artifact and template paths, and execute bounded reproductions.
- [x] Independently recompute representation live3 decision arithmetic and retain its scoped unsuccessful result.
- [x] Check published Team evidence availability and record CB2-01–03, without expanding to small defects.
- [x] Worker demonstrates actual live S/P/T repair on one task at `44de83e`, including wrong-response and disconnected-output controls; the design role accepts this scoped gate.
- [x] Worker constructs/validates a live template or freezes `none`; publishes corrected frozen panels and complete replayable evidence.
- [ ] Interpret the corrected result before selecting stage 8.7's first learner intervention.

## Cognitive Batch 02 original task list

- [x] Fetch `cb8a62a` into a separate design worktree and inspect the acquisition -> retained evaluation/use source connection.
- [x] Accept the scoped implementation milestone without reopening minor review items or claiming live benefit.
- [x] Refine how temporary organization becomes persistent executable coordination, with applicability and opposing evidence.
- [x] Check primary research for precedents, strong baselines and verification limitations.
- [x] Select Team 01 semantics, finite workload, comparison/retention rules, reuse map and acceptance conditions.
- [x] Prepare independent runtime, workload, integrated-experiment and representation-live worker lanes.
- [ ] Worker resolves shared interfaces and executable budget reservations, then builds the connected path.
- [ ] Worker completes LIVE-01–07: outstanding live representation, live team development and template acquisition, frozen evaluation/transfer, fresh-process continuity and reconciled live costs. Verified external blockers remain open obligations; complete live negatives are valid results.
- [ ] Interpret team benefit, retained-coordination benefit and representation benefit separately.
- [ ] Choose the first learner revision from observed bottlenecks; perform stage 9 synthesis when these results exist.

## Current packet checklist

- [x] Inspect the selected design and worker implementation at `be1730d`.
- [x] Restore a current roadmap from philosophy through final implementation.
- [x] Specify acquired competence and the first bounded development episode.
- [x] State alternatives, failure cases and limits on learning claims.
- [x] Write the bounded worker prompt and update the design entry points.
- [x] Worker maps DEV requirements onto code and records implementation choices.
- [x] Worker delivers and reports deterministic Development-01 implementation and suite evidence.
- [x] Inspect `e1b95a6` and independently reproduce four bounded integration gaps with explicit doubles.
- [x] Select the memory/context architecture and its first ten implementation requirements.
- [x] Freeze and run an eight-request live context pilot with `claude-opus-4-6-thinking`; preserve exact packets, responses and limits.
- [x] Prepare the Development-02 handoff combining the four seams with context materialization.
- [x] Worker assesses D02 findings and delivers the deterministic Development-02 slice at `a1d2525`, reporting 509 tests passed.
- [x] Independently inspect the delivered seams and reproduce five limitations with explicit doubles.
- [x] Freeze and run two live production-shaped prompt checks; preserve the formatting and wrong-product failures without executing generated code.
- [x] Accept useful prototype mechanisms and define a bounded live-completion assignment with explicit context restrictions.
- [ ] Complete or explicitly qualify CTX-01 through CTX-10; deterministic implementation does not imply full contract closure.
- [x] Worker executes four live episodes with explicit local uncontained profile; containment remains unqualified.
- [x] Assess the finite-panel summaries without requiring a positive outcome; accept integration and classify learning attribution as confounded.
- [x] Preserve interpretable live baseline solver-to-grader evidence and reconcile internal settlement; external provider billing remains explicitly unknown.
- [ ] Exercise live acquired-method use if a candidate earns release; zero releases is an allowed outcome, not proof of that path.
- [x] Refine stage 8.4 agenda policy using the observed distinction between successful task repair and reusable competence.
- [x] Draft the agenda trajectory protocol and minimal option/continuation semantics.
- [x] Assign whole-repository engineering review/repair with ranked priorities and exhaustive technique/coverage guidance.
- [x] Worker delivers engineering coverage/repair and closure. Final suite worker-reported 590 green; the new smoke's 8,455-unit internal total independently reconciles. Residual current-ledger cleanup is carried into the next integration task; see the [closure assessment](../../reviews/ENGINEERING-CLOSURE-ASSESSMENT.md).
- [x] Consult primary research and record mechanisms, limits and design implications.
- [x] Refine representation/transfer, team and learner-revision semantics with rejecting study designs.
- [x] Connect the cognitive mechanisms and record exactly which further choices depend on implementation evidence.
- [x] Receive relevant worker evidence and resolve the dependencies needed for the next concrete implementation handoff: refreshed compatibility rows 1–6 and the new live smoke bundle. Learned competence and deployment qualification remain open.
- [x] Reconcile agenda records with audited interfaces and write its bounded implementation contract and attachable worker assignment.
- [x] Worker delivers agenda components, a frozen authored panel and 128 recorded trajectories at `29496a0`; delivery is not full contract acceptance.
- [x] Independently assess the result: 27 policy tests pass, original ties reproduce, and focused probes expose checker/qualification gaps. Record six bounded findings and the correction assignment.
- [x] Complete the scoped AGR1/AGR2 prototype correction sequence through `324174f`; real-PG execution is worker-reported and the v3 trace/source acceptance is independently checked. Broader operational recovery remains qualified.
- [x] Inspect the correction at `051811f`; independently run 28 policy tests and reproduce three remaining acceptance failures with scoped probes. Retain substrate/treatment progress.
- [x] Worker delivers AGR2-01 through AGR2-03 with v3 evidence; accept the scoped experiment and retain the disclosed mid-send recovery limitation.
- [x] Design role refines representation invention and transfer into a bounded contract, independently of the agenda correction timeline: Representation 01, with explicit package boundary, finite tasks/budgets and separate acquisition/transfer/benefit verdicts.
- [x] Prepare one combined worker assignment with shared-contract ownership and independent agenda/instrument/execution/acquisition lanes.
- [x] Worker delivers source instruments, representation execution/profile and authored-fixture evidence at `324174f`; this is partial RPR-01–08 completion.
- [x] Worker delivers configured acquisition dispatch/staging, the specified held-out fixture panel and full decision rule at `646e154`. The unconditional preflight blocker is removed; this does not yet complete the joined experiment.
- [x] Connected campaign-selected A/B/C artifacts and behavior to the frozen held-out comparison and fresh-process disposition/use at `9b96f8b` (retention freeze, retained-mode evaluation, phase-naming entry; independent behavioral + disconnect acceptance). Live campaign remains externally unverified.
- [ ] Execute the bounded actual campaign when a valid gateway/grant/profile exists; preserve an external-blocker status separately from implementation completion.
- [ ] Interpret unchanged-core transfer, adapter contribution, acquisition-inclusive costs and complete source outcomes; a passing runner does not complete this obligation.
- [x] Validate agenda treatment sensitivity, freeze and run v3, and retain its limited equal-grade/lower-exploration result. This does not establish a general scheduler advantage.

## Acceptance from here

1. **Blocks the intended experiment:** the path cannot run, evidence is untrustworthy, or a confound defeats the comparison. Address before drawing its conclusion.
2. **Prototype limitation:** controlled conditions or an explicit workaround permit an honest bounded experiment. Record the condition and proceed within it.
3. **Production hardening:** robustness or scale work outside the experiment's conditions. Distinguish it from evidence needed to interpret that experiment. The completed comprehensive audit inspected these areas too; externally blocked deployment qualifications remain explicitly open. Agenda 01 owns its affected paths and experiment, not another whole-repository audit.

Classification depends on use. Absent containment can permit trusted scripted fixtures in an explicitly disposable test environment; it does not qualify arbitrary generated code on an exposed host. Missing paid access blocks a live claim, not implementation or deterministic verification.

The human's comprehensive audit assignment covered every priority level. Its closure is now an accepted experimental baseline, with report-index maintenance folded into the next slice. This does not restart philosophy/formalization. A negative or inconclusive result can complete an experiment while leaving the architectural hypothesis unsupported; audit coverage does not establish learning benefit or final operational qualification.

## Evidence and maintenance

Current evidence: [closure assessment](../../reviews/ENGINEERING-CLOSURE-ASSESSMENT.md), [worker verification](../../reports/VERIFICATION.md), [live smoke bundle](../../reports/evidence/eng-close2/PROVENANCE.md) and [compatibility mapping](../../reviews/COGNITIVE-DESIGN-COMPATIBILITY.md). The design role independently checked stored-source equality/digest, the unchanged smoke-to-closure code and settlement arithmetic; it did not rerun the worker's 590-test suite or the live call. Earlier prompt pilots and the nine-check live-evidence assessment remain historical evidence. Live acquisition benefit/selected-method transfer, verified paid billing, real runsc containment, live DBOS backup interleaving and PostgreSQL 18 remain open. API access and live fallback execution are no longer globally unverified.

E1-E8 in the conceptual architecture track empirical claims. The first A/B/C comparison does not discharge all eight or establish scientific novelty or knowledge absent from model training.

After every handoff, update the current-stage sentence, affected rows, checkboxes and evidence links. Record the source revision and distinguish reported results from independently reproduced results. Preserve attributable historical reports. A passing harness never completes a pending empirical obligation.
