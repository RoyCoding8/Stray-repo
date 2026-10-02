def to_want(pairs, units, want):
    return [round(v * units[u] / units[want], 2) for v, u in pairs]
