"""Locating the checkouts a repository-scanning test has to read.

Several tests in this tree assert over a whole-tree result set rather than over
one fixed subdirectory, so their answer depends on *where the file happens to
live*. The same defect had the same shape twice: a lane's own file or an
untracked claim was invisible to a scan that resolved its root from `__file__`
and walked it.

This module is the one answer to three environment facts that no single test
should rediscover:

  1. Git cannot resolve a linked worktree from WSL. A worktree's `.git` is a
     *file* holding `gitdir: D:/...`, a Windows path git cannot follow on this
     mount, so a lane gets "not a git repository". The canonical root is
     therefore found structurally: the nearest ancestor holding a `.git`
     *directory*. A throwaway clone satisfies the same shape, because a clone's
     `.git` is a directory at its root.
  2. The repository is owned by a uid the suite does not run as, so every git
     call carries `-c safe.directory=*` rather than trusting the runner's
     configuration, which is a property of the host and not of the repository.
  3. `git worktree list` is the authority on which checkouts exist, and it
     prints each linked worktree's path with the common directory glued to the
     front of the Windows one. A structural walk for `.git` entries costs
     seven minutes on this mount, because it descends every source tree of
     every lane, and it is a weaker answer: a directory holding a `.git` *file*
     is a clone of the repository rather than a lane of it.

The split the callers get is `tracked` versus `untracked`, and it is the whole
reason a lane's copy of a tracked file is not a second hit. A lane's checkout
already tracks a file it shares with the repository, so the repository's
tracked set covers it once; what no other checkout has is its untracked files,
and those are the only thing a sibling can contribute that is not a copy.

Callers own the policy. This module owns only the mechanism: where the
repository is, which checkouts belong to it, and what git knows about each.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Git's own safety net. Supplying it here rather than depending on the
# runner's `safe.directory` keeps the answer a property of the repository
# instead of a property of whichever uid launched pytest.
_GIT = ("git", "-c", "safe.directory=*")


def canonical_root(start: Path) -> Path:
    """The one checkout that owns the repository, found structurally.

    No subprocess, and no reliance on where the calling file was invoked. A
    linked worktree resolves to the main clone; a clone resolves to itself.
    """
    for candidate in (start, *start.parents):
        if (candidate / ".git").is_dir():
            return candidate
    raise RuntimeError("no ancestor of %s holds a .git directory" % start)


def checkout_index(canonical: Path, checkout: Path) -> Path:
    """The git index that answers for `checkout`, addressed from the repository.

    A linked worktree keeps its index in the repository's admin directory, and
    its `.git` file names it by a Windows path git cannot follow. Only the last
    component is load-bearing, and the admin directory's name is the same token
    `git worktree list` prints, so the name is what is used. A clone and the
    main checkout keep their own index and are asked directly.
    """
    marker = checkout / ".git"
    if marker.is_dir():
        return marker
    named = marker.read_text(encoding="utf-8", errors="ignore").partition(":")[2]
    name = Path(named.strip()).name
    if not name:
        raise RuntimeError("%s carries a .git file naming no admin directory"
                           % checkout)
    return canonical / ".git" / "worktrees" / name


def _run(args: list[str], cwd: Path) -> str:
    done = subprocess.run(list(_GIT) + args, cwd=str(cwd),
                          capture_output=True, text=True, check=True,
                          env={key: value for key, value in os.environ.items()
                               if key not in ("GIT_DIR", "GIT_WORK_TREE")})
    return done.stdout


def tracked_paths(canonical: Path, suffixes: tuple[str, ...]) -> list[str]:
    """The repository's tracked paths of those suffixes.

    Asked of the repository rather than of the checkout running the test, so
    the file list does not depend on which lane is asking. A lane branched
    behind the repository would otherwise scan a smaller tree than the one the
    same file asks about from the checkout holding the branch, and the two
    answers would both be reported.
    """
    out = _run(["--git-dir", str(canonical / ".git"), "ls-files", "-z", "--",
                *suffixes], cwd=canonical)
    return [name for name in out.split("\0") if name]


def untracked_paths(canonical: Path, checkout: Path,
                    suffixes: tuple[str, ...]) -> list[str]:
    """The paths of those suffixes that `checkout` holds and does not track.

    Asked of the checkout's own index, because "untracked" is a statement about
    that checkout's commits. Answering from the repository's index would report
    a file the lane committed and the branch has not seen as untracked, and key
    it as a stranger's.

    This is the whole of what a sibling checkout can contribute. Anything else
    a lane holds is a copy of a file the repository already tracks, and
    scanning it would read the same claim twice under two paths.

    Two ways this goes quietly wrong on a linked worktree. Both were measured,
    and both return a plausible list rather than an error, so neither announces
    itself.

    `--work-tree` cannot be used to name the checkout. Asked against a lane's
    own admin directory it is ignored and git takes the work tree from the
    *current directory*; asked against the repository's own `.git` beside the
    repository's own work tree it yields an empty index with no stderr. The
    `.git` file a worktree carries holds a `D:/...` path, so `git -C lane` is
    not available either, since it fails `not a git repository`. The working
    directory is the only handle that resolves, and it is also the only one git
    honours when filtering `--others`.

    `--exclude-standard` is what keeps the ignored scratch trees out, which is a
    job the walk-based scanners used to do by naming directories. Dropping it is
    not an option: without it git enumerates every ignored file under the
    mount, and on this checkout that walk does not finish.
    """
    out = _run(["--git-dir", str(checkout_index(canonical, checkout)),
                "ls-files", "-z", "--others", "--exclude-standard", "--",
                *suffixes], cwd=checkout)
    return [name for name in out.split("\0") if name]


def _local_path(raw: str) -> Path:
    if os.name != "nt":
        raw = raw.replace("\\", "/")
    if os.name != "nt" and len(raw) > 2 and raw[1:3] == ":/":
        return Path("/mnt") / raw[0].lower() / raw[3:]
    return Path(raw)


def sibling_checkouts(canonical: Path, own: Path) -> list[Path]:
    """Registered siblings whose Git marker belongs to this repository.

    WSL can prepend the common directory to a Windows registry path; recover
    that path only when Git's ordinary path does not exist.
    """
    out = _run(["-C", str(canonical), "worktree", "list", "--porcelain"],
               cwd=canonical)

    found: list[Path] = []
    for line in out.splitlines():
        if not line.startswith("worktree "):
            continue
        raw = line[len("worktree "):]
        lane = _local_path(raw)
        if not lane.is_dir():
            parts = raw.partition("/.git/worktrees/")[2].split("/", 1)
            if len(parts) != 2:
                continue
            lane = _local_path(parts[1])
        if lane.resolve() in (own.resolve(), canonical.resolve()) or not lane.is_dir():
            continue
        marker = lane / ".git"
        if not marker.is_file():
            continue
        named = marker.read_text(encoding="utf-8").removeprefix("gitdir: ").strip()
        target = _local_path(named)
        if not target.is_absolute():
            target = lane / target
        if target.resolve().parent == (canonical / ".git" / "worktrees").resolve():
            found.append(lane)
    return sorted(found)


def label_for(canonical: Path, lane: Path) -> str:
    """How a lane's findings are named in a failure message.

    Lane-relative where the lane sits under the repository, because that is the
    path a reader would type. A checkout beside the repository is named by its
    own directory, since there is no relative path to give.
    """
    try:
        return lane.relative_to(canonical).as_posix()
    except ValueError:
        return lane.name
