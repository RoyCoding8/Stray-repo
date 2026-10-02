def convert(readings, units, want):
    return [round(r["v"] * units[r["u"]] / units[want], 2)
            for r in readings]
