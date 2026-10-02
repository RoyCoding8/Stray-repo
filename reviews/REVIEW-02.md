# S0-S3 review 02: changes required

Reviewed commit: `8bcf5b83cf73de034dd594682ffd43a75630fbe8` on `codex/implementation-s0-s3`. Reviewed fix diff: `git diff 4c6b35388134af7dad15541ab60986630a43150f...8bcf5b83cf73de034dd594682ffd43a75630fbe8`. The baseline is the rewritten equivalent of REVIEW-01's published commit; its tree was verified identical during the preceding history synchronization. The implementation request identifies `c827942` as its tested code tip.

Disposition: **do not accept S0-S3 as complete yet**. Several fixes address the original narrow reproductions, but important runtime contracts remain incomplete. This is a source review with bounded independent probes, not independent replication of the reported 348-test PostgreSQL suite. No implementation was changed or merged by the reviewer.

## Work and verification record

- [x] Fetch and pin the submitted commit and rewritten review baseline.
- [x] Isolate review in `codex/review-s0-s3-02` and a separate worktree.
- [x] Inspect all 17 previous findings and their affected implementation paths.
- [x] Obtain separate standards and evaluation-specification passes using independent reviewers.
- [x] Independently inspect dispatch, recovery, evidence, launcher, workflow and experiment integration.
- [x] Run available regression tests and focused probes; record limits and next checks.

Environment: Windows, Python 3.12.13, dependencies installed with `uv sync --locked --extra test --python 3.12`. No test database DSN was configured. No live provider, PostgreSQL server, Docker/runsc execution or DBOS recovery deployment was exercised.

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_r01_grader.py tests/test_r01_runsc.py tests/test_r01_deadline_ui.py tests/test_run_compose.py
.\.venv\Scripts\python.exe -m pytest -q reviews/probes/test_review_02.py
```

| Independent check | Result | Meaning |
|---|---|---|
| Existing selected regressions | 27 passed, 17 skipped, 13.87 seconds | Database-dependent grader/UI/composition cases were skipped. gVisor tests use process doubles, not real containment. |
| Review probes | 9 passed, 2.89 seconds | Eight reproduce remaining bad behavior; one verifies rejection of the original import-time grader forgery. |
| Configuration | `asyncio_mode` warning | Same unknown pytest option; not a substantive finding. |

The reported **329 + 19 = 348 passing tests** and workstream evidence were inspected, not rerun. Do not combine these figures with the independent counts above or call the skipped grader integration suite verified here.

[probes/test_review_02.py](probes/test_review_02.py) declares its evidence through explicit test names:

- The hidden-answer leak and original forgery rejection execute the real grader and real candidate subprocesses. They bypass the database/launcher transport and run with the same repository working directory inherited by the submitted local launcher.
- The HTTP deadline probe uses a real bounded localhost server sending response headers slowly. It has a 200 ms request budget and returns only after more than 800 ms. It makes no external request.
- The other probes isolate actual decision functions with scripted database/admission outcomes: changed sender generation, unproved fulfillment, delayed workflow results, checkpoint ordering, release scope broadening and zero-cost inference receipts. They are not PostgreSQL concurrency or container tests.
- The checkpoint probe replaces database/dump operations and platform-specific fsync. Its first run hit Windows read-only-file fsync behavior; the final probe isolates ordering rather than claiming a Linux backup test.

## Previous finding dispositions

“Addressed in source” closes the stated narrow defect, not every invariant of the surrounding subsystem. Database/live checks remain bounded by the verification record above.

| REVIEW-01 ID | Disposition at this revision | Evidence or remaining issue |
|---|---|---|
| R01-001 | Original concurrent-admission case addressed in source | `_send_model` refuses `ALREADY_APPLIED`; stale-generation dispatch is still open under R02-001. |
| R01-002 | Partial | Grant-version pinning and quarantine lookup were added; investigation eligibility and effective sender fencing remain open, R02-001/002. |
| R01-003 | Partial | Required fields and cross-investigation attempt check added; obligations are compared, not discharged, R02-003. |
| R01-004 | Open | Reconciliation is more conservative, but generation counters do not fence the sender, R02-001. |
| R01-005 | Partial | Docker/runsc invocation exists; broker-independent hard lifetime and bounded I/O contract do not, R02-006. |
| R01-006 | Open | Barrier verification and target generation bumps exist; coordinated checkpoint and effective restore fencing remain incomplete, R02-004. |
| R01-007 | Addressed in source for the reported defect | Roots check retraction; bracketed monotonic epoch reads reject mid-traversal changes. Real-PG regression evidence inspected only. |
| R01-008 | Original import-time forgery fixed; isolation partial | Independently checked forgery rejection; protected answers remain readable in the actual live path, R02-007. |
| R01-009 | Partial | Direct/synthetic rows and missing receipt sets rejected; unrelated successful invocations still qualify, R02-008. |
| R01-010 | Wrong-version substitution addressed; scope partial | Exact candidate-version equality added; dropping scope constraints broadens release, R02-009. |
| R01-011 | Partial | CLI and development calls execute, but retained executable acquisition and fair within-task behavior remain incomplete, R02-010. |
| R01-012 | Broker routing addressed; cost/grant enforcement partial | Real HTTP usage settles for zero; CLI grant value is not enforced, R02-011. |
| R01-013 | Partial | Typed outcome helpers added but not integrated into the workflow loop, R02-005. |
| R01-014 | Partial | Body-stream timeout and control-row wait bounds improved; header waits and aggregate command deadline remain open, R02-012. |
| R01-015 | Addressed in source | Route-preserving refresh and scoped data projections added. Browser/DB integration was not independently exercised. |
| R01-S01 | Addressed for API path | Overview uses bounded batched projection. |
| R01-S02 | Addressed in source | Lease TTL policy is shared. |

## Standards

The separate standards pass found **no material new standards findings** in the assigned gateway, API, agenda, stewardship and template changes. The relevant rules are `AGENTS.md:13-16` and shared-interface ownership in `IMPLEMENTATION-WORKFLOW.md`. The compatibility delegation in `agenda.py:196-197` is justified; it does not warrant a new abstraction or removal. The public helper accepts a larger caller-supplied limit, but the reviewed API uses its bounded default, so that observation is not promoted to a defect.

## Spec

The separate evaluation-specification pass found that R01-009 remains partial: a successful operation is not necessarily the assigned evaluation. Direct result insertion and empty receipt sets are now excluded from release; exact tested-version substitution is checked. Root review confirmed those changes and independently found the scope-subset direction error below. Standards and specification conclusions are kept separate.

All source locations below refer to the reviewed commit. Requirement IDs refer to `docs/design/PRACTICAL-SPECIFICATION.md`. P1 blocks acceptance of the affected slice; P2 remains required correctness work.

### R02-001 — P1 — Revalidation accepts another dispatch generation; restore counters do not fence old senders

**Source:** `src/settlement/broker.py:301-309,399-443,476-488`; `src/settlement/store.py:724-730,1019-1044`; `src/settlement/launcher_runsc.py:234-261`.

**Requirements:** EFF-2, EFF-5, REC-3: only the admitted dispatcher may send; negative reconciliation is insufficient while an old sender can still act.

The sender stores its first admission generation, but `_revalidate` treats any `ALREADY_APPLIED` result as valid without comparing that generation. A generation-1 sender can receive a generation-3 result after reset/re-admission and still send. `_finish_send` detects the mismatch only after the external effect. Its mismatch branch also replaces the actual returned receipt with a generic unknown record, losing useful late evidence.

More broadly, bumping rows in a restored database cannot stop a paused sender that still uses the old database or has passed the final read. The model request carries no enforced dispatch-generation fence, and the runsc launcher ignores `op.dispatch_generation`. Local generation files are not updated by the target's restore transaction. The new counter is a stale-result detector, not an effective fence at the effect boundary.

**Independent evidence:** `test_sender_ignores_changed_dispatch_generation` executes the actual send path with admissions at generations 1 and 3 and observes a gateway call using generation 1. Database outcomes are scripted; no provider call is made.

**Next check:** Pause a real dispatcher at multiple points through final admission and launcher/provider send; restore/reset, establish replacement ownership and release the old process. Require zero obsolete sends. Demonstrate fencing across the original and restored databases, not only rejection of a stale command submitted to the new database. Preserve attributable late receipts even when their generation is obsolete. Keep uncertain operations non-retryable unless old senders are effectively fenced or the provider contract establishes idempotency.

### R02-002 — P1 — A withdrawn investigation can still dispatch prepared work

**Source:** `src/settlement/store.py:327-343,461-469`; `src/settlement/run.py:370-406`; `src/settlement/broker.py:364-422`.

**Requirements:** RUN-4 and current dispatch eligibility.

Withdrawal updates only the investigation disposition. Admission checks the attempt lifecycle, grant version and quarantine pins, but does not check the investigation disposition or current investigation revision. `run.check_eligibility` knows that a withdrawn/fulfilled investigation is ineligible, yet the dispatch transition does not use that rule. Preparing an operation, withdrawing its investigation and then dispatching it therefore still passes these checks while the attempt remains running.

**Evidence:** Complete source path inspected; real-PG sequence not executed here.

**Next check:** Exercise prepared operations after withdrawal and after amendment on both workflow and scheduler paths. Current investigation/attempt compatibility must be checked inside authoritative admission. Do not add another optional preflight that the normal path can omit.

### R02-003 — P1 — Fulfillment accepts obligations merely copied from the investigation

**Source:** `src/settlement/store.py:600-642`.

**Requirements:** TX-6, RUN-4: current completion obligations and eligibility must hold in the fulfillment transition.

The handler now validates identity/version fields, but its obligation check is only dictionary equality. An unresolved obligation copied from the investigation is accepted, without checking supporting evidence, required successful outcomes or actual satisfaction. It also does not check pinned quarantine status at fulfillment; a completed attempt can be quarantined before fulfilling. Requiring an epoch field does not prove evidence, and the `< current` comparison also accepts invented future epochs.

**Independent evidence:** `test_fulfillment_accepts_copied_but_unproved_obligations` executes the transaction handler with an explicit unsatisfied obligation. It performs only the investigation read and fulfillment update and returns `APPLIED`.

**Next check:** Define the concrete supported completion-obligation forms and their discharge witnesses. Reject unresolved, missing, stale and quarantined witnesses in the same admission transition. Test a matching obligation map with no proof, an unrelated success receipt, future epochs and post-completion quarantine. Keep explicit operator override separate and attributable.

### R02-004 — P1 — The checkpoint “barrier” is a marker with an incomplete validation interval

**Source:** `scripts/checkpoint.py:151-218`; `src/settlement/store.py:972-1044`; `scripts/restore.py:97-173`.

**Requirements:** REC-1/2/3: stop admissions/executors, produce a coordinated recovery set and restore behind effective fencing.

`checkpoint_barrier` increments an epoch and records counters; admission never checks a paused/barrier state. `run_checkpoint` verifies the counters after dumping but before reading metadata and copying artifacts. A write after verification can make the manifest describe a later state than its dump while the command still succeeds. In-flight effects can continue without changing those counters until their receipt arrives.

The optional workflow-store path calls the same domain barrier on the DBOS database, assuming it has Settlement's `control`, `command_journal` and `outbox` tables. The test supplies another migrated Settlement database, not a DBOS system store. The restore script has no workflow-target input and never restores the optional workflow dump. New target generations also leave prepared operations dispatchable through callers that resolve omitted ownership to the new generation; there is no enforced restore mode disabling effects.

**Independent evidence:** `test_checkpoint_accepts_mutation_after_barrier_verification` scripts a dump at count 1 and a write after successful verification, then observes a successful checkpoint with manifest count 2. This is an ordering probe, not a database backup test.

**Next check:** Test a real active domain database plus a real DBOS system database, including mutation during every checkpoint phase and restoration of both stores. Establish and enforce admission/executor fencing for the whole recovery-set interval. After restore, default scheduler execution must refuse new effects until reconciliation explicitly permits resumption. Do not describe the current marker/counter protocol as a completed barrier.

### R02-005 — P1 — Delayed-result recovery helpers are still outside the workflow loop

**Source:** `src/settlement/broker.py:799-877,919-953`; `src/settlement/run.py:476-487`.

**Requirements:** BOOT-5, RUN-1/2 and S1/S2 fresh-process continuation.

`wf_consume` exists, but `attempt_workflow` never calls it. Once a node is registered as unresolved, `pending_invokes` excludes it and the workflow returns `waiting`, even if its successful receipt is already available. The new fresh-process test explicitly calls the helper; it does not resume the actual workflow loop. Likewise, `restore_workflow_resources` is a manual helper with no production startup call. A failed invocation is removed from unresolved operations without completing/failing the node, allowing repeated handling of the same failed operation until round exhaustion.

**Independent evidence:** `test_delayed_success_is_not_consumed_by_workflow` runs the undecorated production workflow body with an unresolved continuation and an available successful outcome. It returns `waiting` without calling the consumer. This does not exercise DBOS persistence.

**Next check:** Resume the actual registered workflow in a clean process from an unresolved continuation. It must reconstruct admitted dependencies, consume a delayed result exactly once and persist a meaningful next state. Test failures, cancellation and round exhaustion through that same entry point; helper-only success is insufficient.

### R02-006 — P1 — gVisor hard limits still depend on the broker surviving

**Source:** `src/settlement/exec_profile.py:203-222,253-324`; `src/settlement/launcher_runsc.py:73-105,197-221,234-271`.

**Requirements:** EFF-3/7, especially practical specification line 99: killing the broker must not remove the stop mechanism.

The timeout is implemented by the broker process waiting on `docker run` and calling `docker stop`. There is no external watchdog/deadline owner. If that process dies, a sleeping container can outlive the admitted wall bound. Optional per-process CPU ulimit does not solve that case. `communicate` accumulates all output before `_cap` truncates it, so the declared output limit does not bound host buffering. `scratch_bytes` is declared but not applied to the container command.

Additionally, `RunscLauncher.stop` deletes tracking and returns true after attempting stop/kill, without verifying final stopped state. Docker errors can therefore be reported as successful termination. These are missing contract implementations, not merely unverified host compatibility.

**Evidence:** Source inspection; existing mocked process tests passed. No real container probe was run.

**Next check:** On a compatible host, kill the actual broker while a child/container sleeps and require an independent supervisor to terminate it within the admitted bound. Flood output and scratch space under measured host limits. Inject failed stop/kill/inspect calls; preserve tracking and uncertainty until termination is actually established. Supply a controlled artifact input/output path before using this profile for the experiment's host-path-based programs.

### R02-007 — P1 — Live evaluation still exposes protected repository answers to candidate code

**Source:** `experiments/run_live_abc.py:133-146`; `experiments/run_tests.py:65-103`; `src/settlement/launcher_local.py:181-185`; `experiments/fault_tasks.py:12-85`.

**Requirements:** LEARN-2 and EFF-3: protected answers must be outside candidate access, and the candidate/evaluator boundary must be enforced.

Moving candidate execution to a child process rejects the original stdout/SystemExit forgery. However, the live CLI unconditionally creates `LocalLauncher`; it has no contained execution choice and inherits the repository working directory. The candidate can read `experiments/fault_tasks.py`, which contains protected panel/transfer answers and reference fixes. Unlinking the temporary cases file does not remove this copy. Both grader and candidate also share the host filesystem and account.

**Independent evidence:** A candidate that performs only a lookup of the repository's stored expected answer passes all three `panel-triangular` cases through the real new grader. The probe does not implement the mathematical function. The original import-time forgery is independently rejected in a separate test.

**Next check:** Run candidate code behind the admitted containment boundary with an explicit input allowlist, separate evaluator authority and no access to fixture repositories, other arms, hidden artifacts or controller resources. Test the real live command's selected launcher, not only an isolated grader helper. Re-run the answer-lookup attack and require refusal/unavailability of that data. Keeping fixtures in private Git is compatible with this requirement; exposing them to the runtime candidate is not.

### R02-008 — P1 — An unrelated successful operation can still serve as evaluation evidence

**Source:** `src/settlement/evaluation.py:108-160,163-208`; `src/settlement/experiment.py:515-534`; `src/settlement/capabilities.py:255-297`.

**Requirements:** IF-6, EFF-4, LEARN-2/7: results must come from the actual assigned evaluator execution, not arbitrary insertion.

The binding check now prevents some reuse and requires a success receipt for a success label. It still never checks the invocation's effect, evaluator code/profile, task identity or candidate content digest against the assignment. Any previously unused successful operation can be labeled as this evaluation. The “unrelated observed operation refused” error is triggered by reuse, not by an unrelated first use. A grading process can also exit successfully while reporting failed test cases; operation success alone is not evaluation success. The caller's `result['outcome']` remains authoritative.

**Evidence:** Separate specification pass plus primary reviewer source verification. No database exploit executed here.

**Next check:** Establish the evaluation assignment and immutable candidate/evaluator/task binding before launch, and derive the verdict from its authenticated result. Reject a fresh unrelated successful operation, a successful grader process whose tests failed, mismatched candidate bytes and evaluator replacement. Keep the new direct/synthetic-origin refusal checks.

### R02-009 — P1 — Release scope checking permits removal of applicability constraints

**Source:** `src/settlement/capabilities.py:235-252,364-370`.

**Requirement:** LEARN-7: preserve incumbents outside supported scope.

The exact candidate-version check is a real fix. The new scope check iterates only the requested keys, however. Support for `{family: software-repair, language: python}` therefore permits release for `{family: software-repair}`, dropping the language restriction and broadening applicability. Declared applicability also needs to be distinguished from scope actually supported by the trial.

**Independent evidence:** `test_release_scope_can_drop_a_supported_constraint` executes the production validator and observes acceptance.

**Next check:** Define scope inclusion explicitly and require the release scope to imply every supported restriction. Test deleted constraints, incompatible values and legitimate narrowing. Validate against trial-supported scope as well as candidate declarations.

### R02-010 — P1 — The experiment still imports a handwritten method and ignores C's model output

**Source:** `src/settlement/experiment.py:273-339,414-446`; `experiments/run_live_abc.py:71-107`.

**Requirements:** S3 and section 11's development/retention comparison; LEARN-3 matched within-task opportunities.

Development now executes model attempts and grades them, but never synthesizes an executable method from those attempts. It reuses an existing registry method or loads the caller's `--method-source`, defaulting to the handwritten `offbyone_fixer.py` even in live mode. The lesson-authoring prompt contains task IDs and success/failure labels, not the claimed development transcripts. This does not yet implement autonomous method acquisition.

Each comparison arm now pays for one model call, but C's returned text is discarded (`if harness_arm != 'C'`). C is graded on the method's precomputed output while A/B are graded on model output. Equal call counts are not equal reasoning/tool opportunities. There is still no within-task tool loop for A/B. Selection also re-queries the global capability registry during evaluation instead of invoking the exact method frozen by this development run.

**Evidence:** Source path inspection. No live learning result claimed or measured.

**Next check:** Derive retained methods from development work, freeze exact artifacts and information access, and give every arm the same bounded within-task action interface. Retention should change what persists between tasks, not whether the model's answer counts. Test adversarially different C model output and unrelated pre-existing registry entries, then trace the evaluated artifact back to its actual acquisition and costs.

### R02-011 — P1 — HTTP usage is settled as free, and the CLI grant value is only displayed

**Source:** `src/settlement/gateway_http.py:253-279`; `src/settlement/broker.py:432-443`; `src/settlement/store.py:200-229`; `experiments/run_live_abc.py:81-123`.

**Requirements:** EFF-8 and LEARN-3: unknown usage retains conservative exposure; actual costs and resource conditions must be honest.

The HTTP adapter populates token counts but leaves `Usage.charge_units` at its default zero. The broker passes that as `actual_cost=0`, and settlement releases the full reservation while consuming zero units. Real paid inference without explicit pricing is thus treated as free. Receipt-based accounting reproduces that erroneous zero rather than resolving it.

The CLI parses and prints `SETTLEMENT_GRANT_UNITS` but never binds it to an allocation or compares it with the available grant. Setting it to 1 while using a larger existing allocation does not constrain the run to 1. Sandbox occupancy units, estimated tokens and monetary units also need explicit domains/conversions rather than a combined number labeled actual expenditure.

**Independent evidence:** The real HTTP decoder processes 1,500 reported tokens; the actual broker send path constructs a successful receipt with `actual_cost=0`. Transport/admission are doubled in this probe; no paid request or real settlement was performed.

**Next check:** Represent unknown billing separately from zero, retain conservative exposure until pricing/reconciliation is established, and enforce the declared grant against the actual allocation. Test unpriced usage, missing usage, positive priced usage, and a CLI cap smaller than the existing allocation. Never claim a hard monetary ceiling from a token-length estimate alone.

### R02-012 — P2 — Total deadlines still exclude blocking header waits and cumulative database time

**Source:** `src/settlement/gateway_http.py:185-204`; `src/settlement/store.py:97-157`.

**Requirement:** Bounded execution/deadline contract, R01-014.

The body-stream fix works for its tested case. But `client.stream` waits for complete response headers before entering the loop that checks elapsed time. A peer can continually deliver header bytes within the read-inactivity timeout and exceed the total deadline. The database uses a fresh full budget for each statement/retry and does not bound connection establishment or the second transaction used to record a refusal. These are per-wait limits, not one total command deadline.

**Independent evidence:** The bounded localhost header probe demonstrates the HTTP overrun. The database remainder is source-inspected only.

**Next check:** Enforce one absolute deadline across connection, headers, body, lock/statement waits and retries. Test slowly progressing headers, stalled DNS/connect where controllable, cumulative statement time and refusal journaling under contention. Keep provider outcome uncertainty distinct from local cancellation.

## Answers to the pass-02 questions

1. **Do the fencing fixes close the gap?** They close ordinary duplicate admission, but not stale-generation send authority or old-database senders. See R02-001/004. Comparing versions after sending does not fence the effect.
2. **Is bracketed-epoch revalidation acceptable?** Yes for the stated optimistic read contract: every relevant mutation must atomically change a monotonically increasing epoch, and admission must validate the returned snapshot's epoch. The root/premise retraction fix is sound for the reported defect. This does not make unrelated fulfillment/evaluator checks sufficient.
3. **Is the grader plus receipt binding sufficient?** No. The original forgery is fixed, but the live candidate can read hidden repository data and first-use unrelated invocations remain admissible, R02-007/008. The filesystem limitation is directly on the acceptance boundary.
4. **Is only a live A/B/C run outstanding?** No. Autonomous executable acquisition, exact retained-artifact use, comparable within-task behavior, contained execution and trustworthy billing remain implementation work, R02-007/010/011.

## Next implementation handoff

Merge `origin/codex/review-s0-s3-02` into the implementation branch without rewriting history. This pass starts on the submitted rewritten history; do not merge obsolete pre-rewrite review ancestry. The earlier one-time history exception is exhausted.

Keep the current implementation and fix these contracts with additive commits. Use isolated worktrees/databases where helpful, with one owner for shared admission/recovery transitions. The implementation coordinator chooses the models available in its environment and independently assesses review findings.

Prioritize:

1. Effective sender/recovery fencing and a real coordinated checkpoint/restore entry point, R02-001/002/004.
2. Actual completion/continuation semantics, R02-003/005.
3. Contained, bounded evaluator execution and immutable invocation bindings, R02-006/007/008/009.
4. Acquisition/comparison and resource accounting on those verified paths, R02-010/011, with R02-012 deadline work integrated at the execution boundary.

The next acceptance evidence must exercise the real entry points. In particular: actual workflow restart rather than a direct consumer helper; actual DBOS schema rather than a second Settlement database; actual live CLI launcher selection rather than a standalone containment test; and actual evaluation invocation identity rather than matching rows inserted by the test. Smaller complete vertical checks will establish more than another large collection of helper-level assertions.

For every R02 ID, record its fix commit, positive regression and independent negative case. Preserve this probe file as revision-specific evidence: eight tests intentionally assert old bugs and must not be counted as correctness tests after repair. The ninth is a genuine regression for the fixed original forgery. Update the implementation/verification/decision reports and request review at an exact SHA. No S4-S7 expansion is approved by this review.

Standards axis: 0 material new findings. Specification/correctness axis: 12 findings (11 P1, 1 P2); the central unresolved property is enforceable authority and evidence across actual execution boundaries.
