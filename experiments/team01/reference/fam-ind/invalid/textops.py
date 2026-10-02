def transform(op, texts):
    if op == "strip_lower":
        return [t.strip().lower() for t in texts]
    if op == "dedup_sort":
        return sorted(set(texts))
    if op == "reverse":
        return [t[::-1] for t in texts]
    if op == "upper":
        return [t.upper() for t in texts]
    raise ValueError(op)
