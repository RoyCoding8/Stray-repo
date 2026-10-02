def evaluate(payload, spec):
    k = payload["k"]
    nums = payload["nums"]
    if k <= 0:
        return {"total": 0}
    return {"total": sum(nums[:k], 0)}
