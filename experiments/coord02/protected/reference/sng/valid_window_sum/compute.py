def evaluate(payload, spec):
    k = payload["k"]
    nums = payload["nums"]
    if k <= 0:
        return {"total": 0}
    return {"total": sum(nums[max(0, len(nums) - k):], 0)}
