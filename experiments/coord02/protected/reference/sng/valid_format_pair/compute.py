def evaluate(payload, spec):
    return {"text": "%s%s%s" % (payload["a"], spec["sep"], payload["b"])}
