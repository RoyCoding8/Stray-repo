# Worker assignment: Agenda 01

Implement and test the next cognitive slice: durable investigation choice, evidence-qualified continuation, stopping and wakeup. The design starts from the closure tip `913bda791bd0fb3cf87c568fb57daea17fe4a240`. This assignment supersedes the completed whole-repository engineering/closure assignments for new work. Preserve their evidence and implemented contracts.

## Read and orient

Read these committed files first; no old chat, private machine memories or external skill installation is needed to understand the assignment:

1. [Roadmap](docs/design/REFINEMENT-ROADMAP.md): stage 8.4 is the next slice; final implementation is stage 12.
2. [Implementation contract](docs/design/AGENDA-01-IMPLEMENTATION.md): AG01-01 through AG01-12 are required.
3. [Experiment protocol](docs/design/AGENDA-EXPERIMENT-01.md) and [agenda policy](docs/design/AUTONOMOUS-AGENDA.md).
4. [Closure assessment](reviews/ENGINEERING-CLOSURE-ASSESSMENT.md), [compatibility mapping](reviews/COGNITIVE-DESIGN-COMPATIBILITY.md), and the current [verification record](reports/VERIFICATION.md).
5. [Working agreement](AGENTS.md), [implementation workflow](IMPLEMENTATION-WORKFLOW.md), and [collaboration protocol](COLLABORATION.md).

Inspect the runtime seams named in the implementation contract and the relevant migrations/tests before selecting concrete interfaces. Consult the glossary and practical specification where those seams depend on authority, evidence or execution definitions. The later representation/team/learner drafts are context, not additional implementation assignments.

## Integration and ownership

Work on `codex/implementation-agenda-01`. Fetch the design branch `codex/agenda-design-01` from the configured `origin`, inspect it and integrate its packet explicitly before implementation. For a fresh checkout, start the new implementation branch from that design tip. For an existing checkout, preserve all current work and use a separate worktree; do not reset or stash another task's work. If the implementation branch already exists, inspect and continue it rather than recreating it.

The coordinator alone writes the integration checkout and shared reports. Use parallel specialists in distinct task branches/worktrees when dependencies permit. Their prompts must name owned paths, requirement IDs, agreed interfaces, database/artifact/DBOS namespaces and the exact available skills/design sections to read. Each active lane has one writer. A timeout or silent stream is not proof an agent died: verify ownership and stop or release the old writer before takeover. Never have a replacement and original worker write concurrently.

Commit with private identity `Nightjar <nightjar@authors.invalid>` for both author and committer. Use the configured `origin`; do not add personal repository URLs, account identifiers, credentials or machine state to reports. Push your implementation branch normally and verify the remote tip. Never force-push, rewrite history, update the design branch or merge into another owner's branch. No reviewer-specific model name or model restriction is imposed on your implementation team.

## Plan before parallel work

Maintain `reports/PLAN.md` with dependencies, requirements, owned paths, base commits, exact checks and status. Commit the common contract baseline first: tables/migration owner, command types, transaction ownership, option/probe/replication identities, evidence input shape, cost recording, policy observation grammar and experiment boundaries.

Suggested independent lanes after that baseline:

| Lane | Scope | Integration obligation |
|---|---|---|
| State/admission | Durable options, dispositions, versions, attempt links, atomic funding and recovery | AG01-01–04, 07, 09; demonstrate no nested transaction deadlock or orphaned intermediate state. |
| Policy/wakeup | Shared rotation, R/Q, continuation rules, typed wake conditions, cursor | AG01-05–08; work against the common public input, without latent fixture state. |
| Experiment/validation | World fixtures, grader, manifest, independent accounting checker and adverse tests | AG01-10–11; independently review policy information access and whether the controls can fail. |
| Operator/demo | Existing UI/read surface and one reproducible CLI path | AG01-12; no new management service or generic dashboard framework. |

These are ownership suggestions, not a required number of agents. Resolve shared-file conflicts through the coordinator. A reviewer should inspect the exact integrated contracts and experimental fairness in a fresh context. The coordinator remains responsible for the assembled system and must not present branch-local tests as merged verification.

## Execute in gates

1. **Contracts:** implement the smallest necessary extension to the existing store/agenda/broker. Record consequential choices in `reports/DECISIONS.md`, including transaction boundaries, recoverable intermediate states and policy grammar. No new scheduler service, general rule DSL, model calls or production capability release path is needed.
2. **Vertical demonstration:** on real PostgreSQL, demonstrate proposal, funded admission, evidence-linked continuation, refusal, dormancy and fresh-process wake/resume. Include pending effects and the accounting/ownership consequence of stopping. Use trusted deterministic adapters.
3. **Mechanical acceptance:** prove AG01-01–12 with meaningful tests, including races and interrupted processes. Preserve failing-before-fix evidence when repairing a discovered defect. Do not replace real seam tests with a parallel toy implementation.
4. **Freeze:** complete and commit the executable 32-world manifest, two opposite tie orders, R/Q policies, numerical recovery/evaluation allowances, checkers and all source/configuration identities. Validate public/privileged data separation, costs and positive/negative controls before scoring. Record diagnostic fixtures separately.
5. **Comparison:** run all 128 durable trajectories under the frozen protocol. Preserve all results, including Q regressions, incomplete work and unresolved liability. The assignment succeeds with an honest negative result. A post-score apparatus correction requires a new version and complete rerun, not selective repairs to unfavorable rows.
6. **Integrated verification and interpretation:** run affected checks after each merge, then the full existing suite on the final source tree. Report real versus doubled boundaries, exact source and commands. Apply the protocol's descriptive merit criterion without turning authored simulation into a general learning claim.

Budget accounting must reconstruct from durable records, not a report-only counter. Decision retries cannot advance the cursor twice. A fresh probe slot must not escape lineage caps; a legitimate frozen replication slot must not be suppressed as a transport retry. Horizon closure must preserve pending liabilities and must not feed late observations into the scored end-use answers.

Use aggressive engineering scrutiny within this slice: vary ordering and failure timing, follow input-to-effect paths across modules, inspect negative/unknown/stale states, invalidate evidence between reads and use, compare uninterrupted and resumed traces, independently reconcile resource totals, and try to make the comparison unfair in both directions. Check whether the qualifier merely recognizes an author-provided answer label. Inspect the complete affected dependency path when a local fix changes a contract. The earlier [engineering-review techniques](WORKER-ENGINEERING-REVIEW.md) remain useful; this is not a new mandate to repeat the entire historical audit.

## Reports and completion

Create `reports/AGENDA-01.md` with:

- A short implementation explanation and concrete schema/API mapping to AG01 requirements.
- The frozen manifest location/revision and exact replay, checker and demo commands.
- All pair/family/tie-order results, resource vectors, waiting measures, failures and pending liabilities; verdict and its limits.
- An evidence map identifying real PostgreSQL/process checks and simulated observations; source revision and full-suite result.
- What the result supports changing, retaining or studying next. Do not select representation invention, teams or learner revision merely because agenda mechanics pass.

Update the roadmap, implementation status, verification record and review request. Reconcile stale current-summary rows in `reports/ENGINEERING-REVIEW.md`: the closure suite is 590, old duplicate INVA-06/07 entries and superseded INVA-03/04/05/INVB-13 dispositions need one authoritative current mapping, and the active docs/reports coverage row needs an explicit checked disposition. Preserve attributable historical reports; do not rewrite old failures as passes. This small maintenance task is part of integration, not a reason for another closure assignment.

Before cleanup, preserve the manifest, bounded machine-readable traces, operation/reservation/accounting evidence and independent checker needed to reproduce the verdict. Remove only your clean, integrated task worktrees and your isolated scratch databases/artifacts. Leave unrelated reviewer worktrees alone. Report the final pushed branch/SHA, verification, experiment result and remaining qualifications.

You have enough information to choose concrete engineering details and complete this assignment. Ask only for a consequential unresolved contradiction or external dependency. Q need not win; it must receive a fair, reproducible test.
