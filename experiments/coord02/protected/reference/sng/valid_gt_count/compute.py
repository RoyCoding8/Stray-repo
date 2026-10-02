def evaluate(payload, spec):
    return {"count": sum(1 for n in payload["nums"]
                         if n > payload["threshold"])}
