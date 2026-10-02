def packet(row, conv):
    return {conv["in_key"]: row["n"] * conv["scale"]}
