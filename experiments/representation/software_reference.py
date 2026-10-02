"""Independent reference for the software family.

Separately written transition-table interpreter: states are immutable
sorted tuples, each opcode is a table entry mapping (state, op) to a new
(state, observation). Shares no code with software.py; cross-checked
exhaustively against it in tests.
"""

from __future__ import annotations

KEYS = ("a", "b", "c")


def _lookup(state, key):
    for item in state:
        if item[0] == key:
            return item[1]
    return None


def _store(state, key, value):
    return tuple(sorted(
        [(k, v) for (k, v) in state if k != key] + [(key, value)]))


def _drop(state, key):
    return tuple([(k, v) for (k, v) in state if k != key])


def _observe(state, key):
    value = _lookup(state, key)
    if value is None:
        return {"type": "missing", "value": None}
    return {"type": "str", "value": value}


def _apply_reference(state, op):
    name = op["op"]
    table = {
        "set": lambda: (_store(state, op["key"], op["value"]), None),
        "get": lambda: (state, _observe(state, op["key"])),
        "clear": lambda: ((), None),
        "del": lambda: (_drop(state, op["key"]), None),
    }
    if name not in table:
        raise ValueError("unknown-op")
    return table[name]()


def _apply_stale_read(state, pending, op):
    name = op["op"]
    if name == "set":
        key, value = op["key"], op["value"]
        old = _lookup(state, key)
        if old is not None and old != value:
            pending = dict(pending)
            pending[key] = old
        return _store(state, key, value), pending, None
    if name == "get":
        key = op["key"]
        if key in pending:
            pending = dict(pending)
            value = pending.pop(key)
            return state, pending, {"type": "str", "value": value}
        return state, pending, _observe(state, key)
    if name == "clear":
        return (), {}, None
    if name == "del":
        pending = dict(pending)
        pending.pop(op["key"], None)
        return _drop(state, op["key"]), pending, None
    raise ValueError("unknown-op")


def _apply_stale_clear(state, remembered, op):
    name = op["op"]
    if name == "set":
        return _store(state, op["key"], op["value"]), op["key"], None
    if name == "get":
        return state, remembered, _observe(state, op["key"])
    if name == "clear":
        if remembered is not None:
            value = _lookup(state, remembered)
            if value is not None:
                return ((remembered, value),), remembered, None
        return (), remembered, None
    if name == "del":
        return _drop(state, op["key"]), remembered, None
    raise ValueError("unknown-op")


def run_reference(ops):
    state = ()
    out = {}
    for op in ops:
        state, seen = _apply_reference(state, op)
        if seen is not None:
            out[op["id"]] = seen
    return out


def run_faulty(ops, fault):
    if fault == "stale-read":
        state, pending, out = (), {}, {}
        for op in ops:
            state, pending, seen = _apply_stale_read(state, pending, op)
            if seen is not None:
                out[op["id"]] = seen
        return out
    if fault == "stale-clear":
        state, remembered, out = (), None, {}
        for op in ops:
            state, remembered, seen = _apply_stale_clear(state, remembered, op)
            if seen is not None:
                out[op["id"]] = seen
        return out
    raise ValueError("unknown-fault")
