def summarize(op, numbers):
    kept = [n for n in numbers if n >= 0]
    if op == "sum":
        return sum(kept, 0)
    if op == "span":
        return (max(kept) - min(kept)) if kept else 0
    if op == "rmean":
        return round(sum(kept, 0) / len(kept), 2) if kept else 0
    if op == "count_pos":
        return sum(1 for n in kept if n > 0)
    raise ValueError(op)
