# Cognitive Batch 02: build temporary teams and test retained coordination

You are implementing the next cognitive slice. Start from `origin/codex/cognitive-design-02`, which contains worker `cb8a62a` plus this design packet. Create `codex/implementation-cognitive-batch-02`. Use `origin` in commands and documentation. Do not record personal remote URLs or credentials. Preserve the repository's private author/committer identity: `Nightjar <nightjar@authors.invalid>`.

The previous representation end-to-end connection is accepted as an implementation milestone. Do not restart its audit. Its actual live acquisition/transfer result remains open. Our foreground moves from stage 8.5 to 8.6; this assignment builds the next important mechanism, not final production infrastructure.

**Live execution is required.** The user confirms that this worker can run live learning experiments and explicitly assigns them in this batch. Use your available gateway and execute the outstanding representation campaign, live Team 01 development/evaluation, and live retained-coordination acquisition/transfer. Do not stop at implemented CLIs, scripted doubles or runnable commands. Completing a live learning experiment does not require discovering a beneficial change; honest negative and no-candidate outcomes are valid results.

## Read and decide before splitting work

1. Read applicable `AGENTS.md`, [roadmap](docs/design/REFINEMENT-ROADMAP.md), [checkpoint](docs/design/COGNITIVE-DESIGN-CHECKPOINT.md), [Team 01 contract](docs/design/TEAM-01-IMPLEMENTATION.md) and [team semantics](docs/design/TEMPORARY-TEAMS.md).
2. Read the existing runtime paths named in the contract. Consult [memory/context](docs/design/MEMORY-AND-CONTEXT.md), [glossary](docs/design/GLOSSARY.md) and [learner revision](docs/design/LEARNER-REVISION.md) where needed. The latter is context, not a second implementation assignment.
3. Map TM-01–08 to concrete commands, artifacts, tables, tests and shared interfaces in `reports/PLAN.md`. Set one owner for shared runtime/schema changes and the integration entry. Record the minimal engineering choices. Resolve contradictions by evidence and document the interpretation; escalate only changes to the scientific question, authority or protected measurement.
4. Agree on the workload ABI, public entry, plan/submission/template schemas, budget mapping and evidence schema before dependent lanes begin. First identify one complete vertical path; no lane is done because its standalone functions are green.

This is **constrained research engineering**, between a mechanical SWE ticket and open-ended architecture design. Semantics, comparison arms, rejection rules and completion conditions are fixed. APIs, fixtures, layout and economical implementation choices need strong engineering judgment. You may simplify implementation while preserving those contracts. Do not substitute a scripted adaptive policy, fake inference, authored solver or local-success tally for the specified behavior.

## Parallel work, with one owner per writable checkout

Use parallel implementation specialists in isolated Git worktrees and branches, with separate test databases. Assign each a bounded contract, owned paths, dependency inputs, relevant repository skills to load, and required evidence. Choose models appropriate to your environment; no particular model nickname is required. The coordinator integrates serially and owns shared contracts. Agents may not write in the same checkout concurrently.

| Lane | Work | Dependency |
|---|---|---|
| T-RUNTIME | TM-01–04: bounded plans, actual dispatch, owned submissions, integration, revision and resume | Shared contracts first |
| T-WORLD | TM-05 and oracle/control portions of TM-08: four-family tasks, protected checker, freeze and trace verification | Can proceed independently against shared ABI |
| T-EXPERIMENT | TM-06–08: honest S/P/T, public entry, template acquisition/transfer and visible status | Skeleton contracts first; final integration after runtime/world |
| R-LIVE | Existing representation acquisition -> retained evaluation -> disposition -> fresh-process use | Independent of Team 01; no runtime redesign |
| T-LIVE | Required live development, model-derived template construction, frozen 48-episode comparison and 24-episode transfer, live continuity/accounting evidence | Own campaign state/evidence; starts after integrated runtime/world/experiment gates |

Parallelize independent work, not shared mutations. A timeout or silent stream is not proof an agent died. Inspect status and its worktree before taking over; ensure one writer remains. Require explicit handoff reports. Integration and targeted cross-seam reviews are mandatory, even if a specialist disappears. Record takeovers honestly.

## R-LIVE: bounded existing experiment

Use `experiments/representation/acquire/experiment.py:run_experiment`, which accepts the configured gateway object for acquisition. Read the existing representation reports and `retention.py` contract. Freeze a campaign manifest with effective model/API configuration, constructor token limits, source SHA, finite grant/profile and candidate slots. Use your available real gateway; discover the environment rather than assuming an old endpoint still works. Verify authenticated inference, not only model discovery. Never commit keys.

Run one complete bounded campaign first. Preserve request/response artifacts with appropriate credential redaction, candidate/retention digests, phase outcomes and all resource accounting. Prove the actual selected bytes reach held-out execution and fresh-process use. If no candidate qualifies, preserve the full no-candidate/fallback result. Do not demand a positive learning result or manufacture one by swapping in authored artifacts. Further campaigns require a separately declared reason and remaining grant; do not search indefinitely for a win.

Remember the current representation scope: A chooses a closed-vocabulary directive; B executes a bounded selector over `ddmin`/`greedy`; C uses retained compositions with explicit transfer lineage. This is scaffolded acquisition. Report what was learned within that space, not unrestricted algorithm invention. The historical authored negative does not substitute for a live acquired result.

An absent local configuration, unseeded internal grant, missing CLI wiring or insufficient preconfigured token timeout is implementation/setup work: resolve it within the authorized finite campaign envelope. Do not recycle an earlier environment's no-gateway report as a current blocker. If an actual external limit remains after checking your current environment, report observed evidence and the specific user action needed promptly while independent work continues; the live obligation stays open. A public acquisition CLI wrapper is permissible if needed for reproducibility; reuse gateway configuration and keep core logic in the existing function. Do not broaden this into provider hardening or expand external permissions or spending authority.

## Required live evidence checklist

Map these IDs into the same plan/report matrix as TM-01–08. Each row needs the actual run/operation/artifact identifiers, observed outcome and evidence boundary. A source inspection or a fixed response vector cannot close a live row.

| ID | Live work to finish |
|---|---|
| LIVE-01 | Authenticate and make a real inference through the actual broker/gateway path; record effective model/API, response status, token usage and configured bounds. Discovery alone is insufficient. |
| LIVE-02 | Complete Representation 01's real acquisition -> frozen retention -> held-out comparison -> disposition -> fresh-process use. Selected acquired bytes must drive the evaluator. Preserve absent-candidate/fallback outcomes, including why any selected-use branch remains unexercised. |
| LIVE-03 | Run Team 01 development with real model planning, child work, context packets, tool feedback and integration. Preserve delivered packet bytes and resulting actions so actual conditioning can be inspected. Exercise one bounded diagnostic with a meaningful interface/input change and one deliberately incompatible combination; distinguish observed sensitivity from a statistical causal claim. |
| LIVE-04 | Construct the optional coordination template from these live development episodes through broker-routed model inference. Validate/execute returned plan bytes, select only using development evidence and freeze at most one template. Do not hand-author the winning template or transplant a scripted fixture. A rejected candidate or no candidate is an allowed measured outcome. |
| LIVE-05 | Execute the frozen 48 S/P/T evaluation episodes and 24 S/cold-T/warm-T transfer episodes using live model work. Use the frozen template where eligible, or recorded cold-policy fallback. Independently recompute both benefit rules and include failed/refused episodes. |
| LIVE-06 | Demonstrate fresh-process template loading and subsequent execution on new inputs when an eligible experimental template exists. Separately restart a development episode after a real child has durably completed; retain that child's actual output and avoid duplicate successful effects. Inject the restart before the campaign freeze or in a separately labeled continuity probe, not selectively into scored runs. |
| LIVE-07 | Reconcile the union of live operations, receipts, usage, settlement, held liabilities and external billing evidence where available. Provider billing unknown remains unknown; internal zero exposure or free access does not erase model/tool consumption. |

Use at most 24 development episodes and 2 template-construction attempts before freezing the single optional template. Diagnostic and continuity episodes count toward that development ceiling; record their special purpose and exclude them from held-out scores. Keep every attempt inside a finite durable root grant with the contract's per-episode bounds and a declared bound for template construction. The existing representation campaign retains its own finite protocol/grant. Do not charge development to an unreported miscellaneous bucket or obtain a new budget after seeing held-out outcomes.

This is live inference-time learning: generating, evaluating and retaining executable behavior for later use. No gradient training or general learner rewrite is required. If no candidate qualifies, execute the specified fallbacks and report that learning benefit was not demonstrated; do not loop until a release appears. Experimental template use follows the frozen trial authority, not production promotion. An unearned released/selected path remains explicitly unexercised rather than being forced for coverage.

Review the historical live-gate list and map each relevant gap to the rows above. Real runsc containment, PostgreSQL 18 and broad deployment qualification remain separate operational obligations: record their actual status, but do not let an unrelated deployment target prevent a valid live campaign on the authorized isolated profile. Resolve a missing suitable execution environment as a real prerequisite, not by claiming a shim provides containment.

## Implementation and experiment workflow

Build and prove one actual task from plan to checked merged artifact before multiplying fixtures. Use deterministic doubles only at declared model seams for mechanism tests. A real child invocation, actual source change and real integration check must appear in the durable trace. Prove a locally successful but incompatible pair fails, then that a corrected combination passes.

On development tasks, calibrate the declared envelope, validate public-feedback access and distinguish tasks that are trivial from tasks that need unavailable context or tools. Freeze the policy, template candidate or explicit absence, exact panel, model configuration and budgets before protected scoring. Then run the complete required live panels using your available gateway and configured grant/profile. Preserve negatives and fallbacks in their denominators.

The main panel is 48 S/P/T episodes. Transfer is 24 S/cold-T/warm-T episodes. These are finite pilot observations. The contract's promising rules decide whether another trial is worthwhile; they do not authorize release or a general superiority claim. If a verified external dependency interrupts live execution, complete independent work and report the affected rows as open/unverified. Do not declare the full assignment complete with these rows silently deferred, or label an unrun experiment a negative result.

## Verification that cannot be skipped

Use requirement-driven checks that can fail when the intended behavior is absent. A path should be exercised through its public entry, not only by constructing final records directly. Check these as a connected system:

- Planning changes which real child operations run; resource limits hold for the complete root, including synthesis and abandoned work.
- Assembled submitted bytes, not an authored stand-in, reach the final evaluator; local green does not bypass integration.
- A fresh process resumes the same durable work after one child completes, without duplicate successful effects. Unknown effects remain explicit.
- Development-derived template bytes affect a later plan on different inputs; unavailable/mismatched templates refuse and fall back. All-abstain still completes honestly.
- The evidence checker independently reconstructs panel membership, outcomes, phase status and costs. Removing a complete pair or changing bindings is detectable.

After serial integration, commission two independent review passes with disjoint emphasis: (1) artifact/information/authority lineage through the complete path and (2) experimental validity, strong baselines and cost attribution. Reviewers must inspect the merged source and execute a behavioral probe, not merely read lane reports. Give them the relevant skills and the contract. Review is focused on this batch, not an endless whole-repository bug hunt.

For an important confirmed defect, fix the responsible shared boundary, demonstrate a failing check against the old behavior, and rerun affected checks on the merge result. If a finding is false, record the concrete rebuttal. Ledger small issues without turning them into completion blockers. Run the full existing suite once after integrated changes settle; subsequent substantive changes require affected checks and a clear statement of which exact tree the full run covered. Do not conceal flakes, skip markers or unrun live gates.

## Deliver and stop

Commit code, fixtures, executable replay, freeze manifests and sufficient raw evidence to independently recompute results. Record `reports/TEAM-01.md`, a separate representation live report, the requirement matrix, decisions and verification boundaries. Update the roadmap and `reviews/REQUEST.md`. Include a short architecture-facing answer: what failed because of organization, what depended on model/task difficulty, what actually persisted, and which observed bottleneck would justify the first learner revision. Do not assert causal failure attribution from one agent's explanation alone.

Push the integration branch fast-forward and verify remote equality. Clean only owned task worktrees/branches and named scratch databases after confirming integration. Do not touch other coordinators' work or rewrite history. Keep all essential scripts in the repository.

Return the commit, exact tested revisions, actual/doubled/external evidence boundaries, LIVE-01–07 dispositions and run IDs, the three separate verdicts (mechanism, team benefit, retained-coordination benefit), the representation live disposition, and the few material remaining dependencies. Distinguish an attempted live branch that produced no eligible candidate from a branch actually exercised with retained behavior. Then stop: another stack rewrite, broad audit, permanent swarm or general learner implementation is not part of this assignment.
