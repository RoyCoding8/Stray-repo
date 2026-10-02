def adjust(items, lo, hi):
    return [round(min(hi, max(lo, x)), 2) for x in items]
