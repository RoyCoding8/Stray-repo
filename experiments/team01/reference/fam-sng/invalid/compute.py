def compute(spec, payload):
    op = spec["op"]
    if op == "window_sum":
        return {"total": sum(payload["nums"][:payload["k"]], 0)}
    if op == "gt_count":
        return {"count": sum(1 for n in payload["nums"]
                             if n >= payload["threshold"])}
    if op == "get_default":
        return {"value": payload["m"].get(payload["key"])}
    if op == "format_pair":
        return {"text": "%s%s%s" % (payload["b"], spec["sep"], payload["a"])}
    raise ValueError(op)
