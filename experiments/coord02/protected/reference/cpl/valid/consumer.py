from decimal import Decimal, ROUND_HALF_UP


def from_base(x, want, units):
    q = Decimal(str(x / units[want])).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(q)


def flag(v, lo, hi):
    return "low" if v < lo else "high" if v > hi else "ok"
