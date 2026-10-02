# Git collaboration protocol

Git carries the specification, implementation and written reviews. The human initiates work by attaching the worker prompt or requesting a review; no scheduler, cross-agent messaging service or automatic polling is required.

## Branch ownership

| Branch | Owner and purpose |
|---|---|
| `codex/architecture-handoff` | Initial design/review handoff. Contains the complete seed specification and worker assignment. |
| `codex/implementation-s0-s3` | Implementation agent. Starts from the seed; receives implementation and review-fix commits. |
| `codex/task-<task-id>` | One implementation specialist per task. Created in its own worktree; integrated only by the coordinator. |
| `codex/review-s0-s3-01` | First reviewer branch, created from the exact implementation commit being reviewed. Contains review findings and any justified design clarifications. |

Increment the review suffix for subsequent passes. The review branch is not a second implementation line. Do not let two agents concurrently write the same branch.

The human authorizes parallel implementation specialists. [IMPLEMENTATION-WORKFLOW.md](IMPLEMENTATION-WORKFLOW.md) defines task contracts, worktrees, isolated test resources, shared-file ownership, internal review and integration gates. This document governs the external implementation/reviewer exchange. The integration coordinator remains responsible for the complete result produced by its specialists.

Before work, inspect the current branch, status and origin, then fetch. On an existing local branch, use a fast-forward-only pull. Divergence is a condition to inspect, not permission for a reset or force-push. Keep commits additive and preserve their provenance.

## Implementation handoff

The implementation agent maintains these files:

- `reports/PLAN.md`: coordinator-owned task graph, ownership, requirement IDs, base commits, branches/worktrees and gates. Specialists use separate `reports/workstreams/<task-id>.md` files.
- `reports/IMPLEMENTATION-STATUS.md`: S0-S3 status, implemented paths, entry points, setup/run commands, remaining work, and environment limitations.
- `reports/VERIFICATION.md`: requirement-to-check map, exact commands, tested source revision, real/fake dependencies, results, reproduction instructions, and experiment method/results. Link bounded evidence files rather than pasting unlimited logs.
- `reports/DECISIONS.md`: material deviations or resolved ambiguities, each with an identifier, affected requirement, reason, evidence and consequence. Record “None” when there are none.
- `reviews/REQUEST.md`: a compact review request using the template below.

After committing those files, push and compare the remote branch SHA with local HEAD. Supply the final SHA to the human. Do not write that reporting commit's own hash into itself: the file can identify the prior implementation tip, and its containing commit identifies the report snapshot.

## Review request template

    Review: S0-S3, pass 01
    Branch: codex/implementation-s0-s3
    Base commit: <seed or last accepted review base>
    Implementation tip: <source commit tested before the reporting commit>
    Requested review scope: <concrete completed slices and unresolved questions>

    Behavior delivered:
    - <observable outcome>

    Verification:
    - <command, environment, result, evidence path>

    Learning experiment:
    - <protocol, budget/exposure policy, result, limitations; or exact blocker>

    Unmet gates:
    - <requirement ID and reason; “None” only when justified>

    Design deviations:
    - <decision IDs; or “None”>

    Reproduce:
    - <setup and run commands, required external inputs>

## Reviewer handoff

The reviewer fetches the implementation branch, records the exact commit under review, and creates a fresh reviewer branch from that commit. It reads the request and verifies the relevant source, tests and evidence. It does not assume a reported test result was independently reproduced.

Write `reviews/REVIEW-01.md` containing:

1. Reviewed commit and scope.
2. Findings with stable IDs such as `R01-001`, severity, requirement, source location, observed failure and expected behavior.
3. Checks independently performed, checks only inspected, and remaining verification limits.
4. Interpretation of the learning evidence, including experimental confounds or unsupported conclusions.
5. Disposition: changes required, acceptable within stated limits, or insufficient evidence to decide.
6. Required next actions, including any proposed change of implementation scope.

Push the reviewer branch and give its SHA to the human. Use new commits for corrections to a published review. If clarification changes the design, update the relevant specification and record why. Do not silently lower an acceptance criterion to match existing code.

## Applying review fixes

The implementation agent fetches and merges the published review branch into its implementation branch without rewriting history. Because the review started from the reviewed implementation commit, this incorporates the findings and design clarifications. Inspect and resolve any conflicts while preserving later implementation work.

Address each finding with new commits, update `reviews/REQUEST.md` and the reports, and list finding IDs with their dispositions. Push the implementation branch for another review. An agent must not mark another role's review “approved”; acceptance remains attributable to the reviewer or human who makes it.

If implementation continues during review, the review still applies only to its recorded SHA. Do not silently treat later commits as reviewed. Prefer pausing at the S3 boundary to avoid that ambiguity.

## Repository content

Commit source, design, tests, dependency locks, migrations, setup instructions and bounded redacted evidence. Keep runtime outputs in `var/`, local secrets in environment/configuration outside tracked examples, and large artifacts in a designated external location with manifests. Do not commit hidden evaluation answers into the runtime candidate's input workspace; repository storage and runtime access are separate controls.
