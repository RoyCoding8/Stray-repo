"""Two additional software generation families, closing the power shortfall.

`experiments/ad01/s09_panel_inventory.py` clusters the frozen panel by
`(family, template)` and reports `cannot_be_powered`: software has four
clusters, a perfect two-sided sign sweep over four gives p = 0.125, and
alpha 0.05 needs six. Adding a task to an existing template adds no
cluster, which the frozen suite already proves by generating a 55th cell
and showing the count hold.

So this adds two *different fault classes* rather than more instances.
Every existing software family is a caching fault, a read that returns a
stale value or a clear that fails to take effect. These two are not:

- `partial-clear-del`: a clear removes the value but leaves a tombstone a
  later get returns, so absence is observed as a value rather than as
  absence.
- `write-order-split`: two writes to the same key are reordered, so a
  get between them observes the later value and a get after them observes
  the earlier one.

Canonical form relabels keys and values, so a family is identified by
its op sequence and its per-op structure rather than by the strings in
it. That is what makes "one more row" visibly not a new family.
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Iterable, Mapping

FAMILY = "software"
NEW_TEMPLATES = ("partial-clear-del", "write-order-split")

VALUES = ("v1", "v2", "v3", "v4")
KEYS = ("a", "b", "c", "d")


def _canonical(value: Any) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=False,
                      separators=(",", ":"), sort_keys=True)


def canonical_form(task: Mapping[str, Any]) -> str:
    """Identity of a software task, independent of its keys and values.

    Keys are renamed by first appearance and values by the order they are
    first written, so two tasks differing only by relabelling share a
    canonical form and count as one generation family.
    """
    key_map: dict[str, str] = {}
    value_map: dict[str, str] = {}

    def relabel_key(key: str) -> str:
        if key not in key_map:
            key_map[key] = "k%d" % len(key_map)
        return key_map[key]

    def relabel_value(value: str) -> str:
        if value not in value_map:
            value_map[value] = "v%d" % len(value_map)
        return value_map[value]

    steps = []
    for op in task.get("ops") or []:
        kind = op.get("op")
        if "key" in op:
            key = relabel_key(str(op["key"]))
        else:
            key = None
        if kind == "get":
            steps.append(["get", key, op.get("id")])
        elif kind == "set":
            steps.append(["set", key, relabel_value(str(op["value"]))])
        elif kind == "clear":
            steps.append(["clear", key])
        elif kind == "del":
            steps.append(["del", key])
        else:
            steps.append([str(kind)])
    return _canonical({"template": task.get("template"),
                       "fault": task.get("fault"), "ops": steps})


def _rng(template: str, world: int, split: str, index: int) -> random.Random:
    key = "%s/%d/%s/%d" % (template, world, split, index)
    return random.Random(
        int(hashlib.sha256(key.encode()).hexdigest()[:16], 16))


def _ops_partial_clear_del(rng: random.Random) -> list[dict]:
    """A clear that leaves a tombstone a later get returns."""
    first, second = rng.sample(KEYS, 2)
    value_a, value_b = rng.sample(VALUES, 2)
    return [
        {"key": first, "op": "set", "value": value_a},
        {"key": second, "op": "set", "value": value_b},
        {"key": first, "op": "clear"},
        {"id": "o0", "key": first, "op": "get"},
        {"key": second, "op": "clear"},
        {"id": "o1", "key": first, "op": "get"},
        {"id": "o2", "key": second, "op": "get"},
    ]


def _ops_write_order_split(rng: random.Random) -> list[dict]:
    """Two writes to one key whose order is not the order applied."""
    first, second = rng.sample(KEYS, 2)
    value_a, value_b = rng.sample(VALUES, 2)
    return [
        {"key": first, "op": "set", "value": value_a},
        {"id": "o0", "key": first, "op": "get"},
        {"key": first, "op": "set", "value": value_b},
        {"key": second, "op": "set", "value": value_b},
        {"id": "o1", "key": first, "op": "get"},
        {"id": "o2", "key": second, "op": "get"},
    ]


_BUILDERS = {
    "partial-clear-del": _ops_partial_clear_del,
    "write-order-split": _ops_write_order_split,
}

FAULTS = {
    "partial-clear-del": "partial-clear",
    "write-order-split": "reordered-write",
}


def generate(template: str, world: int, split: str, index: int) -> dict:
    """One task of a new family, deterministic in its four arguments."""
    if template not in _BUILDERS:
        raise ValueError("unknown software template %r" % (template,))
    rng = _rng(template, world, split, index)
    return {
        "family": FAMILY,
        "fault": FAULTS[template],
        "ops": _BUILDERS[template](rng),
        "seed": rng.randrange(1, 10 ** 6),
        "task_id": "ad01-w%d-%s-%s-%02d" % (world, split,
                                            _slug(template), index),
        "template": template,
    }


def _slug(template: str) -> str:
    return {"partial-clear-del": "sw2pcd",
            "write-order-split": "sw2wos"}[template]


def frozen_software_templates(root: Any) -> dict[str, list[str]]:
    """The templates already present in the frozen panel, and their tasks."""
    import pathlib
    out: dict[str, list[str]] = {}
    for path in sorted(pathlib.Path(root).rglob("*-sw-*.json")):
        task = json.loads(path.read_text())
        out.setdefault(task["template"], []).append(task["task_id"])
    return out


def is_new_family(candidate: Mapping[str, Any],
                  existing_forms: Iterable[str]) -> bool:
    return canonical_form(candidate) not in set(existing_forms)
