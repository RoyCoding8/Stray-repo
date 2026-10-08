# Agent-Society folder dispositions, updated 2026-10-08

Current registration is one checkout and one local branch, codex/agent-society.
The temporary RSI review worktree was removed. Nine obsolete remote branch
snapshots were preserved as archive/retired-2026-10-08 tags on both remotes
before deletion. Origin's older default branch remains for clone compatibility.
The Oct-6 diagnostic roots under the canonical checkout are now absent. The
privacy snapshot still exists and remains archived. Five empty .worktrees
folders remain: automatic approval review again blocked their removal. The
old lane brief was copied into the Oct-8 archive. Sizes below are historical.

Scope: Agent-Society-related folders under D:/AI, not a whole-disk audit.
Sizes are rounded MiB of file contents. Reparse points were not traversed.
The original size census inspected codex/agent-society at e8e7911e;
the current repair/handoff supersedes its worktree-status observations.

Archive update: 44 diagnostic/snapshot source roots are preserved in
`D:/AI/Agent-Society-archives/2026-10-06/diagnostics-and-snapshots.zip`, with a
verified per-file manifest beside it (5,707 files, 157,137,456 source bytes).
Automatic approval review blocked deletion, so the source folders listed
below remain, except D:/AI/s09o, now absent. VKit is separate and is outside
this task's scope. Completed CI work is consolidated into the canonical branch;
the interrupted construction-budget patch has a recovery tag, not an active
worker checkout. This handoff removes the task's temporary `ci-*` worktrees.

## Keep

| Absolute path | Size | Why |
|---|---:|---|
| D:/AI/Agent-Society-v2 | Canonical checkout | Current source, tracked experiments/evidence, and untracked worker artifacts. |
| D:/AI/Agent-Society-v2/.git | 31.4 MiB | Shared Git history and recovery refs. Before this review: 294 reachable commits, 3 local branches. |
| D:/AI/Agent-Society-v2/.venv | 65.0 MiB | Working Windows Python 3.13.14 environment used for the review gate. |
| D:/AI/Agent-Society | 1.9 MiB | Separate older master history at 2d7ec8fb and untracked .unsnooze material; this chat's cwd. Not a redundant registered v2 worktree. |
| D:/AI/Agent-Society-archives | 63.2 MiB | History recovery bundles and archived reports. |
| D:/AI/Agent-Society-worktree-archives | Less than 0.1 MiB | Historical archive metadata. |

Only Agent-Society-v2 is the current development checkout. The other keep
entries protect history or local material, rather than being active workers.

## Stale or historical material requiring preservation first

| Absolute path | Size | Disposition |
|---|---:|---|
| D:/AI/s09o | Formerly 77.0 MiB | Absent as of this handoff; its pilot material and snapshots are in the verified diagnostics-and-snapshots archive. |
| D:/AI/Agent-Society-v2-privacy-20260910 | 0.7 MiB | Verified archive copy exists; source removal was blocked by automatic approval review. May be removed manually while retaining the archive. |
| D:/AI/Agent-Society-v2/.a53* | Formerly 71.1 MiB combined | Absent on Oct-8; verified archive copies remain. |
| D:/AI/Agent-Society-v2/.ci-read | Formerly 0.6 MiB | Absent on Oct-8; verified archive copy remains. |
| D:/AI/Agent-Society-v2/.scratch | Formerly 0.5 MiB | Absent on Oct-8; verified archive copy remains. |

Do not delete untracked supersession sidecars or evidence directories simply
because Git reports them untracked. This review did not establish their
redundancy. No historical evidence was altered or discarded.

## Empty worktree directories

D:/AI/Agent-Society-v2/.worktrees/e3, hang, m2decide, roots and w0-relay
are empty, have no .git pointer and are absent from Git's worktree list.
They contain no measured file payload, so removing them would free almost
no disk space. Their removal was rejected by automatic approval review;
they may be removed manually.

The two oct06-owner and oct06-evidence review worktrees were created by
this review, around 99.5 MiB combined. Both were removed after their reviewers finished, together with their
temporary branches. The CI contract, durable and platform worktrees are also
retired after integration or recovery preservation; the integration worktree
was removed last. Git now lists only D:/AI/Agent-Society-v2 and the sole local
branch codex/agent-society. Old local backup branches were replaced by verified
archive tags; obsolete remote branch snapshots now also have archive tags.

## Recovery material for this handoff

Keep D:/AI/Agent-Society-archives/2026-10-07/pre-cleanup-all-refs.bundle.
It was verified and preserves the pre-cleanup refs, including the interrupted
construction-budget patch. The old WORKER-PROMPT.md is archived beside it;
the canonical file is now the concise Claude entry point. The recovery tag
recovery/ci-child-construction-2026-10-07 names unqualified work, not a release.
No historical evidence, unrelated project or live database is retired merely
because it is absent from the task's current worktree list.

This inventory does not establish that unrelated D:/AI projects or other
computer folders are stale. Process path matching was inconclusive because
the inventory commands themselves contained those paths. Git registration
and source status determine the classifications above.

## Nearby projects: registration check only

A metadata-only scan of top-level D:/AI Git checkouts found another eleven
worktree registrations belonging to D:/AI/vkit-posix-audit, all pointing
under D:/AI/Poteto's Style/.claude/worktrees. All eleven paths are absent
with ENOENT. These are stale registrations, not existing folders consuming
disk space. Their branches and metadata were left untouched because this
review does not establish which VKit work is safely retired. The other
scanned top-level repositories each report only their own primary checkout.

This is not permission to delete the unrelated projects themselves, their
backup folders, or unregistered directories whose contents were not reviewed.
