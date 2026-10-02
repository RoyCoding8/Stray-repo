# Development 01: acquire a method from experience

Continue from the completed R03 implementation. The new assignment is one bounded development episode: observed work -> proposed intervention -> model-constructed executable method -> development checks -> frozen comparison -> scoped disposition -> fresh-worker use or incumbent fallback.

The human wants a working research prototype and useful architectural evidence. Do not start another unrestricted hardening cycle. A negative or inconclusive learning result is acceptable. This task combines systems engineering with bounded experiment-design choices; it does not ask you to invent the full architecture or prove general autonomous improvement.

## 1. Integrate the design packet

Fetch the configured `origin`. Inspect branch/status and preserve all work. The design branch is `origin/codex/development-design-01`, based on implementation `be1730ddcdba33cc40f9349875509626538fb559`.

Use a new coordinator branch `codex/implementation-development-01`, starting from the current implementation lineage, and merge the design branch into it. If that coordinator branch already exists, inspect it and continue without resetting it. Preserve later implementation commits and resolve genuine merge conflicts. Do not write to the design branch or rewrite published history. Use only configured remotes; do not copy endpoint/account identifiers into reports.

## 2. Read the committed inputs

Read these before planning; they are the complete required context even in a new chat:

1. `AGENTS.md`, `COLLABORATION.md`, `IMPLEMENTATION-WORKFLOW.md`: ownership, integration, verification and handoff.
2. `docs/design/REFINEMENT-ROADMAP.md`: whole-project stages and current task list.
3. `docs/design/LEARNING-MODEL.md`: selected mechanism, first episode, DEV-01 through DEV-12, acceptance boundary.
4. `docs/design/GLOSSARY.md`; `REFINED-ARCHITECTURE.md` sections 3.4, 3.7-3.10, 5 and 7; `REPRESENTATION-DESIGN.md` sections 3-7, all in `docs/design/`.
5. `docs/design/PRACTICAL-SPECIFICATION.md`, especially sections 10-11 and existing execution/artifact/evidence requirements. Consult `TECHNOLOGY-DECISIONS.md` in the same folder for stack constraints.
6. `reports/IMPLEMENTATION-STATUS.md`, `reports/VERIFICATION.md`, `reports/DECISIONS.md`, and `reports/workstreams/r03-eval.md`: actual implementation and evidence limits.

Inspect the relevant source and maintained tests, especially `src/settlement/experiment.py`, `capabilities.py`, `trials.py`, `evaluation.py`, `context.py`, `agenda.py`, existing investigation/broker/launcher paths, and `experiments/run_live_abc.py`. Historical worker prompts are completed assignments, not extra current scope. No uncommitted notes, prior chat, local skills or external repository are needed to interpret the requirements.

## 3. Assess, plan and implement

First map every DEV ID to existing behavior, the missing behavior, owned paths and its acceptance check in `reports/PLAN.md`. The design role inspected the default exact-lookup synthesizer and extension hook; independently confirm what they actually do in your checkout. Reuse compliant behavior instead of reimplementing it.

Challenge an incorrect observation or impractical seam with source evidence and a concrete alternative. Resolve ordinary engineering choices yourself. Record material design amendments in `reports/DECISIONS.md` with affected DEV IDs and consequences; do not silently weaken experimental meaning or authority/evidence guarantees. Continue independent work when an external input is missing.

Implement the selected seed policy in `LEARNING-MODEL.md`: a caller-admitted episode, at most two proposed explanations, one diagnostic probe and two constructed candidate versions; finite resource ceilings; development-only candidate selection; frozen protected comparison; subsequent fresh-worker use or fallback. These are ceilings, not obligations to waste calls. A model can return uncertainty or no candidate.

The constructor must use real broker-routed model inference when running live. Package and invoke its output through the existing artifact/capability/launcher contracts. A caller-supplied program or deterministic double proves integration only. Keep the exact-lookup baseline labeled and available. Never run generated construction logic in a trusted host callback.

Use the existing bounded software tasks if they can support meaningful source-group splits. Choose exact tasks, grading, budget policy, finite-panel useful-gain threshold and regression bounds before development. Include varied structures and cases where the method should abstain. Do not require SWE-to-math transfer in this pass. Do not insert a hand-authored general repair algorithm and claim the system acquired it.

Exercise both candidate-release and candidate-rejection paths, using labeled fixtures where necessary. Prove a fresh process can resume after publication without the constructor's scratch or process-local state, and a fresh worker actually consumes the selected artifact's output. Preserve costs, pending effects and exact version identities. Extend the existing operator view sufficiently to inspect the episode; no separate UI project.

Preserve A/B/C and the no-op control. Verify actual usable within-task affordances, not just prompt labels. Charge development and failed candidates honestly, distinguish per-arm comparison costs from the actual cash ledger, freeze policy before development and exact version bindings after development-only selection. Hidden comparison feedback must not silently produce another candidate.

## 4. Parallel work and verification

Parallel specialists in isolated Git worktrees are authorized where tasks are independent. Choose available models and team structure yourself. Establish shared contracts and the task graph first. Each delegation names its DEV IDs, owned paths, exact relevant design sections and available skills to load. If a skill is unavailable, the committed requirements remain sufficient.

Keep one owner for tightly coupled `experiment.py`/development integration. Independent task fixtures, operator presentation and test work can run alongside it once contracts are stable. Isolate databases and runtime resources. The coordinator reviews complete changes and tests each integration; do not have several workers edit the same shared module and reconcile it afterward by guesswork.

Verify the actual entry point with real PostgreSQL and real subprocesses where available, plus explicitly labeled model/runtime doubles. Run focused checks during development and the full integrated suite once the final source is ready. Repeat only after relevant changes or unresolved failures. Record tested source revision, commands, environment, real versus doubled components and outcomes. Commit useful reproducible probes rather than leaving them only in temporary directories.

Run live only with supplied model access, an admitted finite allocation and an appropriate explicit execution profile. Without them, finish implementation and deterministic checks, then report the exact missing inputs and runnable command. An uncontained profile remains explicitly uncontained; scripted fixture success does not qualify arbitrary generated execution. Do not make PostgreSQL 18 or comprehensive recovery qualification an unrelated prerequisite for this slice.

Independently review the assembled slice for broken episode transitions, contamination, wrong-version reuse, unaccounted acquisition, and misleading result labels. Classify remaining issues as experiment-blocking, controlled prototype limitations, or later operational qualification. Fix the first category; document the others without launching an endless general audit.

## 5. Stop and hand back a concrete result

Complete DEV-01 through DEV-12 within verified conditions. Full autonomous agendas, representation languages, adaptive teams, learner self-revision, fine-tuning and production qualification are outside this assignment. More candidates, more files, a simulated win or a self-authored score are not learning evidence.

Update:

- `reports/PLAN.md`: DEV task graph, ownership, integration and checks.
- `reports/DEVELOPMENT-01.md`: question, frozen protocol, grouped tasks, candidates/lineage, complete outcomes, costs, release/fallback, subsequent use and limits. Distinguish live observation from fixture evidence.
- `reports/IMPLEMENTATION-STATUS.md`, `reports/VERIFICATION.md`, `reports/DECISIONS.md`: implemented behavior, exact commands/revisions, amendments and open inputs.
- `docs/design/REFINEMENT-ROADMAP.md`: affected status rows/checklists; do not mark empirical learning done from simulated tests.
- `reviews/REQUEST.md`: request a bounded review of this episode and its experimental interpretation, with specific unresolved questions.

Use the configured private author and committer identity; verify it before committing. Commit additively, push `codex/implementation-development-01` to configured `origin`, verify the remote tip equals local HEAD, and report the SHA with DEV dispositions and evidence limits. Preserve all work before cleaning only your owned temporary worktrees/databases. A blocked live experiment and an inconclusive completed experiment are different outcomes; report which occurred.
