from helper import last_k


def evaluate(payload, spec):
    if payload["k"] <= 0:
        return {"total": 0}
    return {"total": sum(last_k(payload["nums"], payload["k"]), 0)}
