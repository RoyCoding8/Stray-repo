def evaluate(payload, spec):
    return {"text": "%s%s%s" % (payload["b"], spec["sep"], payload["a"])}
