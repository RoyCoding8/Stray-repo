def last_k(nums, k):
    if k <= 0:
        return []
    return nums[max(0, len(nums) - k):]
