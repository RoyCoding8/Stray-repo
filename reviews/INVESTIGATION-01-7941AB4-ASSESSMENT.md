# Investigation 01 completion review at 7941ab4

Reviewed `7941ab43eaf334302aec9cd108bdb9fe014f3f0c`, fetched from the reported completion branch. Review date: 2026-09-20. **Accept the delivered core improvements; do not close the technical batch or describe a human grant as its sole remainder.** Three bounded areas below prevent the intended live qualification. The next task is [study readiness](../WORKER-INVESTIGATION-01-STUDY-READINESS.md), not a new architecture or general audit.

## Accepted changes

- The public AD01 trajectory invokes `DecisionConsumer` for both software and graph decisions. This closes the earlier disconnected-consumer finding.
- Construction now subdivides a parent allocation; `ensure_campaign` binds existing authority and refuses an unbound store. Preserve these changes. The remaining authority problem is the aggregate study runner, not the old per-episode minting function.
- The generated method result envelope is executor-owned, explicitly rendered and checked in the child. Preserve this completed interface work.
- Same-process correction carries the failure into the next proposal. New validation-interruption tests and broker recovery logic are substantial progress. Do not infer diagnostic or partially corrected decision recovery from validation tests.
- Exports and the recording pilot exist. Their validation is incomplete; this does not mean the recorded mechanics did nothing.

The worker reports 828 passing tests. The committed completion report also records 592 skipped tests and two setup errors, followed by a three-test DBOS file rerun. Keep that exact distinction rather than calling it a fully provisioned all-green database suite.

## ICR-01: the proposed live entry and aggregate authority are unfinished, P1

`scripts/inv01_study.py` is hardwired to `InvCQualificationDouble` at `_run_trajectory`, with `MODEL = 'inv01-study-double'`. Its CLI has no model, live mode, study root or grant input. The documented instruction to run this entry “with a live model label” fails: the real CLI exits 2 on `--model review-live-model`. Supplying endpoint credentials cannot change its selected provider.

The runner self-authorizes each trajectory, prepares/clears its disposable database on every start, and constructs an in-memory `StudyBudget`. That budget is checked before each development trajectory, not before each effect or the later use phase. Restart recreates its counters and clock. `deadline_s` does not govern already admitted trajectory work or protected use. The cap sheet contains no enforced aggregate witness-query or execution-time counters. The report acknowledges the missing single pilot root as a future bottleneck, but one study root across all phases is an existing requirement.

Implement an explicit recording/live choice through the same entry, bind a separately authorized persistent study, and enforce its actual budgets/deadline across calibration, comparison, use and resume. Fixture database setup must not be the live/resume entry. Cross-store duplicate authorization by a human is a separate policy issue; a distributed authorization system is not requested. The current runner's missing live mode and automatic reinitialization are enough to block the proposed live request.

## ICR-02: partially completed decisions lose state on resume, P1

`DecisionConsumer.decide` restores only the number of correction rows, then sets `prior = None` and `required_target = None`. The probe supplies one persisted correction rejecting a software target and uses the real consumer and real admission validator. The next request contains no failure, and a graph target is admitted with correction count 1. This controlled-storage probe demonstrates the decision restoration error; it is not a real-DB crash qualification.

The production `trajectory._run_boundary` still invokes `run_diagnostic` after loading an accepted pending decision. No diagnostic completion record is read before that call. Re-entering the accepted graph boundary in the probe executes the real diagnostic twice, spending 14 queries each time. `authority.note_phase` and `phase_status` have only test callers. Their standalone crash driver does not establish the public trajectory's diagnostic checkpoint.

Persist and restore the complete corrective state, including rejected target, failure and count. Save the actual diagnostic observation and spend before construction, then reuse them after interruption. A consumer stopped after its first refusal must resume that correction, and a campaign stopped after a diagnostic must not redo the diagnostic. Keep the existing validation-receipt recovery behavior and honest handling of uncertain post-spawn effects.

## ICR-03: exports and recomputation omit relevant evidence, P1

`records.export_campaign` selects the exact base learner operation or names containing `-b<seq>-`. Correction operations use `learner-0-c1`, which matches neither. On a controlled snapshot containing the base learner and its correction, both appear in top-level operations but only the base appears in the transition, receipts and raw responses. `recompute_accounting` returns one model call instead of two because it trusts the incomplete transition counters. Export packets are reconstructed without the corrective failure context rather than bound to the request actually delivered.

`recompute_study` compares only model and construction call counts. A probe with zero use records, accounting claiming 24, and a false query total still exits 0. It does not require the frozen panel membership or the expected phase records. The runner also omits its separate empty-use records from totals. Thus “recompute exits zero” does not prove the complete study or matching totals.

Export every initial/correction/repair/use attempt through explicit decision/operation relationships, retain actual permitted request/response and configuration identities, and compute from the complete operation/receipt set. Check every advertised total and exact frozen membership, not merely two counters. Missing, duplicate, altered or unattributed records must fail or produce an explicitly incomplete result. Preserve uncertainty rather than manufacturing usage values.

## Independent evidence and limits

[Probe](probes/investigation_01_completion.py) and [observations](evidence/investigation-01-completion-review/observed.json) cover real CLI parsing, the actual consumer/admission with a stored-correction read double, actual diagnostic execution, actual export/accounting over controlled stored rows, and actual offline recomputation. No provider or database effects occurred. These are falsification probes for the named contracts, not substitutes for the worker's public real-DB acceptance runs.

Eight selected tests passed in 2.06 seconds: two study-cap helper checks, same-process same-target correction, three method envelope/prompt checks and two additional envelope-rendering checks. The local environment has no `SETTLEMENT_TEST_DSN`; the PostgreSQL recording pilot, worker's crash suite and full suite were not independently run. A successful helper test does not contradict an uncovered integrated counterexample.

Jev received the accepted progress, the concrete counterexamples and these verification limits. It favored partial acceptance and one bounded follow-up, and did not support claiming observed live overspend. [Input](evidence/investigation-01-completion-review/jev-input.json) and [response](evidence/investigation-01-completion-review/jev-output.json) are recorded. Jev judged reviewer-supplied facts; it did not independently inspect the repository or authorize spending.

## Review checklist

- [x] Fetch the exact tip and inspect the implemented public path.
- [x] Preserve accepted improvements and reproduce material remaining discrepancies.
- [x] Check the live request against the actual entry and enforced bounds.
- [x] Obtain a bounded Jev second opinion and record its limits.
- [ ] Complete ICR-01–03 and the corresponding public-path counterchecks.
- [ ] Run live qualification under valid authority, or present the final runnable manifest and enforced cap sheet as the sole external remainder.

We remain in stage 8. No new conceptual layer, expanded benchmark or positive-result requirement is introduced by this review.
