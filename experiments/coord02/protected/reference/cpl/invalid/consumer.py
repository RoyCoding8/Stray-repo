def from_base(x, want, units):
    return round(x / units[want], 2)


def flag(v, lo, hi):
    return "low" if v < lo else "ok" if v < hi else "high"
