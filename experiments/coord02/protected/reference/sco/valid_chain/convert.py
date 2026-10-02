from decimal import Decimal, ROUND_HALF_UP


def to_want(pairs, units, want):
    out = []
    for v, u in pairs:
        x = v * units[u] / units[want]
        q = Decimal(str(x)).quantize(Decimal("0.01"),
                                     rounding=ROUND_HALF_UP)
        out.append(float(q))
    return out
