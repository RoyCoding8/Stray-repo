def check(spec, payload):
    op = spec["op"]
    if op == "window_sum":
        nums, k = payload["nums"], payload["k"]
        if not isinstance(nums, list) or not isinstance(k, int):
            raise ValueError("bad window payload")
        if k < 0 or k > len(nums):
            raise ValueError("window out of range")
    elif op == "gt_count":
        if not isinstance(payload["nums"], list):
            raise ValueError("bad count payload")
    elif op == "get_default":
        if not isinstance(payload["m"], dict) or "key" not in payload:
            raise ValueError("bad lookup payload")
    elif op == "format_pair":
        if "a" not in payload or "b" not in payload:
            raise ValueError("bad pair payload")
    else:
        raise ValueError(op)
