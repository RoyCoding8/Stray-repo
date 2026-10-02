def summarize(op, numbers):
    if op == "sum":
        return sum(numbers, 0)
    if op == "span":
        return (max(numbers) - min(numbers)) if numbers else 0
    if op == "rmean":
        return round(sum(numbers, 0) / len(numbers), 2) if numbers else 0
    if op == "count_pos":
        return sum(1 for n in numbers if n > 0)
    raise ValueError(op)
