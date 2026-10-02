# Parallel implementation workflow

The human authorizes parallel subagents and Git worktrees for implementation. The current handoff is [Agenda 01](WORKER-AGENDA-01.md); earlier audit and S0-S3 examples below are historical. Its coordinator owns `codex/implementation-agenda-01`, and its contract controls scope, requirements and gates. Token expenditure is not a reason to avoid useful design comparisons, adversarial review, or investigation. Concurrency should follow independent work and available execution resources. Do not invent busywork to fill agent slots.

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

The table below is the historical S0-S3 build example. For Agenda 01, derive waves from the state/admission, policy/wakeup, experiment/validation and operator dependencies in its worker assignment. Historical audit priorities do not commission another audit.

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

Complete the current assignment's coverage, fixes and internal review gates before the external handoff. For the whole-repository audit, independently inspect the final integrated behavior and resolve discovered defects across all priorities; do not stop after each finding to wait for the design reviewer. Then commit reports and the review request, push the owned integration branch and hand off under `COLLABORATION.md`.

## 8. Resource and scope boundaries

The human's free-token statement applies to implementation effort. Use reasoning, specialist work and review when valuable. It does not remove finite CPU/RAM, database, port or disk capacity, and does not change the autonomous runtime's requirement for explicit resource grants and honest experimental accounting.

The current audit covers all existing first-party functionality, tests, operations and active documentation, including older completed slices. It does not authorize implementing pending research stages or speculative features merely to occupy additional agents. Its ranked priorities sequence the work; they do not exclude lower-priority repair.
