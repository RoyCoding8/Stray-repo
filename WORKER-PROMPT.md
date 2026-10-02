# Initial implementation assignment: Agent-Society v2

You are the implementation engineer for this project. The human has chosen this private Git repository as the collaboration channel between you and an architecture/review agent:

`the configured repository`

Implement the assignment below, verify it, make coherent commits, and push your branch to this origin. Commit and push are authorized; do not ask for confirmation again. Work only in this v2 checkout. No access to the older Agent-Society checkout, another conversation, or uncommitted design files is required.

## 1. Start here

Read `AGENTS.md` and `COLLABORATION.md`. Confirm the checkout's origin and inspect its status before changing anything. Fetch origin. The seed design is on `origin/codex/architecture-handoff`. For the first implementation, create `codex/implementation-s0-s3` from that seed. If that implementation branch already exists, inspect and continue it rather than replacing its history. Preserve any existing work; never reset, clean, or force-push to make the checkout match your expectations.

All required design documents are committed under `docs/design/`. Read them in this order:

1. `README.md` in the repository root: scope and file map.
2. `docs/design/GLOSSARY.md`: precise vocabulary.
3. `docs/design/REFINED-ARCHITECTURE.md`: purpose, mechanisms, abstract semantics, invariants, failure cases and experimental obligations.
4. `docs/design/REPRESENTATION-DESIGN.md`: the selected representation contracts.
5. `docs/design/TECHNOLOGY-DECISIONS.md`: selected technology, primary sources, assumptions and limits.
6. `docs/design/PRACTICAL-SPECIFICATION.md`: normative implementation requirements and acceptance gates.
7. `docs/design/REFINEMENT-ROADMAP.md`: design history and open empirical obligations.

The old constitution and D1-D82 appear only in a historical replacement map. They are not missing dependencies or additional binding constraints. References to the earlier no-implementation design pass describe its provenance. This assignment authorizes implementation in this repository.

## 2. The outcome

Build S0-S3 from the practical specification: a functioning first learning system, with the relevant operator interface and real verification. Stop at the S3 review boundary after pushing the implementation and evidence. Do not expand into S4-S7 during this assignment unless the human explicitly changes its scope.

The system should let a temporary worker perform a bounded investigation, preserve what happened, resume through a fresh worker, develop and retain an executable method, and test whether that retained method benefits independently selected tasks. Software diagnosis is the first proving ground; the architecture remains general.

A collection of placeholders, interfaces, fake workers and simulated successes does not satisfy this assignment. Simulations are useful for deterministic tests and may demonstrate the pipeline, but their results must remain labeled as simulated. Actual learning claims require the corresponding real experiment.

## 3. Required slices

- **S0:** reproducible dependency/image manifest, configuration and explicit grants, database constraints/migrations, admitted execution profile, and separate gateway discovery/authentication/inference checks.
- **S1:** a real bounded investigation loop, domain transition protocol, operation identities, reservation and settlement, durable workflow recovery, and usable operator inspection/control.
- **S2:** immutable artifacts, grouped evidence derivations, current invalidation, constructed context with provenance, and fresh-worker continuation with unresolved effects preserved.
- **S3:** executable candidate packages, frozen candidate/reference trials, attributable results, scoped release and actual method reuse; run the A/B/C comparison specified in section 11 of the practical specification when the environment permits it.

Use the selected Python/PostgreSQL/DBOS foundation, controlled gateway transport and gVisor execution profile. Implement the narrow runtime contracts required for these slices. Keep the first composition interpreter small while preserving the chosen semantics. Generated code must not run in the trusted application process.

Do not downgrade generated execution to an unrestricted subprocess when a sandbox is missing. Do not substitute an in-memory store for the required durability and concurrency tests. Preserve current authority checks even when an attempt pins an older capability version.

## 4. How to work

Maintain a task list and implement coherent vertical slices. Make routine implementation choices yourself. Use compact functions and meaningful database constraints. Avoid inline comments, duplicated logic, generic wrapper layers, unused extension points, and tests that merely repeat implementation expressions. Keep operator wording truthful and specific.

Follow the substantive design unless a concrete contradiction, dependency incompatibility, or measured failure requires a change. Record such a change with the affected requirement, evidence, selected alternative and consequence in `reports/DECISIONS.md`. Do not silently rewrite a requirement to make a failing test pass. For an unresolved material conflict, finish independent work and leave a precise question in the review request.

Check primary documentation for the actual locked dependency versions. Do not assume every API in current online documentation exists in an older package pin. Commit the tested lock, runtime/image metadata, and reproducible setup instructions. Do not copy source code or development databases from the old project.

Subagents require the human's permission first. They are not necessary to complete this assignment. An unavailable optional plugin or skill is not a reason to abandon otherwise feasible implementation; use the committed specification directly.

## 5. Gateway, resources and unavailable infrastructure

The human will supply an external inference endpoint; do not build a multi-provider gateway service. Implement its narrow adapter contract, configuration, typed errors, deadlines, request attribution and usage accounting. Fake adapters are permitted in tests. Do not invent credentials or report a simulated response as live inference.

You may build and verify everything independent of the live endpoint before it is available. Likewise, an unavailable Linux/gVisor environment is an unverified integration gate, not a reason to weaken isolation or claim containment was tested. Make the remaining setup and exact commands reproducible for the human or reviewer.

Live API expenditure requires a configured endpoint and an explicit resource grant supplied for that run. A grant must cover the actual billable exposure; usage estimates alone do not establish a hard monetary ceiling. Do not ask for these inputs until there is a concrete run ready and independent work is complete. A missing input must be stated specifically.

## 6. Verification and experiment

Map applicable requirement IDs to actual checks in `reports/VERIFICATION.md`. Include exact commands, tested revision, environment versions, outcomes and limitations. Distinguish static/unit, real Postgres, real sandbox, live gateway, recovery and learning tests.

Exercise concurrency and failures at the actual boundaries. In particular: last-unit reservation races; duplicate commands and receipts; stale ownership; a broker crash after sending; domain commit before workflow checkpoint; evidence retraction racing release; artifact publication failure; and cancellation while an external outcome is unknown.

The A/B/C experiment compares ordinary baseline behavior, retained textual lessons, and retained executable methods. Permit equally strong within-task tool use, match total resources and task exposure, include acquisition costs, and keep final evaluation tasks independent of development examples. A fresh worker must actually invoke the retained method. Report regressions and inconclusive outcomes. Do not alter the test after seeing which arm wins.

Finite-panel observed gains are sufficient for a limited experimental release if its obligations hold. They do not justify a general statistical superiority claim. A failed learning hypothesis is a legitimate result; fixing the experimental result by hiding failed cases is not.

## 7. Commit, report and push

Make reviewable commits as coherent slices stabilize. Use specific commit messages. Commit implementation, migrations, tests, lock files, documentation and suitably sized reproducibility evidence. Exclude credentials, local environment files, database contents, caches, sandbox scratch and bulk run output. A private repository is still the shared source and evidence channel, not the runtime data directory.

Complete `reports/IMPLEMENTATION-STATUS.md`, `reports/VERIFICATION.md`, `reports/DECISIONS.md` and `reviews/REQUEST.md` according to `COLLABORATION.md`. The review request must identify the seed/base commit and implementation tip, summarize changed behavior, list unmet gates and give exact reproduction commands. Never claim the final reporting commit's own hash inside that same file; use the implementation tip and supply the final pushed HEAD in your final response.

Push `codex/implementation-s0-s3` to origin with its upstream configured. Verify the remote branch points to your final local commit. If transport/authentication prevents pushing, preserve all local commits and report the exact failure; do not fabricate publication.

Your final response must include: remote branch, final pushed commit, completed slices, verification performed, experiment result or exact blocker, and remaining material issues. Then wait for review at the agreed S3 boundary. Future revisions will arrive through commits and the review protocol.
