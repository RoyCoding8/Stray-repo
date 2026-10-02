# Cognitive batch 01: architecture and completion assessment

2026-09-12. Reviewed `324174f4e98890c95c25bca039feec267a061e8a` on an isolated assessment branch. This is a bounded assessment of the two experiments and their implications, not another whole-repository audit. Reproduction: [read-only probe](probes/cognitive_batch01_assessment.py), [recorded output](COGNITIVE-BATCH-01-assessment.json).

## Decision

**Accept Agenda 01 as a scoped prototype experiment and move the architectural foreground to representation acquisition. Accept the representation authored-fixture apparatus as useful progress; the acquisition/held-out transfer assignment is incomplete.** No successful learning or general representation advantage has been demonstrated. The worker's negative fixture result is retained and does not need to be made positive.

| Part | What this review supports | Boundary |
|---|---|---|
| Agenda v3 | Verified frozen source; strict stored-trace checker passes 128 trajectories / 64 pairs with no violations. Grades total 288 per arm; exploration R 2,292, Q 2,276. Savings occur in family 1. | Finite authored world distribution, not a general scheduler advantage. Real-PG execution is worker-reported, not rerun here. |
| Agenda continuity | Reviewed test now invokes `--resume`, checks the same database identity and sentinel, and compares actual saved progress/control trace. Prepared-operation recovery has a separate test. | The worker reports a claimed/partially receipted mid-send state that fails loudly rather than repairs. Keep that recovery limitation open for the appropriate operational slice. |
| Representation instruments/profile | Source instruments, independent checks, named profile, core/adapter identities and real-execution implementation exist. Focused local tests: 61 passed, 4 skipped. | Not a rerun of real PostgreSQL or generated code execution. |
| Representation fixture results | Stored evidence checker passes 27 benefit records plus its controls/use evidence. C software mean 0.310173 vs A/B 0.709740; graph mean 0.117873 vs A/B 0.222588. No release; supported use falls back to A. | Nine development/check tasks, all behavioral bytes authored. These are apparatus observations, not an acquired-representation held-out trial. |
| Acquisition/transfer | An authored shared core and distinct adapters demonstrate a concrete proposed mechanism. | The model-construction path is absent, and the held-out evaluation fixtures have not been consumed. |

The reported 788-pass full suite remains worker-reported evidence. The current verification/status/request documents were not updated by this batch; its PLAN and new representation report provide narrower records. This documentation lag belongs in completion housekeeping, not another independent architecture gate.

## Three coherent completion obligations

### CBR-01: implement acquisition, not only a preflight blocker

`experiments/representation/acquire/live_campaign.py:44–91` returns a blocked record for both missing and fully supplied configuration, and `main` always exits 2. Its description explicitly says it performs no inference; supplying endpoint/key/grant merely changes the reason to `awaiting-authorization`. The advertised command cannot run the experiment when access becomes available. The CLI's `--grant` does not reach `preflight` either.

The probe supplies non-secret placeholder configuration to the pure function, without networking or spending, and reproduces the unconditional block. This is missing implementation alongside the genuine external-access uncertainty. The authorized finite campaign still requires a valid grant and execution profile, but the prior worker prompt did not require an additional reviewer permission round trip once those prerequisites were satisfied.

Complete the broker-routed model construction and actual artifact consumption path, including A/B/C retention rules, core freeze before graph exposure, adapter-only transfer and explicit abstention. Authored fixtures remain fixtures. A deterministic adapter double can verify that configured requests reach the real orchestration and returned bytes become executed candidates; it cannot establish live acquisition. Missing access can still block the live run after this path exists.

### CBR-02: retain the mechanics panel and implement the specified evaluation phase

`experiments/representation/acquire/panel.py:20–25,109–113` chooses seven development tasks and two check tasks, all assigned development/check trial groups. No held-out benefit case is selected. A/B are frozen native-reducer selectors; B does not yet contain a model-acquired task-specific procedure. The report discloses these facts, but the overall completion message overstates the implemented scope.

Preserve `RPR-ACQ/1` as authored mechanics evidence. The main contract calls for eight software and eight graph held-out benefit inputs plus four controls across three arms: 60 arm-task records, with separate subsequent use. Connect that phase after actual acquisition and transfer selection are frozen. Do not spend a campaign merely to repeat the known losing authored example on all holdouts. Implement the phase with deterministic positive/negative fixtures, then use it for the bounded actual acquisition campaign, or report the remaining external blocker. Exposing graph data while constructing a new core would change the intended experiment.

### CBR-03: complete the decision rule before assessing a possible winner

`experiments/representation/experiment/checker.py:223–247` checks four quality clauses only. It omits the specified resource bounds and secondary efficiency outcome; control/validity problems are separate from the returned promising flag. The frozen manifest nevertheless describes the full rule. A synthetic quality-passing candidate with one million times baseline elapsed time still returns `promising=true` in the probe. This is a decision-function counterexample, not altered campaign evidence.

The existing negative result remains negative because its quality clauses already fail. Before a new candidate can receive a favorable pilot verdict, implement the full validity/control/quality/resource conjunction, the declared efficiency alternative, finite/nonnegative accounting checks and explicit treatment of missing CPU/exposure measurements. Unknown measurements cannot certify a resource win. Preserve complete acquisition, execution and fallback costs; native implementations need not pay artificial translation overhead, but their real checks and costs cannot disappear. Keep promotion and release distinct: the pilot can justify a broader trial without qualifying a general release.

## Verification performed here

- Fetched the reported commit and verified the agenda v3 frozen sources with `manifest.load_verified`; ran the strict checker over all committed v3 traces and independently summed its pair rows.
- Ran the representation stored-evidence checker: clean, 27 benefit records, negative quality verdict; checked source-selected panel membership and the configured live refusal path.
- Ran the six focused files `test_rpr01_{software,graphs,checkers,reducers,splits}.py` and `test_rpr02_profile.py`: **61 passed, 4 skipped**, using the existing Python environment with this checkout on `PYTHONPATH`.
- Executed the synthetic resource counterexample. No network access, model spend, real-DB tests or full runtime suite in this assessment.

Local portability qualification: Windows checkout line-ending conversion initially changes byte-pinned artifacts. Checking exact committed bytes resolves stored-evidence checks. Regeneration still differs in six source-context path strings (`/` versus `\`); all six differences are platform path spelling. This does not invalidate the worker's Linux result. Normalize serialized relative paths when touching this seam; platform conversion is not an invitation to silently re-freeze historical evidence. Full replay CLI regeneration was therefore not passed on this machine.

## Architecture implication and next task

Stage 8.4 has produced an interpretable limited scheduler result. Keep the mechanism available and its recovery limitation visible; stop making general design wait for repeated agenda polishing. Stage 8.5 has produced a concrete executable interpretation/core boundary, independent witnesses and a negative authored baseline comparison. That justifies completing the acquisition path; it does not yet justify adding more representational machinery or concluding representations do not help.

The central unanswered question remains whether the society can construct a useful change from experience and preserve its meaning in another domain. Complete [the bounded representation assignment](../WORKER-REPRESENTATION-01-COMPLETION.md), then let that evidence determine the next architecture change. Temporary teams and learner self-revision stay later slices. No production implementation changes were made by this review.
