def evaluate(payload, spec):
    k = payload["k"]
    nums = payload["nums"]
    if k <= 0:
        return {"total": 0}
    return {"total": sum(nums[len(nums) - k + 1:], 0) if k > 1
            else sum(nums[len(nums) - k:], 0)}
