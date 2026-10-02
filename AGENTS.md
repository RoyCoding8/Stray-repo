# Agent-Society v2 working agreement

## Scope and authority

- This checkout implements the committed Settlement design.
- The human's current assignment takes precedence over historical design notes. The current worker assignment is `WORKER-EC02-AD01-BEHAVIORAL-COMPLETION.md`: finish actual shared execution and the model-driven two-domain development cycle. Review `23a3e68` in `reviews/EC02-AD01-COMPLETION-ASSESSMENT.md`; its C1/C3 and EC02-closure labels are not accepted. EC02 and AD01 retain separate freezes, verdicts and finite authority. Earlier assignments provide unchanged contracts and context, not competing scope or a new whole-repository audit. See `docs/design/REFINEMENT-ROADMAP.md` for maintained stage status.
- Commit and push to the assigned branch are authorized. No force-push, history rewriting, unrelated checkout edits, or automatic merge into another agent's branch.
- The design/review role evaluates results and records findings; it does not take over implementation unless the human requests that change of role.
- Parallel subagents and Git worktrees are authorized for implementation assignments, including Development 02. Follow `IMPLEMENTATION-WORKFLOW.md`; do not ask again for that permission. Each delegation must name its worktree, owned paths, requirement IDs and exact skills/design sections to load. Review available skills and project context, but do not require uncommitted local skills or memories to understand the assignment.

## Work quality

- Preserve the original generality goal across long tasks and handoffs: autonomous discovery, capability acquisition, knowledge/context management and improvement across SWE, mathematics and scientific exploration. Narrow task families are experimental instruments, not the product definition. Before proposing the next batch, apply the generality checkpoint in `docs/design/REFINEMENT-ROADMAP.md`. Do not let repeated SWE hardening displace autonomous development and cross-domain transfer.

- Maintain a task list. Complete meaningful vertical slices and their applicable checks.
- Compact code, clear functions, data-driven repeated structure, no inline comments, no unused abstraction layers.
- Preserve the specified authority, resource, evidence, version and recovery semantics. Complexity is justified by a concrete requirement.
- No execution of candidate code in the trusted host process; no silent unrestricted fallback.
- Report verification boundaries exactly. Fake providers and fake sandboxes do not validate live inference or containment.
- Keep secrets and machine/runtime state outside Git. Commit enough configuration examples, locks, scripts and bounded evidence to reproduce results.

## Collaboration

Read `IMPLEMENTATION-WORKFLOW.md` for team execution and `COLLABORATION.md` for external handoffs. The coordinator alone writes the integration branch; specialists use separate task branches and worktrees. Inspect status first, preserve uncommitted work, use fast-forward-only pulls on your own branch, and never overwrite another owner's branch. Integrate approved task commits with explicit merges and rerun affected checks. Apply review fixes as new commits with the finding IDs they address.
