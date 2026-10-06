# Agent-Society workspace inventory, 2026-10-06

Scope: Agent-Society-related folders under D:/AI, not a whole-disk audit.
Sizes are rounded MiB of file contents. Reparse points were not traversed.
The canonical source inspected was codex/agent-society at e8e7911e.

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
| D:/AI/s09o | 77.0 MiB total | Old pilot work area, including live evidence, logs, a tar, snapshots and abandoned-pilot-partial.patch. Preserve those unique artifacts before retiring the directory. |
| D:/AI/s09o/u6-baseline | About 24 MiB | Broken checkout. Its .git file points at the absent Agent-Society-v2-investigation-review registration; Git cannot resolve HEAD. No current registration. This does not prove its contents are redundant. |
| D:/AI/s09o/snapshot-c3e8566 | About 25 MiB | Plain snapshot, not a registered Git worktree. Keep until contents/patches are covered by an archive. |
| D:/AI/Agent-Society-v2-privacy-20260910 | 0.7 MiB | Historical plain snapshot, not a registered worktree. No content-equivalence proof was performed. |
| D:/AI/Agent-Society-v2/.a53* | 71.1 MiB combined | Roughly 40 worker CI artifact groups/files. These are scratch evidence rather than source checkouts. Some are cited by historical reports; preserve or archive before removing. |
| D:/AI/Agent-Society-v2/.ci-read | 0.6 MiB | Worker diagnostic output, not a worktree. Preserved. |
| D:/AI/Agent-Society-v2/.scratch | 0.5 MiB | Worker scratch files, not a worktree. Preserved. |

Do not delete untracked supersession sidecars or evidence directories simply
because Git reports them untracked. This review did not establish their
redundancy. No historical evidence was altered or discarded.

## Empty worktree directories

D:/AI/Agent-Society-v2/.worktrees/e3, hang, m2decide, roots and w0-relay
are empty, have no .git pointer and are absent from Git's worktree list.
They contain no measured file payload, so removing them would free almost
no disk space. They were left alone.

The two oct06-owner and oct06-evidence review worktrees were created by
this review, around 99.5 MiB combined. Both were removed after their reviewers finished, together with their
temporary branches. The final registered worktree list contains only
D:/AI/Agent-Society-v2.

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
