# Agent-Society v2 working agreement

## Scope and authority

- This is a fresh implementation of the committed design, separate from the older Agent-Society repository.
- The human's current assignment takes precedence over historical design notes. The first assignment is `WORKER-PROMPT.md`: S0-S3, followed by review.
- Commit and push to the assigned branch on `the configured repository` are authorized. No force-push, history rewriting, unrelated checkout edits, or automatic merge into another agent's branch.
- The design/review role evaluates results and records findings; it does not take over implementation unless the human requests that change of role.
- Ask before spawning subagents. Review available skills and project context, but do not require uncommitted local skills or memories to understand the assignment.

## Work quality

- Maintain a task list. Complete meaningful vertical slices and their applicable checks.
- Compact code, clear functions, data-driven repeated structure, no inline comments, no unused abstraction layers.
- Preserve the specified authority, resource, evidence, version and recovery semantics. Complexity is justified by a concrete requirement.
- No execution of candidate code in the trusted host process; no silent unrestricted fallback.
- Report verification boundaries exactly. Fake providers and fake sandboxes do not validate live inference or containment.
- Keep secrets and machine/runtime state outside Git. Commit enough configuration examples, locks, scripts and bounded evidence to reproduce results.

## Collaboration

Read `COLLABORATION.md` before pulling another agent's changes or sending work for review. Inspect status first, preserve uncommitted work, use fast-forward-only pulls on your own branch, and never overwrite the other role's branch. Apply review fixes as new commits with the finding IDs they address.
