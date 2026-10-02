from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import oracle

ROOT = oracle.ROOT

CORPUS_VERSION = "coord02-corpus/1"
FREEZE_VERSION = "coord02-freeze/1"
PROTOCOL_DEV = "coord02-dev-v1"
PROTOCOL_EVAL = "coord02-eval-v1"
PROTOCOL_TRANSFER = "coord02-transfer-v1"

ARMS = ("S", "A", "F", "L")
REPEATS = (1, 2)
PANELS = ("development", "evaluation", "transfer")

CEILINGS = {"model_calls": 12, "input_tokens": 128000,
            "output_tokens": 48000, "tool_invocations": 20,
            "sandbox_ops": 64, "policy_steps": 8,
            "children": 2, "probe_batches": 1,
            "probe_invocations": 4, "rework_rounds": 1,
            "wall_seconds": 900}

RULES = {"comparison": "L vs S, A, F independently",
         "ratio": 1.25,
         "resources": ["model_tokens", "tool_invocations", "sandbox_ops"],
         "eval_family_cap": 1, "transfer_family_cap": 0}


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pinned_dir(path: Path, hashed: str) -> bytes:
    raw = path.read_bytes()
    try:
        pinned = (path.parent / hashed).read_text().strip()
    except OSError:
        raise ValueError("missing hash for %s" % path.name)
    if _digest(raw) != pinned:
        raise ValueError("hash mismatch for %s" % path.name)
    return raw


def _pinned(path: Path) -> bytes:
    raw = path.read_bytes()
    try:
        pinned = Path(str(path) + ".sha256").read_text().strip()
    except OSError:
        raise ValueError("missing hash for %s" % path.name)
    if _digest(raw) != pinned:
        raise ValueError("hash mismatch for %s" % path.name)
    return raw


def _manifest() -> dict:
    return json.loads(_pinned_dir(ROOT / "corpus" / "manifest.json",
                                 "manifest.sha256"))


def build_schedule() -> list:
    order = []
    for panel in PANELS:
        for task in oracle.SPLITS[panel]:
            for repeat in REPEATS:
                shift = (oracle.ALL_TASKS.index(task) + repeat) % len(ARMS)
                arms = ARMS[shift:] + ARMS[:shift]
                for arm in arms:
                    order.append({"panel": panel, "task": task,
                                  "repeat": repeat, "arm": arm})
    return order


def expected_pairs(schedule: list, panel: str, freeze_id: str) -> set:
    return {(freeze_id, cell["panel"], cell["task"], cell["repeat"],
             cell["arm"]) for cell in schedule if cell["panel"] == panel}


def build_freeze(freeze_id: str, *, source_sha: str,
                 package: dict | None = None,
                 baselines: dict | None = None,
                 model: dict | None = None,
                 config: dict | None = None) -> dict:
    manifest = _manifest()
    return {"version": FREEZE_VERSION, "freeze_id": freeze_id,
            "source": {"repo_base": source_sha},
            "corpus": {"version": manifest["version"],
                       "manifest_digest": _digest(
                           (ROOT / "corpus" / "manifest.json").read_bytes()),
                       "splits": manifest["splits"],
                       "membership": manifest["membership"],
                       "seeds": manifest["seeds"]},
            "evaluator": dict(manifest["evaluator"]),
            "oracle_digest": _digest((ROOT / "oracle.py").read_bytes()),
            "checker_digest": _digest((ROOT / "checker.py").read_bytes()),
            "model": model or {"status": "unconfigured",
                               "note": "pinned at selection"},
            "config": config or {"status": "unconfigured",
                                 "note": "pinned at selection"},
            "package": package or {"kind": "none",
                                   "reason": "workload lane holds no "
                                             "candidate; selection owns "
                                             "this field"},
            "baselines": baselines or {"status": "declared-by-lane-E"},
            "protocols": [PROTOCOL_DEV, PROTOCOL_EVAL, PROTOCOL_TRANSFER],
            "schedule": build_schedule(),
            "budgets": dict(CEILINGS), "rules": dict(RULES)}


def write_freeze(path: Path, freeze: dict) -> Path:
    raw = (json.dumps(freeze, sort_keys=True, indent=2) + "\n").encode()
    path = Path(path)
    path.write_bytes(raw)
    Path(str(path) + ".sha256").write_text(_digest(raw) + "\n")
    return path


def verify_freeze(path: Path) -> list:
    problems = []
    path = Path(path)
    try:
        raw = _pinned(path)
    except ValueError as exc:
        return [str(exc)]
    try:
        freeze = json.loads(raw)
    except ValueError:
        return ["unreadable-freeze"]
    for field in ("version", "freeze_id", "source", "corpus", "evaluator",
                  "oracle_digest", "checker_digest", "model", "config",
                  "package", "baselines", "protocols", "schedule",
                  "budgets", "rules"):
        if field not in freeze:
            problems.append("missing-field %s" % field)
    if problems:
        return problems
    if freeze.get("version") != FREEZE_VERSION:
        problems.append("version-mismatch %r" % freeze.get("version"))
    try:
        manifest = _manifest()
    except ValueError as exc:
        return problems + ["corpus-%s" % exc]
    corpus = freeze["corpus"]
    if corpus.get("manifest_digest") != _digest(
            (ROOT / "corpus" / "manifest.json").read_bytes()):
        problems.append("corpus-drift")
    if corpus.get("splits") != manifest["splits"]:
        problems.append("splits-drift")
    if corpus.get("membership") != manifest["membership"]:
        problems.append("membership-drift")
    if freeze.get("oracle_digest") != _digest(
            (ROOT / "oracle.py").read_bytes()):
        problems.append("oracle-drift")
    try:
        checker_digest = _digest((ROOT / "checker.py").read_bytes())
    except OSError:
        problems.append("missing-checker")
    else:
        if freeze.get("checker_digest") != checker_digest:
            problems.append("checker-drift")
    if freeze.get("schedule") != build_schedule():
        problems.append("schedule-drift")
    if freeze.get("budgets") != CEILINGS:
        problems.append("budgets-drift")
    if freeze.get("rules") != RULES:
        problems.append("rules-drift")
    pair_keys = [(c.get("panel"), c.get("task"), c.get("repeat"), c.get("arm"))
                 for c in freeze.get("schedule", [])]
    if len(set(pair_keys)) != len(pair_keys):
        problems.append("schedule-collision")
    return problems
