def total(packets, conv, discount=0):
    return round(sum(p["qty"] for p in packets) * conv["scale"], 2)
