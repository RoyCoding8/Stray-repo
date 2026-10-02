"""Supersession markers for the evidence tree, and the check that reads them.

B6/B7 of `TASKS.md` §B. The tree carries two conventions and neither is
discoverable from the artifact it describes: `RETRACTED.md` is correct,
hand-run, and unreachable; a `supersedes` field in generated JSON is
reachable and only exists in artifacts their own writer can rewrite, which
is structurally unavailable for every file that most needs annotating.

A marker is a new file beside the artifact. The tree's rules forbid editing,
regenerating or deleting anything already committed, so reachability has to
come from a sibling. That sibling is worthless unless it can be checked, so
`artifact_sha256` binds it to the bytes it describes and `check_evidence_tree`
fails when the two drift apart.

Five shapes exist because five relations do. See `reports/STAGE-09-SUPERSESSION.md`
for which of the four rows each one carries.

    VESSEL           container_mislabelled; artifact_digest is the file, which
                     is correct; the defect is the directory name. Nothing
                     about the bytes is wrong, so `void_scope` is empty and
                     must be.
    DATA             void_scope covers the artifact in full. B1, and the three
                     older RETRACTED.md directories.
    SCOPE            void_scope is a JSON pointer; everything outside it
                     survives, and `surviving_claim` says what. B6.
    EDITS            DATA plus `intact_at_ref`, a ref holding the pre-edit
                     bytes. B2: the artifact is wrong now and correct there,
                     and the backward edge is a stronger recovery than any
                     successor.
    NAME             the artifact is a valid record of a run that is not the
                     one its directory claims. Not a defect at all.

The honest limit: this cannot make a retraction visible to a reader who opens
only the JSON and parses no sibling. That requires the writer to emit the
field, and for these four artifacts the writer cannot be re-run without
overwriting the evidence the annotation exists to preserve.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

MARKER_SUFFIX = ".supersession.json"
EVIDENCE_ROOT = "reports/evidence"

SHAPES = ("VESSEL", "DATA", "SCOPE", "EDITS", "NAME")
VERDICTS = ("VOID", "PARTIALLY_VOID", "CONTAINER_MISLABELLED", "NAME_MISLABELLED")

SCOPED = ("SCOPE", "EDITS")
BACKWARD_EDGES = ("EDITS",)

_MARKER_KEYS = frozenset({
    "artifact", "artifact_sha256", "shape", "verdict", "finding",
    "annotation", "void_scope", "surviving_claim",
    "superseded_by", "intact_at_ref", "container_mislabelled",
    "note",
})
_SCOPE_KEYS = frozenset({"pointer", "reason", "finding"})

_INDEX_SKIP = frozenset({"__pycache__"})


class MarkerError(ValueError):
    """A marker is malformed, or its claims do not survive checking."""


def sha256_file(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve_pointer(document, pointer: str):
    """Resolve a restricted JSON pointer over plain data.

    Supports `$.key`, `$.a.b` and `$.list.0.item`. Raises MarkerError with
    the failing token rather than KeyError, so a stale pointer is reported
    as a stale pointer and not as a crash.
    """
    if not isinstance(pointer, str) or not pointer.startswith("$"):
        raise MarkerError("pointer must start with '$': %r" % (pointer,))
    cursor = document
    rest = pointer[1:]
    for token in [t for t in rest.replace("[", ".").replace("]", "").split(".") if t]:
        if isinstance(cursor, list):
            if not token.isdigit() or int(token) >= len(cursor):
                raise MarkerError("no such index %r in %r" % (token, pointer))
            cursor = cursor[int(token)]
        elif isinstance(cursor, dict):
            if token not in cursor:
                raise MarkerError("no such key %r in %r" % (token, pointer))
            cursor = cursor[token]
        else:
            raise MarkerError("pointer %r descends into %s" % (pointer, type(cursor).__name__))
    return cursor


def _require(marker, key, kinds, where):
    if key not in marker:
        raise MarkerError("%s: missing %r" % (where, key))
    value = marker[key]
    if kinds is str:
        if not isinstance(value, str):
            raise MarkerError("%s: %r is %s, expected str" % (where, key, type(value).__name__))
        if not value:
            raise MarkerError("%s: missing %r" % (where, key))
    elif not isinstance(value, kinds):
        raise MarkerError("%s: %r is %s, expected %s" % (
            where, key, type(value).__name__, kinds))
    return value


def _optional_str(marker, key, where) -> str | None:
    value = marker.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise MarkerError("%s: %r must be a non-empty string or absent" % (where, key))
    return value


def load_marker(path: Path | str) -> dict:
    """Read one marker and refuse it if it does not satisfy the schema."""
    path = Path(path)
    try:
        marker = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MarkerError("%s: unreadable marker (%s)" % (path, exc))
    if not isinstance(marker, dict):
        raise MarkerError("%s: marker is not an object" % (path,))
    validate_marker(marker, where=str(path))
    return marker


def validate_marker(marker: dict, where: str = "marker") -> None:
    unknown = sorted(set(marker) - _MARKER_KEYS)
    if unknown:
        raise MarkerError("%s: unknown key(s) %s" % (where, ", ".join(unknown)))

    shape = _require(marker, "shape", str, where)
    if shape not in SHAPES:
        raise MarkerError("%s: shape %r not in %s" % (where, shape, "/".join(SHAPES)))

    verdict = _require(marker, "verdict", str, where)
    if verdict not in VERDICTS:
        raise MarkerError("%s: verdict %r not in %s" % (where, verdict, "/".join(VERDICTS)))

    _require(marker, "artifact", str, where)
    _require(marker, "artifact_sha256", str, where)
    _require(marker, "finding", str, where)
    _require(marker, "annotation", str, where)

    scope = _require(marker, "void_scope", list, where)
    for entry in marker["void_scope"]:
        if not isinstance(entry, dict):
            raise MarkerError("%s: void_scope entries must be objects" % where)
        extra = sorted(set(entry) - _SCOPE_KEYS)
        if extra:
            raise MarkerError("%s: void_scope entry has unknown key(s) %s"
                              % (where, ", ".join(extra)))
        _require(entry, "pointer", str, where + " void_scope entry")
        _require(entry, "reason", str, where + " void_scope entry")

    if shape in BACKWARD_EDGES:
        _require(marker, "intact_at_ref", str, where)
    elif marker.get("intact_at_ref") is not None:
        raise MarkerError("%s: intact_at_ref is only meaningful for %s"
                          % (where, "/".join(BACKWARD_EDGES)))
    if shape == "SCOPE":
        if not scope:
            raise MarkerError("%s: SCOPE needs a non-empty void_scope" % where)
        _require(marker, "surviving_claim", str, where)
    elif shape == "DATA":
        if not scope:
            raise MarkerError("%s: DATA needs a non-empty void_scope" % where)
        _require(marker, "surviving_claim", str, where)
    elif shape in ("VESSEL", "NAME"):
        if scope:
            raise MarkerError("%s: %s must have an empty void_scope — the bytes are "
                              "correct and only the referent is wrong"
                              % (where, shape))
        if marker.get("surviving_claim") is not None:
            raise MarkerError("%s: %s must not carry surviving_claim" % (where, shape))


def check_marker(repo_root: Path | str, marker_path: Path | str) -> list[str]:
    """Every claim one marker makes, checked against the bytes it describes.

    Returns problems; empty means the marker is true of the tree as it
    stands. Three classes are checked and none needs a run: the schema, the
    digest of the named artifact, and the JSON pointers.
    """
    repo_root = Path(repo_root)
    marker_path = Path(marker_path)
    if not marker_path.is_absolute():
        marker_path = repo_root / marker_path

    try:
        marker = load_marker(marker_path)
    except MarkerError as exc:
        return [str(exc)]

    problems: list[str] = []
    where = marker_path.name

    artifact = repo_root / marker["artifact"]
    if not artifact.is_file():
        problems.append("%s: artifact %s does not exist" % (where, marker["artifact"]))
        return problems

    actual = sha256_file(artifact)
    if actual != marker["artifact_sha256"]:
        problems.append(
            "%s: stale marker — artifact_sha256 is %s but %s hashes to %s"
            % (where, marker["artifact_sha256"][:12], marker["artifact"], actual[:12]))

    annotation = repo_root / marker["annotation"]
    if not annotation.is_file():
        problems.append("%s: annotation %s does not exist" % (where, marker["annotation"]))

    pointers = [entry["pointer"] for entry in marker["void_scope"]
                if entry["pointer"] != "$"]
    if pointers:
        try:
            document = json.loads(artifact.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append("%s: cannot read %s as JSON (%s)"
                            % (where, marker["artifact"], exc))
        else:
            for pointer in pointers:
                try:
                    resolve_pointer(document, pointer)
                except MarkerError as exc:
                    problems.append("%s: %s" % (where, exc))

    if marker["shape"] in BACKWARD_EDGES and _ref_missing(repo_root, marker["intact_at_ref"]):
        problems.append("%s: intact_at_ref %r is not a commit in this repository"
                        % (where, marker["intact_at_ref"]))

    return problems


def _ref_missing(repo_root: Path, ref: str) -> bool:
    """True when `ref` does not name a commit this repository can read.

    Reachability is not the question -- `d422c93` is an ancestor of HEAD but
    names no branch -- so this asks git for the commit directly.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "cat-file", "-e", "%s^{commit}" % ref],
            cwd=str(repo_root), capture_output=True)
    except OSError:
        return True
    return result.returncode != 0


def iter_markers(repo_root: Path | str = ".") -> list[Path]:
    root = Path(repo_root) / EVIDENCE_ROOT
    return sorted(p for p in root.rglob("*" + MARKER_SUFFIX)
                  if _INDEX_SKIP.isdisjoint(p.parts))


def check_evidence_tree(repo_root: Path | str = ".") -> list[str]:
    """Every marker in the tree, checked. Empty means the tree is self-consistent."""
    repo_root = Path(repo_root)
    problems: list[str] = []
    for marker_path in iter_markers(repo_root):
        problems.extend(check_marker(repo_root, marker_path))
    return problems


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Check every supersession marker in the evidence tree.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)

    problems = check_evidence_tree(args.repo_root)
    markers = iter_markers(args.repo_root)
    for problem in problems:
        print(problem)
    print("%d marker(s) checked, %d problem(s)" % (len(markers), len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
