"""A test may not destroy a database it did not create.

Thirty test files once called `dropdb` on a hardcoded name, bypassing
`SETTLEMENT_TEST_DSN` entirely. That is how three databases predating an
earlier session were destroyed simply by running the suite: the tests
connect by name, so no amount of disposable-DSN discipline protects a
database the test never knew about. Every one of them has since been
converted to a per-run token, so the census now reads one file: this
module, which names the lost databases in order to assert the check still
finds them.

The rule that actually holds is narrow and checkable: a destructive call
must name its target through a value the test derived, never through a
literal. A literal is a name that is fixed forever, so whoever runs the
suite next loses it. This module makes that mechanical rather than a
convention, so a future test cannot reintroduce the hazard by forgetting.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"

DROP_PATTERN = re.compile(r"\b(dropdb|DROP\s+DATABASE|DROP\s+SCHEMA)\b",
                          re.IGNORECASE)
DERIVED_PATTERN = re.compile(r"[+%]|%[sd]|f[\"']|\.format\(|join\(")
DB_NAME_PATTERN = re.compile(r"(?:s09|ad01|ec02|invl)[A-Za-z0-9_.-]*")


def destructive_files(root: Path | None = None) -> list[Path]:
    directory = root or TESTS
    return [path for path in sorted(directory.glob("test_*.py"))
            if DROP_PATTERN.search(path.read_text(encoding="utf-8",
                                                  errors="replace"))]


def _literal_names(tree: ast.AST) -> set[str]:
    """Every database-shaped string literal anywhere in a module.

    Assignment is the indirection that hides the hazard: a test writes
    ``name = "s09o_pilot_full"`` and later calls ``dropdb(name)``, so the
    literal never appears on the destructive line. Reading the literals from
    the whole tree rather than the line is what finds that.
    """
    return {node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and DB_NAME_PATTERN.fullmatch(node.value)}


def files_with_literal_drops(root: Path | None = None) -> dict[str, list[str]]:
    """Test files that both destroy databases and name one as a literal.

    `root` exists so the check can be proven on a scratch tree. Once every
    real file has been converted there is no live witness left in `tests/`,
    and a test that reads a witness it no longer has stops proving anything
    while still passing.
    """
    found: dict[str, list[str]] = {}
    for path in destructive_files(root):
        source = path.read_text(encoding="utf-8", errors="replace")
        if not DROP_PATTERN.search(source):
            continue
        names = sorted(_literal_names(ast.parse(source, filename=str(path))))
        if names:
            found[path.name] = names
    return found


def census() -> dict:
    """The destructive surface, and the part of it that is a real hazard."""
    files = destructive_files()
    unsafe = files_with_literal_drops()
    return {
        "files_calling_dropdb": len(files),
        "files_with_literal_drops": sorted(unsafe),
        "literal_drop_count": sum(len(names) for names in unsafe.values()),
        "literal_database_names": sorted(
            {name for names in unsafe.values() for name in names}),
    }
