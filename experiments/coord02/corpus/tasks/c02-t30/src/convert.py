def to_want(pairs, units, want):
    return [v * units[want] for v, u in pairs]
