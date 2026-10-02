import math

V1_KEYS = {"a": "xs", "b": "ys"}


def compute(rule, spec, payload, mode):
    values = list(payload[V1_KEYS[mode]])
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
