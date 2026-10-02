"""Remove named top-level functions from a Python file, block and all.

A function with decorators is not one `def` line: the decorator above it and
the whole indented body below it belong to the definition. Deleting the `def`
line alone leaves an orphaned body that still executes at import and still
references names the caller deleted. This walks from the `def`/`@` line to the
first following line that is not blank and not indented, which is where the
block ends, and takes the trailing blank lines with it so no double gap is
left behind.

It refuses to run if a name does not resolve to exactly one top-level
definition, or if that definition is not preceded solely by decorators and a
comment block. That guard is the point: a hand-checked list of "dead" symbols
is exactly the kind of list that goes stale, and a silent miss here would
delete the wrong lines.

    uv run python scripts/remove_functions.py --dry-run NAME:path:line ...
    uv run python scripts/remove_functions.py NAME:path:line ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _block_bounds(lines: list[str], start: int) -> tuple[int, int]:
    """Where the definition beginning at `start` (0-based) ends."""
    indent = len(lines[start]) - len(lines[start].lstrip())
    if indent:
        raise SystemExit("line %d is not a top-level definition" % (start + 1))
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and not line.startswith(" " * (indent + 1)) \
                and not line.startswith("\t"):
            break
        end += 1
    while end < len(lines) and not lines[end].strip():
        end += 1
    return start, end


def _definition_start(lines: list[str], decl: int) -> int:
    """Walk back over decorators and the comment block introducing it."""
    i = decl
    while i > 0:
        prev = lines[i - 1]
        if prev.startswith("@") or prev.startswith("#") \
                or (prev.startswith(" ") and prev.strip()):
            i -= 1
            continue
        break
    return i


def remove(spec: str, *, dry_run: bool = False) -> str:
    """Remove one top-level function named by `NAME:PATH` or `NAME:PATH:LINE`.

    The line number is optional and, when given, only a cross-check. Removing
    a function shifts every line below it, so a caller working through a list
    of previously-measured lines silently aims the second and later removals
    at the wrong row -- and the guard then aborts the whole batch at the first
    stale one. Looking the definition up by name is what makes a list of
    removals order-independent.
    """
    parts = spec.split(":")
    name, rel = parts[0], parts[1]
    path = REPO / rel
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

    needle = "def %s(" % name
    found = [i for i, line in enumerate(lines)
             if line.startswith(needle) or line.startswith(" " + needle)]
    if len(found) != 1:
        raise SystemExit(
            "%s defines %s %d times at top level; refusing to guess"
            % (rel, name, len(found)))
    decl = found[0]

    if len(parts) == 3 and int(parts[2]) != decl + 1:
        print("  note: %s:%s is now line %d, not %s"
              % (rel, name, decl + 1, parts[2]))

    start = _definition_start(lines, decl)
    _, end = _block_bounds(lines, decl)
    removed = "".join(lines[start:end])

    if not dry_run:
        path.write_text("".join(lines[:start] + lines[end:]),
                        encoding="utf-8", newline="")

    body = [l for l in removed.splitlines() if l.strip()]
    return "%-34s %s:%d  %3d lines, %5d B" % (
        name, rel, decl + 1, len(body), len(removed.encode("utf-8")))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("specs", nargs="+", metavar="NAME:path:line")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    for spec in args.specs:
        print(remove(spec, dry_run=args.dry_run))
    if args.dry_run:
        print("\ndry run; nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
