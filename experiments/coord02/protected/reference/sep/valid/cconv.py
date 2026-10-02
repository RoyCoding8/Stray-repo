def label(values, lo, hi):
    return ["low" if v < lo else "high" if v > hi else "ok"
            for v in values]
