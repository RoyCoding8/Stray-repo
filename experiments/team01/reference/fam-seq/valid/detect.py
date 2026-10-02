def mode(rule, spec, payload):
    kind = rule["kind"]
    if kind == "key":
        return "b" if rule["key"] in payload else "a"
    if kind == "threshold":
        return "b" if payload["code"] >= rule["at"] else "a"
    if kind == "prefix":
        return "b" if payload["kind"].startswith(rule["prefix"]) else "a"
    if kind == "shape":
        return "b" if isinstance(payload["items"], dict) else "a"
    raise ValueError(kind)
