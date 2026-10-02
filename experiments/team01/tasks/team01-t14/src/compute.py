def compute(spec, payload):
    op = spec["op"]
    if op == "window_sum":
        return {"total": sum(payload["nums"], 0)}
    if op == "gt_count":
        return {"count": sum(1 for n in payload["nums"]
                             if n < payload["threshold"])}
    if op == "get_default":
        return {"value": spec["default"]}
    if op == "format_pair":
        return {"text": "%s" % payload["a"]}
    raise ValueError(op)
