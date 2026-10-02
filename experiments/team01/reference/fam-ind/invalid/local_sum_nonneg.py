import numops


def main():
    assert numops.summarize("sum", [1, 2, 3]) == 6
    assert numops.summarize("sum", [0, 4]) == 4
    print("local-nonneg-sum-green")


if __name__ == "__main__":
    main()
