# Agent-Society v2 working agreement

## Scope and authority

- This checkout implements the committed Settlement design.
- The human's current assignment takes precedence over historical design notes. The current assignment is `WORKER-DEVELOPMENT-01-PROMPT.md`; `WORKER-PROMPT.md` and numbered review prompts describe earlier assignments. See `docs/design/REFINEMENT-ROADMAP.md` for maintained stage status.
- Commit and push to the assigned branch are authorized. No force-push, history rewriting, unrelated checkout edits, or automatic merge into another agent's branch.
- The design/review role evaluates results and records findings; it does not take over implementation unless the human requests that change of role.
- Parallel subagents and Git worktrees are authorized for implementation assignments, including Development 01. Follow `IMPLEMENTATION-WORKFLOW.md`; do not ask again for that permission. Each delegation must name its worktree, owned paths, requirement IDs and exact skills/design sections to load. Review available skills and project context, but do not require uncommitted local skills or memories to understand the assignment.

## Work quality

- Maintain a task list. Complete meaningful vertical slices and their applicable checks.
- Compact code, clear functions, data-driven repeated structure, no inline comments, no unused abstraction layers.
- Preserve the specified authority, resource, evidence, version and recovery semantics. Complexity is justified by a concrete requirement.
- No execution of candidate code in the trusted host process; no silent unrestricted fallback.
- Report verification boundaries exactly. Fake providers and fake sandboxes do not validate live inference or containment.
- Keep secrets and machine/runtime state outside Git. Commit enough configuration examples, locks, scripts and bounded evidence to reproduce results.

## Collaboration

Read `IMPLEMENTATION-WORKFLOW.md` for team execution and `COLLABORATION.md` for external handoffs. The coordinator alone writes the integration branch; specialists use separate task branches and worktrees. Inspect status first, preserve uncommitted work, use fast-forward-only pulls on your own branch, and never overwrite another owner's branch. Integrate approved task commits with explicit merges and rerun affected checks. Apply review fixes as new commits with the finding IDs they address.
