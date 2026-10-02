def compute(spec, payload):
    op = spec["op"]
    if op == "window_sum":
        k = payload["k"]
        nums = payload["nums"]
        return {"total": sum(nums[len(nums) - k:], 0) if k > 0 else 0}
    if op == "gt_count":
        return {"count": sum(1 for n in payload["nums"]
                             if n > payload["threshold"])}
    if op == "get_default":
        return {"value": payload["m"].get(payload["key"], spec["default"])}
    if op == "format_pair":
        return {"text": "%s%s%s" % (payload["a"], spec["sep"], payload["b"])}
    raise ValueError(op)
