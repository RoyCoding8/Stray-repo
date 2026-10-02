def total(packets, conv, discount=0):
    key = conv["in_key"]
    return round(sum(p[key] for p in packets)
                 / conv["scale"] * (1 - discount), 2)
