def evaluate(payload, spec):
    return {"value": payload["m"][payload["key"]]
            if payload["m"].get(payload["key"]) else spec["default"]}
