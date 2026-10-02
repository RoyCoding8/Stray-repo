from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import oracle

ROOT = oracle.ROOT

PROTOCOL_DEV = "team01-dev-v1"
PROTOCOL_EVAL = "team01-eval-v1"

SEEDS = {("team01-t%02d" % i): 100 + i for i in range(1, 17)}
SAMPLING_OFFSET = 16

POLICY_VERSIONS = {"profile": "team-work/1", "selector": "team-select/1",
                   "template": "coordination-template/1",
                   "evaluator": oracle.EVALUATOR_VERSION}

CEILINGS = {"model_invocations": 8, "input_tokens": 96000,
            "output_tokens": 24000, "tool_executions": 16,
            "wall_seconds": 900, "simultaneous_children": 2,
            "plan_revisions": 1}

RANKING = {"selection": "fewest public failures, then lowest task id",
           "primary_outcome": "protected pass count of the frozen artifact",
           "pilot_rule": "T strictly more protected solves than S and P with"
                         " model tokens and tool executions each at most 1.25x"
                         " that comparator, and no family losing more than one"
                         " solved episode against either comparator"}


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _rel(path: Path) -> str:
    return "experiments/team01/" + path.relative_to(ROOT).as_posix()


def _entry(path: Path) -> dict:
    raw = path.read_bytes()
    return {"path": _rel(path), "digest": _digest(raw), "bytes": len(raw)}


def manifest_files() -> list:
    found = []
    for task_id in oracle.ALL_TASKS:
        tdir = ROOT / "tasks" / task_id
        found.append(tdir / "spec.md")
        found.append(tdir / "spec.json")
        found.append(tdir / "public.json")
        for mod in sorted((tdir / "src").glob("*.py")):
            found.append(mod)
        found.append(ROOT / "protected" / (task_id + ".json"))
    for fam in oracle.FAMILIES:
        for kind in ("valid", "invalid"):
            for mod in sorted((ROOT / "reference" / fam / kind).glob("*.py")):
                found.append(mod)
    for name in ("oracle.py", "barrier.py", "freeze.py", "register.py"):
        found.append(ROOT / name)
    return [_entry(path) for path in found]


def build_manifest() -> dict:
    files = manifest_files()
    files.sort(key=lambda entry: entry["path"])
    return {"version": "team01-corpus/1",
            "splits": {key: list(val)
                       for key, val in oracle.SPLITS.items()},
            "membership": dict(oracle.TASK_FAMILY),
            "seeds": dict(SEEDS),
            "sampling_offset": SAMPLING_OFFSET,
            "evaluator": {"id": oracle.EVALUATOR_ID,
                          "version": oracle.EVALUATOR_VERSION,
                          "code_digest": _digest(
                              (ROOT / "oracle.py").read_bytes())},
            "protocols": [PROTOCOL_DEV, PROTOCOL_EVAL],
            "policy_versions": dict(POLICY_VERSIONS),
            "ceilings": dict(CEILINGS),
            "ranking": dict(RANKING),
            "files": files}


def write_manifest() -> dict:
    manifest = build_manifest()
    raw = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    (ROOT / "manifest.json").write_bytes(raw)
    (ROOT / "manifest.sha256").write_text(_digest(raw) + "\n")
    return manifest


def verify_committed(name: str = "manifest.json",
                     regenerate: bool = True) -> list:
    try:
        manifest_raw = (ROOT / name).read_bytes()
    except OSError:
        return ["missing-manifest"]
    try:
        pinned = (ROOT / (Path(name).stem + ".sha256")).read_text().strip()
    except OSError:
        return ["missing-manifest-hash"]
    if _digest(manifest_raw) != pinned:
        return ["manifest-hash-mismatch"]
    problems = []
    if regenerate:
        try:
            fresh = build_manifest()
        except (ValueError, KeyError, OSError) as exc:
            return ["regeneration-failed %s" % exc]
        if json.loads(manifest_raw) != fresh:
            problems.append("manifest-content-mismatch")
    manifest = json.loads(manifest_raw)
    seen = set()
    for entry in manifest.get("files", []):
        path = entry.get("path", "")
        if path in seen:
            problems.append("duplicate-file %s" % path)
        seen.add(path)
        target = ROOT.parent.parent / path
        if not target.is_file():
            problems.append("missing-file %s" % path)
            continue
        if _digest(target.read_bytes()) != entry.get("digest"):
            problems.append("digest-mismatch %s" % path)
    return problems
