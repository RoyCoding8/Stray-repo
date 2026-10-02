from __future__ import annotations

import json
from pathlib import Path

from .oracle import PROTECTED, REFERENCE, ROOT, TASKS

FORBIDDEN_LABELS = ("fam-ind", "fam-cpl", "fam-seq", "fam-sng",
                    "independent-repairs", "coupled-interface",
                    "sequential-discovery", "adequate-single")

FORBIDDEN_PATHS = ("protected/", "reference/")


def participant_files(root: Path = ROOT) -> list:
    found = []
    tasks = root / "tasks"
    for task_dir in sorted(tasks.iterdir()):
        if not task_dir.is_dir():
            continue
        for name in ("spec.md", "spec.json", "public.json"):
            path = task_dir / name
            if path.is_file():
                found.append(path)
        for path in sorted((task_dir / "src").glob("*.py")):
            found.append(path)
    return found


def _canon_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _walk(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        yield value
        for item in value:
            yield from _walk(item)


def audit_barrier(root: Path = ROOT) -> list:
    problems = []
    files = participant_files(root)
    if not files:
        return ["no-participant-files"]
    texts = {}
    for path in files:
        try:
            texts[path] = path.read_text(encoding="utf-8")
        except OSError:
            problems.append("unreadable %s" % path.name)
    joined = "\n".join(texts.values())
    lowered = joined.lower()
    for label in FORBIDDEN_LABELS:
        if label in lowered:
            problems.append("family label %r visible in participant inputs"
                            % label)
    for marker in FORBIDDEN_PATHS:
        if marker in lowered:
            problems.append("protected path reference %r in participant inputs"
                            % marker)
    protected_dir = root / "protected"
    hidden = []
    if protected_dir.is_dir():
        for doc_path in sorted(protected_dir.glob("*.json")):
            try:
                cases = json.loads(doc_path.read_text())
            except (OSError, ValueError):
                problems.append("unreadable protected %s" % doc_path.name)
                continue
            for case in cases:
                hidden.append((doc_path.stem, _canon_json(case["expected"])))
    for path, text in texts.items():
        if path.suffix == ".json":
            try:
                doc = json.loads(text)
            except ValueError:
                problems.append("unreadable participant %s" % path.name)
                continue
            seen = {_canon_json(node) for node in _walk(doc)
                    if isinstance(node, (dict, list))}
            for stem, needle in hidden:
                if needle in seen:
                    problems.append(
                        "protected answer for %s visible in %s"
                        % (stem, path.name))
        else:
            flat = "".join(text.split())
            for stem, needle in hidden:
                if needle in flat:
                    problems.append(
                        "protected answer for %s visible in %s"
                        % (stem, path.name))
    reference_dir = root / "reference"
    if reference_dir.is_dir():
        for ref_path in sorted(reference_dir.rglob("*.py")):
            try:
                ref_text = ref_path.read_text(encoding="utf-8")
            except OSError:
                continue
            ref_flat = "".join(ref_text.split())
            if len(ref_flat) < 40:
                continue
            for path, text in texts.items():
                if ref_flat in "".join(text.split()):
                    problems.append("reference patch %s visible in %s"
                                    % (ref_path.name, path.name))
    return sorted(set(problems))
