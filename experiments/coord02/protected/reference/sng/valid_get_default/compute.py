def evaluate(payload, spec):
    return {"value": payload["m"].get(payload["key"], spec["default"])}
