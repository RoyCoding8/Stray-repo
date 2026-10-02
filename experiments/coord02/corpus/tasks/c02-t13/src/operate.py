import math


def _operands(rule, spec, payload, mode):
    kind = rule["kind"]
    if kind == "key":
        return list(payload[spec["list_keys"][mode]])
    if kind in ("threshold", "prefix"):
        if "list_keys" in spec:
            return list(payload[spec["list_keys"][mode]])
        return list(payload["vals"])
    items = payload["items"]
    return list(items) if mode == "a" else list(items.values())


def compute(rule, spec, payload, mode):
    values = _operands(rule, spec, payload, mode)
    op = spec["ops"][mode]
    if op == "sum":
        return sum(values, 0)
    if op == "prod":
        return math.prod(values)
    if op == "min":
        return min(values) if values else 0
    if op == "max":
        return max(values) if values else 0
    raise ValueError("unknown op")
