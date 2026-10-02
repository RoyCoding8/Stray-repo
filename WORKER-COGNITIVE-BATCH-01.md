# Worker: agenda closure and representation acquisition/transfer

This is a combined implementation assignment suitable for a new chat. Finish the three bounded agenda acceptance gates and build Representation 01. You may develop them in parallel. The architecture/design role has advanced the next slice so you need not return after every small correction.

## Start and integration

Use the repository already cloned in your environment and configured remote `origin`. Fetch `origin/codex/representation-design-01`. Its base includes worker revision `051811fd59ab6d1de0f85a1be8849e94b638ebf5` and the three-gate assessment at `55df063`. The design branch changes documentation only after that base.

Inspect status and ancestry before integration. Preserve any current implementation work; use normal additive merges/commits, never reset or rewrite it. If the earlier three-gate assignment is already underway, retain that work and evidence rather than restarting it. Create owned integration branch `codex/implementation-cognitive-batch-01` from your latest applicable implementation plus this design packet; record the exact merge/base in `reports/PLAN.md`. Do not move or edit another task's checkout. Push the combined result there and verify remote equality. Use private author and committer `Nightjar <nightjar@authors.invalid>`, configured remote names and no credentials in Git.

Read in this order:

1. [Roadmap](docs/design/REFINEMENT-ROADMAP.md): stage 8.4 closure plus stage 8.5 first prototype; final infrastructure is later.
2. [Three agenda gates](WORKER-AGENDA-01-THREE-GATES.md) and its linked assessment/probe/contracts. All AGR2 requirements remain in force.
3. [Representation 01 implementation contract](docs/design/REPRESENTATION-01-IMPLEMENTATION.md), including its claim limits, finite budget and freeze sequence.
4. [Representation semantics](docs/design/REPRESENTATION-AND-TRANSFER.md), [learning model](docs/design/LEARNING-MODEL.md), [research notes](docs/design/COGNITIVE-RESEARCH-NOTES.md), and the affected runtime interfaces.
5. Existing repository instructions, implementation workflow, current decisions and verification reports. Historical reports are evidence with dates, not overrides of this assignment.

This combined prompt supersedes the earlier prompt's branch destination and exclusion of representation work. It does not relax its three gates or authorize all other cognitive drafts.

## Work graph and parallel lanes

First inspect the actual interfaces and write the shared JSON/profile, source-oracle and evidence record contracts, requirement/path ownership and dependency graph in `reports/PLAN.md`. Verify that these contracts allow the authored end-to-end path before assigning independent implementations. This is an engineering design task with constrained research choices, not transcription of fully specified code.

Parallel specialists are authorized. Choose models according to task difficulty and availability; no reviewer-side model naming constraint applies to your environment. Each specialist gets explicit requirements, owned paths, relevant local skills, its own worktree/branch and isolated database. The coordinator alone integrates and edits shared reports. Never have two active writers in a worktree. A silent stream is not proof that a writer has stopped; establish ownership before a takeover.

| Lane | Owns | Can start when | Completion boundary |
|---|---|---|---|
| A: agenda | AGR2-01/02 shared driver, time and resume semantics; AGR2-03 freeze/checker | Immediately after integration | Short gates, worker-side independent review of actual paths, then one corrected preserved full panel. |
| B: source instruments | RPR-01; software/graph fixtures, independent source checkers, baseline reducers, development/split generators | Shared contracts recorded | Small exhaustive checker cross-checks; fidelity and signal controls; no inspection of final outcomes to improve the generator. |
| C: representation execution | RPR-02/05/07; package profile, core/adapter runner, durable step state, incumbent and operation/receipt linkage | Shared contracts recorded | Authored package through real runtime; genuine process resume; invocation and scope view. |
| D: acquisition and experiment | RPR-03/04/06/08; construction contexts/lineage, transfer freeze, A/B/C runner, evidence checker and report | Shared contracts recorded; can use explicit fixtures until B/C merge | Integrated deterministic run, then one bounded live campaign if prerequisites exist; honest disposition and fresh-process use. |

B/C/D proceed without waiting for agenda policy acceptance: Representation 01 is explicitly admitted, not selected by the autonomous agenda. Within representation work, B and C unblock D's integrated run. A need not finish its full panel before that run if it has no shared-runtime impact. Any changes to shared store, broker, gateway, artifacts, capabilities, migrations, global tests or UI go through one coordinator-designated owner, with dependent lanes waiting for that commit instead of duplicating changes. Merge shared changes before their dependent acceptance runs. Resource-heavy panels may run sequentially to avoid timing distortion even when implementation is parallel.

Do not split by arbitrary file counts or create seven speculative frameworks to occupy workers. Split by independently testable contracts. The coordinator can perform a lane directly. Inspect each branch's full affected diff and real execution evidence before merge; an agent's reported success is not enough. Correct integration defects in traceable commits and rerun affected checks on the merged source.

## Priorities: complete all in scope, not just the first priority

**P0: preserve interpretability.** Real operations/receipts, correct witness identity, split isolation, frozen staged component bytes, finite exposure and continuity. Refute your own happy path: ask what observation would look successful if the real mechanism were bypassed. Verify actual calls, flags and database identity. Never promote injected fixture bytes to live inference evidence.

**P1: make both experiments executable.** Close AGR2 with a corrected panel; integrate the representation authored path and bounded actual acquisition/transfer. Give baselines the same public instruments and honest native implementations. A zero-gain result is complete if its evidence is interpretable.

**P2: finish operational usability within the experiment.** Reproducible committed commands/manifests, intelligible operator state, real restart, persistent disposition and future selection/fallback. Treat missing live access as an explicit gate and complete independent deterministic work. Never claim containment, paid billing or a release path from a double.

**P3: documentation and cleanup.** Reconcile requirement evidence, source revisions and limitations; retain only appropriately scoped historical claims; remove your own disposable resources after evidence is preserved. Leave other tasks' worktrees untouched.

All four priorities are part of this assignment. Existing unrelated production-hardening ledger items stay ledgered; do not restart a whole-repository hunt. Fix incidental defects that block these paths, with targeted regressions. Record unrelated findings for later.

## Decisions you may make and when to stop

Choose schemas, module boundaries, named entry layout, small fixture semantics, concrete manifests, narrowly needed migrations and test organization. Preserve the contract's meaning and record consequential decisions. Prefer existing primitives and compact code. No universal interpreter, dependency graph service, new scheduler or general plugin framework is required.

Before expensive execution, have a worker-side reviewer inspect the actual short gate paths and representation fidelity controls. You do not need to wait for the architectural reviewer to perform that review. Use meaningful red-capable regressions; do not preserve probes whose only assertion is an obsolete limitation. Record replacement correspondence.

Before live construction, record the finite model/provider/grant configuration and phase-specific exposure controls required by the contract. Use the authorized available gateway without guessing credentials or committing them. Never silently raise a budget after seeing failure. If blocked, finish the deterministic batch and give the exact missing prerequisite plus a runnable command. No fabricated model candidate or forced release.

The following require a reported architectural decision rather than silent implementation: changing the witness task, exposing transfer data before core freeze, allowing the adapter its own oracle-driven search, redefining the benefit baseline, altering core bytes while claiming unchanged-core transfer, or replacing durable execution with an in-memory-only harness. Preserve a minimal example and propose a bounded alternative. Routine engineering choices do not require another round trip.

## Final evidence and handback

Update `reports/PLAN.md`, `reports/AGENDA-01.md`, `reports/REPRESENTATION-01.md`, `reports/VERIFICATION.md`, `reports/IMPLEMENTATION-STATUS.md`, `reports/DECISIONS.md`, `reviews/REQUEST.md` and the roadmap. Cross-link detailed lane reports rather than repeating all transcripts. Keep the engineering ledger synchronized only for affected entries.

Run the affected checks after each integration and the full suite once on the final code. Record exact tested revisions, component profiles, real/doubled boundaries and any later changes. If a known unrelated timing flake appears, preserve its failure and focused follow-up honestly; do not rerun a large suite merely until green. The agenda and representation finite experiments each need their own complete checked evidence; suite counts are not substitutes.

Hand back the pushed SHA, clean/remote-equal status, a table for AGR2-01–03 and RPR-01–08, the two experiment verdicts, and the distinct representation verdicts in contract section 1. State what was supplied, what the model constructed, whether the core actually transferred, what C used, all acquisition/reuse costs and why later use selected a composition or the incumbent. If no useful acquisition is shown, say so plainly and identify the smallest next discriminating experiment. Do not start it automatically.
