"""Software family: tiny deterministic key/value state machine.

Tasks are DATA (plain JSON dicts), never host-executed programs. A task
holds an op sequence of at most 24 ops, a named fault and a designated
witness: one stable get-observation whose typed reference-vs-faulty
disagreement must be preserved by any valid reduction.
"""

from __future__ import annotations

MAX_OPS = 24
KEYS = ("a", "b", "c")
FAULTS = ("stale-read", "stale-clear")

MISSING = "missing"
PRESENT = "str"


class SoftwareInvalid(Exception):
    pass


def _fail(reason: str) -> SoftwareInvalid:
    return SoftwareInvalid(reason)


def parse_ops(raw) -> list:
    if not isinstance(raw, list):
        raise _fail("ops-not-a-list")
    if len(raw) > MAX_OPS:
        raise _fail("too-many-ops")
    seen_ids: set = set()
    ops: list = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise _fail("op-not-a-dict")
        kind = entry.get("op")
        if kind == "set":
            key, value = entry.get("key"), entry.get("value")
            if key not in KEYS:
                raise _fail("bad-set-key")
            if not isinstance(value, str) or not value:
                raise _fail("bad-set-value")
            if set(entry) - {"op", "key", "value"}:
                raise _fail("extra-set-field")
            ops.append({"op": "set", "key": key, "value": value})
        elif kind == "get":
            key, oid = entry.get("key"), entry.get("id")
            if key not in KEYS:
                raise _fail("bad-get-key")
            if not isinstance(oid, str) or not oid:
                raise _fail("bad-get-id")
            if oid in seen_ids:
                raise _fail("duplicate-get-id")
            seen_ids.add(oid)
            if set(entry) - {"op", "key", "id"}:
                raise _fail("extra-get-field")
            ops.append({"op": "get", "key": key, "id": oid})
        elif kind == "clear":
            if set(entry) - {"op"}:
                raise _fail("extra-clear-field")
            ops.append({"op": "clear"})
        elif kind == "del":
            key = entry.get("key")
            if key not in KEYS:
                raise _fail("bad-del-key")
            if set(entry) - {"op", "key"}:
                raise _fail("extra-del-field")
            ops.append({"op": "del", "key": key})
        else:
            raise _fail("unknown-op")
    return ops


def reference_run(ops: list) -> dict:
    state: dict = {}
    observations: dict = {}
    for entry in ops:
        kind = entry["op"]
        if kind == "set":
            state[entry["key"]] = entry["value"]
        elif kind == "get":
            key = entry["key"]
            if key in state:
                observations[entry["id"]] = {"type": PRESENT, "value": state[key]}
            else:
                observations[entry["id"]] = {"type": MISSING, "value": None}
        elif kind == "clear":
            state = {}
        elif kind == "del":
            state.pop(entry["key"], None)
    return observations


def faulty_run(ops: list, fault: str) -> dict:
    if fault not in FAULTS:
        raise _fail("unknown-fault")
    state: dict = {}
    observations: dict = {}
    if fault == "stale-read":
        pending: dict = {}
        for entry in ops:
            kind = entry["op"]
            if kind == "set":
                key, value = entry["key"], entry["value"]
                if key in state and state[key] != value:
                    pending[key] = state[key]
                state[key] = value
            elif kind == "get":
                key = entry["key"]
                if key in pending:
                    observations[entry["id"]] = {"type": PRESENT, "value": pending.pop(key)}
                elif key in state:
                    observations[entry["id"]] = {"type": PRESENT, "value": state[key]}
                else:
                    observations[entry["id"]] = {"type": MISSING, "value": None}
            elif kind == "clear":
                state = {}
                pending = {}
            elif kind == "del":
                state.pop(entry["key"], None)
                pending.pop(entry["key"], None)
        return observations
    last_written: str | None = None
    for entry in ops:
        kind = entry["op"]
        if kind == "set":
            state[entry["key"]] = entry["value"]
            last_written = entry["key"]
        elif kind == "get":
            key = entry["key"]
            if key in state:
                observations[entry["id"]] = {"type": PRESENT, "value": state[key]}
            else:
                observations[entry["id"]] = {"type": MISSING, "value": None}
        elif kind == "clear":
            if last_written is not None and last_written in state:
                state = {last_written: state[last_written]}
            else:
                state = {}
        elif kind == "del":
            state.pop(entry["key"], None)
    return observations


def parse_task(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise _fail("task-not-a-dict")
    if raw.get("family") != "software":
        raise _fail("wrong-family")
    fault = raw.get("fault")
    if fault not in FAULTS:
        raise _fail("unknown-fault")
    ops = parse_ops(raw.get("ops"))
    witness = raw.get("witness")
    if not isinstance(witness, dict):
        raise _fail("witness-not-a-dict")
    obs = witness.get("observation")
    if not isinstance(obs, str) or not obs:
        raise _fail("witness-observation-missing")
    if set(witness) - {"observation", "ref", "faulty"}:
        raise _fail("witness-extra-field")
    for side in ("ref", "faulty"):
        typed = witness.get(side)
        if not isinstance(typed, dict) or set(typed) != {"type", "value"}:
            raise _fail("witness-side-malformed")
        if typed["type"] not in (PRESENT, MISSING):
            raise _fail("witness-side-type")
        if typed["type"] == PRESENT and not isinstance(typed["value"], str):
            raise _fail("witness-side-value")
        if typed["type"] == MISSING and typed["value"] is not None:
            raise _fail("witness-side-value")
    task_id = raw.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise _fail("task-id-missing")
    return {"family": "software", "task_id": task_id, "fault": fault,
            "ops": ops, "witness": witness, "seed": raw.get("seed")}


def actual_witness(ops: list, fault: str, observation: str) -> dict:
    ref = reference_run(ops).get(observation)
    bad = faulty_run(ops, fault).get(observation)
    if ref is None or bad is None:
        raise _fail("observation-missing")
    return {"observation": observation, "ref": ref, "faulty": bad}


def witness_holds(task: dict, ops: list) -> bool:
    witness = task["witness"]
    try:
        actual = actual_witness(ops, task["fault"], witness["observation"])
    except SoftwareInvalid:
        return False
    return (actual["ref"] != actual["faulty"]
            and actual["ref"] == witness["ref"]
            and actual["faulty"] == witness["faulty"])


def task_is_valid(task: dict) -> bool:
    try:
        parsed = parse_task(task)
    except SoftwareInvalid:
        return False
    try:
        actual = actual_witness(parsed["ops"], parsed["fault"],
                                parsed["witness"]["observation"])
    except SoftwareInvalid:
        return False
    return (actual["ref"] != actual["faulty"]
            and actual["ref"] == parsed["witness"]["ref"]
            and actual["faulty"] == parsed["witness"]["faulty"])


def is_legal_deletion(task_ops: list, candidate_ops: list) -> bool:
    try:
        want = parse_ops(candidate_ops)
    except SoftwareInvalid:
        return False
    cursor = 0
    for entry in want:
        found = False
        while cursor < len(task_ops):
            current = task_ops[cursor]
            cursor += 1
            if current == entry:
                found = True
                break
        if not found:
            return False
    return True


def measure(ops: list) -> int:
    return len(ops)


def task_digest(task: dict) -> str:
    from settlement.common import payload_digest
    return payload_digest({"task_id": task["task_id"], "family": "software",
                           "fault": task["fault"], "ops": task["ops"],
                           "witness": task["witness"]})
