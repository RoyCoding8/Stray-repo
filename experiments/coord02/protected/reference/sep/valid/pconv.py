from decimal import Decimal, ROUND_HALF_UP


def convert(readings, units, want):
    out = []
    for r in readings:
        x = r["v"] * units[r["u"]] / units[want]
        q = Decimal(str(x)).quantize(Decimal("0.01"),
                                     rounding=ROUND_HALF_UP)
        out.append(float(q))
    return out
