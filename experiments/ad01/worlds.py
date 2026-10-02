"""AD01 freeze: three worlds, two domains, dev/use split with manifest.

World ``w`` holds 3 visible development tasks per domain plus 12 protected
use tasks (3 within-scope + 3 structural-transfer per domain). Tasks derive
from AD01 seeds via ``representation.splits.generate_ad01``; the manifest
pins every file by content hash under freeze id ``ad01``.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from experiments.representation import splits

FREEZE_ID = splits.AD01_FREEZE_ID
VERSION = "AD01/1"
WORLDS = splits.AD01_WORLDS
DEV_PER_DOMAIN = 3
USE_WITHIN_PER_DOMAIN = 3
USE_TRANSFER_PER_DOMAIN = 3
FROZEN_DIR = Path(__file__).resolve().parent / "worlds"

# The HMAC key for public task ids, and the reason it lives here rather
# than in a per-campaign config.
#
# N-01 replaced `rule-dev-0004` with a digest, which stopped the id
# *naming* its seed. N-34 measured that the leak survived anyway: the
# digest is unsalted over a 0..9999 seed space, so enumerating the space
# reproduces any id - for `make_task("dev", 4)` at seed 4, in a thousand
# hashes. A keyed digest closes it, because recovering the id now needs
# the key.
#
# The key is frozen world state rather than a per-campaign secret.
# `offline_recompute` re-derives ids from `(split, seed)` in a *different
# process* to verify frozen evidence - `_task_id_for` and the frozen-task
# check both compare `make_task(...)[task_id]` against the bundle. A
# per-run key would make that verification impossible. A frozen key is
# stable across processes, which the recompute needs, and absent from the
# policy view, which is the whole point.
#
# It is a study constant, not a secret in any operational sense: it is in
# the repository. What it buys is that the id stops being a function of
# published values alone, so a policy holding the view cannot invert it
# without also holding the source. That is a real reduction in what a
# policy can do from the view alone, and it is not a defence against an
# adversary who reads this file.
TASK_ID_KEY = b"ad01-task-id-hmac-v1"


def _world_tasks(world: int) -> list:
    tasks = []
    for family in ("software", "graph"):
        for index in range(DEV_PER_DOMAIN):
            tasks.append(splits.generate_ad01(family, world, "dev", index))
        for index in range(USE_WITHIN_PER_DOMAIN):
            tasks.append(splits.generate_ad01(family, world, "within", index))
        for index in range(USE_TRANSFER_PER_DOMAIN):
            tasks.append(splits.generate_ad01(family, world, "transfer",
                                              index))
    return tasks


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build_freeze(root) -> dict:
    from .benefit import digest as benefit_digest
    root = Path(root)
    manifest: dict = {"freeze_id": FREEZE_ID, "version": VERSION,
                      "benefit_rule_digest": benefit_digest(),
                      "files": [], "worlds": {}}
    for world in WORLDS:
        by_kind: dict = {}
        for task in _world_tasks(world):
            kind = task["task_id"].split("-")[2]
            target = root / ("world-%d" % world) / kind / \
                ("%s.json" % task["task_id"])
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = (json.dumps(task, sort_keys=True, indent=2) + "\n").encode()
            target.write_bytes(raw)
            manifest["files"].append(
                {"path": target.relative_to(root).as_posix(),
                 "task_id": task["task_id"], "digest": _digest(raw),
                 "bytes": len(raw)})
            by_kind.setdefault(kind, {}).setdefault(task["family"],
                                                    []).append(task["task_id"])
        manifest["worlds"][str(world)] = by_kind
    manifest["files"].sort(key=lambda entry: entry["path"])
    manifest_raw = (json.dumps(manifest, sort_keys=True, indent=2)
                    + "\n").encode()
    (root / "manifest.json").write_bytes(manifest_raw)
    (root / "manifest.sha256").write_text(_digest(manifest_raw) + "\n")
    return manifest


def verify_freeze(root) -> list:
    root = Path(root)
    try:
        manifest_raw = (root / "manifest.json").read_bytes()
        pinned = (root / "manifest.sha256").read_text().strip()
    except OSError:
        return ["manifest-missing"]
    problems = []
    if _digest(manifest_raw) != pinned:
        return ["manifest-hash-mismatch"]
    manifest = json.loads(manifest_raw)
    if manifest.get("freeze_id") != FREEZE_ID:
        problems.append("wrong-freeze-id")
    seen = set()
    for entry in manifest.get("files", []):
        path = entry.get("path", "")
        if path in seen:
            problems.append("duplicate-file %s" % path)
        seen.add(path)
        target = root / path
        if not target.is_file():
            problems.append("missing-file %s" % path)
            continue
        if _digest(target.read_bytes()) != entry.get("digest"):
            problems.append("digest-mismatch %s" % path)
    return problems


def verify_committed() -> list:
    return verify_freeze(FROZEN_DIR)


def load_task(root, task_id: str) -> dict:
    for path in Path(root).rglob("%s.json" % task_id):
        return json.loads(path.read_text())
    raise KeyError(task_id)


def _parse_task_id(task_id: str) -> tuple:
    parts = task_id.split("-")
    family = {"sw": "software", "gr": "graph"}[parts[3]]
    return family, int(parts[1][1:]), parts[2], int(parts[4])


_canonical = splits.ad01_content_key


_SW_TRANSFER_TEMPLATES = frozenset({"stale-read-3chain",
                                    "stale-clear-del-core"})
_GR_TRANSFER_TEMPLATES = frozenset(splits.AD01_GRAPH_TRANSFER_SPECS)
_GR_DEV_TEMPLATES = frozenset(splits.AD01_GRAPH_DEV_SPECS)


def audit_tasks(tasks: list) -> list:
    problems = []
    by_world: dict = {}
    for task in tasks:
        try:
            family, world, kind, index = _parse_task_id(task["task_id"])
        except (KeyError, IndexError, ValueError):
            problems.append("bad-task-id %s" % task.get("task_id"))
            continue
        if task.get("family") != family:
            problems.append("family-mismatch %s" % task["task_id"])
        expected_seed = splits._ad01_seed(family, world, kind, index)
        if task.get("seed") != expected_seed:
            problems.append("seed-mismatch %s" % task["task_id"])
        if task != splits.generate_ad01(family, world, kind, index):
            problems.append("regeneration-mismatch %s" % task["task_id"])
        by_world.setdefault(world, []).append((kind, task))
    for world, members in by_world.items():
        dev = [t for k, t in members if k == "dev"]
        use = [t for k, t in members if k in ("within", "transfer")]
        within = [t for k, t in members if k == "within"]
        transfer = [t for k, t in members if k == "transfer"]
        if len(dev) != 6 or len(within) != 6 or len(transfer) != 6:
            problems.append("world-%d-counts dev=%d within=%d transfer=%d"
                            % (world, len(dev), len(within),
                               len(transfer)))
        dev_content = {_canonical(t) for t in dev}
        for task in use:
            if _canonical(task) in dev_content:
                problems.append("dev-use-leakage %s" % task["task_id"])
        for task in transfer + dev + within:
            template = task.get("template")
            if task["family"] == "software":
                is_transfer = template in _SW_TRANSFER_TEMPLATES
            else:
                if template in _GR_TRANSFER_TEMPLATES:
                    is_transfer = True
                elif template in _GR_DEV_TEMPLATES:
                    is_transfer = False
                else:
                    problems.append("unknown-template %s" % task["task_id"])
                    continue
            kind = ("transfer" if task["task_id"].split("-")[2] == "transfer"
                    else "dev")
            if (kind == "transfer") != is_transfer:
                problems.append("transfer-separation %s" % task["task_id"])
    return problems


def audit_committed() -> list:
    tasks = []
    for path in sorted(FROZEN_DIR.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        tasks.append(json.loads(path.read_text()))
    return audit_tasks(tasks)


def world_membership(root) -> dict:
    return json.loads((Path(root) / "manifest.json").read_text())["worlds"]


def main(argv: list) -> int:
    if len(argv) == 3 and argv[1] == "build":
        build_freeze(argv[2])
        return 0
    if len(argv) == 2 and argv[1] == "verify":
        problems = verify_freeze(FROZEN_DIR)
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    print("usage: worlds.py build <dir> | verify", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
