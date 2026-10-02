def describe(values):
    return round(sum(values, 0) / len(values), 2) if values else 0
