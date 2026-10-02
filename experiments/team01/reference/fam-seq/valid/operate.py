def operands(rule, spec, payload, md):
    kind = rule["kind"]
    if kind == "key":
        return list(payload[spec["list_keys"][md]])
    if kind in ("threshold", "prefix"):
        return list(payload["vals"])
    items = payload["items"]
    return list(items) if md == "a" else list(items.values())


def apply(op, values):
    if op == "sum":
        return sum(values, 0)
    if op == "prod":
        return __import__("math").prod(values)
    if op == "min":
        return min(values) if values else 0
    if op == "max":
        return max(values) if values else 0
    raise ValueError(op)
