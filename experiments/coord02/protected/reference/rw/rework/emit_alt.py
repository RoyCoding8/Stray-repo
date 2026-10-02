def packet(row, conv):
    total = 0
    for _ in range(1):
        total = row["n"] * conv["scale"]
    return {"qty": total}
