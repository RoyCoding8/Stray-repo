"""Immutable task bank: instruction, solution slots, pristine verifier and reference."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import sys
from types import MappingProxyType
from typing import Mapping

from settlement import artifacts, db, store
from settlement.common import Command, ResultCode, SettlementError

SCOPE = "rsi-task"
SPLITS = ("dev", "val", "anchor")
DRIVER_PATH = "_rsi_verify.py"


class TaskError(SettlementError):
    pass


def file_manifest(files: Mapping[str, bytes]) -> list[dict]:
    return [{"path": rel, "kind": "file", "size": len(raw),
             "digest": hashlib.sha256(raw).hexdigest()}
            for rel, raw in sorted(files.items())]


@dataclass(frozen=True)
class Task:
    name: str
    split: str
    instruction: str
    workspace: Mapping[str, bytes]
    verifier: Mapping[str, bytes]
    reference: Mapping[str, bytes]
    test_files: tuple[str, ...]
    driver: bytes = field(default_factory=lambda: Path(__file__).with_name(
        "_unittest_runner.py").read_bytes())
    runtime: str = field(default_factory=lambda: sys.version)
    digest: str = field(init=False)
    evaluator_version: str = field(init=False)

    def __post_init__(self):
        if self.split not in SPLITS or not self.name or not self.instruction.strip():
            raise TaskError("task needs a name, instruction and dev|val|anchor split")
        for attr in ("workspace", "verifier", "reference"):
            files = dict(sorted(getattr(self, attr).items()))
            for rel, raw in files.items():
                artifacts._check_relpath(rel)
                if rel == DRIVER_PATH or rel.casefold() == "_receipt.json":
                    raise TaskError(f"reserved task path {rel!r}")
                if not isinstance(raw, bytes):
                    raise TaskError(f"task file {rel!r} must be bytes")
            # Windows cannot distinguish case-only paths, nor file/directory aliases.
            paths = {rel.casefold() for rel in files}
            if len(paths) != len(files) or any(
                    "/".join(rel.split("/")[:i]) in paths
                    for rel in paths for i in range(1, len(rel.split("/")))):
                raise TaskError("task paths collide")
            object.__setattr__(self, attr, MappingProxyType(files))
        if not self.workspace or set(self.reference) != set(self.workspace):
            raise TaskError("reference must replace every solution slot")
        combined = [p.casefold() for p in (*self.workspace, *self.verifier)]
        paths = set(combined)
        if len(paths) != len(combined) or any(
                "/".join(rel.split("/")[:i]) in paths
                for rel in paths for i in range(1, len(rel.split("/")))):
            raise TaskError("solution and verifier paths collide")
        tests = tuple(self.test_files)
        if not tests or any(p not in self.verifier or not p.endswith(".py") for p in tests):
            raise TaskError("test_files must name pristine Python verifier files")
        object.__setattr__(self, "test_files", tests)
        evaluator = {"files": {**dict(self.verifier), DRIVER_PATH: self.driver},
                     "test_files": tests, "runtime": self.runtime,
                     "python_flags": ["-I", "-S", "-B"]}
        encoded = json.dumps({**evaluator, "files": {
            rel: raw.hex() for rel, raw in evaluator["files"].items()}},
            sort_keys=True, separators=(",", ":")).encode()
        object.__setattr__(self, "evaluator_version", hashlib.sha256(encoded).hexdigest())
        object.__setattr__(self, "digest", hashlib.sha256(
            artifacts.package_bytes(self.manifest(), self.package_files(), SCOPE)).hexdigest())

    def package_files(self) -> dict[str, bytes]:
        files = {f"{kind}/{rel}": raw for kind in ("workspace", "verifier", "reference")
                 for rel, raw in getattr(self, kind).items()}
        files["driver.py"] = self.driver
        return files

    def manifest(self) -> dict:
        return {"kind": SCOPE, "name": self.name, "split": self.split,
                "instruction": self.instruction, "test_files": list(self.test_files),
                "runtime": self.runtime, "evaluator_version": self.evaluator_version,
                "files": file_manifest(self.package_files())}


def publish(dsn: str, task: Task, *, staging_root: str | Path,
            artifacts_root: str | Path) -> str:
    receipt = artifacts.stage_package(dsn, staging_root, manifest=task.manifest(),
                                      files=task.package_files(), scope=SCOPE,
                                      access_label="hidden" if task.split == "anchor" else "evaluator",
                                      format=SCOPE)
    if receipt["digest"] != task.digest:
        raise TaskError("task digest disagrees with artifact digest")
    result = artifacts.publish_package(dsn, Command(
        request_id=f"rsi-task-art-{task.digest}", payload={"digest": task.digest}),
        artifacts_root, receipt)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise TaskError(result.detail)

    def record(cur, control):
        cur.execute("INSERT INTO rsi_tasks (digest, name, split, evaluator_version)"
                    " VALUES (%s, %s, %s, %s) ON CONFLICT (digest) DO NOTHING",
                    (task.digest, task.name, task.split, task.evaluator_version))
        return (ResultCode.APPLIED, "task published", {"digest": task.digest},
                [("rsi.task.published", {"digest": task.digest, "split": task.split})], [])
    result = store.transact(dsn, Command(request_id=f"rsi-task-{task.digest}",
                                         payload={"digest": task.digest}), record)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise TaskError(result.detail)
    return task.digest


def load(dsn: str, artifacts_root: str | Path, digest: str) -> Task:
    with db.connect(dsn) as conn:
        row = conn.execute("SELECT name, split, evaluator_version FROM rsi_tasks"
                           " WHERE digest = %s", (digest,)).fetchone()
    if row is None:
        raise TaskError(f"unknown task {digest[:12]}")
    raw = (Path(artifacts_root) / digest).read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise TaskError("stored task bytes do not match digest")
    package = json.loads(raw)
    meta, files = package["manifest"], package["files"]
    groups = {kind: {rel.removeprefix(kind + "/"): bytes.fromhex(value)
                     for rel, value in files.items() if rel.startswith(kind + "/")}
              for kind in ("workspace", "verifier", "reference")}
    task = Task(meta["name"], meta["split"], meta["instruction"], **groups,
                test_files=tuple(meta["test_files"]), driver=bytes.fromhex(files["driver.py"]),
                runtime=meta["runtime"])
    if (task.digest != digest or row != (task.name, task.split, task.evaluator_version)):
        raise TaskError("task registry disagrees with stored package")
    return task


def split_for(name: str) -> str:
    """Fixed 50/25/25 hash buckets. Adding tasks never moves an existing task."""
    bucket = int(hashlib.sha256(name.encode()).hexdigest(), 16) % 4
    return "dev" if bucket < 2 else "val" if bucket == 2 else "anchor"


def from_exercism(root: str | Path) -> list[Task]:
    tasks = []
    for exercise in sorted(Path(root).iterdir()):
        if not exercise.is_dir():
            continue
        name = exercise.name
        solution = name.replace("-", "_") + ".py"
        test = name.replace("-", "_") + "_test.py"
        instruction = (exercise / ".docs/instructions.md").read_text(encoding="utf-8")
        append = exercise / ".docs/instructions.append.md"
        if append.exists():
            instruction += "\n" + append.read_text(encoding="utf-8")
        verifier = {p.name: p.read_bytes() for p in sorted(exercise.glob("*.py"))
                    if p.name != solution}
        tasks.append(Task(name, split_for(name), instruction,
                          {solution: (exercise / solution).read_bytes()}, verifier,
                          {solution: (exercise / ".meta/example.py").read_bytes()}, (test,)))
    if not tasks:
        raise TaskError("task source is empty")
    return tasks
