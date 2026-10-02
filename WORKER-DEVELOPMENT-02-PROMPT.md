# Development 02: make experience and context operational

Continue the stage-8 prototype. Preserve the Development-01 machinery. Implement one coherent next slice: actual experience reaches diagnosis/construction through a versioned decision-context packet, then selected behavior is evaluated and used on a separate subsequent task. This is bounded engineering and experiment design, not a full memory platform or a new general hardening pass.

## Integrate and read

Fetch configured `origin` and inspect status/ownership. The design branch is `origin/codex/development-design-02`, based on `e1b95a6119e0c5a3f0c8f67732c2cec8c3e937b0`. Use coordinator branch `codex/implementation-development-02` from the current implementation lineage and merge the design packet, preserving later work. Continue an existing branch safely if it already exists. No reset, history rewrite, or writes to another owner's branch.

Required committed inputs:

1. `AGENTS.md`, `COLLABORATION.md`, `IMPLEMENTATION-WORKFLOW.md`.
2. `docs/design/REFINEMENT-ROADMAP.md` for stage status.
3. `docs/design/MEMORY-AND-CONTEXT.md` for DMC decisions and CTX-01 through CTX-10.
4. `reviews/DEVELOPMENT-01-READINESS.md` and its four characterization probes for D02-001 through D02-004.
5. `docs/design/LEARNING-MODEL.md`, the glossary, existing representation design and practical specification, particularly evidence/context and LEARN-1 through LEARN-9.
6. `reports/DEVELOPMENT-01.md`, existing verification/decisions, and `reports/CONTEXT-PILOT-01.md` for the limited independent model pilot. A synthetic packet pilot is not a replacement for your runtime experiment.

Read current code and relevant tests rather than relying solely on either agent's report. Historical prompts are completed assignments. No old conversation, uncommitted notes, external repository or reviewer-local credentials are required.

## Establish the implementation contract

In `reports/PLAN.md`, map every D02 finding and CTX requirement to existing behavior, missing behavior, owned paths and observable checks. Independently assess each finding as confirmed, partial, rebutted or externally blocked. The probes use explicit store/gateway/lifecycle doubles: a passing characterization probe records a gap, not a database-level proof. Correct mistaken assessments with reproducible evidence. Choose the remedy yourself inside the required semantics.

Keep one coherent episode path. The four required seams are:

- Resolve or execute a permitted development batch before diagnosis/construction; materialize actual inputs, attempted behavior, outcomes, costs and the required response/invocation contract. IDs and family tags alone do not supply experience.
- Use the selected immutable binding as the sole source of candidate behavior. A development rejection must not feed the rejected bytes into `run_abcs` via a closure over the built map.
- Freeze the actual task/access/budget/scoring/stopping/release policy before development feedback; bind candidate/lesson/reference/evaluator versions afterward. Finite-panel rules are sufficient; do not invent inferential certainty.
- After disposition, run a separate subsequent-use assignment through a fresh process. Obtain the candidate or incumbent via normal selection, invoke it, consume its output and record the outcome/cost. Routing or pinning alone does not complete use.

Refactor the existing development/comparison seam only as needed to avoid running the development batch twice or keeping contradictory episode and harness candidate selections. No second workflow engine. Preserve old fixtures as labeled fixtures and maintain useful existing regressions.

## Build the bounded memory/context slice

Implement the three decision contracts in `MEMORY-AND-CONTEXT.md`: diagnosis, construction and continuation. Resolve their required data through existing stores and artifact/evidence checks, construct a bounded model-facing payload, preserve known qualifications/counterevidence and bind the actual delivered bytes to a packet identity and invocation.

Start with a deterministic policy. Return ready, needs-information or stale with the stated meaning. A ready packet must contain the required content or current state; it cannot rely on an unusable list of references. If mandatory content cannot fit, stage/narrow the decision rather than dropping it. Keep token estimates labeled and include serialization overhead/output reserves in the bound.

Revalidate affected evidence routes, artifacts, quarantine and pending operations before consequential use. Preserve valid alternative support routes. A current summary cannot revive retracted support or missing executable bytes. Scope labels come from authoritative records; model-written metadata cannot expose protected evaluation material.

Extend existing context/evidence/continuation/episode records and the existing operator view. Show phase, next decision, packet sources/qualifications/gaps, candidate identity, costs and real subsequent-use outcomes. No new vector database, universal ontology, automatic destructive forgetting, full active-retrieval framework or separate management application.

## Team and checks

Parallel specialists in isolated worktrees/databases are authorized for independent work. Choose models available in your environment. Establish contracts first, give each specialist owned paths, requirement IDs and exact relevant skills/design sections to load, and keep one coordinator responsible for integration. Keep tightly coupled episode/harness changes under one owner. Context materialization, challenge fixtures and operator presentation can be separate lanes only after the interface is stable.

Migrate the four defect probes to intended contracts or replace them with stronger maintained tests and record correspondence. Prove the repaired path through real entry points and PostgreSQL/subprocesses, with explicit model/runtime doubles where needed. Include rejection/no-candidate, stale evidence with an alternative route, known negative evidence, oversized required context, missing bytes and a fresh-process continuation with pending operations. Run focused checks during implementation and the full integrated suite on the final source; repeat when changes or failures justify it.

Use your configured live gateway. The human selected `claude-opus-4-6-thinking` for the reviewer's pilot; use that model for the episode comparison if available, pin the requested configuration and report the response model. If unavailable, identify the needed model choice instead of silently substituting one mid-comparison. Verify discovery, authentication and inference separately.

Freeze live task groups, resource ceilings, expected outcome rules and exposure before running. Keep A/B/C usable affordances matched and account for the common development batch, arm-specific retention construction, failed candidates, context work and subsequent use. Use an admitted finite allocation and suitable execution profile; model access alone does not verify containment or paid billing. Do not copy credentials or private endpoint identifiers into committed reports.

Run one live finite-panel episode if your supplied gateway/allocation/profile permits it. If a required external condition is missing, complete implementation and deterministic checks and state the exact remaining gate with a runnable command. A positive result is not required. Do not tune candidates against protected feedback until they appear to win.

## Handoff and stop rule

Update `reports/PLAN.md`, `reports/DEVELOPMENT-02.md`, implementation status, verification and decisions. Include exact source revision/commands, D02 dispositions, CTX coverage, frozen protocol, all assigned outcomes, delivered-packet and artifact identities, costs, real versus doubled components and remaining conditions. Update the maintained roadmap without marking unrun empirical obligations complete.

Request a bounded review in `reviews/REQUEST.md`: does the revised episode deliver the declared experience, preserve selection and exposure, and execute actual subsequent use? Classify additional findings as experiment-blocking, controlled prototype limitation or later operational qualification. Resolve the first class and document the rest. Full agenda policy, representation invention, adaptive teams, learner self-revision and comprehensive deployment qualification remain later stages.

Use the configured private author and committer identity. Commit additively, push `codex/implementation-development-02` to configured `origin`, verify remote tip equals local HEAD, and report the SHA and evidence limits. Preserve work before cleaning only owned temporary resources. New chats can use this prompt directly; it contains the complete assignment.
