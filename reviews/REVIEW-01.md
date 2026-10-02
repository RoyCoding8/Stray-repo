# S0-S3 review 01: changes required

Reviewed source: `d69e5ffb626e1ab979f6dc0ebe4ba74bee6f7fbd`, relative to seed `be7956d12dacea712e178c9926362356e89d148a`.

Review branch: `codex/review-s0-s3-01`. This branch changes review material only. It does not approve or modify the implementation. Findings apply to the recorded source, not subsequent commits.

The implementation establishes substantial useful scaffolding, but S0-S3 cannot be accepted as complete. Several critical requirements are missing from executable paths, and others are bypassable. A passing regression suite does not establish these properties when its fixtures do not challenge the relevant boundaries.

The disclosures concerning unavailable live inference, runsc, PostgreSQL 18 and statistical analysis are valuable. However, missing implementation must be distinguished from implementation awaiting environmental verification: neither installing runsc nor supplying gateway credentials makes the submitted sandbox launcher or live A/B/C command complete.

## Review task record

- [x] Pin source/base and inspect the implementation request, specification and verification reports.
- [x] Isolate review in a separate worktree; preserve other work and its uncommitted edits.
- [x] Complete separate standards and specification inspections.
- [x] Inspect dispatch, authority, evidence, evaluation and recovery paths.
- [x] Run available focused tests and bounded defect probes.
- [x] Record findings, evidence limits and implementation acceptance checks.

## Independent verification

Environment: Windows, CPython 3.12.13; dependencies installed from the submitted lockfile using `uv sync --locked --extra test --python 3.12`.

From the review repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_s0_gateway.py tests/test_run_compose.py
.\.venv\Scripts\python.exe -m pytest -q reviews/probes/test_review_01.py
```

Results:

| Check | Independently observed result | Boundary |
|---|---|---|
| Existing focused tests | 27 passed, 2 skipped, 30.88 seconds | Two tests require `SETTLEMENT_TEST_DSN`; this environment has none configured. |
| Review defect probes | 4 passed, 2.73 seconds | These deliberately assert defective behavior at the submitted revision. Passing means reproduction, not acceptance. |
| Pytest configuration | Unknown `asyncio_mode` warning | Not treated as a substantive blocker. |

Probe details in [probes/test_review_01.py](probes/test_review_01.py):

1. Actual grader subprocess executes candidate import-time code, accepts its fabricated JSON, and `_grade` returns success for a nonexistent function. The broker/launcher receipt transport is replaced by a small adapter; no containment claim is made.
2. Two real Python threads call `dispatch_operation` on the same prepared operation. The database boundary is replaced with its two documented serialized outcomes, `APPLIED` and `ALREADY_APPLIED`. Both threads call the gateway. This is an executable control-flow reproduction, not a PostgreSQL concurrency test.
3. A successful mocked gVisor probe produces `available=True`, yet dispatch still unconditionally raises `IncompatibleVersion`.
4. The actual evidence traversal, supplied a scripted cursor containing a retracted claim with a live derivation, accepts that claim as a root and rejects it as a premise. This isolates traversal semantics; it does not reproduce a database transaction or concurrent invalidation.

The reported 244-test PostgreSQL 16/subprocess suite was inspected in `reports/VERIFICATION.md`, not independently rerun. No PostgreSQL server, live provider, gVisor runtime, DBOS recovery deployment, containment test or real learning experiment was exercised here. Do not aggregate the two test counts above into a full-suite claim.

## Specification and correctness findings

P1 findings block acceptance of the affected slice. P2 findings require correction but need not hold up independent work on other slices. Source locations below refer to the reviewed commit. Requirements refer to `docs/design/PRACTICAL-SPECIFICATION.md` unless otherwise stated.

### R01-001 — P1 — Duplicate model dispatch remains possible

**Source:** `src/settlement/broker.py:316-345,377-393`; `src/settlement/store.py:118-126,625-632`. **Requirements:** EFF-2, EFF-5.

Two callers can both read `prepared`. Both use the same advance-command identity. The second serialized advance returns `ALREADY_APPLIED`, which `_send_model` treats as permission to call `gateway.infer` again. The operation ID is not evidence that the HTTP provider implements deduplication. The local launcher's filesystem claim does not protect this route. Exposure can be incurred twice against one reservation.

**Evidence:** Probe 2 reproduces two sends with precisely these advance outcomes.

**Required behavior/check:** Give the actual sender exclusive, durable dispatch authority. Replayed commands return existing state without authorizing another send. On PostgreSQL, race at least eight model dispatchers, assert one provider request, then crash at admission/send/receipt boundaries and show that uncertainty retains exposure without an unproven resend. Do not fix only the fake adapter or rely on an operation header the provider does not guarantee.

### R01-002 — P1 — Current dispatch eligibility is optional or bypassed

**Source:** `src/settlement/store.py:429-432,625-650`; `src/settlement/broker.py:616-630,751-763`; `src/settlement/run.py:370-406`. **Requirements:** EFF-2, RUN-4.

`advance_dispatch` checks grant freshness only if supplied, and owner generation only if non-null. Normal scheduler dispatch defaults both to null; the workflow supplies generation but omits grant version. The transaction does not check current quarantine/release eligibility. `check_eligibility` exists separately but neither path invokes it at dispatch admission. A prepared operation can therefore cross a revocation/quarantine boundary and still be sent.

**Evidence:** Source inspection of the normal callers and admission transaction.

**Required behavior/check:** Make current authority, ownership and applicable eligibility checks unavoidable in the authoritative transition; a preflight helper alone is insufficient. Prepare an operation, then revoke its grant, quarantine its pinned capability, or change owner generation. Exercise both scheduler and workflow dispatch and assert zero new sends. Include a race between validation and admission and require missing admission inputs to be refused or resolved authoritatively.

### R01-003 — P1 — Fulfillment can bypass completion obligations and ownership

**Source:** `src/settlement/store.py:548-579`; `src/settlement/steward.py:288-289`. **Requirements:** TX-6, RUN-4.

The fulfillment handler allows omission of expected revision, authority version and attempt identity. With no attempt, it updates an investigation directly to fulfilled without checking completion obligations. When an attempt is supplied, matching revision numbers are checked, but its investigation identity is not compared with the investigation being fulfilled. The stewardship entry simply delegates to this handler.

**Evidence:** Source inspection; no database exploit executed.

**Required behavior/check:** Validate current completion authority, exact investigation/attempt relationship, generation, revision and current obligations in one transition. Test minimal payloads, an unrelated completed attempt at the same revision, stale evidence and authority, and duplicate fulfillment. Any privileged manual override must be an explicit separately attributable operation, not an omitted field that weakens normal fulfillment.

### R01-004 — P1 — Empty launcher records do not establish that an old dispatcher cannot send

**Source:** `src/settlement/broker.py:565-580`; `src/settlement/launcher_local.py:67-74,136-172`; `src/settlement/store.py:739-757`. **Requirements:** EFF-2, EFF-5.

Reconciliation resets dispatching to prepared when the run directory contains no matching records. An older dispatcher can be paused after admission but before `_claim`, so those records are absent even though it can still send later. No dispatcher fence or generation is established by the reset. The stable-directory atomic claim helps prevent two local spawns, but it does not revoke the old dispatcher's authority or prove that a post-revocation send cannot occur. A newly created empty directory also cannot prove historical non-dispatch.

**Evidence:** Source inspection; this is a fencing failure, not a claim that the existing local exclusive file creation always permits duplicate spawns.

**Required behavior/check:** Couple negative launcher evidence to a durable dispatch generation and effective fencing of prior senders. Pause a dispatcher immediately before filesystem claim, reconcile, change authority, then release it. It must not send under the old admission. Also test loss/recreation of launcher state and two successive recovery interruptions; uncertain history must remain unresolved.

### R01-005 — P1 — The admitted gVisor execution path is unimplemented

**Source:** `src/settlement/launcher_runsc.py:31-73`; `src/settlement/exec_profile.py:196-207`. **Requirements:** S0, EFF-7 and the declared execution profile.

`RunscLauncher.dispatch` always raises, including when its probe succeeds. Its recovery methods are placeholders. The other gVisor dispatch entry also refuses when the runtime is present because no admitted launcher is implemented. This is missing functionality, not only an unavailable test host.

**Evidence:** Probe 3.

**Required behavior/check:** Implement the declared launcher and recovery contract, retaining explicit refusal on incompatible hosts. Validate on a compatible host with actual containment and externally enforced resource/deadline checks. The labeled `local-process` profile remains useful for trusted integration fixtures; it cannot establish isolation for agent-authored code or satisfy the missing contained path. Record implementation status separately from host verification status.

### R01-006 — P1 — Checkpoint and restore do not implement the specified recovery barrier

**Source:** `scripts/checkpoint.py:97-115,142-166`; `scripts/restore.py:93-155`. **Requirements:** REC-1, REC-2, REC-3, BOOT-5.

Checkpoint runs `pg_dump`, then independently reads domain metadata/counts and artifact state. It does not stop admissions/executors, establish the domain barrier or reconcile the outbox. Concurrent mutations can make its manifest describe a different state from its dump. The workflow system uses a separately configured DBOS database, but this script accepts and dumps one database without coordinating a domain/DBOS recovery set. Restore validates fresh destinations and copied content, but does not establish new ownership generations or enforce an external-effect fence. A different database name is not an execution fence.

**Evidence:** Source inspection. Fresh-destination refusal tests are useful but do not verify the required executor fencing protocol.

**Required behavior/check:** Implement an enforceable checkpoint barrier and a coordinated recovery set for the configured domain/workflow stores. Restore must remain unable to issue effects until version checks, ownership replacement and old-executor reconciliation succeed. Test writes during checkpoint, a live old dispatcher after restore, and a post-backup external action. Measure the recovery behavior rather than describing an ordinary copy test as fenced restore.

### R01-007 — P1 — Retracted roots and mixed evidence snapshots can remain admissible

**Source:** `src/settlement/evidence.py:137-168,175-232`; `src/settlement/db.py:16-18`. **Requirements:** TX-4, S2, R5 current-support semantics.

Retraction of a claim records its ID, but only invalidates derivations whose own ID equals the target. `_supported` does not check whether its root claim was retracted, although `_live_premise` checks the same condition for dependencies. Separately, `current_support` traverses under default READ COMMITTED and reads the epoch afterward. A concurrent invalidation can occur after support was read but before the epoch read, producing old support labeled with the new epoch.

**Evidence:** Probe 4 reproduces the root/premise inconsistency. The concurrent snapshot issue is source-inspected, not dynamically reproduced here.

**Required behavior/check:** Apply retraction consistently to roots and premises; evaluate and label support from a coherent snapshot and validate that snapshot at admission. Test direct claim retraction, alternate support after derivation-only retraction, and a barrier-controlled invalidation between support traversal and epoch read. No stale `true` result may acquire the newer epoch.

### R01-008 — P1 — Candidate code can forge its own evaluator success

**Source:** `experiments/run_tests.py:25-49`; `src/settlement/experiment.py:70-85`. **Requirements:** IF-6, LEARN-2.

The grader imports candidate code into its own process after loading hidden cases. Candidate code shares grader memory, arguments and stdout. Printing a successful JSON object followed by `sys.exit(0)` during import causes the submitted grader to exit successfully before any test executes. `_grade` trusts this object. Putting both inside a sandbox protects neither grading authority nor hidden cases from the candidate within that sandbox.

**Evidence:** Probe 1 obtains a success verdict for a candidate with no required function, claiming 999 passes.

**Required behavior/check:** Separate protected evaluator authority and hidden data from candidate execution. The evaluator derives results through a constrained execution channel and owns the final authenticated receipt. Repeat the exploit, attempted hidden-answer access, stdout spoofing, exit/crash and timeout probes; none may produce successful evidence without actual independent checks.

### R01-009 — P1 — Release evidence can be created from unbound caller outcomes

**Source:** `src/settlement/trials.py:154-180`; `src/settlement/evaluation.py:109-148`; `src/settlement/capabilities.py:174-188,247-257`. **Requirements:** IF-6, LEARN-2, LEARN-7.

`record_result` accepts outcomes with an empty invocation reference. Release checks allow an empty evaluator-receipt set because an empty set has no mismatched versions. The evaluator receipt entry checks that some operation is observed, but accepts the caller's outcome without binding it to the actual evaluator execution, candidate and assignment or deriving it from that invocation's result. Thus successful trial rows can support release without the required evaluation evidence. This is separate from compromising an evaluator process in R01-008.

**Evidence:** Source inspection of result insertion and release queries.

**Required behavior/check:** Require complete, authenticated, assignment-bound evaluator results for release. Keep any synthetic fixture insertion explicitly outside release-eligible production evidence. Attempt release from direct outcome rows, an empty evaluator set, an unrelated observed operation, a failed operation labeled success, and mismatched evaluator/candidate versions. All must refuse.

### R01-010 — P1 — A favorable trial can release an unrelated version

**Source:** `src/settlement/capabilities.py:220-267`. **Requirement:** LEARN-7.

`scoped_release` checks that requested versions exist and are not quarantined, but never binds them to the frozen protocol's tested candidate version. Its protocol query selects only the evaluator version. Evidence for candidate A can therefore authorize existing candidate B, which was never tested. The release scope also needs validation against the scope actually supported by the protocol/evidence, not merely storage of the supplied object.

**Evidence:** Source inspection.

**Required behavior/check:** Atomically bind exact tested candidate versions and supported applicability to the release. Test a favorable A trial submitted for B, mixed A/B version sets and widened scope. Preserve the incumbent where the evidence does not support replacement.

### R01-011 — P1 — The live A/B/C and development experiment are not implemented

**Source:** `experiments/run_live_abc.py:29-49`; `src/settlement/experiment.py:133-139,187-226`. **Requirements:** S3, LEARN-2/3 and practical specification section 11.

With endpoint, key and grant present, the live command only probes discovery/authentication, prints a suggested function call and exits zero. It never executes an arm or uses its DSN/allocation/artifact arguments. The suggested `gateway=` argument also does not match `run_abcs`'s required `double=` argument.

Wiring the command alone would still leave the central experiment missing: `dev_ids` is unused, lessons and executable methods are supplied in advance, C invokes a preinstalled method, and A/B receive single completions without an equivalent within-task tool loop. This compares differently equipped fixtures; it does not test autonomous development, retention and transfer under the specified matched policy.

**Evidence:** Source inspection; simulated reports are not reinterpreted as measured learning.

**Required behavior/check:** Execute the development phase, freeze its retained products, start independent workers and run A/B/C with matched within-task tools and declared retention differences. Make the CLI actually execute this protocol with configured model selection and honest exit status. Demonstrate locally with deterministic adapters first; then run the same path live when the required environment exists. Endpoint access alone is not the outstanding implementation task.

### R01-012 — P1 — Experiment inference bypasses reservations and its costs are synthetic

**Source:** `src/settlement/experiment.py:174-179,203-240`; `experiments/run_live_abc.py:38-47`. **Requirements:** EFF-1/2, LEARN-3.

`run_abcs` directly calls `double.infer`; supplying a real adapter would bypass operation admission, resource reservation and model receipts. The CLI prints the grant without installing/enforcing it. Cost reports use fixed upper-bound estimates rather than observed model expenditure, omit A inference from the accumulated arm costs, and label C's method invocation as retrieval. These figures cannot establish matched expenditure or amortization.

**Evidence:** Source inspection.

**Required behavior/check:** Route every real effect through the same broker/resource contract. Account separately for reservations, settled usage and unresolved exposure, including construction and failed trials. Run with a deliberately insufficient grant and require refusal before provider dispatch; reconcile every arm's reported cost to actual receipts. A free-token implementation environment does not remove the runtime experiment's resource-accounting requirements.

### R01-013 — P1 — Workflow continuation does not consume delayed outcomes or distinguish failure

**Source:** `src/settlement/broker.py:751-826`. **Requirements:** RUN-1/2, BOOT-5, S1/S2.

`wf_record` turns every `observed` dispatch into `node_completed` without examining the receipt's outcome. Non-observed dispatches become unresolved operations; the workflow then returns `waiting` when no new invokes are available, without a receipt-consumption step in this loop to resolve those operations when results arrive. Workflow execution also requires `ATTEMPT_WORKFLOW_RESOURCES[attempt_id]`, an in-memory dictionary with no production restoration path in the submitted source. Process-local test setup is not restart recovery.

**Evidence:** Source inspection, including the only production references to the resources dictionary. No DBOS process-restart reproduction was performed here.

**Required behavior/check:** Advance from durable, typed operation outcomes, including failure/unknown/suspension, and consume delayed/reconciled results into the continuation exactly once. Reconstruct versioned runtime dependencies before workflow recovery. Kill the process after recording an unresolved operation, restart a genuinely fresh process without manually repopulating test globals, deliver its result, and require correct continuation progress. Also show a failed invocation cannot silently count as successful completion.

### R01-014 — P1 — Advertised deadlines do not bound blocking execution

**Source:** `src/settlement/gateway_http.py:79-91,172-197`; `src/settlement/store.py:97-106`. **Requirements:** bounded operations and supervision; practical specification sections 4-5.

The gateway limits a read-inactivity timeout and checks total elapsed time only after the blocking HTTP call returns. A response that continues delivering bytes can exceed the total attempt deadline without triggering that read timeout. Injected clients do not receive a per-request timeout override. The database command likewise computes a deadline but can wait on the control-row lock without a corresponding PostgreSQL lock/statement bound. A deadline checked after a blocking call or only between retries is not an enforced execution bound.

**Evidence:** Source inspection, not a live provider or lock-contention timing test.

**Required behavior/check:** Enforce elapsed deadlines at the execution boundary, including queue/connect/write/read/lock waits, and retain uncertain provider exposure after cancellation. Test a bounded local trickle-response server, an injected client, and a held database lock. Confirm timely return/cancellation under the declared policy rather than merely a late `TIMEOUT` label.

### R01-015 — P2 — Operator detail pages lose their route and comparative data is absent

**Source:** `templates/base.html:16`; `src/settlement/api.py:109-113,172`. **Requirements:** UI-2/3.

The shared template refreshes every page with `hx-get="/"`; a detail or learning view is replaced by the overview after its polling interval while the browser retains the detail URL. The learning route always supplies `comparisons=[]`, so actual comparative outcomes cannot appear. Investigation evidence is drawn from the first 100 global derivations rather than filtered to that investigation.

**Evidence:** Template and route inspection; browser interaction was not run.

**Required behavior/check:** Refresh the current view with a bounded, correctly scoped projection and provide stored comparison/resource results. Test navigation plus at least one poll, multiple investigations with different evidence, and populated comparisons. The user must be able to inspect what the system did and why, without silently changing pages.

## Standards review — separate axis

No consequential hard standards breach was confirmed in the modules assigned to this pass. The following are non-blocking architectural judgments, not claims that the repository prohibits direct SQL or mandates new abstraction layers.

**R01-S01 — P2, projection ownership:** `src/settlement/api.py:81-84` calls `agenda.next_decision_for` for every persisted attempt. `src/settlement/agenda.py:153-161` opens a connection and queries operations per call; the overview includes historical attempts. This creates unbounded per-refresh work and multiple snapshots. Use one bounded/paginated projection with shared next-decision derivation. Validate query count and result scope with many historical attempts. Relevant guidance: `AGENTS.md:14` and implementation workflow shared-interface ownership.

**R01-S02 — P3, duplication:** `src/settlement/steward.py:139-154,199-209` duplicates TTL validation, expiry calculation and lease activation fields/events across issuance and reacquisition. Share that existing policy while retaining each command's distinct eligibility checks. Validate both paths after future lease-policy changes; do not add a generic lease framework merely to remove a few lines.

## Answers to the implementation review request

1. **Local-process plus probe-gated gVisor:** adequate for disclosed trusted development fixtures and testing incompatible-host refusal; insufficient to mark the contained execution slice implemented. R01-005 identifies the code still required.
2. **Never-sent reset with stable run directory:** the atomic file claim is useful, but stable storage alone does not fence a previously admitted sender. Accept the intent of recovery, not the current proof; see R01-004.
3. **Review-fix scope:** the submitted race, receipt, quarantine, authentication and parked-operation fixes address legitimate S0-S3 concerns. This review does not certify every historical fix independently. Findings above identify remaining cross-boundary gaps in the resulting implementation.
4. **Merge/acceptance:** preserve the branch and its provenance, but do not accept it as S0-S3 complete or proceed to S4-S7 on that basis. No implementation merge was performed by this review.

## Learning evidence interpretation

The simulated harness demonstrates pieces of registration, bookkeeping, method invocation and report generation. It does not yet demonstrate autonomous acquisition, fair retained-method advantage, protected evaluation or improved general capability. The current evaluator and release defects also prevent treating a favorable stored verdict as trustworthy evidence.

Keep the statistical refusal for LEARN-6. Do not convert this small fixture into a broad learning claim by increasing its number of scripted cases. Establish evaluation integrity and comparable development/use conditions first; then report measured results, uncertainty, costs and explicit transfer scope. Neither this design nor a passing implementation suite guarantees optimal general intelligence.

## Next implementation cycle

Merge this review branch into the implementation branch without rewriting history. Preserve later work if the implementation branch has advanced. The implementation coordinator chooses its specialists and remains responsible for integrated correctness.

Use isolated worktrees and databases again, but allocate by invariants and their shared mutation boundaries. A suitable sequence is:

1. **Admission and recovery contracts first:** agree on sender fencing, required authority fields, outcome consumption and checkpoint ownership. Resolve R01-001/002/003/004/006/013 together where they share broker/store transitions. Assign one owner to shared store/broker edits.
2. **Parallel independent work:** implement the actual contained launcher (R01-005); repair evidence snapshot/retraction semantics (R01-007); implement evaluator/result/release integrity (R01-008/009/010). Split these only after their interface obligations are explicit.
3. **Integrate deadline enforcement and UI corrections:** R01-014/015 and the standards observations. Do not let a larger test count substitute for boundary probes.
4. **Rebuild the experiment on those verified paths:** R01-011/012, including real development and equivalent within-task tools. Only then attempt live comparison.

For every finding, add a focused regression that asserts the required behavior, report its result and link its fix commit. The review probe file intentionally asserts the old bugs; preserve it as historical evidence or clearly supersede it, and do not count it as a correctness test after fixes. Several source-inspected findings need real PostgreSQL/process tests as specified above.

Update `reports/PLAN.md`, `reports/IMPLEMENTATION-STATUS.md`, `reports/VERIFICATION.md`, `reports/DECISIONS.md` and `reviews/REQUEST.md`. Separate implemented-and-tested, implemented-but-unverified, incomplete and deferred states. Request another review at an exact source SHA. Do not mark this review approved on the reviewer's behalf.
