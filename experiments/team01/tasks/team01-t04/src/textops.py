def transform(op, texts):
    if op == "strip_lower":
        return [t.upper() for t in texts]
    if op == "dedup_sort":
        return [t[::-1] for t in texts]
    if op == "reverse":
        return [t.strip().lower() for t in texts]
    if op == "upper":
        return sorted(set(texts))
    raise ValueError(op)
