# Parallel implementation workflow

The current human assignment and its linked specification define scope. Older assignment names, audit instructions and task graphs below are historical examples. Every coordinator and specialist must read section 9 and apply the relevant counterchecks; it records recurring failures from actual handoffs.

The human authorizes parallel subagents and Git worktrees for implementation. The current handoff is [stage 8 closeout and stage 9 start](WORKER-STAGE-08-CLOSE-STAGE-09-START.md), written for a new worker chat. Its coordinator owns `codex/implementation-stage-08-close-stage-09-start`, and its contract controls scope, requirements and gates. Earlier assignment names and branch examples below are historical. Token expenditure is not a reason to avoid useful design comparisons, adversarial review, or investigation. Concurrency should follow independent work and available execution resources. Do not invent busywork to fill agent slots.

## 1. What kind of assignment this is

This is **bounded engineering design and implementation with an empirical research component**. The architecture defines intended behavior, representation families, module responsibilities, important invariants, technology direction, failure semantics and staged acceptance. It does not specify every schema column, interface signature, package API, scheduling parameter, UI component or experimental task generator.

| Decision class | Status | Expected judgment |
|---|---|---|
| Purpose and core semantics | Specified in R0-R5 | Implement faithfully; identify contradictions rather than silently reinterpret them. |
| Technology direction and operating envelope | Selected in R6 | Resolve actual package compatibility and deployment details with primary documentation and tests. |
| Concrete engineering | Intentionally open within the contracts | Design SQL schema and constraints, interfaces, composition representation, deployment configuration, test fixtures and usable UI. |
| Mechanism trade-offs | Constrained but not completely determined | Compare alternatives when they affect concurrency, evidence, effect reconciliation, recovery or experimental fairness. Record consequential choices. |
| Learning advantage | Unproven | Implement an honest experiment; report gain, regression or inconclusiveness. A positive result is not guaranteed. |

S0-S2 are chiefly demanding systems engineering. S3 adds experimental design and interpretation. This is more demanding than translating a fully enumerated CRUD specification, but the implementer is not being asked to invent the entire agent philosophy or discover a new general theory of learning.

Use a strong reasoning/coding model as coordinator and for the critical state/effect/evidence work. Bounded adapters, UI components and ordinary test fixtures are suitable for implementation specialists once their contracts are fixed. Use a capable reviewer for failure analysis and experimental confounds. Increasing the number of weak workers does not replace an engineer who can resolve cross-module contradictions.

## 2. Roles and responsibilities

Start with a coordinator, two or three implementation specialists, and a validation/review specialist where the environment supports them. This is an initial organization, not a permanent team size. Expand when additional independent work is ready; shrink when integration or a shared decision is the bottleneck.

| Role | Owns | Must not do |
|---|---|---|
| Coordinator/integrator | Task graph, common contracts, shared-file ownership, integration branch, final reports, cross-module acceptance | Delegate away responsibility for the assembled system. |
| Implementation specialist | One bounded subsystem or vertical task, its focused tests and task report | Edit another task's files or redefine shared contracts unilaterally. |
| Validation specialist | Acceptance harness, fault scenarios, reproducibility and integrated checks | Replace a real integration gate with mocks and call it verified. |
| Adversarial reviewer | Exact-commit review against requirements, counterexamples and experimental fairness | Approve its own implementation or silently repair the code under review. |

A person/model may perform different roles in successive tasks, but the author is not the sole reviewer of a critical change. Where feasible, conduct the review in a fresh context with the specification and exact artifact. Different agent labels are not proof of independent judgment.

The coordinator keeps `reports/PLAN.md`: task IDs, dependencies, requirement IDs, owner, branch/worktree, base commit, owned paths, checks and status. Specialists write distinct `reports/workstreams/<task-id>.md` files. Only the coordinator edits shared summary reports, so reporting itself does not become a merge conflict.

## 3. Establish contracts before splitting implementation

The coordinator first translates the practical specification into a dependency graph and commits a small contract baseline:

- Command/result types, identities, revision conventions and error vocabulary.
- Table ownership, migration ordering and transaction entry points.
- Execution broker/launcher boundary and gateway adapter contract.
- Artifact publication/reference interface and evidence-admission interface.
- Test environment naming, common fixtures and configuration/lock ownership.

The baseline must describe actual interfaces needed by the current assignment, not speculative extension layers. During an audit, map the existing contracts first and revise only those that require repair. A signature whose transaction or failure meaning is unclear is not a settled contract. Use focused design comparisons for the ambiguous boundaries, choose one, and record the decision.

Assign one owner for each migration sequence and shared file, including the dependency lock, project configuration and exported types. Other tasks request changes through that owner. The coordinator can reassign ownership explicitly. Do not ask every specialist to independently scaffold the repository or design the database.

## 4. Dependency-aware waves

The table below is the historical S0-S3 build example. For Investigation 01, derive waves from the contracts/domain interfaces, shared state/resource continuation and independent verification/export dependencies in its worker assignment. Historical audit priorities do not commission another audit.

| Wave | Work that can proceed in parallel | Integration condition |
|---|---|---|
| Contract/S0 | Dependency/runtime compatibility probes; schema/transition design; acceptance and experiment design | Coordinator resolves results into committed common contracts and a reproducible environment definition. |
| S1 | Durable state and outbox; broker/launcher/gateway; operator views against the common API; fault-harness work on assigned paths | A real investigation runs through the integrated stack and its effect/restart boundaries are checked. |
| S2 | Artifact persistence; evidence derivations/invalidation; context and continuation using those agreed APIs | A fresh worker resumes correctly, including pending effects and current support. |
| S3 | Capability/trial execution; independently authored task/evaluator fixtures; comparison UI and reporting | A/B/C comparison uses actual integrated behavior with matched information and resources. |

These are candidate partitions, not permission to overlap code ownership. For example, if the evidence task still needs an unsettled artifact contract, settle that dependency before coding the dependent path. A mock enables early consumer work but does not close the integration gate.

The task/evaluator specialist should establish expected outcomes and contamination checks independently of the candidate-method implementation. Everyone may know the experimental design; runtime candidates must receive only their assigned information.

## 5. Worktree and branch protocol

The coordinator alone writes the assigned integration branch, currently `codex/implementation-agenda-01`. Each implementation task gets a unique branch, such as `codex/task-ag01-state`, and a separate worktree created from a recorded integration commit. These are implementation-team task branches, distinct from the later external reviewer branches in `COLLABORATION.md`.

Historical S0-S3 example: after recording and committing the common base, the coordinator could create worktrees with the commands below. For the current assignment use its actual integration branch and unique audit task names:

```bash
git worktree add -b codex/task-s1-state ../Agent-Society-v2-s1-state codex/implementation-s0-s3
git worktree add -b codex/task-s1-broker ../Agent-Society-v2-s1-broker codex/implementation-s0-s3
```

Resolve and record the actual starting commit for each task. Inspect existing branches/worktrees before running an example; reuse an existing task only after examining its state. Each agent's working directory must be its assigned worktree. Never have two writers use the same branch or directory. Git worktrees provide separate checkout state while sharing repository metadata; they are not process or credential sandboxes. [Git worktree documentation](https://git-scm.com/docs/git-worktree)

Give every worktree its own virtual environment, scratch/artifact roots, database or fully isolated test namespace, DBOS namespace, container-name prefix and allocated ports. Shared Git objects do not make shared mutable test databases safe. Preserve actual authentication and isolation boundaries for tests that exercise them; do not treat namespace labels as access control.

The coordinator owns repository-wide configuration, worktree creation/removal and integration. Specialists may commit and push only their assigned task branch. They do not move another checked-out branch, run global cleanup, alter remotes, or force-push. When testing a commit from another branch, use a separate detached review/test worktree rather than changing an active writer's checkout.

Remove a worktree only after its owner has stopped, status is clean, and its commits are integrated or otherwise preserved. Use `git worktree remove` on the verified assigned path; never force removal to dispose of unexplained changes.

If workers run on separate machines, give each its own clone and task branch; local worktrees cannot be shared through the remote. The same ownership, commit and integration protocol applies. If the selected environment cannot run subagents, execute the task graph serially while retaining the contracts and review gates, and report that limitation.

## 6. Every delegated assignment is a concrete contract

Include all of the following in the specialist's prompt:

1. Task ID, outcome and relevant requirement IDs.
2. Exact starting commit, branch and absolute worktree path.
3. Owned files/directories and forbidden shared edits.
4. Required design sections and exact available skills to load, or an explicit statement that no external skill is required. Do not rely on inherited conversation context.
5. Input/output contracts and prerequisite commits.
6. Acceptance checks, including which must use real infrastructure.
7. Expected commit/report deliverables and the next integration dependency.

Require a short finding report when a contract is inconsistent. The coordinator resolves it with affected owners and updates the contract baseline before dependent tasks continue. Routine implementation details remain delegated; material design decisions remain traceable.

## 7. Integration and review gates

1. The specialist completes focused checks, commits its changes, and reports exact tip/base SHAs, modified paths, outcomes and limitations. Pushing a task branch does not mark it integrated.
2. A reviewer examines the exact task tip and the relevant requirements. Critical changes receive a failure-oriented pass: resource races, lost replies, stale authority, invalidated evidence, incomplete artifacts or unfair trial conditions as appropriate.
3. The coordinator integrates one ready task at a time, in dependency order, using a normal merge that preserves task history. Use cherry-pick only for an explicitly selected self-contained patch and record its origin; do not mix strategies casually.
4. Resolve conflicts semantically with the owners. A conflict-free merge still requires integration checks; changed behavior can conflict without touching the same lines.
5. Run the targeted combined checks, then the slice's real end-to-end gate. Any fix changes the tested commit and requires the affected checks again. Record results against the exact integrated revision.
6. Advance the common base and issue the next dependent tasks. Existing tasks incorporate relevant integration changes deliberately; do not rebase or merge an active specialist's branch behind its back.

No self-certified “all green” summaries. The final coordinator verifies the integrated result and distinguishes independently executed checks from inspected reports. Token availability supports more scrutiny; duplicated tests against the wrong environment do not improve confidence.

Complete the current assignment's coverage, fixes and internal review gates before the external handoff. Independently inspect the final integrated behavior and resolve defects that invalidate the assigned functionality or evidence; do not stop after each finding to wait for the design reviewer. A whole-repository audit applies only when the current assignment requests one. Then commit reports and the review request, push the owned integration branch and hand off under `COLLABORATION.md`.

## 8. Resource and scope boundaries

The human's free-token statement applies to implementation effort. Use reasoning, specialist work and review when valuable. It does not remove finite CPU/RAM, database, port or disk capacity, and does not change the autonomous runtime's requirement for explicit resource grants and honest experimental accounting.

An explicitly assigned whole-repository audit may cover older completed slices. An ordinary implementation or bounded correction does not inherit that scope. Record unrelated minor defects without delaying the important current work. Do not implement pending research stages or speculative features merely to occupy additional agents.

## 9. Recurring failures and required counterchecks

These patterns have appeared in prior worker handoffs. They describe failure modes to test, not judgments about an individual worker. Awareness alone is insufficient: select the relevant counterchecks before implementation, run them after integration, and keep the evidence. The current assignment controls which behaviors must be live and which can be doubled.

| Recurring mistake | Required behavior and countercheck |
|---|---|
| Authored answers or fake adapters remain in the supposed live route | Explicit fixture mode only. Poison reference-answer loaders on the solver path; use distinct model outputs and show the public runner submits and grades those exact bytes. A label or model-name flag cannot convert fixture execution into live execution. |
| A retained artifact is merely mentioned, hashed or pasted into a prompt | Follow loaded bytes into the actual computation or accepted decision. Disconnect them and change a behavior-bearing part; show the resulting execution difference. Distinguish executable use from advice interpreted by a model, and both from mere retrieval. |
| Plans, permissions or evaluation bindings are added after the work | Record and validate them before the affected dispatch. A refused plan/binding must cause zero dependent calls. Trace timestamps and operation identities; a graph reconstructed afterward is provenance, not control. |
| Multiple arms exist by name but perform the same stand-in behavior | Review each treatment against its specified information, decision computation, tools and budget. Exercise a distinguishing scenario. A strong baseline must really perform its permitted iterative work; an interpreted-memory arm must actually call the interpreter/model. Ties can be real, but labels cannot establish distinct treatments. |
| Stored experience never reaches the constructor or child | Inspect the final rendered request, not the packet builder alone. Use distinct source, contract, outcome and counterexample contents and verify delivery with their relationships preserved. A digest or inaccessible reference does not satisfy a required input. |
| The parser expects an interface the model was never taught | Supply complete request/response and nested action schemas, execution entry requirements and bounded failure behavior. Test a valid transport specimen through the real parser/invoker. Keep examples free of authored task solutions. Classify malformed output separately from transport/provider failure. |
| Success, receipts or resource usage are filled in with convenient constants | Derive facts from attributable operations and independently checked artifacts. Reconcile a mixed-cost run with retries, checks, shared/replayed operations and cancellation. Missing measurement stays unknown; absence of a receipt is not a zero-cost success. |
| Aggregate cost is copied onto every receipt, or builds/retries vanish from totals | Union by operation identity and sum each operation's own charge once. Include construction, planning, tools, grading, failed attempts and unresolved exposure. Recompute totals independently from the final records and compare with the durable store when available. |
| A budget is checked after spending, or a restart creates fresh allowances | Refuse over-cap effects before dispatch. Recreate the coordinator against the same campaign and verify consumed attempts/liabilities survive. New UUIDs distinguish operations; they do not authorize another campaign or erase spend. Free implementation tokens do not waive experiment limits. |
| A fresh database or resubmitted episode is presented as resume | Stop the original process; continue in the same persistent store with a sentinel and pending/completed operations. Confirm no repeated settled effect and no reconstructed replacement task. Distinguish recovery of ambiguous effects from a proven clean resume. |
| Test cleanup or worktree teardown destroys live evidence | Enforce disposable-purpose and ownership checks before destructive setup. Exercise refusal using an isolated sentinel store. Export and verify required evidence before cleanup; never test deletion protection on surviving live receipts. A naming reminder or memory note alone is not enforcement. |
| Frozen selection, source or schedule silently changes at execution | Execute exact frozen cells/order and verify actual package/config/input identities before effects. Filter the requested phase without rewriting the manifest. Preserve old freezes and as-run records; publish corrections as linked derived evidence. |
| Failures disappear behind fallback, refusal becomes missing evidence, or unknown effects become ordinary failure | Preserve original status, selected/attempted policy, fallback reason, remaining budget and liabilities. Score known settled refusal as specified; do not hide uncertainty. `none` acquisition is valid when established, but does not prove that fallback or transfer ran. |
| Green tests restate the current implementation or reviewers only read reports | For each major claim, include a countercheck that fails if that claim is false: substitution, disconnect, changed observation, stale version, missing pair or exhausted budget. Inspect the actual public entry and critical callers. Do not retire/invert a failing probe without its requirement rationale and replacement coverage. |
| Lane-local success is mistaken for integrated success | Merge serially, inspect the complete combined diff and rerun affected checks against the merged revision. Check producer/consumer schemas, receipt formats, migration manifests, source pins and CLI defaults together. A conflict-free merge can still break behavior. |
| A silent specialist is declared dead and replaced while still writing | Inspect task/process state, worktree and commits. Obtain stand-down or stop the old writer before takeover. One writer per worktree and shared file. Record adopted work honestly; never fabricate a specialist's completion report. |
| Provider diagnosis outruns evidence | Keep the actual request, raw response/finish status and decoded result, with secrets removed. Distinguish authentication, timeout, unfinished reasoning, truncation, empty completion and invalid schema. A successful discovery/prose probe proves only that specific path, not construction readiness. Use bounded discriminating probes instead of repeatedly increasing timeout or budget. |
| Essential drivers and evidence remain only in temporary directories | Check trackedness and run the documented entry/replay in a fresh checkout. Importability alone is not end-to-end reproduction. Keep exact source/config lineage; label reconstructed scripts and lost evidence rather than asserting historical identity. |
| “All green” refers to an older tip, a selected subset, or a retried flake | Record command, tested revision, outcome, exclusions and real/doubled dependencies. Recheck affected behavior after fixes. Keep failed full-suite results with same-revision follow-up evidence; do not silently convert them into a passing full suite. Communicate progress during long runs. |
| One overall ACCEPT hides unrun mechanisms or an implementation gap is mistaken for a negative research result | Report implementation, mechanism execution, live acquisition, behavior change, benefit, transfer and operational qualification separately. A no-acquisition result says nothing about the usefulness of a procedure that never existed; a fixture test says nothing about a live arm not yet connected. |

For each major requirement, the existing workstream report should identify its executable path, observed run/revision, dependency reality and rejecting countercheck. Independent reviewers examine those records and the actual path, rather than duplicating generic whole-repo passes. Prioritize errors that invalidate behavior, authority, persistence or conclusions; log unrelated polish and continue the assigned work. Once applicable checks pass, proceed to the next authorized phase without repeatedly asking the external design reviewer to approve ordinary implementation steps.

### Completion-specific counterchecks from `23a3e68`

- A byte or digest change is not evidence of a behavioral change. Comment stamping fails the latter obligation. Use a behavior-bearing intervention and a cosmetic negative control.
- An authored seed chosen from a fixed registry remains authored. An acquisition claim needs model-produced executable bytes that survive checking, retention and later invocation.
- Inspect the final decision consumer: logging `stop` while an outer loop continues, or recording one selected task while executing another, leaves the learner disconnected.
- Check the persisted learning state, not only elapsed/spend totals: restart must recover observations, capability identities and pending operations. Invented nonempty operation names are not receipts.
- The coordinator cannot accept a cross-lane dependency merely because another lane owns it. Explicitly open entry/accounting findings prevent unconditional integrated acceptance.
- A named repair stage needs an actual repair attempt. Do not manufacture its row by revalidating the initial bytes. Phase caps remain separate even when an overall grant has headroom.
