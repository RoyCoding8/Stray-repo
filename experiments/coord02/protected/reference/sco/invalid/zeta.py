def scale(cells, factor):
    return [round(c["v"] * factor, 2) for c in cells]
