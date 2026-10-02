def label(values, lo, hi):
    return ["low" if v < lo else "ok" if v < hi else "high"
            for v in values]
